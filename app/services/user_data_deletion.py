"""Transactional deletion of data owned by one user."""

from __future__ import annotations

from typing import Dict

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.models import (
    ChatMessage,
    ChatSession,
    ErrorItem,
    ErrorReviewEvent,
    ExamPaper,
    ExamSubmission,
    LearningRecord,
    Memory,
    MemoryAccessLog,
    MemoryTag,
    UserProfile,
    UserKnowledgeState,
    ReviewSchedule,
)


async def delete_user_data(session: AsyncSession, user_id: str) -> Dict[str, int]:
    """Delete all learning data for a user while retaining the account."""
    memory_ids = select(Memory.id).where(Memory.user_id == user_id)
    session_ids = select(ChatSession.id).where(ChatSession.user_id == user_id)
    paper_ids = select(ExamPaper.id).where(ExamPaper.user_id == user_id)

    statements = (
        (
            "memory_access_logs",
            delete(MemoryAccessLog).where(
                (MemoryAccessLog.user_id == user_id)
                | MemoryAccessLog.memory_id.in_(memory_ids)
            ),
        ),
        ("memory_tags", delete(MemoryTag).where(MemoryTag.memory_id.in_(memory_ids))),
        ("memories", delete(Memory).where(Memory.user_id == user_id)),
        ("user_profiles", delete(UserProfile).where(UserProfile.user_id == user_id)),
        (
            "chat_messages",
            delete(ChatMessage).where(ChatMessage.session_id.in_(session_ids)),
        ),
        ("chat_sessions", delete(ChatSession).where(ChatSession.user_id == user_id)),
        (
            "exam_submissions",
            delete(ExamSubmission).where(ExamSubmission.paper_id.in_(paper_ids)),
        ),
        ("exam_papers", delete(ExamPaper).where(ExamPaper.user_id == user_id)),
        ("error_review_events", delete(ErrorReviewEvent).where(ErrorReviewEvent.user_id == user_id)),
        ("error_items", delete(ErrorItem).where(ErrorItem.user_id == user_id)),
        ("review_schedules", delete(ReviewSchedule).where(ReviewSchedule.user_id == user_id)),
        ("user_knowledge_states", delete(UserKnowledgeState).where(UserKnowledgeState.user_id == user_id)),
        (
            "learning_records",
            delete(LearningRecord).where(LearningRecord.user_id == user_id),
        ),
    )

    counts: Dict[str, int] = {}
    for name, statement in statements:
        result = await session.execute(statement)
        counts[name] = max(result.rowcount or 0, 0)
    return counts
