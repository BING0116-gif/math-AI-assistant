"""Capability Readiness 矩阵。

依据 `plans/知微_能力就绪度矩阵PRD_v1.0_2026-09-07.md` 实现。

把散落在各处的能力状态检查聚合为统一的三态评估，供管理员面板消费，
用于根治「配置漂移导致能力静默失效」这一类故障。

设计约束（PRD 第 5、7、8 节）：
- 只读：不写库、不改配置、无副作用。
- 轻量：只做配置检查与轻量探测，绝不发起付费 LLM 调用，可高频刷新。
- 隔离：单项检查失败不影响整体响应，异常项降级为 warning 并附 check_error。
- 脱敏：密钥类信息只暴露尾号，绝不返回完整值。
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Literal

from pydantic import BaseModel, Field

from app.config.settings import settings

CapabilityStatus = Literal["ok", "warning", "blocker"]

# 单项检查超时（秒）。超时即降级为 warning，避免整个端点被拖慢。
_CHECK_TIMEOUT = 2.0

# 已知在 DeepSeek 端点上不可用 / 已下线的模型名。
# 依据 2026-09-01 实测：/v1/models 仅返回 deepseek-v4-* 系列。
_DEPRECATED_ON_DEEPSEEK = {"deepseek-chat", "deepseek-reasoner"}

# qwen 系列模型打 DeepSeek 端点必然 404；文本链路统一走 DeepSeek，故视为可疑。
_QWEN_PREFIX = "qwen"


class CapabilityResult(BaseModel):
    """单项能力的就绪度结果。"""

    id: str = Field(description="能力标识，稳定不变，供前端与测试引用")
    name: str = Field(description="能力中文名")
    status: CapabilityStatus = Field(description="ok / warning / blocker")
    reason: str = Field(default="", description="判定原因，人类可读")
    remediation: str = Field(default="", description="修复建议；ok 时可为空")
    details: dict[str, Any] = Field(default_factory=dict, description="辅助诊断信息（已脱敏）")


class ReadinessSummary(BaseModel):
    """矩阵汇总。"""

    total: int = 0
    ok: int = 0
    warning: int = 0
    blocker: int = 0
    overall: CapabilityStatus = "ok"


class ReadinessMatrix(BaseModel):
    """完整矩阵响应体。"""

    generated_at: str
    summary: ReadinessSummary
    capabilities: list[CapabilityResult]


def _key_tail(key: str | None, size: int = 4) -> str | None:
    """返回密钥尾号用于识别「当前带的是哪把 key」。

    只取尾号，绝不返回完整密钥（PRD 第 12 节：Secrets Rules）。
    """
    if not key:
        return None
    return key[-size:]


def _masked(key: str | None) -> dict[str, Any]:
    """构造脱敏后的密钥描述。"""
    return {"present": bool(key), "tail": _key_tail(key)}


# ══════════════════════════════════════════════════════════════
# 八项能力检查
# ══════════════════════════════════════════════════════════════


async def check_ai_analysis() -> CapabilityResult:
    """AI 题目分析：provider 与 DeepSeek key 配置。"""
    provider = (settings.CONTENT_AI_PROVIDER or "").strip() or "mock"
    deepseek_key = settings.DEEPSEEK_API_KEY
    details: dict[str, Any] = {
        "provider": provider,
        "model": settings.DEEPSEEK_MODEL,
        "deepseek_key": _masked(deepseek_key),
    }

    # 复用既有 provider 状态，避免重复实现判定逻辑。
    try:
        from app.services.content_ai_analysis import get_provider_status

        status = get_provider_status()
        details["available"] = bool(getattr(status, "available", None))
        details["reason"] = getattr(status, "reason", None)
    except Exception as exc:  # pragma: no cover - 诊断信息，失败不影响主判定
        details["provider_status_error"] = str(exc)

    allow_mock = bool(getattr(settings, "ALLOW_MOCK_PUBLISH", False))

    if provider == "mock":
        if allow_mock:
            return CapabilityResult(
                id="ai_analysis",
                name="AI 题目分析",
                status="warning",
                reason=f"当前 provider 为 mock，分析结果不可正式发布（已通过 ALLOW_MOCK_PUBLISH 显式允许）",
                remediation="联调完成后改回 CONTENT_AI_PROVIDER=deepseek，并移除 ALLOW_MOCK_PUBLISH 旁路",
                details=details,
            )
        return CapabilityResult(
            id="ai_analysis",
            name="AI 题目分析",
            status="blocker",
            reason=f"当前 provider 为 mock，且未显式允许发布，分析结果无法进入正式题库",
            remediation=(
                "在 .env 设置 CONTENT_AI_PROVIDER=deepseek，并确认 docker-compose.yml 的 "
                "web.environment 已透传该变量（compose 是白名单，.env 不会自动进容器）"
            ),
            details=details,
        )

    if not deepseek_key:
        return CapabilityResult(
            id="ai_analysis",
            name="AI 题目分析",
            status="blocker",
            reason=f"provider={provider} 但 DEEPSEEK_API_KEY 为空",
            remediation="在 .env 配置 DEEPSEEK_API_KEY，并在 docker-compose.yml web.environment 中透传",
            details=details,
        )

    model = (settings.DEEPSEEK_MODEL or "").strip()
    if model in _DEPRECATED_ON_DEEPSEEK:
        return CapabilityResult(
            id="ai_analysis",
            name="AI 题目分析",
            status="warning",
            reason=f"模型 {model} 在 DeepSeek 端点已下线，请求会 404",
            remediation="改用 deepseek-v4-flash（可用模型以 /v1/models 实测为准）",
            details=details,
        )

    return CapabilityResult(
        id="ai_analysis",
        name="AI 题目分析",
        status="ok",
        reason=f"{provider} / {model} 已配置",
        details=details,
    )


async def check_vision_ocr() -> CapabilityResult:
    """视觉识题：仅读 DASHSCOPE_API_KEY。

    注意：轻量探测无法验证 key 是否真实有效，只能检测缺失与格式异常。
    """
    key = settings.DASHSCOPE_API_KEY
    details: dict[str, Any] = {"dashscope_key": _masked(key)}

    if not key:
        return CapabilityResult(
            id="vision_ocr",
            name="视觉识题",
            status="blocker",
            reason="DASHSCOPE_API_KEY 为空，拍照上传链路完全不可用",
            remediation="配置有效的 DASHSCOPE_API_KEY；或改用 deepseek-v4-flash-vision-exp 并同步改链路代码",
            details=details,
        )

    if len(key) < 16:
        return CapabilityResult(
            id="vision_ocr",
            name="视觉识题",
            status="warning",
            reason=f"DASHSCOPE_API_KEY 长度异常（{len(key)}），疑似无效或占位值",
            remediation="核对 .env 中的 key 是否为完整值",
            details=details,
        )

    return CapabilityResult(
        id="vision_ocr",
        name="视觉识题",
        status="ok",
        reason=f"已配置（尾号 {_key_tail(key)}）；注意：无法验证有效性，需实际调用确认",
        details=details,
    )


async def check_assessment() -> CapabilityResult:
    """智能组卷：文本 LLM key 与章节数据。"""
    llm_key = settings.LLM_API_KEY
    fallback_key = settings.DASHSCOPE_API_KEY
    math_model = (settings.LLM_MATH_MODEL or "").strip()
    details: dict[str, Any] = {
        "llm_key": _masked(llm_key),
        "fallback_dashscope_key": _masked(fallback_key),
        "math_model": math_model,
    }

    if not llm_key and not fallback_key:
        return CapabilityResult(
            id="assessment",
            name="智能组卷",
            status="blocker",
            reason="LLM_API_KEY 为空，且回退的 DASHSCOPE_API_KEY 也为空",
            remediation="在 .env 配置 LLM_API_KEY，并在 docker-compose.yml web.environment 中透传",
            details=details,
        )

    if not llm_key:
        # 有回退但仍属配置漂移，属于应当告警的状态。
        details["fallback_active"] = True

    try:
        from sqlalchemy import func, select

        from app.data.database import get_db_session
        from app.data.models import Chapter

        async with get_db_session() as db:
            chapter_count = int(
                await db.scalar(select(func.count(Chapter.id))) or 0
            )
        details["chapter_count"] = chapter_count
        if chapter_count == 0:
            return CapabilityResult(
                id="assessment",
                name="智能组卷",
                status="warning",
                reason="章节数据为空，蓝图规划缺少可选范围",
                remediation="执行 scripts/seed_calculus_knowledge.py 或导入课程数据",
                details=details,
            )
    except Exception as exc:
        details["chapter_check_error"] = str(exc)

    if math_model.startswith(_QWEN_PREFIX):
        return CapabilityResult(
            id="assessment",
            name="智能组卷",
            status="warning",
            reason=f"LLM_MATH_MODEL={math_model} 为 qwen 系列，打 DeepSeek 端点会 404",
            remediation="改为 deepseek-v4-flash",
            details=details,
        )
    if math_model in _DEPRECATED_ON_DEEPSEEK:
        return CapabilityResult(
            id="assessment",
            name="智能组卷",
            status="warning",
            reason=f"LLM_MATH_MODEL={math_model} 在 DeepSeek 端点已下线",
            remediation="改为 deepseek-v4-flash",
            details=details,
        )
    if not llm_key:
        return CapabilityResult(
            id="assessment",
            name="智能组卷",
            status="warning",
            reason="LLM_API_KEY 为空，已回退到 DASHSCOPE_API_KEY",
            remediation="显式配置 LLM_API_KEY，避免依赖回退",
            details=details,
        )

    return CapabilityResult(
        id="assessment",
        name="智能组卷",
        status="ok",
        reason=f"已配置，LLM_MATH_MODEL={math_model}",
        details=details,
    )


async def _qdrant_state() -> dict[str, Any]:
    """获取 Qdrant 与 SQL 题目计数。

    返回 dict，异常由上层捕获。
    """
    from sqlalchemy import func, select

    from app.data.database import get_db_session
    from app.data.models import Question
    from app.services.vector_store import get_vector_store

    store = await get_vector_store()
    available = await store.check_availability()
    stats = await store.get_collection_stats()
    async with get_db_session() as db:
        expected = int(
            await db.scalar(
                select(func.count(Question.id)).where(Question.review_status == "published")
            )
            or 0
        )
    indexed = int(stats.get("total_documents", -1)) if stats.get("mode") == "qdrant" else -1
    return {
        "available": bool(available),
        "mode": stats.get("mode"),
        "indexed": indexed,
        "sql_published": expected,
    }


async def check_rag_recommend() -> CapabilityResult:
    """RAG 推荐：开关与 Qdrant 可达性。"""
    details: dict[str, Any] = {
        "rag_enabled": settings.RAG_ENABLED,
        "vector_search_enabled": settings.RAG_ENABLE_VECTOR_SEARCH,
    }

    if not settings.RAG_ENABLED:
        return CapabilityResult(
            id="rag_recommend",
            name="RAG 推荐",
            status="blocker",
            reason="RAG_ENABLED=false，推荐能力整体关闭",
            remediation="在 .env 设置 RAG_ENABLED=true",
            details=details,
        )

    try:
        state = await _qdrant_state()
        details.update(state)
    except Exception as exc:
        return CapabilityResult(
            id="rag_recommend",
            name="RAG 推荐",
            status="blocker",
            reason=f"Qdrant 不可达：{exc}",
            remediation="确认 qdrant 容器已启动且端口映射正确（注意 Windows NAT 排除端口段）",
            details=details,
        )

    if not state.get("available"):
        return CapabilityResult(
            id="rag_recommend",
            name="RAG 推荐",
            status="blocker",
            reason="Qdrant 不可用",
            remediation="启动 qdrant 容器并检查 QDRANT_PORT 配置",
            details=details,
        )

    if state.get("sql_published", 0) == 0:
        return CapabilityResult(
            id="rag_recommend",
            name="RAG 推荐",
            status="warning",
            reason="题库中无 published 题目，推荐无可用语料",
            remediation="完成题库审核与发布，或导入种子题",
            details=details,
        )

    return CapabilityResult(
        id="rag_recommend",
        name="RAG 推荐",
        status="ok",
        reason=f"Qdrant 可用，published 题 {state.get('sql_published')} 道",
        details=details,
    )


async def check_vector_search() -> CapabilityResult:
    """向量检索：Qdrant 索引数与 SQL 一致性。"""
    details: dict[str, Any] = {"collection": getattr(settings, "QUESTION_QDRANT_COLLECTION", None)}

    try:
        state = await _qdrant_state()
        details.update(state)
    except Exception as exc:
        return CapabilityResult(
            id="vector_search",
            name="向量检索",
            status="blocker",
            reason=f"Qdrant 不可达：{exc}",
            remediation="启动 qdrant 容器；容器内用 hostname qdrant:6333，宿主机用映射端口",
            details=details,
        )

    indexed = state.get("indexed", -1)
    expected = state.get("sql_published", 0)

    if not state.get("available") or indexed < 0:
        return CapabilityResult(
            id="vector_search",
            name="向量检索",
            status="blocker",
            reason="Qdrant 不可用或未处于 qdrant 模式",
            remediation="检查 qdrant 容器与 collection 配置",
            details=details,
        )

    if indexed == 0:
        return CapabilityResult(
            id="vector_search",
            name="向量检索",
            status="blocker",
            reason="向量库中无索引点，检索不可用",
            remediation="执行向量同步脚本（scripts/migration/migrate_questions_to_qdrant.py）",
            details=details,
        )

    if indexed != expected:
        return CapabilityResult(
            id="vector_search",
            name="向量检索",
            status="warning",
            reason=f"索引数 {indexed} 与 SQL published 题数 {expected} 不一致",
            remediation="执行 Qdrant 审计同步，核对 outbox 事件是否积压",
            details=details,
        )

    return CapabilityResult(
        id="vector_search",
        name="向量检索",
        status="ok",
        reason=f"索引 {indexed} 点，与 SQL 一致",
        details=details,
    )


async def check_memory() -> CapabilityResult:
    """记忆系统：embedding 服务可用性。"""
    details: dict[str, Any] = {
        "model": settings.MEMORY_EMBEDDING_MODEL,
        "vector_model": settings.VECTOR_EMBEDDING_MODEL,
    }

    try:
        from app.services.embedding_service import get_embedding_service

        health = get_embedding_service().health()
        if isinstance(health, dict):
            details.update(health)
        else:
            details["health"] = health
    except Exception as exc:
        return CapabilityResult(
            id="memory",
            name="记忆系统",
            status="blocker",
            reason=f"embedding 服务不可用：{exc}",
            remediation="检查本地 BGE 模型文件与 VECTOR_EMBEDDING_MODEL 配置",
            details=details,
        )

    health_dict = health if isinstance(health, dict) else {}
    if health_dict and not health_dict.get("available", True):
        return CapabilityResult(
            id="memory",
            name="记忆系统",
            status="blocker",
            reason=f"embedding 模型不可用：{health_dict.get('error') or health_dict}",
            remediation="确认 BAAI/bge-small-zh-v1.5 已下载且维度为 512",
            details=details,
        )

    dim = health_dict.get("dim") or health_dict.get("dimension")
    if dim and int(dim) != 512:
        return CapabilityResult(
            id="memory",
            name="记忆系统",
            status="warning",
            reason=f"embedding 维度为 {dim}，预期 512",
            remediation="核对 VECTOR_EMBEDDING_MODEL 与既有 collection 维度是否匹配",
            details=details,
        )

    return CapabilityResult(
        id="memory",
        name="记忆系统",
        status="ok",
        reason=f"embedding 可用（{settings.MEMORY_EMBEDDING_MODEL}）",
        details=details,
    )


async def check_migration() -> CapabilityResult:
    """数据库迁移：alembic 版本与 head 一致性。"""
    details: dict[str, Any] = {}

    try:
        from pathlib import Path

        from alembic.config import Config
        from alembic.script import ScriptDirectory
        from sqlalchemy import text as sa_text

        from app.data import database

        if database.engine is None:
            return CapabilityResult(
                id="migration",
                name="数据库迁移",
                status="blocker",
                reason="数据库未初始化",
                remediation="启动后端服务后再查看",
                details=details,
            )

        async with database.engine.connect() as conn:
            result = await conn.execute(sa_text("SELECT version_num FROM alembic_version"))
            rows = [r[0] for r in result.fetchall()]

        config = Config(str(Path(__file__).resolve().parents[1] / "data" / "alembic.ini"))
        script = ScriptDirectory.from_config(config)
        heads = list(script.get_heads())

        details["current"] = rows
        details["heads"] = heads

        if len(heads) > 1:
            return CapabilityResult(
                id="migration",
                name="数据库迁移",
                status="blocker",
                reason=f"存在多个 head：{heads}，迁移链分叉",
                remediation="执行 alembic merge heads 合并后再升级",
                details=details,
            )

        head = heads[0] if heads else None
        if not rows:
            return CapabilityResult(
                id="migration",
                name="数据库迁移",
                status="blocker",
                reason="未找到迁移版本，数据库尚未升级",
                remediation="执行 alembic upgrade head",
                details=details,
            )

        if head and rows[0] != head:
            return CapabilityResult(
                id="migration",
                name="数据库迁移",
                status="blocker",
                reason=f"当前版本 {rows[0]} 落后于 head {head}",
                remediation="执行 alembic upgrade head",
                details=details,
            )

        return CapabilityResult(
            id="migration",
            name="数据库迁移",
            status="ok",
            reason=f"位于 head {head}",
            details=details,
        )
    except Exception as exc:
        return CapabilityResult(
            id="migration",
            name="数据库迁移",
            status="blocker",
            reason=f"迁移状态检查失败：{exc}",
            remediation="检查数据库连接与 alembic 配置",
            details=details,
        )


async def check_outbox_cache() -> CapabilityResult:
    """outbox 与缓存：最终一致性积压与 Redis 连通。"""
    details: dict[str, Any] = {}

    try:
        from app.services.outbox import outbox_health

        health = await outbox_health()
        details["outbox"] = health
    except Exception as exc:
        details["outbox_error"] = str(exc)
        health = {}

    try:
        from app.services.cache import get_cache_manager

        cache = get_cache_manager()
        details["redis_connected"] = cache.redis is not None
    except Exception as exc:
        details["cache_error"] = str(exc)
        details["redis_connected"] = False

    pending = 0
    if isinstance(health, dict):
        pending = int(health.get("pending") or health.get("pending_count") or 0)
    details["pending"] = pending

    # 积压阈值：超过 100 条视为最终一致性已落后，需人工介入。
    if pending > 100:
        return CapabilityResult(
            id="outbox_cache",
            name="outbox 与缓存",
            status="blocker",
            reason=f"outbox 积压 {pending} 条事件，最终一致性严重落后",
            remediation="检查 outbox 消费者是否存活，必要时执行 dead event replay",
            details=details,
        )

    if not details.get("redis_connected"):
        return CapabilityResult(
            id="outbox_cache",
            name="outbox 与缓存",
            status="warning",
            reason="Redis 未连接，缓存降级（功能可用但性能下降）",
            remediation="走 docker compose 即用；宿主机直连需显式指定端口（Redis 未发布到宿主）",
            details=details,
        )

    if pending > 0:
        return CapabilityResult(
            id="outbox_cache",
            name="outbox 与缓存",
            status="warning",
            reason=f"outbox 有 {pending} 条待处理事件",
            remediation="观察是否收敛；持续增长则需排查消费者",
            details=details,
        )

    return CapabilityResult(
        id="outbox_cache",
        name="outbox 与缓存",
        status="ok",
        reason="Redis 已连接，outbox 无积压",
        details=details,
    )


# ══════════════════════════════════════════════════════════════
# 聚合
# ══════════════════════════════════════════════════════════════

# 注册表：新增能力只需在此追加一个检查函数。
_CHECKS: list[Callable[[], Awaitable[CapabilityResult]]] = [
    check_ai_analysis,
    check_vision_ocr,
    check_assessment,
    check_rag_recommend,
    check_vector_search,
    check_memory,
    check_migration,
    check_outbox_cache,
]


def _fallback(capability_id: str, exc: BaseException) -> CapabilityResult:
    """检查函数自身失败时的兜底结果。

    PRD FR-5：单项失败不得导致整个端点 500。
    """
    return CapabilityResult(
        id=capability_id,
        name=capability_id,
        status="warning",
        reason=f"该项检查未能完成：{exc}",
        remediation="这是诊断端点自身的问题，请查看服务端日志",
        details={"check_error": str(exc)},
    )


async def _run_one(check: Callable[[], Awaitable[CapabilityResult]]) -> CapabilityResult:
    """执行单项检查，带超时与异常隔离。"""
    try:
        return await asyncio.wait_for(check(), timeout=_CHECK_TIMEOUT)
    except asyncio.TimeoutError:
        return CapabilityResult(
            id=check.__name__.removeprefix("check_"),
            name=check.__name__.removeprefix("check_"),
            status="warning",
            reason=f"检查超时（>{_CHECK_TIMEOUT}s）",
            remediation="该项依赖的外部服务响应过慢，请检查容器状态",
            details={"check_error": "timeout"},
        )
    except Exception as exc:  # noqa: BLE001 - 诊断端点需吞掉一切异常
        return _fallback(check.__name__.removeprefix("check_"), exc)


def _summarize(capabilities: list[CapabilityResult]) -> ReadinessSummary:
    ok = sum(1 for c in capabilities if c.status == "ok")
    warning = sum(1 for c in capabilities if c.status == "warning")
    blocker = sum(1 for c in capabilities if c.status == "blocker")
    if blocker:
        overall: CapabilityStatus = "blocker"
    elif warning:
        overall = "warning"
    else:
        overall = "ok"
    return ReadinessSummary(
        total=len(capabilities),
        ok=ok,
        warning=warning,
        blocker=blocker,
        overall=overall,
    )


async def build_readiness_matrix() -> ReadinessMatrix:
    """构建完整的 Capability Readiness 矩阵。"""
    results = await asyncio.gather(*(_run_one(check) for check in _CHECKS))
    capabilities = list(results)
    return ReadinessMatrix(
        generated_at=datetime.now(timezone.utc).isoformat(),
        summary=_summarize(capabilities),
        capabilities=capabilities,
    )
