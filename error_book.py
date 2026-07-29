"""
错题本模块 - 管理数学错题的收集、存储和复习

使用数据库存储，支持用户隔离。
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import List, Dict, Any, Optional

from sqlalchemy import select, delete, update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.database import get_db_session
from app.data.models import ErrorItem as ErrorItemModel


@dataclass
class ErrorItem:
    """错题数据模型（DTO，与数据库模型解耦）"""
    id: str
    question: str
    question_type: str  # "text" | "image"
    image_path: Optional[str] = None
    error_reason: str = ""
    categories: List[str] = None
    original_answer: str = ""
    correct_answer: str = ""
    notes: str = ""
    added_at: str = ""
    mastery_level: int = 3  # 1-5, 默认3
    is_mastered: bool = False

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())[:8]
        if self.categories is None:
            self.categories = []
        if not self.added_at:
            self.added_at = datetime.now().strftime("%Y-%m-%d %H:%M")

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ErrorItem":
        return cls(**data)

    @classmethod
    def from_db_model(cls, model: ErrorItemModel) -> "ErrorItem":
        """从数据库模型创建 DTO"""
        return cls(
            id=model.item_id,
            question=model.question,
            question_type=model.question_type,
            image_path=model.image_path,
            error_reason=model.error_reason or "",
            categories=list(model.categories) if model.categories else [],
            original_answer=model.original_answer or "",
            correct_answer=model.correct_answer or "",
            notes=model.notes or "",
            added_at=model.added_at or "",
            mastery_level=model.mastery_level or 3,
            is_mastered=model.is_mastered or False,
        )


class ErrorBookManager:
    """错题本管理器 - 使用数据库存储，按 user_id 实现用户隔离"""

    def __init__(self):
        pass

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------

    async def _row_to_item(self, row: ErrorItemModel) -> ErrorItem:
        """将数据库行转为 ErrorItem DTO"""
        return ErrorItem.from_db_model(row)

    async def _rows_to_items(self, rows: List[ErrorItemModel]) -> List[ErrorItem]:
        return [await self._row_to_item(r) for r in rows]

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    async def add(self, user_id: str, item: ErrorItem) -> str:
        """添加错题（异步）"""
        if not item.id:
            item.id = str(uuid.uuid4())[:8]

        async with get_db_session() as db:
            db_item = ErrorItemModel(
                user_id=user_id,
                item_id=item.id,
                question=item.question,
                question_type=item.question_type,
                image_path=item.image_path,
                error_reason=item.error_reason,
                categories=item.categories,
                original_answer=item.original_answer,
                correct_answer=item.correct_answer,
                notes=item.notes,
                added_at=item.added_at,
                mastery_level=item.mastery_level,
                is_mastered=item.is_mastered,
            )
            db.add(db_item)
            await db.flush()  # 让数据库生成 id，但不提交（get_db_session 会提交）
        return item.id

    async def remove(self, user_id: str, item_id: str) -> bool:
        """删除错题（异步）"""
        async with get_db_session() as db:
            result = await db.execute(
                delete(ErrorItemModel).where(
                    ErrorItemModel.user_id == user_id,
                    ErrorItemModel.item_id == item_id,
                )
            )
            return result.rowcount > 0

    async def update(self, user_id: str, item_id: str, **kwargs) -> bool:
        """更新错题（异步）"""
        # 过滤掉 None 值，只更新提供的字段
        update_data = {k: v for k, v in kwargs.items() if v is not None}
        if not update_data:
            return False

        async with get_db_session() as db:
            result = await db.execute(
                sa_update(ErrorItemModel)
                .where(
                    ErrorItemModel.user_id == user_id,
                    ErrorItemModel.item_id == item_id,
                )
                .values(**update_data)
            )
            return result.rowcount > 0

    async def get(self, user_id: str, item_id: str) -> Optional[ErrorItem]:
        """获取单个错题"""
        async with get_db_session() as db:
            result = await db.execute(
                select(ErrorItemModel).where(
                    ErrorItemModel.user_id == user_id,
                    ErrorItemModel.item_id == item_id,
                )
            )
            row = result.scalar_one_or_none()
            if row is None:
                return None
            return await self._row_to_item(row)

    async def get_all(self, user_id: str) -> List[ErrorItem]:
        """获取用户的所有错题（按添加时间倒序）"""
        async with get_db_session() as db:
            result = await db.execute(
                select(ErrorItemModel)
                .where(ErrorItemModel.user_id == user_id)
                .order_by(ErrorItemModel.added_at.desc())
            )
            rows = result.scalars().all()
            return await self._rows_to_items(rows)

    async def filter(
        self,
        user_id: str,
        categories: Optional[List[str]] = None,
        search_text: Optional[str] = None,
        mastered: Optional[bool] = None,
        mastery_level: Optional[int] = None,
    ) -> List[ErrorItem]:
        """筛选错题"""
        async with get_db_session() as db:
            query = select(ErrorItemModel).where(
                ErrorItemModel.user_id == user_id
            )

            if categories:
                # SQLite 的 JSON 数组包含判断：用 JSON_EACH 或 LIKE
                # 此处使用一个简单策略：对每个 category 做 LIKE 匹配
                from sqlalchemy import or_
                category_filters = [
                    ErrorItemModel.categories.like(f'%"{cat}"%')
                    for cat in categories
                ]
                query = query.where(or_(*category_filters))

            if search_text:
                search_lower = search_text.lower()
                from sqlalchemy import or_
                text_filters = []
                for col in [ErrorItemModel.question, ErrorItemModel.error_reason, ErrorItemModel.correct_answer]:
                    text_filters.append(col.ilike(f"%{search_lower}%"))
                query = query.where(or_(*text_filters))

            if mastered is not None:
                query = query.where(ErrorItemModel.is_mastered == mastered)

            if mastery_level is not None:
                query = query.where(ErrorItemModel.mastery_level == mastery_level)

            query = query.order_by(ErrorItemModel.added_at.desc())
            result = await db.execute(query)
            rows = result.scalars().all()
            return await self._rows_to_items(rows)

    async def get_all_categories(self, user_id: str) -> List[str]:
        """获取用户已使用的所有分类标签"""
        async with get_db_session() as db:
            result = await db.execute(
                select(ErrorItemModel.categories).where(
                    ErrorItemModel.user_id == user_id
                )
            )
            categories_set: set[str] = set()
            for row in result.scalars().all():
                if row:
                    categories_set.update(row)
            return sorted(categories_set)

    async def get_statistics(self, user_id: str) -> Dict[str, Any]:
        """获取错题统计数据"""
        async with get_db_session() as db:
            result = await db.execute(
                select(ErrorItemModel).where(
                    ErrorItemModel.user_id == user_id
                )
            )
            rows = result.scalars().all()

        total = len(rows)
        mastered_count = sum(1 for r in rows if r.is_mastered)
        not_mastered = total - mastered_count

        categories_count: Dict[str, int] = {}
        for r in rows:
            if r.categories:
                for cat in r.categories:
                    categories_count[cat] = categories_count.get(cat, 0) + 1

        mastery_dist = {i: 0 for i in range(1, 6)}
        for r in rows:
            level = r.mastery_level or 3
            mastery_dist[level] = mastery_dist.get(level, 0) + 1

        return {
            "total": total,
            "mastered": mastered_count,
            "not_mastered": not_mastered,
            "categories_count": categories_count,
            "mastery_distribution": mastery_dist,
        }

    async def export_to_dict(self, user_id: str) -> Dict[str, Any]:
        """导出用户的所有数据为字典"""
        items = await self.get_all(user_id)
        stats = await self.get_statistics(user_id)
        return {
            "items": [item.to_dict() for item in items],
            "exported_at": datetime.now().isoformat(),
            "statistics": stats,
        }