"""
记忆存储层 — MySQL + Qdrant 数据操作。

提供 4 类记忆（错题、对话、里程碑、画像）的写入、查询、更新、归档操作。
支持异步写入、状态流转、Qdrant 向量同步。
"""

import asyncio
import json
import logging
import math
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.config.settings import settings
from app.data.database import get_db_session

logger = logging.getLogger(__name__)

# 记忆类型常量
MEMORY_TYPE_ERROR = "error"
MEMORY_TYPE_CONVERSATION = "conversation"
MEMORY_TYPE_MILESTONE = "milestone"
MEMORY_TYPE_PROFILE = "profile"

# 记忆状态常量
STATUS_PENDING = "pending"
STATUS_ACTIVE = "active"
STATUS_ARCHIVED = "archived"
STATUS_DELETED = "deleted"

# 初始强度配置
MEMORY_INIT_STRENGTH = {
    MEMORY_TYPE_ERROR: 0.70,
    MEMORY_TYPE_CONVERSATION: 0.60,
    MEMORY_TYPE_MILESTONE: 0.85,
    MEMORY_TYPE_PROFILE: 1.0,
}

# 有效期配置（秒）
MEMORY_TTL = {
    MEMORY_TYPE_ERROR: 2 * 365 * 86400,       # 2 年
    MEMORY_TYPE_CONVERSATION: 180 * 86400,     # 6 个月
    MEMORY_TYPE_MILESTONE: 100 * 365 * 86400,  # 永久（100年）
    MEMORY_TYPE_PROFILE: 30 * 86400,           # 30 天
}

# 衰减系数（每日）
DECAY_LAMBDA = {
    MEMORY_TYPE_ERROR: 0.0045,
    MEMORY_TYPE_CONVERSATION: 0.0045,
    MEMORY_TYPE_MILESTONE: 0.0015,
    MEMORY_TYPE_PROFILE: 0.0,  # 不参与日常衰减
}


