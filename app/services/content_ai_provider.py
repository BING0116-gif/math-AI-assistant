"""Content AI Provider abstraction (Step 1.1-E2-A0).

目标（§14 / §20 / §24 / §25）：
- 业务层通过 ContentAIProvider 接口调用 AI，绝不直接依赖具体 provider / SDK。
- MockContentAIProvider：不调用网络、不读取 API Key、输出稳定 deterministic 结构、
  可通过 mock_case 注入 PASS / DOUBTFUL / FAILED；用于 UI / workflow / API / DB 测试。
- DeepSeekContentAIProvider：真实 provider（OpenAI 兼容，调用 DeepSeek /v1/chat/completions）。
  仅在 CONTENT_AI_PROVIDER=deepseek 且已配置 DEEPSEEK_API_KEY 时调用真实接口、消耗 token。
- QwenContentAIProvider：仅定义接口骨架；当前调用即抛 AI_PROVIDER_NOT_IMPLEMENTED
  （稳定 unavailable），禁止偷偷调用真实 API。
- ContentAIProviderFactory：mock → 实现；deepseek → 真实；qwen / auto → stub。

安全规则：
- API Key 只在后端 settings 读取，永不离开后端、永不传入前端。
- mock 模式不发起任何网络请求；deepseek 模式仅在用户显式配置 Key 后发起真实请求。
- deepseek 分析结果标记 ai_provider='deepseek'，服务端允许正式发布（仅 mock 被禁止）。
"""

from __future__ import annotations

import hashlib
import json
import re
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Tuple

import httpx

from app.config.settings import settings
from app.models.content_ai import (
    ContentAIAnswerCheck,
    ContentAIAnalysisResult,
    ContentAIVerificationResult,
)

# 稳定错误码（§25）
AI_PROVIDER_NOT_IMPLEMENTED = "AI_PROVIDER_NOT_IMPLEMENTED"

MOCK_PROVIDER_NAME = "mock"
QWEN_PROVIDER_NAME = "qwen"
DEEPSEEK_PROVIDER_NAME = "deepseek"

MOCK_PROMPT_VERSION = "mock-v1"
QWEN_PROMPT_VERSION = "qwen-v1"
DEEPSEEK_PROMPT_VERSION = "deepseek-v1"

# 稳定错误码（§25，沿用上方 AI_PROVIDER_NOT_IMPLEMENTED）
AI_PROVIDER_REQUEST_FAILED = "AI_PROVIDER_REQUEST_FAILED"
AI_PROVIDER_PARSE_FAILED = "AI_PROVIDER_PARSE_FAILED"

# 与 content_import.SUPPORTED_TYPES 保持一致的自动判题支持题型集合。
# 为简化用户流程，AI provider 不再把不在此集合的题型强制回退为 choice：
# 真实 AI 可返回任意题型，仅 answer_spec / draft 阶段做兜底处理。
from app.services.content_import import SUPPORTED_TYPES as _SUPPORTED_TYPES


def _is_supported_type(qtype: Optional[str]) -> bool:
    return (qtype or "") in _SUPPORTED_TYPES


def _strict_bool(value: Any, default: bool = False) -> bool:
    """严格解析 AI 返回的布尔字段；非法/缺失一律失败关闭（False），杜绝 bool("false")==True 陷阱。"""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        s = value.strip().lower()
        if s in ("true", "1", "yes"):
            return True
        if s in ("false", "0", "no", ""):
            return False
        return default
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    return default


