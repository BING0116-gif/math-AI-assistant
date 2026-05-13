from typing import TypeVar, Generic, List, Optional, Dict, Any, Sequence
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update, delete, and_, or_
from sqlalchemy.orm import DeclarativeBase

from app.data.models import (
    User,
    LearningRecord,
    Question,
    ChatSession,
    ChatMessage,
    ExamPaper,
    ExamSubmission,
)

T = TypeVar("T", bound=DeclarativeBase)


class BaseRepository(Generic[T]):
    def __init__(self, session: AsyncSession, model: type[T]):
        self.session = session
        self.model = model

    async def create(self, **kwargs) -> T:
        instance = self.model(**kwargs)
        self.session.add(instance)
        await self.session.flush()
        return instance

    async def get_by_id(self, id_value) -> Optional[T]:
        stmt = select(self.model).where(self.model.id == id_value)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all(
        self, offset: int = 0, limit: int = 100, order_by: str = "created_at"
    ) -> List[T]:
        order_col = getattr(self.model, order_by, self.model.created_at)
        stmt = (
            select(self.model)
            .order_by(order_col.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update(self, id_value, **kwargs) -> Optional[T]:
        instance = await self.get_by_id(id_value)
        if instance is None:
            return None
        for key, value in kwargs.items():
            if hasattr(instance, key) and value is not None:
                setattr(instance, key, value)
        await self.session.flush()
        return instance

    async def delete(self, id_value) -> bool:
        instance = await self.get_by_id(id_value)
        if instance is None:
            return False
        await self.session.delete(instance)
        await self.session.flush()
        return True

    async def count(self, **filters) -> int:
        stmt = select(func.count()).select_from(self.model)
        if filters:
            conditions = [
                getattr(self.model, k) == v for k, v in filters.items()
            ]
            stmt = stmt.where(and_(*conditions))
        result = await self.session.execute(stmt)
        return result.scalar() or 0

    async def exists(self, id_value) -> bool:
        stmt = select(self.model.id).where(self.model.id == id_value)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def bulk_create(self, items: List[Dict[str, Any]]) -> List[T]:
        instances = [self.model(**item) for item in items]
        self.session.add_all(instances)
        await self.session.flush()
        return instances


class UserRepository(BaseRepository[User]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, User)

    async def get_by_username(self, username: str) -> Optional[User]:
        stmt = select(User).where(User.username == username)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> Optional[User]:
        stmt = select(User).where(User.email == email)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_active_users(
        self, offset: int = 0, limit: int = 100
    ) -> List[User]:
        stmt = (
            select(User)
            .where(User.is_active == True)
            .order_by(User.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def increment_failed_login(self, user_id: str) -> None:
        stmt = (
            update(User)
            .where(User.id == user_id)
            .values(failed_login_count=User.failed_login_count + 1)
        )
        await self.session.execute(stmt)
        await self.session.flush()

    async def reset_failed_login(self, user_id: str) -> None:
        stmt = (
            update(User)
            .where(User.id == user_id)
            .values(failed_login_count=0, locked_until=None)
        )
        await self.session.execute(stmt)
        await self.session.flush()

    async def get_user_stats(self, user_id: str) -> Dict[str, Any]:
        from sqlalchemy import case

        stmt = select(
            func.count().label("total"),
            func.sum(
                case((LearningRecord.is_correct == True, 1), else_=0)
            ).label("correct"),
            func.avg(LearningRecord.time_spent).label("avg_time"),
            func.count(func.distinct(LearningRecord.category)).label(
                "categories_count"
            ),
        ).where(LearningRecord.user_id == user_id)

        result = await self.session.execute(stmt)
        row = result.one()

        total = row.total or 0
        correct = row.correct or 0

        return {
            "total": total,
            "correct": correct,
            "correct_rate": correct / max(total, 1),
            "avg_time": round(row.avg_time or 0, 1),
            "unique_categories": row.categories_count or 0,
        }


class LearningRecordRepository(BaseRepository[LearningRecord]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, LearningRecord)

    async def get_by_user(
        self,
        user_id: str,
        category: Optional[str] = None,
        event_type: Optional[str] = None,
        is_correct: Optional[bool] = None,
        offset: int = 0,
        limit: int = 50,
    ) -> List[LearningRecord]:
        conditions = [LearningRecord.user_id == user_id]

        if category:
            conditions.append(LearningRecord.category == category)
        if event_type:
            conditions.append(LearningRecord.event_type == event_type)
        if is_correct is not None:
            conditions.append(LearningRecord.is_correct == is_correct)

        stmt = (
            select(LearningRecord)
            .where(and_(*conditions))
            .order_by(LearningRecord.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_user_category_stats(
        self, user_id: str, category: str
    ) -> Dict[str, Any]:
        stmt = select(
            func.count().label("total"),
            func.sum(
                func.cast(LearningRecord.is_correct == True, type_=type(0))
            ).label("correct"),
            func.avg(LearningRecord.time_spent).label("avg_time"),
            func.avg(LearningRecord.difficulty).label("avg_difficulty"),
        ).where(
            and_(
                LearningRecord.user_id == user_id,
                LearningRecord.category == category,
            )
        )

        result = await self.session.execute(stmt)
        row = result.one()

        total = row.total or 0
        correct = row.correct or 0

        return {
            "category": category,
            "total": total,
            "correct": correct,
            "correct_rate": correct / max(total, 1),
            "avg_time": round(row.avg_time or 0, 1),
            "avg_difficulty": round(row.avg_difficulty or 0, 1),
        }

    async def get_errors_by_user(
        self, user_id: str, limit: int = 50
    ) -> List[LearningRecord]:
        stmt = (
            select(LearningRecord)
            .where(
                and_(
                    LearningRecord.user_id == user_id,
                    LearningRecord.is_correct == False,
                )
            )
            .order_by(LearningRecord.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_recent_records(
        self, user_id: str, days: int = 30, limit: int = 100
    ) -> List[LearningRecord]:
        from datetime import datetime, timedelta, timezone

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        stmt = (
            select(LearningRecord)
            .where(
                and_(
                    LearningRecord.user_id == user_id,
                    LearningRecord.created_at >= cutoff,
                )
            )
            .order_by(LearningRecord.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class QuestionRepository(BaseRepository[Question]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, Question)

    async def get_by_category(
        self,
        category: str,
        difficulty: Optional[int] = None,
        offset: int = 0,
        limit: int = 50,
    ) -> List[Question]:
        conditions = [
            Question.category == category,
            Question.is_active == True,
        ]
        if difficulty:
            conditions.append(Question.difficulty == difficulty)

        stmt = (
            select(Question)
            .where(and_(*conditions))
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def search_questions(
        self,
        query: str,
        category: Optional[str] = None,
        difficulty: Optional[int] = None,
        limit: int = 20,
    ) -> List[Question]:
        conditions = [Question.is_active == True]

        if query:
            conditions.append(Question.content.ilike(f"%{query}%"))
        if category:
            conditions.append(Question.category == category)
        if difficulty:
            conditions.append(Question.difficulty == difficulty)

        stmt = (
            select(Question)
            .where(and_(*conditions))
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update_usage_stats(
        self,
        question_id: str,
        is_correct: bool,
        time_spent: Optional[int] = None,
    ) -> None:
        instance = await self.get_by_id(question_id)
        if instance is None:
            return

        instance.usage_count = (instance.usage_count or 0) + 1

        if is_correct is not None:
            current_rate = instance.correct_rate or 0.0
            current_count = instance.usage_count - 1
            new_rate = (
                (current_rate * current_count + (1.0 if is_correct else 0.0))
                / instance.usage_count
            )
            instance.correct_rate = new_rate

        if time_spent is not None:
            current_avg = instance.avg_time_spent or 0.0
            current_count = instance.usage_count - 1
            instance.avg_time_spent = (
                (current_avg * current_count + time_spent) / instance.usage_count
            )

        await self.session.flush()


class ChatSessionRepository(BaseRepository[ChatSession]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, ChatSession)

    async def get_by_user(
        self, user_id: str, status: Optional[str] = None, limit: int = 50
    ) -> List[ChatSession]:
        conditions = [ChatSession.user_id == user_id]
        if status:
            conditions.append(ChatSession.status == status)

        stmt = (
            select(ChatSession)
            .where(and_(*conditions))
            .order_by(ChatSession.updated_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def increment_message_count(self, session_id: str) -> None:
        stmt = (
            update(ChatSession)
            .where(ChatSession.id == session_id)
            .values(
                message_count=ChatSession.message_count + 1,
                updated_at=func.now(),
            )
        )
        await self.session.execute(stmt)
        await self.session.flush()


class ChatMessageRepository(BaseRepository[ChatMessage]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, ChatMessage)

    async def get_by_session(
        self,
        session_id: str,
        offset: int = 0,
        limit: int = 100,
    ) -> List[ChatMessage]:
        stmt = (
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.asc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def search_messages(
        self, user_id: str, query: str, limit: int = 20
    ) -> List[ChatMessage]:
        stmt = (
            select(ChatMessage)
            .join(ChatSession)
            .where(
                and_(
                    ChatSession.user_id == user_id,
                    ChatMessage.content.ilike(f"%{query}%"),
                )
            )
            .order_by(ChatMessage.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class ExamPaperRepository(BaseRepository[ExamPaper]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, ExamPaper)

    async def get_by_user(
        self, user_id: str, status: Optional[str] = None, limit: int = 20
    ) -> List[ExamPaper]:
        conditions = [ExamPaper.user_id == user_id]
        if status:
            conditions.append(ExamPaper.status == status)

        stmt = (
            select(ExamPaper)
            .where(and_(*conditions))
            .order_by(ExamPaper.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class ExamSubmissionRepository(BaseRepository[ExamSubmission]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, ExamSubmission)

    async def get_by_paper(
        self, paper_id: str
    ) -> List[ExamSubmission]:
        stmt = (
            select(ExamSubmission)
            .where(ExamSubmission.paper_id == paper_id)
            .order_by(ExamSubmission.id.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())