class MemoryStore:
    """记忆存储层，封装 MySQL + Qdrant 操作。"""

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
            host = settings.QDRANT_HOST if hasattr(settings, 'QDRANT_HOST') else "localhost"
            port = settings.QDRANT_PORT if hasattr(settings, 'QDRANT_PORT') else 6333
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
                        size=settings.MEMORY_QDRANT_VECTOR_SIZE,
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
        if self._embedder is not None:
            try:
                return self._embedder.encode(text).tolist()
            except Exception as e:
                logger.error(f"[记忆存储] Embedding 生成失败: {e}")

        # 降级：使用简单哈希向量
        import hashlib
        vector_size = settings.MEMORY_QDRANT_VECTOR_SIZE
        hash_bytes = hashlib.md5(text.encode()).digest()
        seed = int.from_bytes(hash_bytes, 'big')
        rng = __import__('random').Random(seed)
        return [rng.random() for _ in range(vector_size)]

    async def _generate_embedding_summary(
        self, content: str, memory_type: str, metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """生成 embedding_summary 摘要文本。

        优先模板拼接，可选调用 LLM 精炼。
        """
        if memory_type == MEMORY_TYPE_ERROR:
            return f"错题: {content[:150]}"
        elif memory_type == MEMORY_TYPE_CONVERSATION:
            return f"对话: {content[:120]}"
        elif memory_type == MEMORY_TYPE_MILESTONE:
            return f"里程碑: {content[:80]}"
        elif memory_type == MEMORY_TYPE_PROFILE:
            return f"画像: {content[:50]}"
        return content[:150]

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
    ) -> Optional[int]:
        """创建错题记忆。

        1. 写入 MySQL（status=pending）
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
                         last_accessed, access_count)
                        VALUES
                        (:user_id, :memory_type, :high_category, :category, :content,
                         :embedding_summary, :importance, :difficulty, :status,
                         :expire_at, :memory_strength, :source_id, :created_at,
                         :last_accessed, :access_count)
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
                    memory_id=memory_id,
                    user_id=user_id,
                    memory_type=MEMORY_TYPE_ERROR,
                    high_category=high_category,
                    category=category,
                    summary=summary,
                    importance=0.7,
                    difficulty=difficulty,
                    tags=knowledge_points or [],
                    status=STATUS_ACTIVE,
                    expire_at=expire_at,
                )

                # 更新状态为 active
                await db.execute(
                    sa_text("""
                        UPDATE memories SET status = :status
                        WHERE id = :id
                    """),
                    {"status": STATUS_ACTIVE, "id": memory_id},
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
                         expire_at, memory_strength, created_at, last_accessed)
                        VALUES
                        (:user_id, :memory_type, :high_category, :category, :content,
                         :embedding_summary, :importance, :status,
                         :expire_at, :memory_strength, :created_at, :last_accessed)
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
                    memory_id=memory_id,
                    user_id=user_id,
                    memory_type=MEMORY_TYPE_CONVERSATION,
                    high_category=high_category,
                    category=category,
                    summary=summary,
                    importance=importance,
                    tags=tags or [],
                    status=STATUS_ACTIVE,
                    expire_at=expire_at,
                )

                await db.execute(
                    sa_text("UPDATE memories SET status = :status WHERE id = :id"),
                    {"status": STATUS_ACTIVE, "id": memory_id},
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
                         expire_at, memory_strength, created_at, last_accessed)
                        VALUES
                        (:user_id, :memory_type, :high_category, :category, :content,
                         :embedding_summary, :importance, :status,
                         :expire_at, :memory_strength, :created_at, :last_accessed)
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
                    }
                )
                memory_id = result.lastrowid or 0

                await self._sync_to_qdrant(
                    memory_id=memory_id,
                    user_id=user_id,
                    memory_type=MEMORY_TYPE_MILESTONE,
                    high_category=high_category,
                    category=category,
                    summary=description[:80],
                    importance=0.85,
                    tags=[milestone_type],
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
                         expire_at, memory_strength, created_at, last_accessed)
                        VALUES
                        (:user_id, :memory_type, :high_category, :category, :content,
                         :embedding_summary, :importance, :status,
                         :expire_at, :memory_strength, :created_at, :last_accessed)
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
                    }
                )
                memory_id = result.lastrowid or 0

                await self._sync_to_qdrant(
                    memory_id=memory_id,
                    user_id=user_id,
                    memory_type=MEMORY_TYPE_PROFILE,
                    high_category=high_category,
                    category=category,
                    summary=summary_text,
                    importance=1.0,
                    tags=["profile"],
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
        memory_id: int,
        user_id: str,
        memory_type: str,
        high_category: str,
        category: str,
        summary: str,
        importance: float,
        difficulty: Optional[int] = None,
        tags: Optional[List[str]] = None,
        status: str = STATUS_ACTIVE,
        expire_at: Optional[int] = None,
    ):
        """同步记忆到 Qdrant。"""
        if not self._QDRANT_AVAILABLE:
            return

        try:
            client = await self._get_qdrant_client()
            if client is None:
                return

            from qdrant_client.models import PointStruct

            vector = self._generate_embedding(summary)
            now = int(time.time())

            payload = {
                "memory_id": memory_id,
                "user_id": user_id,
                "memory_type": memory_type,
                "high_category": high_category,
                "category": category,
                "importance": importance,
                "status": status,
                "created_at": now,
                "last_accessed": now,
                "access_count": 0,
                "memory_strength": MEMORY_INIT_STRENGTH.get(memory_type, 0.5),
                "source_id": "",
            }

            if difficulty is not None:
                payload["difficulty"] = difficulty
            if expire_at is not None:
                payload["expire_at"] = expire_at
            if tags:
                payload["tags"] = json.dumps(tags, ensure_ascii=False)

            point = PointStruct(
                id=memory_id,
                vector=vector,
                payload=payload,
            )

            client.upsert(
                collection_name=settings.MEMORY_QDRANT_COLLECTION,
                points=[point],
            )

        except Exception as e:
            logger.warning(f"[记忆存储] Qdrant 同步失败: memory_id={memory_id}, error={e}")

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
        return await self.get_user_memories(
            user_id=user_id,
            memory_type=memory_type,
            status=STATUS_ACTIVE,
            limit=1000,
        )

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

                await db.execute(
                    sa_text("""
                        UPDATE memories
                        SET memory_strength = :strength, last_accessed = :now
                        WHERE id = :id
                    """),
                    {"strength": strength, "now": int(time.time()), "id": memory_id},
                )
                return True
        except Exception as e:
            logger.error(f"[记忆存储] 更新记忆强度失败: {e}")
            return False

    async def update_memory_access(
        self, memory_id: int, strength_increment: float = 0.06
    ) -> bool:
        """更新记忆访问（命中后强化）。"""
        try:
            async with get_db_session() as db:
                from sqlalchemy import text as sa_text

                now = int(time.time())
                await db.execute(
                    sa_text("""
                        UPDATE memories
                        SET memory_strength = LEAST(memory_strength + :inc, 1.0),
                            access_count = access_count + 1,
                            last_accessed = :now
                        WHERE id = :id AND status = 'active'
                    """),
                    {"inc": strength_increment, "now": now, "id": memory_id},
                )
                return True
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

                await db.execute(
                    sa_text("""
                        UPDATE memories
                        SET content = :content, embedding_summary = :summary
                        WHERE id = :id
                    """),
                    {"content": content, "summary": summary, "id": memory_id},
                )
                return True
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

                await db.execute(
                    sa_text("""
                        UPDATE memories
                        SET status = :status
                        WHERE id = :id AND status = 'active'
                    """),
                    {"status": STATUS_ARCHIVED, "id": memory_id},
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
                await db.execute(
                    sa_text("""
                        UPDATE memories
                        SET status = :status, deleted_at = :now
                        WHERE id = :id
                    """),
                    {"status": STATUS_DELETED, "now": now, "id": memory_id},
                )
                return True
        except Exception as e:
            logger.error(f"[记忆存储] 软删除记忆失败: {e}")
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
                from sqlalchemy import text as sa_text

                result = await db.execute(
                    sa_text("""
                        UPDATE memories
                        SET status = :status
                        WHERE source_id = :source_id AND status = 'active'
                    """),
                    {"status": STATUS_ARCHIVED, "source_id": source_id},
                )
                return result.rowcount
        except Exception as e:
            logger.error(f"[记忆存储] 归档 source_id 关联记忆失败: {e}")
            return 0

    async def batch_archive_expired(self) -> int:
        """批量归档过期记忆（expire_at < now）。"""
        try:
            async with get_db_session() as db:
                from sqlalchemy import text as sa_text

                now = int(time.time())
                result = await db.execute(
                    sa_text("""
                        UPDATE memories
                        SET status = :status
                        WHERE status = 'active' AND expire_at < :now
                    """),
                    {"status": STATUS_ARCHIVED, "now": now},
                )
                count = result.rowcount
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
                from sqlalchemy import text as sa_text

                result = await db.execute(
                    sa_text("""
                        UPDATE memories
                        SET status = :status
                        WHERE status = 'active' AND memory_strength < :threshold
                    """),
                    {"status": STATUS_ARCHIVED, "threshold": threshold},
                )
                count = result.rowcount
                if count > 0:
                    logger.info(f"[记忆存储] 批量归档低强度记忆: {count} 条")
                return count
        except Exception as e:
            logger.error(f"[记忆存储] 批量归档低强度记忆失败: {e}")
            return 0

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