class ContentAIProviderError(Exception):
    """稳定 application error，携带稳定 code（如 AI_PROVIDER_NOT_IMPLEMENTED）。"""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class ContentAIProvider(ABC):
    """AI 内容分析 provider 统一接口（§14）。

    业务服务只依赖此接口，不直接依赖具体 provider / SDK。

    analyze / verify 均接收可序列化的 candidate snapshot 与 context（不传 ORM 对象），
    保证 provider 可在无 DB 依赖下被测试注入。
    """

    name: str = "abstract"

    @abstractmethod
    def is_available(self) -> bool:
        """当前 provider 是否可用（mock 永远 True；qwen 需 key 且未实现时为 False）。"""
        raise NotImplementedError

    @abstractmethod
    def analyze(
        self, snapshot: Dict[str, Any], context: Dict[str, Any]
    ) -> ContentAIAnalysisResult:
        """对 candidate 做一次结构化分析。禁止网络调用（mock）/ 真实调用（qwen stub）。"""
        raise NotImplementedError

    @abstractmethod
    def verify(
        self,
        analysis: ContentAIAnalysisResult,
        snapshot: Dict[str, Any],
        context: Dict[str, Any],
    ) -> ContentAIVerificationResult:
        """对分析结果做独立验证，输出 verdict（pass / doubtful / fail）。"""
        raise NotImplementedError

    def analyze_and_verify(
        self,
        snapshot: Dict[str, Any],
        context: Dict[str, Any],
    ) -> Tuple[ContentAIAnalysisResult, ContentAIVerificationResult]:
        """可选的优化入口：真实 provider 可一次 LLM 调用同时完成分析与验证。

        默认 fallback 到 analyze + verify 两次调用（保持 mock/qwen 兼容）。
        """
        analysis = self.analyze(snapshot, context)
        verifier = self.verify(analysis, snapshot, context)
        return analysis, verifier


def _hash_int(value: str) -> int:
    return int(hashlib.sha256(value.encode("utf-8")).hexdigest(), 16)


def _build_answer_spec(qtype: str, original_answer: str, options: Any) -> Optional[Dict[str, Any]]:
    """依据 candidate 的原答案 / 选项确定性构造 answer_spec（供后续 draft 校验一致）。"""
    ans = (original_answer or "").strip()
    if qtype == "choice":
        opt_ids = [str(o.get("id", "")).strip() for o in options if isinstance(o, dict)] if isinstance(options, list) else []
        correct = ans if ans in opt_ids else (opt_ids[0] if opt_ids else ans)
        return {"version": 1, "kind": "choice", "correct": correct}
    if qtype == "judge":
        truthy = ans in ("对", "正确", "true", "True", "T", "1", "√")
        return {"version": 1, "kind": "judge", "correct": truthy}
    if qtype == "numeric_fill":
        try:
            value = float(ans)
        except (ValueError, TypeError):
            value = 0.0
        return {"version": 1, "kind": "numeric_fill", "value": value}
    if qtype == "expression_fill":
        return {"version": 1, "kind": "expression_fill", "canonical": ans, "variables": []}
    # 未知题型（计算题 / 证明题 / 简答题等）：用通用文本兜底，保留原答案，
    # 不强制转成 choice，避免题型信息丢失。
    return {"version": 1, "kind": "text", "canonical": ans}


