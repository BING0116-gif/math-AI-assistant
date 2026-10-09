"""
记忆存储层 — PostgreSQL + Qdrant 数据操作。

提供 4 类记忆（错题、对话、里程碑、画像）的写入、查询、更新、归档操作。
支持异步写入、状态流转、Qdrant 向量同步。
"""

import json
import logging
import math
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.config.settings import settings
from app.data.database import get_db_session
from app.services.memory_policy import (
    CONFIDENCE_AUTO_EXTRACTED,
    CONFIDENCE_REOBSERVED_BONUS,
    CONFIDENCE_STRENGTH_ARCHIVE_THRESHOLD,
    CONFIDENCE_USER_CONFIRMED,
    CONFIDENCE_USER_CORRECTED,
    DECAY_LAMBDA,
    MEMORY_INIT_STRENGTH,
    MEMORY_KIND_FACT,
    MEMORY_KIND_MISCONCEPTION,
    MEMORY_KIND_PREFERENCE,
    MEMORY_TTL,
    MEMORY_TYPE_CONVERSATION,
    MEMORY_TYPE_ERROR,
    MEMORY_TYPE_MILESTONE,
    MEMORY_TYPE_PROFILE,
    STATUS_ACTIVE,
    STATUS_ARCHIVED,
    STATUS_DELETED,
    STATUS_PENDING,
    build_embedding_summary,
    infer_conversation_kind,
    infer_memory_kind,
)

logger = logging.getLogger(__name__)