class MockContentAIProvider(ContentAIProvider):
    """Mock AI provider（§15 / §16 / §30）。

    - 不调用网络、不读取 API Key、不消耗 token。
    - 输出稳定 deterministic 结构（同一 candidate 永远得到同一结果）。
    - 可通过 forced_case 注入 pass / doubtful / fail（测试用 DI；生产 UI 不暴露）。
    - 默认 deterministic 混合分布（基于 candidate_id 哈希），便于演示真实分布。

    职责只是验证「整个 AI Content Pipeline」，不写复杂数学推理器。
    """

    name = MOCK_PROVIDER_NAME

    def __init__(self, forced_case: Optional[str] = None):
        # forced_case ∈ {'pass','doubtful','fail'} 仅用于测试注入
        self._forced_case = forced_case

    def is_available(self) -> bool:
        return True

    def _decide_case(self, candidate_id: str, context: Optional[Dict[str, Any]] = None) -> str:
        # 优先使用 context["mock_case"]（由 analyze_candidate 注入，用于测试 DI / 演示）；
        # 其次使用实例构造参数 self._forced_case；最后回退确定性哈希分布。
        injected = (context or {}).get("mock_case")
        if injected in ("pass", "doubtful", "fail"):
            return injected
        if self._forced_case in ("pass", "doubtful", "fail"):
            return self._forced_case
        # deterministic 混合分布：~70% pass / ~20% doubtful / ~10% fail
        r = _hash_int(candidate_id) % 10
        if r < 7:
            return "pass"
        if r < 9:
            return "doubtful"
        return "fail"

    def analyze(
        self, snapshot: Dict[str, Any], context: Dict[str, Any]
    ) -> ContentAIAnalysisResult:
        candidate_id = str(snapshot.get("candidate_id", ""))
        qtype = snapshot.get("detected_question_type") or "choice"
        # mock 保持旧行为： unsupported 题型回退为 choice（mock 只验证 pipeline）。
        if qtype not in _SUPPORTED_TYPES:
            qtype = "choice"
        original_answer = snapshot.get("original_answer") or ""
        options = snapshot.get("options") or []

        # 知识点：优先使用 context 提供的合法 code 列表确定性选取；否则回退候选建议 code
        known = list(context.get("known_knowledge_point_codes") or [])
        suggested = list(snapshot.get("suggested_knowledge_point_codes") or [])
        kp_codes: list[str] = []
        if known:
            kp_codes = [known[_hash_int(candidate_id) % len(known)]]
        elif suggested:
            kp_codes = suggested[:1]

        difficulty = (_hash_int(candidate_id + ":diff") % 3) + 1  # 1..3
        confidence = round(0.9 + (_hash_int(candidate_id + ":conf") % 10) / 100.0, 2)  # 0.90..0.99

        analysis_text = (
            f"[MOCK] 示例解析：本题为{qtype}，依据原答案「{original_answer}」生成结构化结果。"
            "（Mock AI 不保证数学正确性，仅用于验证 Content Pipeline。）"
        )

        answer_spec = _build_answer_spec(qtype, original_answer, options)

        return ContentAIAnalysisResult(
            question_type=qtype,
            knowledge_point_codes=kp_codes,
            difficulty=difficulty,
            analysis=analysis_text,
            answer_spec=answer_spec,
            common_mistakes=[],
            answer_check=ContentAIAnswerCheck(
                official_answer=original_answer,
                consistent=True,
                reason="[MOCK] deterministic answer check",
            ),
            confidence=confidence,
            flags=[],
        )

    def verify(
        self,
        analysis: ContentAIAnalysisResult,
        snapshot: Dict[str, Any],
        context: Dict[str, Any],
    ) -> ContentAIVerificationResult:
        candidate_id = str(snapshot.get("candidate_id", ""))
        case = self._decide_case(candidate_id, context)
        # verdict ∈ pass / doubtful / fail（§28）
        verdict = case if case in ("pass", "doubtful", "fail") else "pass"
        if verdict == "pass":
            return ContentAIVerificationResult(
                verdict="pass",
                answer_consistent=True,
                analysis_correct=True,
                kp_valid=bool(analysis.knowledge_point_codes),
                answer_spec_valid=True,
                issues=[],
                confidence=analysis.confidence,
            )
        if verdict == "doubtful":
            return ContentAIVerificationResult(
                verdict="doubtful",
                answer_consistent=True,
                analysis_correct=True,
                kp_valid=bool(analysis.knowledge_point_codes),
                answer_spec_valid=True,
                issues=["[MOCK] 确定性存疑：建议人工复核"],
                confidence=analysis.confidence,
            )
        # fail
        return ContentAIVerificationResult(
            verdict="fail",
            answer_consistent=False,
            analysis_correct=False,
            kp_valid=bool(analysis.knowledge_point_codes),
            answer_spec_valid=True,
            issues=["[MOCK] 确定性失败：分析未通过验证"],
            confidence=analysis.confidence,
        )


class QwenContentAIProvider(ContentAIProvider):
    """真实 Qwen provider 骨架（§25）。

    当前为 stub：调用即抛 AI_PROVIDER_NOT_IMPLEMENTED（稳定 unavailable）。
    禁止偷偷调用真实 API / 读取 Key 发起网络请求。

    未来实现：读取 settings.QWEN_API_KEY / QWEN_MODEL / QWEN_BASE_URL，
    通过兼容 OpenAI 的接口发起请求，并复用现有结构化 schema 返回。
    届时只需在此实现 analyze / verify，UI / API / DB / workflow 无需改动。
    """

    name = QWEN_PROVIDER_NAME

    def __init__(self, api_key: str = "", model: str = "", base_url: str = ""):
        self._api_key = api_key
        self._model = model or settings.QWEN_MODEL
        self._base_url = base_url or settings.QWEN_BASE_URL

    def is_available(self) -> bool:
        # stub 阶段尚未实现真实分析，不可用（即使有 key）。
        return False

    def analyze(
        self, snapshot: Dict[str, Any], context: Dict[str, Any]
    ) -> ContentAIAnalysisResult:
        raise ContentAIProviderError(
            AI_PROVIDER_NOT_IMPLEMENTED,
            "Qwen Content AI provider 尚未实现（当前为 stub）。请勿在生产调用。",
        )

    def verify(
        self,
        analysis: ContentAIAnalysisResult,
        snapshot: Dict[str, Any],
        context: Dict[str, Any],
    ) -> ContentAIVerificationResult:
        raise ContentAIProviderError(
            AI_PROVIDER_NOT_IMPLEMENTED,
            "Qwen Content AI provider 尚未实现（当前为 stub）。请勿在生产调用。",
        )


class DeepSeekContentAIProvider(ContentAIProvider):
    """真实 DeepSeek provider（OpenAI 兼容，调用 /v1/chat/completions）。

    - 仅在 CONTENT_AI_PROVIDER=deepseek 且 DEEPSEEK_API_KEY 已配置时调用真实接口、消耗 token。
    - analyze / verify 均为同步实现（provider 接口约定为同步），内部用 httpx 同步客户端。
    - answer_spec 不依赖模型输出，统一由 _build_answer_spec 从官方答案确定性构造，降低脆弱性。
    - 模型返回非 JSON 时抛 AI_PROVIDER_PARSE_FAILED；网络失败时抛 AI_PROVIDER_REQUEST_FAILED。
    """

    name = DEEPSEEK_PROVIDER_NAME

    _SYSTEM_PROMPT = (
        "你是一名大学数学题库结构化分析助手。你必须且只能输出一个 JSON 对象，"
        "不要输出任何解释性文字、不要用 Markdown 代码块包裹。"
    )

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None, base_url: Optional[str] = None):
        # 显式传空字符串表示「无 key」，不再回退到 settings（便于测试和程序化构造）。
        self._api_key = settings.DEEPSEEK_API_KEY if api_key is None else api_key
        self.model = settings.DEEPSEEK_MODEL if model is None else model
        self._base_url = (settings.DEEPSEEK_BASE_URL if base_url is None else base_url).rstrip("/")
        self._timeout = float(getattr(settings, "DEEPSEEK_TIMEOUT_SECONDS", 60) or 60)

    def is_available(self) -> bool:
        return bool(self._api_key and self._api_key.strip())

    # ── 内部：同步调用 DeepSeek chat/completions ──
    def _chat(self, user_prompt: str, temperature: float) -> str:
        if not self.is_available():
            raise ContentAIProviderError(
                AI_PROVIDER_NOT_IMPLEMENTED,
                "DeepSeek API Key 未配置（请在 .env 设置 DEEPSEEK_API_KEY）。",
            )
        url = f"{self._base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self._SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "response_format": {"type": "json_object"},
        }
        try:
            with httpx.Client(timeout=self._timeout) as client:
                resp = client.post(url, headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPStatusError as e:
            body = ""
            try:
                body = e.response.text[:300]
            except Exception:  # noqa: BLE001
                pass
            raise ContentAIProviderError(
                AI_PROVIDER_REQUEST_FAILED,
                f"DeepSeek 返回 HTTP {e.response.status_code}: {body}",
            )
        except httpx.HTTPError as e:
            raise ContentAIProviderError(
                AI_PROVIDER_REQUEST_FAILED, f"调用 DeepSeek 失败: {e}"
            )
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            raise ContentAIProviderError(
                AI_PROVIDER_PARSE_FAILED, f"DeepSeek 返回结构异常: {e}"
            )

    @staticmethod
    def _parse_json(text: str) -> Dict[str, Any]:
        text = (text or "").strip()
        fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
        if fence:
            text = fence.group(1).strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1 and end > start:
                try:
                    return json.loads(text[start : end + 1])
                except json.JSONDecodeError:
                    pass
        raise ContentAIProviderError(
            AI_PROVIDER_PARSE_FAILED, "DeepSeek 返回无法解析为 JSON"
        )

    # ── 提示词构造 ──
    @staticmethod
    def _fmt_options(options: Any) -> str:
        if not isinstance(options, list) or not options:
            return "（无选项）"
        parts = []
        for o in options:
            if isinstance(o, dict):
                parts.append(f"{o.get('id', '')}: {o.get('text', o.get('content', ''))}")
            else:
                parts.append(str(o))
        return "\n".join(parts)

    def _build_analysis_prompt(self, snapshot: Dict[str, Any], context: Dict[str, Any]) -> str:
        """旧入口：analyze + verify 两次调用时的分析 prompt（保留兼容）。"""
        return self._build_single_prompt(snapshot, context, include_verification=False)

    def _build_verification_prompt(
        self,
        analysis: ContentAIAnalysisResult,
        snapshot: Dict[str, Any],
        context: Dict[str, Any],
    ) -> str:
        """旧入口：analyze + verify 两次调用时的验证 prompt（保留兼容）。"""
        qtype = snapshot.get("detected_question_type") or "choice"
        return (
            "这是对上一道题目的独立验证任务。请作为审核者验证 AI 分析是否正确。\n\n"
            f"检测到的题型：{qtype}\n"
            f"题干：\n{snapshot.get('stem') or '（空）'}\n\n"
            f"选项：\n{self._fmt_options(snapshot.get('options'))}\n\n"
            f"原答案（ground truth）：{snapshot.get('original_answer') or '（空）'}\n\n"
            f"AI 解析：\n{analysis.analysis or '（空）'}\n\n"
            f"AI 答案自检：{analysis.answer_check.model_dump() if analysis.answer_check else '（无）'}\n\n"
            "输出 JSON，字段严格如下：\n"
            "{\n"
            '  "verdict": "pass / doubtful / fail",\n'
            '  "answer_consistent": true,\n'
            '  "analysis_correct": true,\n'
            '  "kp_valid": true,\n'
            '  "answer_spec_valid": true,\n'
            '  "issues": ["问题描述，无则 []"],\n'
            '  "confidence": 0.9\n'
            "}"
        )

    def _build_single_prompt(
        self,
        snapshot: Dict[str, Any],
        context: Dict[str, Any],
        include_verification: bool = True,
    ) -> str:
        """单次调用 prompt：同时输出结构化分析与自我验证，减少一次网络往返。"""
        qtype = snapshot.get("detected_question_type") or "choice"
        known = context.get("known_knowledge_point_codes") or []
        suggested = snapshot.get("suggested_knowledge_point_codes") or []
        verification_part = (
            ',\n  "verification": {\n'
            '    "verdict": "pass / doubtful / fail",\n'
            '    "answer_consistent": true,\n'
            '    "analysis_correct": true,\n'
            '    "kp_valid": true,\n'
            '    "answer_spec_valid": true,\n'
            '    "issues": ["问题描述，无则 []"],\n'
            '    "confidence": 0.9\n'
            '  }'
            if include_verification
            else ""
        )
        return (
            "请对以下数学题目做结构化分析，并给出自我验证结论。你必须且只能输出一个 JSON 对象。\n\n"
            f"检测到的题型（可作为参考，若不一致请按你判断的真实题型输出）：{qtype}\n"
            f"题干：\n{snapshot.get('stem') or '（空）'}\n\n"
            f"选项：\n{self._fmt_options(snapshot.get('options'))}\n\n"
            f"原答案（ground truth，请据此做答案自检）：{snapshot.get('original_answer') or '（空）'}\n"
            f"原解析（参考）：\n{snapshot.get('original_solution') or '（空）'}\n\n"
            f"建议知识点 code：{suggested}\n"
            f"已知知识点 code 列表（只能从中挑选，无合适则返回空数组）：{known}\n\n"
            "输出 JSON，字段严格如下：\n"
            "{\n"
            '  "question_type": "从 choice/judge/numeric_fill/expression_fill/calculation/proof/short_answer 中选其一",\n'
            '  "knowledge_point_codes": ["从已知列表中挑选 1-3 个最相关 code；无合适则 []"],\n'
            '  "difficulty": 1,\n'
            '  "analysis": "详细中文解题过程，步骤清晰",\n'
            '  "common_mistakes": [{"type": "错误类型", "description": "学生常见错误描述"}],\n'
            '  "answer_check": {"official_answer": "你独立求解得到的答案", "consistent": true, "reason": "与原答案是否一致的简要理由"},\n'
            '  "confidence": 0.9,\n'
            '  "flags": ["需要人工关注的标签，如 ambiguous_stem；无则 []"]'
            f"{verification_part}\n"
            "}"
        )

    # ── 结果映射（防御性，缺字段用默认）──
    def _to_analysis_result(
        self, data: Dict[str, Any], snapshot: Dict[str, Any]
    ) -> ContentAIAnalysisResult:
        qtype = data.get("question_type") or snapshot.get("detected_question_type")
        # P0-3：题型必须属于受支持枚举；缺失/非法失败关闭（禁止静默回退 choice）。
        # 真实 AI 可返回任意受支持题型（calculation / proof / short_answer 等）。
        if qtype not in _SUPPORTED_TYPES:
            raise ContentAIProviderError(
                AI_PROVIDER_PARSE_FAILED,
                f"AI 返回非法 question_type: {qtype!r}（支持: {sorted(_SUPPORTED_TYPES)}）",
            )
        original_answer = snapshot.get("original_answer") or ""
        options = snapshot.get("options") or []
        kp = data.get("knowledge_point_codes") or []
        if not isinstance(kp, list):
            kp = []
        answer_check_raw = data.get("answer_check") or {}
        if not isinstance(answer_check_raw, dict):
            answer_check_raw = {}
        answer_check = ContentAIAnswerCheck(
            official_answer=answer_check_raw.get("official_answer") or original_answer,
            consistent=_strict_bool(answer_check_raw.get("consistent")),
            reason=str(answer_check_raw.get("reason", "")),
        )
        try:
            confidence = float(data.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        confidence = max(0.0, min(1.0, confidence))
        flags = data.get("flags") or []
        if not isinstance(flags, list):
            flags = []
        common_mistakes = data.get("common_mistakes") or []
        if not isinstance(common_mistakes, list):
            common_mistakes = []
        return ContentAIAnalysisResult(
            question_type=qtype,
            knowledge_point_codes=[str(c) for c in kp],
            difficulty=max(1, min(5, int(data.get("difficulty", 2) or 2))),
            analysis=str(data.get("analysis") or ""),
            answer_spec=_build_answer_spec(qtype, original_answer, options),
            common_mistakes=common_mistakes,
            answer_check=answer_check,
            confidence=confidence,
            flags=flags,
        )

    def _to_verification_result(self, data: Dict[str, Any]) -> ContentAIVerificationResult:
        verdict = str(data.get("verdict") or "").strip().lower()
        # P0-3：verdict 缺失/非法 → doubtful（失败关闭，绝不允许静默 pass）
        if verdict not in ("pass", "doubtful", "fail"):
            verdict = "doubtful"
        try:
            confidence = float(data.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        confidence = max(0.0, min(1.0, confidence))
        issues = data.get("issues") or []
        if not isinstance(issues, list):
            issues = []
        return ContentAIVerificationResult(
            verdict=verdict,
            answer_consistent=_strict_bool(data.get("answer_consistent")),
            analysis_correct=_strict_bool(data.get("analysis_correct")),
            kp_valid=_strict_bool(data.get("kp_valid")),
            answer_spec_valid=_strict_bool(data.get("answer_spec_valid")),
            issues=issues,
            confidence=confidence,
        )

    # ── 接口实现 ──
    def analyze(
        self, snapshot: Dict[str, Any], context: Dict[str, Any]
    ) -> ContentAIAnalysisResult:
        if not self.is_available():
            raise ContentAIProviderError(
                AI_PROVIDER_NOT_IMPLEMENTED,
                "DeepSeek API Key 未配置（请在 .env 设置 DEEPSEEK_API_KEY）。",
            )
        raw = self._chat(self._build_analysis_prompt(snapshot, context), temperature=0.2)
        data = self._parse_json(raw)
        return self._to_analysis_result(data, snapshot)

    def verify(
        self,
        analysis: ContentAIAnalysisResult,
        snapshot: Dict[str, Any],
        context: Dict[str, Any],
    ) -> ContentAIVerificationResult:
        if not self.is_available():
            raise ContentAIProviderError(
                AI_PROVIDER_NOT_IMPLEMENTED,
                "DeepSeek API Key 未配置（请在 .env 设置 DEEPSEEK_API_KEY）。",
            )
        raw = self._chat(
            self._build_verification_prompt(analysis, snapshot, context), temperature=0.0
        )
        data = self._parse_json(raw)
        return self._to_verification_result(data)

    def analyze_and_verify(
        self,
        snapshot: Dict[str, Any],
        context: Dict[str, Any],
    ) -> Tuple[ContentAIAnalysisResult, ContentAIVerificationResult]:
        """单次 LLM 调用同时完成分析与验证，减少 50% 网络往返。"""
        if not self.is_available():
            raise ContentAIProviderError(
                AI_PROVIDER_NOT_IMPLEMENTED,
                "DeepSeek API Key 未配置（请在 .env 设置 DEEPSEEK_API_KEY）。",
            )
        raw = self._chat(self._build_single_prompt(snapshot, context), temperature=0.2)
        data = self._parse_json(raw)
        analysis = self._to_analysis_result(data, snapshot)
        verification = self._to_verification_result(data.get("verification") or {})
        return analysis, verification


class ContentAIProviderFactory:
    """Provider 工厂（§24）。

    - mock  → MockContentAIProvider（实现，确定性，不联网）
    - deepseek → DeepSeekContentAIProvider（真实，OpenAI 兼容，需 DEEPSEEK_API_KEY）
    - qwen / auto → 当前 QwenContentAIProvider（stub，unavailable）
    """

    def __init__(self, provider: Optional[str] = None):
        self._mode = (provider or settings.CONTENT_AI_PROVIDER or "mock").strip().lower()

    def get_provider(self) -> ContentAIProvider:
        if self._mode == MOCK_PROVIDER_NAME:
            return MockContentAIProvider()
        if self._mode == DEEPSEEK_PROVIDER_NAME:
            return DeepSeekContentAIProvider(api_key=settings.DEEPSEEK_API_KEY)
        # qwen / auto：当前 stub
        return QwenContentAIProvider(api_key=settings.QWEN_API_KEY)

    def provider_status(self):
        from app.models.content_ai import ContentAIProviderStatusData

        qwen_key = bool(settings.QWEN_API_KEY and settings.QWEN_API_KEY.strip())
        deepseek_key = bool(settings.DEEPSEEK_API_KEY and settings.DEEPSEEK_API_KEY.strip())
        if self._mode == MOCK_PROVIDER_NAME:
            return ContentAIProviderStatusData(
                mode=self._mode,
                provider=MOCK_PROVIDER_NAME,
                available=True,
                real_available=deepseek_key or qwen_key,
                reason="mock",
            )
        if self._mode == DEEPSEEK_PROVIDER_NAME:
            return ContentAIProviderStatusData(
                mode=self._mode,
                provider=DEEPSEEK_PROVIDER_NAME,
                # 真实可用 = 有 key（is_available 会再做一次校验）
                available=deepseek_key,
                real_available=deepseek_key,
                reason="ok" if deepseek_key else "missing_api_key",
            )
        # qwen / auto：当前 stub 未实现 → 不可用；但记录真实 key 是否已配置
        return ContentAIProviderStatusData(
            mode=self._mode,
            provider=QWEN_PROVIDER_NAME,
            available=False,
            real_available=qwen_key,
            reason="not_implemented" if qwen_key else "missing_api_key",
        )


# 轻量单例（供 API / 服务复用）
_factory: Optional[ContentAIProviderFactory] = None
_provider: Optional[ContentAIProvider] = None


def get_provider_factory() -> ContentAIProviderFactory:
    global _factory
    if _factory is None:
        _factory = ContentAIProviderFactory()
    return _factory


def get_content_ai_provider() -> ContentAIProvider:
    """返回当前选中的 provider 单例。

    若为 qwen/auto 且不可用，调用方应使用 provider_status() 暴露不可用状态，
    并在 analyze 时捕获 ContentAIProviderError → 返回稳定 AI_UNAVAILABLE。
    """
    global _provider
    if _provider is None:
        _provider = get_provider_factory().get_provider()
    return _provider


def reset_for_test() -> None:
    """测试用：清空单例（避免跨测试污染）。"""
    global _factory, _provider
    _factory = None
    _provider = None