class MemoryStore:
    """记忆存储层，封装 PostgreSQL + Qdrant 操作。"""

    def __init__(self):
        self._qdrant_client = None
        self._embedder = None
        self._qdrant_available = False
        self._init_qdrant_lazy()

    def _init_qdrant_lazy(self):
        """延迟初始化 Qdrant 客户端。"""
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.models import (
                Distance, VectorParams, PointStruct, Filter,
                FieldCondition, MatchValue, Range,
            )
            self._QdrantClient = QdrantClient
            self._VectorParams = VectorParams
            self._PointStruct = PointStruct
            self._Distance = Distance
            self._Filter = Filter
            self._FieldCondition = FieldCondition
            self._MatchValue = MatchValue
            self._Range = Range
            self._QDRANT_AVAILABLE = True
        except ImportError:
            logger.warning("[记忆存储] qdrant-client 未安装，Qdrant 功能不可用")
            self._QDRANT_AVAILABLE = False

    async def _get_qdrant_client(self):
        """获取 Qdrant 客户端（延迟初始化）。"""
        if self._qdrant_client is not None:
            return self._qdrant_client

        if not self._QDRANT_AVAILABLE:
            self._qdrant_available = False
            return None

        try:
            host = settings.QDRANT_HOST
            port = settings.QDRANT_PORT
            self._qdrant_client = self._QdrantClient(host=host, port=port)
            self._qdrant_available = True

            # 确保 collection 存在
            collection_name = settings.MEMORY_QDRANT_COLLECTION
            collections = self._qdrant_client.get_collections()
            exists = any(c.name == collection_name for c in collections.collections)
            if not exists:
                self._qdrant_client.create_collection(
                    collection_name=collection_name,
                    vectors_config=self._VectorParams(
                        size=settings.VECTOR_SIZE,
                        distance=self._Distance.COSINE,
                    ),
                )
                logger.info(f"[记忆存储] Qdrant collection 创建: {collection_name}")

            return self._qdrant_client
        except Exception as e:
            logger.warning(f"[记忆存储] Qdrant 连接失败: {e}")
            self._qdrant_available = False
            return None

    def _generate_embedding(self, text: str) -> List[float]:
        """生成文本向量。"""
        from app.services.embedding_service import get_embedding_service
        return get_embedding_service().encode(text)

    # ── 阶段四 6.4:冲突检测与仲裁 ──────────────────────────────────────

    @staticmethod
    def _cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(y * y for y in b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    @staticmethod
    def decide_conflict(*, kind: str, similarity: float, old_confidence: float, new_confidence: float) -> Tuple[str, str]:
        """6.4 仲裁纯函数 → (action, conflict_status)。

        分支:语义相同合并;0.85–0.92 按 kind 仲裁(preference 新胜旧 /
        fact 高置信胜·接近进复核 / misconception 双保留);低于检测线互不影响。
        """
        try:
            from app.config.settings import settings
            merge_line = settings.MEMORY_CONFLICT_MERGE_SIMILARITY
            detect_line = settings.MEMORY_CONFLICT_DETECT_SIMILARITY
        except Exception:
            merge_line, detect_line = 0.92, 0.85
        if similarity >= merge_line:
            return "merge", "merged"
        if similarity < detect_line:
            return "keep_both", "none"
        if kind == MEMORY_KIND_PREFERENCE:
            # 偏好天然时效性:新胜旧
            return "supersede_old", "superseded"
        if kind == MEMORY_KIND_FACT:
            if abs(old_confidence - new_confidence) < 0.1:
                return "keep_review", "review"  # 冲突不可自动裁定:双保留进人工复核
            return ("keep_old", "none") if old_confidence > new_confidence else ("supersede_old", "superseded")
        # misconception:错误理解本会演变,双保留,按 superseded_by 时间链可追溯
        return "keep_both", "none"

    async def arbitrate_memory_write(
        self,
        *,
        user_id: str,
        memory_id: int,
        memory_type: str,
        kind: Optional[str] = None,
        content: str,
    ) -> str:
        """写入后仲裁(6.4):对同 user、同 kind、active 近邻执行合并/让位/复核。

        返回裁决 action;MEMORY_CONFLICT_ENABLED 关闭时恒为 "disabled"(现状)。
        """
        try:
            from app.config.settings import settings
            if not settings.MEMORY_CONFLICT_ENABLED:
                return "disabled"
        except Exception:
            return "disabled"

        resolved_kind = infer_memory_kind(memory_type, kind)
        try:
            new_embedding = self._generate_embedding(content)
            async with get_db_session() as db:
                from sqlalchemy import select, text as sa_text
                from app.data.models import Memory
                from app.services.outbox import enqueue_outbox

                rows = list((await db.execute(select(Memory).where(
                    Memory.user_id == user_id,
                    Memory.memory_kind == resolved_kind,
                    Memory.status == STATUS_ACTIVE,
                    Memory.deleted_at.is_(None),
                    Memory.id != memory_id,
                ).order_by(Memory.created_at.desc()).limit(50))).scalars())
                if not rows:
                    return "keep_both"

                best_row, best_similarity = None, -1.0
                for row in rows:
                    similarity = self._cosine_similarity(
                        new_embedding,
                        self._generate_embedding(row.embedding_summary or row.content),
                    )
                    if similarity > best_similarity:
                        best_row, best_similarity = row, similarity
                if best_row is None:
                    return "keep_both"

                action, conflict_status = self.decide_conflict(
                    kind=resolved_kind,
                    similarity=best_similarity,
                    old_confidence=float(best_row.confidence or 0.6),
                    new_confidence=CONFIDENCE_AUTO_EXTRACTED,
                )

                if action == "merge":
                    # 语义相同:合并到旧记忆(access_count+1、置信上调封顶 0.95),新行下线
                    await db.execute(sa_text("""
                        UPDATE memories
                        SET access_count = access_count + 1,
                            confidence = MIN(0.95, confidence + :bonus)
                        WHERE id = :id
                    """), {"bonus": CONFIDENCE_REOBSERVED_BONUS, "id": best_row.id})
                    await db.execute(sa_text("""
                        UPDATE memories
                        SET status = :archived, conflict_status = 'merged', superseded_by = :old_id
                        WHERE id = :new_id
                    """), {"archived": STATUS_ARCHIVED, "old_id": best_row.id, "new_id": memory_id})
                    await enqueue_outbox(
                        db, event_type="memory.vector.delete", aggregate_type="memory",
                        aggregate_id=str(memory_id), user_id=user_id,
                        idempotency_key=f"memory-vector-merged:{memory_id}:{best_row.id}",
                    )
                elif action == "supersede_old":
                    # 新胜旧:旧记忆 superseded_by 指向新记忆并下线
                    await db.execute(sa_text("""
                        UPDATE memories
                        SET status = :archived, conflict_status = 'superseded', superseded_by = :new_id
                        WHERE id = :old_id
                    """), {"archived": STATUS_ARCHIVED, "new_id": memory_id, "old_id": best_row.id})
                    await enqueue_outbox(
                        db, event_type="memory.vector.delete", aggregate_type="memory",
                        aggregate_id=str(best_row.id), user_id=user_id,
                        idempotency_key=f"memory-vector-conflict-superseded:{best_row.id}:{memory_id}",
                    )
                elif action == "keep_review":
                    # 双保留进人工复核队列,注入侧由检索排序兜底
                    await db.execute(sa_text(
                        "UPDATE memories SET conflict_status = 'review' WHERE id IN (:a, :b)"
                    ), {"a": best_row.id, "b": memory_id})
                return action
        except Exception as e:
            logger.error(f"[记忆存储] 写入仲裁失败(按双保留处理): {e}")
            return "keep_both"

    async def _generate_embedding_summary(
        self, content: str, memory_type: str, metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """生成 embedding_summary 摘要文本。

        优先模板拼接，可选调用 LLM 精炼。
        """
        return build_embedding_summary(content, memory_type, metadata)

    # ========================================================================
    # 记忆写入
    # ========================================================================

    async def create_error_memory(
        self,
        user_id: str,
        question_id: str,
        question_content: str,
        high_category: str,
        category: str,
        knowledge_points: Optional[List[str]] = None,
        difficulty: int = 3,
        user_answer: str = "",
        correct_answer: str = "",
        error_type: str = "",
        kind: Optional[str] = None,
    ) -> Optional[int]:
        """创建错题记忆。

        1. 写入 PostgreSQL（status=pending）
        2. 异步生成 embedding_summary
        3. 生成向量并写入 Qdrant
        4. 更新 MySQL 状态为 active
        """
        now = int(time.time())
        summary = await self._generate_embedding_summary(
            question_content, MEMORY_TYPE_ERROR
        )

        content = json.dumps({
            "question_content": question_content,
            "user_answer": user_answer,
            "correct_answer": correct_answer,
            "error_type": error_type,
        }, ensure_ascii=False)

        memory_id = None
        try:
            async with get_db_session() as db:
                from sqlalchemy import text as sa_text

                expire_at = now + MEMORY_TTL[MEMORY_TYPE_ERROR]
                init_strength = MEMORY_INIT_STRENGTH[MEMORY_TYPE_ERROR]

                result = await db.execute(
                    sa_text("""
                        INSERT INTO memories
                        (user_id, memory_type, high_category, category, content,
                         embedding_summary, importance, difficulty, status,
                         expire_at, memory_strength, source_id, created_at,
                         last_accessed, access_count, memory_kind, confidence)
                        VALUES
                        (:user_id, :memory_type, :high_category, :category, :content,
                         :embedding_summary, :importance, :difficulty, :status,
                         :expire_at, :memory_strength, :source_id, :created_at,
                         :last_accessed, :access_count, :memory_kind, :confidence)
                    """),
                    {
                        "user_id": user_id,
                        "memory_type": MEMORY_TYPE_ERROR,
                        "high_category": high_category,
                        "category": category,
                        "content": content,
                        "embedding_summary": summary,
                        "importance": 0.7,
                        "difficulty": difficulty,
                        "status": STATUS_PENDING,
                        "expire_at": expire_at,
                        "memory_strength": init_strength,
                        "source_id": question_id,
                        "created_at": now,
                        "last_accessed": now,
                        "access_count": 0,
                        "memory_kind": infer_memory_kind(MEMORY_TYPE_ERROR, kind),
                        "confidence": CONFIDENCE_AUTO_EXTRACTED,
                    }
                )
                memory_id = result.lastrowid or 0

                # 写入标签
                if knowledge_points:
                    for kp in knowledge_points:
                        await db.execute(
                            sa_text("""
                                INSERT INTO memory_tags (memory_id, tag_name)
                                VALUES (:memory_id, :tag_name)
                            """),
                            {"memory_id": memory_id, "tag_name": kp},
                        )

                # 同步写入 Qdrant
                await self._sync_to_qdrant(
                    db=db,
                    memory_id=memory_id,
                    user_id=user_id,
                    status=STATUS_ACTIVE,
                    expire_at=expire_at,
                )

                # 更新状态为 active
                result = await db.execute(
                    sa_text("""
                        UPDATE memories SET status = :status
                        WHERE id = :id
                    """),
                    {"status": STATUS_ACTIVE, "id": memory_id},
                )

                # 阶段四 6.4:写入后同 kind 近邻仲裁(开关关闭时为 no-op)
                await self.arbitrate_memory_write(
                    user_id=user_id,
                    memory_id=memory_id,
                    memory_type=MEMORY_TYPE_ERROR,
                    kind=kind,
                    content=content,
                )

            logger.info(
                f"[记忆存储] 错题记忆已创建: id={memory_id}, user={user_id}, "
                f"category={category}"
            )
            return memory_id

        except Exception as e:
            logger.error(f"[记忆存储] 创建错题记忆失败: {e}")
            return None

    async def create_conversation_memory(
        self,
        user_id: str,
        content: str,
        high_category: str = "",
        category: str = "",
        importance: float = 0.6,
        tags: Optional[List[str]] = None,
        kind: Optional[str] = None,
    ) -> Optional[int]:
        """创建对话记忆。"""
        now = int(time.time())
        summary = await self._generate_embedding_summary(
            content, MEMORY_TYPE_CONVERSATION
        )

        memory_id = None
        try:
            async with get_db_session() as db:
                from sqlalchemy import text as sa_text

                expire_at = now + MEMORY_TTL[MEMORY_TYPE_CONVERSATION]
                init_strength = MEMORY_INIT_STRENGTH[MEMORY_TYPE_CONVERSATION]

                result = await db.execute(
                    sa_text("""
                        INSERT INTO memories
                        (user_id, memory_type, high_category, category, content,
                         embedding_summary, importance, status,
                         expire_at, memory_strength, created_at, last_accessed,
                         memory_kind, confidence)
                        VALUES
                        (:user_id, :memory_type, :high_category, :category, :content,
                         :embedding_summary, :importance, :status,
                         :expire_at, :memory_strength, :created_at, :last_accessed,
                         :memory_kind, :confidence)
                    """),
                    {
                        "user_id": user_id,
                        "memory_type": MEMORY_TYPE_CONVERSATION,
                        "high_category": high_category,
                        "category": category,
                        "content": content,
                        "embedding_summary": summary,
                        "importance": importance,
                        "status": STATUS_PENDING,
                        "expire_at": expire_at,
                        "memory_strength": init_strength,
                        "created_at": now,
                        "last_accessed": now,
                        # 6.6:对话记忆 kind 细分——风格→preference、进度→fact,其余 context
                        "memory_kind": infer_memory_kind(MEMORY_TYPE_CONVERSATION, kind) if kind is not None else infer_conversation_kind(content),
                        "confidence": CONFIDENCE_AUTO_EXTRACTED,
                    }
                )
                memory_id = result.lastrowid or 0

                if tags:
                    for tag in tags:
                        await db.execute(
                            sa_text("""
                                INSERT INTO memory_tags (memory_id, tag_name)
                                VALUES (:memory_id, :tag_name)
                            """),
                            {"memory_id": memory_id, "tag_name": tag},
                        )

                await self._sync_to_qdrant(
                    db=db,
                    memory_id=memory_id,
                    user_id=user_id,
                    status=STATUS_ACTIVE,
                    expire_at=expire_at,
                )

                await db.execute(
                    sa_text("UPDATE memories SET status = :status WHERE id = :id"),
                    {"status": STATUS_ACTIVE, "id": memory_id},
                )

                # 阶段四 6.4:写入后同 kind 近邻仲裁(开关关闭时为 no-op)
                await self.arbitrate_memory_write(
                    user_id=user_id,
                    memory_id=memory_id,
                    memory_type=MEMORY_TYPE_CONVERSATION,
                    kind=kind,
                    content=content,
                )

            return memory_id

        except Exception as e:
            logger.error(f"[记忆存储] 创建对话记忆失败: {e}")
            return None

    async def create_milestone_memory(
        self,
        user_id: str,
        milestone_type: str,
        description: str,
        high_category: str = "",
        category: str = "",
        kind: Optional[str] = None,
    ) -> Optional[int]:
        """创建里程碑记忆。"""
        now = int(time.time())

        memory_id = None
        try:
            async with get_db_session() as db:
                from sqlalchemy import text as sa_text

                expire_at = now + MEMORY_TTL[MEMORY_TYPE_MILESTONE]
                init_strength = MEMORY_INIT_STRENGTH[MEMORY_TYPE_MILESTONE]

                result = await db.execute(
                    sa_text("""
                        INSERT INTO memories
                        (user_id, memory_type, high_category, category, content,
                         embedding_summary, importance, status,
                         expire_at, memory_strength, created_at, last_accessed,
                         memory_kind, confidence)
                        VALUES
                        (:user_id, :memory_type, :high_category, :category, :content,
                         :embedding_summary, :importance, :status,
                         :expire_at, :memory_strength, :created_at, :last_accessed,
                         :memory_kind, :confidence)
                    """),
                    {
                        "user_id": user_id,
                        "memory_type": MEMORY_TYPE_MILESTONE,
                        "high_category": high_category,
                        "category": category,
                        "content": description,
                        "embedding_summary": description[:80],
                        "importance": 0.85,
                        "status": STATUS_ACTIVE,
                        "expire_at": expire_at,
                        "memory_strength": init_strength,
                        "created_at": now,
                        "last_accessed": now,
                        "memory_kind": infer_memory_kind(MEMORY_TYPE_MILESTONE, kind),
                        "confidence": CONFIDENCE_AUTO_EXTRACTED,
                    }
                )
                memory_id = result.lastrowid or 0

                if milestone_type:
                    await db.execute(
                        sa_text("""
                            INSERT INTO memory_tags (memory_id, tag_name)
                            VALUES (:memory_id, :tag_name)
                        """),
                        {"memory_id": memory_id, "tag_name": milestone_type},
                    )

                await self._sync_to_qdrant(
                    db=db,
                    memory_id=memory_id,
                    user_id=user_id,
                    status=STATUS_ACTIVE,
                    expire_at=expire_at,
                )

            return memory_id

        except Exception as e:
            logger.error(f"[记忆存储] 创建里程碑记忆失败: {e}")
            return None

    async def create_profile_memory(
        self,
        user_id: str,
        summary_text: str,
        full_profile_json: str,
        high_category: str = "",
        category: str = "",
        kind: Optional[str] = None,
    ) -> Optional[int]:
        """创建画像记忆。"""
        now = int(time.time())

        memory_id = None
        try:
            async with get_db_session() as db:
                from sqlalchemy import text as sa_text

                expire_at = now + MEMORY_TTL[MEMORY_TYPE_PROFILE]
                init_strength = MEMORY_INIT_STRENGTH[MEMORY_TYPE_PROFILE]

                result = await db.execute(
                    sa_text("""
                        INSERT INTO memories
                        (user_id, memory_type, high_category, category, content,
                         embedding_summary, importance, status,
                         expire_at, memory_strength, created_at, last_accessed,
                         memory_kind, confidence)
                        VALUES
                        (:user_id, :memory_type, :high_category, :category, :content,
                         :embedding_summary, :importance, :status,
                         :expire_at, :memory_strength, :created_at, :last_accessed,
                         :memory_kind, :confidence)
                    """),
                    {
                        "user_id": user_id,
                        "memory_type": MEMORY_TYPE_PROFILE,
                        "high_category": high_category,
                        "category": category,
                        "content": full_profile_json,
                        "embedding_summary": summary_text,
                        "importance": 1.0,
                        "status": STATUS_ACTIVE,
                        "expire_at": expire_at,
                        "memory_strength": init_strength,
                        "created_at": now,
                        "last_accessed": now,
                        "memory_kind": infer_memory_kind(MEMORY_TYPE_PROFILE, kind),
                        "confidence": CONFIDENCE_AUTO_EXTRACTED,
                    }
                )
                memory_id = result.lastrowid or 0

                await db.execute(
                    sa_text("""
                        INSERT INTO memory_tags (memory_id, tag_name)
                        VALUES (:memory_id, :tag_name)
                    """),
                    {"memory_id": memory_id, "tag_name": "profile"},
                )

                await self._sync_to_qdrant(
                    db=db,
                    memory_id=memory_id,
                    user_id=user_id,
                    status=STATUS_ACTIVE,
                    expire_at=expire_at,
                )

            return memory_id

        except Exception as e:
            logger.error(f"[记忆存储] 创建画像记忆失败: {e}")
            return None

    # ========================================================================
    # Qdrant 同步
    # ========================================================================

    async def _sync_to_qdrant(
        self,
        db,
        memory_id: int,
        user_id: str,
        status: str = STATUS_ACTIVE,
        expire_at: Optional[int] = None,
    ):
        """Enqueue vector sync in the same SQL transaction as the memory fact."""
        from app.services.outbox import enqueue_outbox
        await enqueue_outbox(
            db,
            event_type="memory.vector.upsert",
            aggregate_type="memory",
            aggregate_id=str(memory_id),
            user_id=user_id,
            idempotency_key=f"memory-vector-upsert:{memory_id}:{status}:{expire_at or 0}",
        )

    # ========================================================================
    # 记忆查询
    # ========================================================================

    async def get_memory_by_id(self, memory_id: int) -> Optional[Dict[str, Any]]:
        """根据 ID 获取单条记忆（含标签）。"""
        try:
            async with get_db_session() as db:
                from sqlalchemy import select
                from app.data.models import Memory, MemoryTag

                result = await db.execute(
                    select(Memory).where(
                        Memory.id == memory_id,
                        Memory.deleted_at.is_(None),
                    )
                )
                row = result.scalar_one_or_none()
                if row is None:
                    return None

                # 应用层读取标签（替代 GROUP_CONCAT）
                tag_result = await db.execute(
                    select(MemoryTag.tag_name).where(
                        MemoryTag.memory_id == memory_id
                    )
                )
                tags = [t[0] for t in tag_result.fetchall()]

                data = {
                    c.name: getattr(row, c.name)
                    for c in row.__table__.columns
                }
                data["tags"] = ",".join(tags) if tags else None
                return data
        except Exception as e:
            logger.error(f"[记忆存储] 查询记忆失败: id={memory_id}, error={e}")
            return None

    async def get_user_memories(
        self,
        user_id: str,
        memory_type: Optional[str] = None,
        status: str = STATUS_ACTIVE,
        offset: int = 0,
        limit: int = 20,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """分页查询用户记忆列表（含标签，应用层聚合替代 GROUP_CONCAT）。"""
        try:
            async with get_db_session() as db:
                from sqlalchemy import select, func
                from app.data.models import Memory, MemoryTag

                filters = [Memory.user_id == user_id, Memory.deleted_at.is_(None)]
                if memory_type:
                    filters.append(Memory.memory_type == memory_type)
                if status:
                    filters.append(Memory.status == status)

                # 查询总数
                count_result = await db.execute(
                    select(func.count(Memory.id)).where(*filters)
                )
                total = count_result.scalar() or 0

                # 查询列表
                result = await db.execute(
                    select(Memory)
                    .where(*filters)
                    .order_by(Memory.created_at.desc())
                    .offset(offset)
                    .limit(limit)
                )
                rows = result.scalars().all()

                # 批量读取标签（应用层聚合替代 GROUP_CONCAT）
                memory_ids = [m.id for m in rows]
                if memory_ids:
                    tag_result = await db.execute(
                        select(MemoryTag.memory_id, MemoryTag.tag_name)
                        .where(MemoryTag.memory_id.in_(memory_ids))
                    )
                    tags_by_memory: Dict[int, List[str]] = {}
                    for mid, tname in tag_result.fetchall():
                        tags_by_memory.setdefault(mid, []).append(tname)
                else:
                    tags_by_memory = {}

                memories = []
                for m in rows:
                    data = {
                        c.name: getattr(m, c.name)
                        for c in m.__table__.columns
                    }
                    tags = tags_by_memory.get(m.id, [])
                    data["tags"] = ",".join(tags) if tags else None
                    memories.append(data)

                return memories, total
        except Exception as e:
            logger.error(f"[记忆存储] 查询用户记忆列表失败: {e}")
            return [], 0

    async def get_active_memories_by_user(
        self, user_id: str, memory_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """获取用户所有 active 状态记忆。"""
        memories, _ = await self.get_user_memories(
            user_id=user_id,
            memory_type=memory_type,
            status=STATUS_ACTIVE,
            limit=1000,
        )
        return memories

    # ========================================================================
    # 记忆更新
    # ========================================================================

    async def update_memory_strength(
        self, memory_id: int, strength: float
    ) -> bool:
        """更新记忆强度。"""
        try:
            async with get_db_session() as db:
                from sqlalchemy import text as sa_text

                result = await db.execute(
                    sa_text("""
                        UPDATE memories
                        SET memory_strength = :strength, last_accessed = :now
                        WHERE id = :id
                    """),
                    {"strength": strength, "now": int(time.time()), "id": memory_id},
                )
                return result.rowcount > 0
        except Exception as e:
            logger.error(f"[记忆存储] 更新记忆强度失败: {e}")
            return False

    async def update_memory_access(
        self,
        memory_id: int,
        strength_increment: float = 0.06,
        *,
        user_id: Optional[str] = None,
    ) -> bool:
        """更新记忆访问；提供 ``user_id`` 时同时强制校验所有权。"""
        try:
            async with get_db_session() as db:
                from sqlalchemy import text as sa_text

                now = int(time.time())
                result = await db.execute(
                    sa_text("""
                        UPDATE memories
                        SET memory_strength = CASE
                                WHEN memory_strength + :inc > 1.0 THEN 1.0
                                ELSE memory_strength + :inc
                            END,
                            access_count = access_count + 1,
                            last_accessed = :now
                        WHERE id = :id
                          AND status = 'active'
                          AND (:user_id IS NULL OR user_id = :user_id)
                    """),
                    {
                        "inc": strength_increment,
                        "now": now,
                        "id": memory_id,
                        "user_id": user_id,
                    },
                )
                return result.rowcount > 0
        except Exception as e:
            logger.error(f"[记忆存储] 更新记忆访问失败: {e}")
            return False

    async def update_mastery_weight(
        self,
        user_id: str,
        high_category: str,
        category: str,
        is_correct: bool,
    ) -> None:
        """更新知识点权重（答对时强化关联记忆）。"""
        # 当前为轻量实现，后续可扩展
        pass

    async def update_memory_content(
        self, memory_id: int, content: str, summary: str
    ) -> bool:
        """更新记忆内容和摘要。"""
        try:
            async with get_db_session() as db:
                from sqlalchemy import text as sa_text

                result = await db.execute(
                    sa_text("""
                        UPDATE memories
                        SET content = :content, embedding_summary = :summary
                        WHERE id = :id
                    """),
                    {"content": content, "summary": summary, "id": memory_id},
                )
                return result.rowcount > 0
        except Exception as e:
            logger.error(f"[记忆存储] 更新记忆内容失败: {e}")
            return False

    # ========================================================================
    # 记忆归档与删除
    # ========================================================================

    async def archive_memory(self, memory_id: int) -> bool:
        """归档单条记忆（soft archive）。"""
        try:
            async with get_db_session() as db:
                from sqlalchemy import text as sa_text

                result = await db.execute(
                    sa_text("""
                        UPDATE memories
                        SET status = :status
                        WHERE id = :id AND status = 'active'
                    """),
                    {"status": STATUS_ARCHIVED, "id": memory_id},
                )
                if result.rowcount <= 0:
                    return False
                from app.services.outbox import enqueue_outbox
                await enqueue_outbox(
                    db, event_type="memory.vector.delete", aggregate_type="memory",
                    aggregate_id=str(memory_id), idempotency_key=f"memory-vector-archive:{memory_id}",
                )
                return True
        except Exception as e:
            logger.error(f"[记忆存储] 归档记忆失败: {e}")
            return False

    async def soft_delete_memory(self, memory_id: int) -> bool:
        """软删除单条记忆。"""
        try:
            async with get_db_session() as db:
                from sqlalchemy import text as sa_text

                now = int(time.time())
                result = await db.execute(
                    sa_text("""
                        UPDATE memories
                        SET status = :status, deleted_at = :now
                        WHERE id = :id
                    """),
                    {"status": STATUS_DELETED, "now": now, "id": memory_id},
                )
                if result.rowcount <= 0:
                    return False
                from app.services.outbox import enqueue_outbox
                await enqueue_outbox(
                    db, event_type="memory.vector.delete", aggregate_type="memory",
                    aggregate_id=str(memory_id), idempotency_key=f"memory-vector-delete:{memory_id}",
                )
                return True
        except Exception as e:
            logger.error(f"[记忆存储] 软删除记忆失败: {e}")
            return False

    async def list_user_memories(
        self,
        user_id: str,
        *,
        status: str = "active",
        include_deleted: bool = False,
        offset: int = 0,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """用户可控记忆列表(6.5):只返回本人记忆的展示字段。"""
        try:
            async with get_db_session() as db:
                from sqlalchemy import select
                from app.data.models import Memory

                query = select(Memory).where(Memory.user_id == user_id)
                if not include_deleted:
                    query = query.where(Memory.deleted_at.is_(None))
                if status and not include_deleted:
                    query = query.where(Memory.status == status)
                rows = list((await db.execute(
                    query.order_by(Memory.created_at.desc()).offset(max(0, offset)).limit(max(1, min(200, limit)))
                )).scalars())
                return [
                    {
                        "id": row.id,
                        "memory_type": row.memory_type,
                        "memory_kind": row.memory_kind or "context",
                        "category": row.category or "",
                        "content": row.content,
                        "status": row.status,
                        "confidence": float(row.confidence or 0.6),
                        "memory_strength": float(row.memory_strength or 0),
                        "conflict_status": row.conflict_status or "none",
                        "superseded_by": row.superseded_by,
                        "created_at": row.created_at,
                        "last_confirmed_at": row.last_confirmed_at,
                        "expire_at": row.expire_at,
                    }
                    for row in rows
                ]
        except Exception as e:
            logger.error(f"[记忆存储] 用户记忆列表查询失败: {e}")
            return []

    async def delete_memory_owned(self, user_id: str, memory_id: int) -> bool:
        """用户删除本人记忆(6.5):软删 + 向量下线;owner 校验,幂等。"""
        try:
            async with get_db_session() as db:
                from sqlalchemy import text as sa_text
                from app.services.outbox import enqueue_outbox

                now = int(time.time())
                result = await db.execute(
                    sa_text("""
                        UPDATE memories
                        SET status = :status, deleted_at = :now
                        WHERE id = :id AND user_id = :user_id AND deleted_at IS NULL
                    """),
                    {"status": STATUS_DELETED, "now": now, "id": memory_id, "user_id": user_id},
                )
                if result.rowcount <= 0:
                    return False
                await enqueue_outbox(
                    db, event_type="memory.vector.delete", aggregate_type="memory",
                    aggregate_id=str(memory_id), user_id=user_id,
                    idempotency_key=f"memory-vector-user-delete:{memory_id}",
                )
                return True
        except Exception as e:
            logger.error(f"[记忆存储] 用户删除记忆失败: {e}")
            return False

    async def delete_user_vectors(self, user_id: str) -> bool:
        """Permanently remove all memory vectors belonging to one user."""
        if not self._QDRANT_AVAILABLE:
            return True

        client = await self._get_qdrant_client()
        if client is None:
            return False

        try:
            from qdrant_client.models import FilterSelector

            user_filter = self._Filter(
                must=[
                    self._FieldCondition(
                        key="user_id",
                        match=self._MatchValue(value=user_id),
                    )
                ]
            )
            client.delete(
                collection_name=settings.MEMORY_QDRANT_COLLECTION,
                points_selector=FilterSelector(filter=user_filter),
                wait=True,
            )
            return True
        except Exception:
            logger.exception(
                "[memory-store] Failed to delete vectors for user %s", user_id
            )
            return False

    async def archive_by_source_id(self, source_id: str) -> int:
        """根据 source_id 归档关联记忆。"""
        try:
            async with get_db_session() as db:
                from sqlalchemy import select, text as sa_text
                from app.data.models import Memory

                ids = list((await db.execute(select(Memory.id).where(
                    Memory.source_id == source_id, Memory.status == STATUS_ACTIVE
                ))).scalars())

                result = await db.execute(
                    sa_text("""
                        UPDATE memories
                        SET status = :status
                        WHERE source_id = :source_id AND status = 'active'
                    """),
                    {"status": STATUS_ARCHIVED, "source_id": source_id},
                )
                from app.services.outbox import enqueue_outbox
                for memory_id in ids:
                    await enqueue_outbox(
                        db, event_type="memory.vector.delete", aggregate_type="memory",
                        aggregate_id=str(memory_id),
                        idempotency_key=f"memory-vector-source-archive:{memory_id}:{source_id}",
                    )
                return result.rowcount
        except Exception as e:
            logger.error(f"[记忆存储] 归档 source_id 关联记忆失败: {e}")
            return 0

    async def batch_archive_expired(self) -> int:
        """批量归档过期记忆（expire_at < now）。"""
        try:
            async with get_db_session() as db:
                from sqlalchemy import select, text as sa_text
                from app.data.models import Memory

                now = int(time.time())
                ids = list((await db.execute(select(Memory.id).where(
                    Memory.status == STATUS_ACTIVE, Memory.expire_at < now
                ))).scalars())
                result = await db.execute(
                    sa_text("""
                        UPDATE memories
                        SET status = :status
                        WHERE status = 'active' AND expire_at < :now
                    """),
                    {"status": STATUS_ARCHIVED, "now": now},
                )
                count = result.rowcount
                from app.services.outbox import enqueue_outbox
                for memory_id in ids:
                    await enqueue_outbox(
                        db, event_type="memory.vector.delete", aggregate_type="memory",
                        aggregate_id=str(memory_id),
                        idempotency_key=f"memory-vector-expired:{memory_id}",
                    )
                if count > 0:
                    logger.info(f"[记忆存储] 批量归档过期记忆: {count} 条")
                return count
        except Exception as e:
            logger.error(f"[记忆存储] 批量归档过期记忆失败: {e}")
            return 0

    async def batch_archive_low_strength(self, threshold: float = 0.2) -> int:
        """批量归档低强度记忆（memory_strength < threshold）。"""
        try:
            async with get_db_session() as db:
                from sqlalchemy import select, text as sa_text
                from app.data.models import Memory

                ids = list((await db.execute(select(Memory.id).where(
                    Memory.status == STATUS_ACTIVE, Memory.memory_strength < threshold
                ))).scalars())

                result = await db.execute(
                    sa_text("""
                        UPDATE memories
                        SET status = :status
                        WHERE status = 'active' AND memory_strength < :threshold
                    """),
                    {"status": STATUS_ARCHIVED, "threshold": threshold},
                )
                count = result.rowcount
                from app.services.outbox import enqueue_outbox
                for memory_id in ids:
                    await enqueue_outbox(
                        db, event_type="memory.vector.delete", aggregate_type="memory",
                        aggregate_id=str(memory_id),
                        idempotency_key=f"memory-vector-low-strength:{memory_id}",
                    )
                if count > 0:
                    logger.info(f"[记忆存储] 批量归档低强度记忆: {count} 条")
                return count
        except Exception as e:
            logger.error(f"[记忆存储] 批量归档低强度记忆失败: {e}")
            return 0

    async def batch_archive_low_confidence(self, threshold: float = CONFIDENCE_STRENGTH_ARCHIVE_THRESHOLD) -> int:
        """置信度联动归档（6.3）:confidence × memory_strength < 阈值 → archive。

        旧数据无 confidence 列时由 server_default 0.6 参与计算,行为向后兼容。
        """
        try:
            async with get_db_session() as db:
                from sqlalchemy import select, text as sa_text
                from app.data.models import Memory

                ids = list((await db.execute(select(Memory.id).where(
                    Memory.status == STATUS_ACTIVE,
                    Memory.confidence * Memory.memory_strength < threshold,
                ))).scalars())

                result = await db.execute(
                    sa_text("""
                        UPDATE memories
                        SET status = :status
                        WHERE status = 'active'
                          AND confidence * memory_strength < :threshold
                    """),
                    {"status": STATUS_ARCHIVED, "threshold": threshold},
                )
                count = result.rowcount
                from app.services.outbox import enqueue_outbox
                for memory_id in ids:
                    await enqueue_outbox(
                        db, event_type="memory.vector.delete", aggregate_type="memory",
                        aggregate_id=str(memory_id),
                        idempotency_key=f"memory-vector-low-confidence:{memory_id}",
                    )
                if count > 0:
                    logger.info(f"[记忆存储] 批量归档低置信记忆: {count} 条")
                return count
        except Exception as e:
            logger.error(f"[记忆存储] 批量归档低置信记忆失败: {e}")
            return 0

    async def confirm_memory(self, user_id: str, memory_id: int) -> bool:
        """用户显式确认（6.5）:置信度 → 0.9 并记录确认时间;owner 校验,幂等。"""
        try:
            async with get_db_session() as db:
                from sqlalchemy import text as sa_text

                result = await db.execute(
                    sa_text("""
                        UPDATE memories
                        SET confidence = :confidence, last_confirmed_at = :now
                        WHERE id = :id AND user_id = :user_id AND deleted_at IS NULL
                    """),
                    {
                        "confidence": CONFIDENCE_USER_CONFIRMED,
                        "now": int(time.time()),
                        "id": memory_id,
                        "user_id": user_id,
                    },
                )
                return (result.rowcount or 0) > 0
        except Exception as e:
            logger.error(f"[记忆存储] 确认记忆失败: {e}")
            return False

    async def correct_memory(self, user_id: str, memory_id: int, corrected_content: str) -> Optional[int]:
        """用户纠正（6.5）:生成新记忆(confidence=0.95),旧记忆 superseded_by 指向新记忆
        并归档下线(SQL+Qdrant 同步);重复纠正幂等返回同一新记忆 id。"""
        if not corrected_content.strip():
            return None
        try:
            async with get_db_session() as db:
                from sqlalchemy import select, text as sa_text
                from app.data.models import Memory
                from app.services.outbox import enqueue_outbox

                old = (await db.execute(select(Memory).where(
                    Memory.id == memory_id,
                    Memory.user_id == user_id,
                    Memory.deleted_at.is_(None),
                ))).scalar_one_or_none()
                if old is None:
                    return None
                if old.superseded_by is not None:
                    return old.superseded_by  # 幂等:已纠正过,返回既有新记忆

                now = int(time.time())
                new_kind = old.memory_kind or infer_memory_kind(old.memory_type)
                expire_at = now + MEMORY_TTL.get(old.memory_type, MEMORY_TTL[MEMORY_TYPE_CONVERSATION])
                result = await db.execute(
                    sa_text("""
                        INSERT INTO memories
                        (user_id, memory_type, high_category, category, content,
                         embedding_summary, importance, status,
                         expire_at, memory_strength, created_at, last_accessed,
                         memory_kind, confidence, conflict_status)
                        VALUES
                        (:user_id, :memory_type, :high_category, :category, :content,
                         :embedding_summary, :importance, :status,
                         :expire_at, :memory_strength, :created_at, :last_accessed,
                         :memory_kind, :confidence, :conflict_status)
                    """),
                    {
                        "user_id": user_id,
                        "memory_type": old.memory_type,
                        "high_category": old.high_category,
                        "category": old.category,
                        "content": corrected_content,
                        "embedding_summary": build_embedding_summary(corrected_content, old.memory_type),
                        "importance": old.importance,
                        "status": STATUS_ACTIVE,
                        "expire_at": expire_at,
                        "memory_strength": old.memory_strength,
                        "created_at": now,
                        "last_accessed": now,
                        "memory_kind": new_kind,
                        "confidence": CONFIDENCE_USER_CORRECTED,
                        "conflict_status": "corrected",
                    },
                )
                new_id = result.lastrowid or 0

                # 旧记忆下线:superseded 链可追溯 + 向量同步删除
                await db.execute(
                    sa_text("""
                        UPDATE memories
                        SET superseded_by = :new_id, conflict_status = 'superseded', status = :archived
                        WHERE id = :old_id
                    """),
                    {"new_id": new_id, "archived": STATUS_ARCHIVED, "old_id": memory_id},
                )
                await enqueue_outbox(
                    db, event_type="memory.vector.upsert", aggregate_type="memory",
                    aggregate_id=str(new_id), user_id=user_id,
                    idempotency_key=f"memory-vector-upsert:{new_id}:active:{expire_at}",
                )
                await enqueue_outbox(
                    db, event_type="memory.vector.delete", aggregate_type="memory",
                    aggregate_id=str(memory_id), user_id=user_id,
                    idempotency_key=f"memory-vector-superseded:{memory_id}:{new_id}",
                )
                logger.info(f"[记忆存储] 记忆已纠正: old={memory_id} -> new={new_id}, user={user_id}")
                return new_id
        except Exception as e:
            logger.error(f"[记忆存储] 纠正记忆失败: {e}")
            return None

    # ========================================================================
    # Qdrant 向量检索
    # ========================================================================

    async def vector_search(
        self,
        user_id: str,
        query_text: str,
        top_k: int = 20,
        memory_types: Optional[List[str]] = None,
        high_category: Optional[str] = None,
        min_score: float = 0.6,
        min_importance: float = 0.0,
    ) -> List[Dict[str, Any]]:
        """Qdrant 向量语义检索。"""
        if not self._QDRANT_AVAILABLE:
            return []

        try:
            client = await self._get_qdrant_client()
            if client is None:
                return []

            from qdrant_client.models import Filter, FieldCondition, MatchValue, Range

            vector = self._generate_embedding(query_text)

            # 构建过滤条件
            conditions = [
                FieldCondition(key="user_id", match=MatchValue(value=user_id)),
                FieldCondition(key="status", match=MatchValue(value=STATUS_ACTIVE)),
            ]

            if memory_types:
                from qdrant_client.models import MatchAny
                conditions.append(
                    FieldCondition(key="memory_type", match=MatchAny(any=memory_types))
                )

            if high_category:
                conditions.append(
                    FieldCondition(key="high_category", match=MatchValue(value=high_category))
                )

            if min_importance > 0:
                conditions.append(
                    FieldCondition(key="importance", range=Range(gte=min_importance))
                )

            # 未过期过滤
            now = int(time.time())
            conditions.append(
                FieldCondition(key="expire_at", range=Range(gte=now))
            )

            query_filter = Filter(must=conditions)

            response = client.query_points(
                collection_name=settings.MEMORY_QDRANT_COLLECTION,
                query=vector,
                query_filter=query_filter,
                limit=top_k,
                with_payload=True,
                score_threshold=min_score,
            )

            results = []
            for point in response.points:
                payload = point.payload or {}
                results.append({
                    "memory_id": payload.get("memory_id", 0),
                    "user_id": payload.get("user_id", ""),
                    "memory_type": payload.get("memory_type", ""),
                    "high_category": payload.get("high_category", ""),
                    "category": payload.get("category", ""),
                    "summary": "",  # 通过 MySQL 获取完整内容
                    "importance": payload.get("importance", 0.5),
                    "memory_strength": payload.get("memory_strength", 0.5),
                    "difficulty": payload.get("difficulty"),
                    "created_at": payload.get("created_at", 0),
                    "last_accessed": payload.get("last_accessed", 0),
                    "access_count": payload.get("access_count", 0),
                    "score": point.score,
                })

            return results

        except Exception as e:
            logger.warning(f"[记忆存储] Qdrant 向量检索失败: {e}")
            return []

    # ========================================================================
    # 维护操作
    # ========================================================================

    async def get_memory_stats(self, user_id: str) -> Dict[str, Any]:
        """获取用户记忆统计。"""
        try:
            async with get_db_session() as db:
                from sqlalchemy import text as sa_text

                result = await db.execute(
                    sa_text("""
                        SELECT
                            memory_type,
                            COUNT(*) as total,
                            SUM(CASE WHEN status = 'active' THEN 1 ELSE 0 END) as active_count,
                            AVG(memory_strength) as avg_strength,
                            AVG(importance) as avg_importance
                        FROM memories
                        WHERE user_id = :user_id AND deleted_at IS NULL
                        GROUP BY memory_type
                    """),
                    {"user_id": user_id},
                )
                rows = result.fetchall()
                stats = {}
                for row in rows:
                    d = dict(row._mapping)
                    stats[d["memory_type"]] = {
                        "total": d["total"],
                        "active": d["active_count"],
                        "avg_strength": round(float(d["avg_strength"] or 0), 2),
                        "avg_importance": round(float(d["avg_importance"] or 0), 2),
                    }
                return stats
        except Exception as e:
            logger.error(f"[记忆存储] 获取记忆统计失败: {e}")
            return {}


# 全局单例
_memory_store_instance: Optional[MemoryStore] = None


def get_memory_store() -> MemoryStore:
    global _memory_store_instance
    if _memory_store_instance is None:
        _memory_store_instance = MemoryStore()
    return _memory_store_instance
