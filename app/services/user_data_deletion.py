"""Transactional deletion of data owned by one user."""

from __future__ import annotations

from typing import Any, Dict
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.models import (
    ChatMessage,
    ChatSession,
    ErrorItem,
    ErrorReviewEvent,
    LearningRecord,
    Memory,
    MemoryAccessLog,
    MemoryEvidence,
    MemoryTag,
    ProfileEvidence,
    UserProfile,
    UserKnowledgeState,
    ReviewSchedule,
    VariantGeneration,
    AsyncTask, AnimationArtifact, AnimationJob, SourceDocument, ImportBatch,
    NoteAsset, NoteRevision, StudentPaper, PracticeSession, PracticeAttempt,
    EventIdempotency, OutboxEvent,
    LearningGoal,
    LearningPlan, LearningPlanTask,
    LearningAutomationPreference, ProactiveLearningAction,
    AIInteractionRun,
    RefreshToken, ReviewScheduleAction, LearningActivitySession, LegacyClientImport,
    AssessmentBlueprint, PracticeSessionDraftAnswer, PracticeDiagnosticEvent,
    SubjectiveEvaluation, MasteryCorrectionEvent, StudyNote, NotePage, NoteRevision,
    NoteAsset, NoteCleanupTask, NoteAiRun, NoteKnowledgeLink, StudentPaperQuestion,
)


@dataclass
class DeletionPreview:
    user_id: str
    counts: Dict[str, int]
    file_keys: list[str]
    redis_scope: str
    qdrant_scope: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


async def preview_user_deletion(session: AsyncSession, user_id: str) -> DeletionPreview:
    """Build an owner-scoped manifest without mutating SQL or external stores."""
    if not user_id:
        raise ValueError("user_id is required")
    counts: Dict[str, int] = {}
    queries = {
        "memories": select(Memory.id).where(Memory.user_id == user_id),
        "source_documents": select(SourceDocument.id).where(SourceDocument.created_by == user_id),
        "animation_jobs": select(AnimationJob.id).where(AnimationJob.user_id == user_id),
        "animation_artifacts": select(AnimationArtifact.id).where(AnimationArtifact.user_id == user_id),
        "notes_assets": select(NoteAsset.id).where(NoteAsset.user_id == user_id),
        "note_revisions": select(NoteRevision.id).where(NoteRevision.user_id == user_id),
        "student_papers": select(StudentPaper.id).where(StudentPaper.user_id == user_id),
        "practice_sessions": select(PracticeSession.id).where(PracticeSession.user_id == user_id),
        "practice_attempts": select(PracticeAttempt.id).where(PracticeAttempt.user_id == user_id),
        "outbox_events": select(OutboxEvent.id).where(OutboxEvent.user_id == user_id),
        "learning_goals": select(LearningGoal.id).where(LearningGoal.user_id == user_id),
        "learning_plans": select(LearningPlan.id).where(LearningPlan.user_id == user_id),
        "learning_plan_tasks": select(LearningPlanTask.id).where(LearningPlanTask.user_id == user_id),
        "proactive_learning_actions": select(ProactiveLearningAction.id).where(ProactiveLearningAction.user_id == user_id),
        "ai_interaction_runs": select(AIInteractionRun.id).where(AIInteractionRun.user_id == user_id),
        "refresh_tokens": select(RefreshToken.id).where(RefreshToken.user_id == user_id),
        "review_schedule_actions": select(ReviewScheduleAction.id).where(ReviewScheduleAction.user_id == user_id),
        "learning_activity_sessions": select(LearningActivitySession.id).where(LearningActivitySession.user_id == user_id),
        "legacy_client_imports": select(LegacyClientImport.id).where(LegacyClientImport.user_id == user_id),
        "assessment_blueprints": select(AssessmentBlueprint.id).where(AssessmentBlueprint.user_id == user_id),
        "practice_draft_answers": select(PracticeSessionDraftAnswer.id).where(PracticeSessionDraftAnswer.user_id == user_id),
        "practice_diagnostic_events": select(PracticeDiagnosticEvent.id).where(PracticeDiagnosticEvent.user_id == user_id),
        "subjective_evaluations": select(SubjectiveEvaluation.id).where(SubjectiveEvaluation.user_id == user_id),
        "mastery_correction_events": select(MasteryCorrectionEvent.id).where(MasteryCorrectionEvent.user_id == user_id),
        "study_notes": select(StudyNote.id).where(StudyNote.user_id == user_id),
        "note_pages": select(NotePage.id).where(NotePage.user_id == user_id),
        "note_revisions": select(NoteRevision.id).where(NoteRevision.user_id == user_id),
        "note_assets": select(NoteAsset.id).where(NoteAsset.user_id == user_id),
        "note_cleanup_tasks": select(NoteCleanupTask.id).where(NoteCleanupTask.user_id == user_id),
        "note_ai_runs": select(NoteAiRun.id).where(NoteAiRun.user_id == user_id),
        "note_knowledge_links": select(NoteKnowledgeLink.id).where(NoteKnowledgeLink.user_id == user_id),
        "student_paper_questions": select(StudentPaperQuestion.id).where(StudentPaperQuestion.paper_id.in_(select(StudentPaper.id).where(StudentPaper.user_id == user_id))),
    }
    for name, query in queries.items():
        counts[name] = len(list((await session.scalars(query)).all()))
    keys = list((await session.scalars(select(NoteAsset.storage_key).where(NoteAsset.user_id == user_id))).all())
    keys += list((await session.scalars(select(NoteRevision.stroke_storage_key).where(NoteRevision.user_id == user_id))).all())
    keys += list((await session.scalars(select(AnimationArtifact.storage_key).where(AnimationArtifact.user_id == user_id))).all())
    keys += list((await session.scalars(select(SourceDocument.storage_key).where(SourceDocument.created_by == user_id))).all())
    return DeletionPreview(user_id, counts, sorted(set(keys)), f"user:{user_id}:*", f"memory user_id={user_id}")


async def request_user_deletion(session: AsyncSession, *, user_id: str, requested_by: str, confirmation: str) -> dict[str, Any]:
    """Create an auditable, retryable deletion task. This does not delete data."""
    if confirmation != "DELETE_USER_DATA":
        raise PermissionError("explicit deletion confirmation required")
    preview = await preview_user_deletion(session, user_id)
    task = AsyncTask(id=str(uuid.uuid4()), task_type="user_data_deletion", resource_type="user", resource_id=user_id,
                     user_id=user_id, status="pending", max_attempts=5, idempotency_key=f"user-data-delete:{user_id}",
                     payload={"requested_by": requested_by, "preview": preview.as_dict(), "confirmation": confirmation},
                     queued_at=datetime.now(timezone.utc))
    existing = await session.scalar(select(AsyncTask).where(AsyncTask.task_type == task.task_type, AsyncTask.idempotency_key == task.idempotency_key))
    if existing:
        return {"task_id": existing.id, "status": existing.status, "preview": existing.payload.get("preview", {})}
    session.add(task)
    await session.flush()
    return {"task_id": task.id, "status": task.status, "preview": preview.as_dict()}


async def execute_user_deletion(task_id: str, *, retry: bool = False) -> dict[str, Any]:
    """Execute one task; external failures remain retryable and visible."""
    async with get_db_session() as db:
        task = await db.get(AsyncTask, task_id)
        if task is None or task.task_type != "user_data_deletion": raise LookupError("deletion task not found")
        if task.status in {"succeeded", "permanently_failed"} and not retry: return task.result or {"status": task.status}
        task.status, task.attempts = "running", int(task.attempts or 0) + 1
        user_id = task.resource_id
        preview = await preview_user_deletion(db, user_id)
    failures: dict[str, str] = {}
    # SQL facts are removed in one transaction before external cleanup.
    try:
        async with get_db_session() as db:
            await delete_user_data(db, user_id)
            # Source documents can be referenced by provenance rows with RESTRICT
            # FKs. Retain the audit metadata while marking the uploaded binary
            # deleted; this keeps SQL provenance consistent with file cleanup.
            source_docs = list((await db.scalars(select(SourceDocument).where(SourceDocument.created_by == user_id))).all())
            for document in source_docs:
                document.status = "deleted"
            for model, column, name in ((AnimationArtifact, AnimationArtifact.user_id, "animation_artifacts"), (AnimationJob, AnimationJob.user_id, "animation_jobs"), (StudentPaper, StudentPaper.user_id, "student_papers"), (PracticeAttempt, PracticeAttempt.user_id, "practice_attempts"), (PracticeSession, PracticeSession.user_id, "practice_sessions"), (OutboxEvent, OutboxEvent.user_id, "outbox_events")):
                await db.execute(delete(model).where(column == user_id))
    except Exception as exc:
        failures["sql"] = str(exc)[:500]
    if not failures:
        try:
            from app.services.memory_store import get_memory_store
            if not await get_memory_store().delete_user_vectors(user_id): failures["qdrant"] = "memory vector deletion failed"
        except Exception as exc: failures["qdrant"] = str(exc)[:500]
        try:
            from app.services.cache import get_cache_manager
            await get_cache_manager().invalidate_user(user_id)
        except Exception as exc: failures["redis"] = str(exc)[:500]
        for key in preview.file_keys:
            try:
                if key.startswith("artifacts/"):
                    from app.services.animation_storage import resolve_storage_key
                elif key.startswith("revisions/") or key.startswith("assets/"):
                    from app.services.note_storage import resolve_storage_key
                else:
                    from app.services.content_import import ContentImportService
                    path = ContentImportService()._resolve_storage_path(key)
                    path.unlink(missing_ok=True); continue
                resolve_storage_key(key).unlink(missing_ok=True)
            except Exception as exc: failures[f"file:{key}"] = str(exc)[:300]
    result = {"status": "retryable_failed" if failures else "succeeded", "user_id": user_id, "attempts": task.attempts, "preview": preview.as_dict(), "failures": failures}
    async with get_db_session() as db:
        row = await db.get(AsyncTask, task_id)
        row.result = result; row.last_error = "; ".join(failures.values())[:2000] if failures else None
        row.status = "retryable_failed" if failures and row.attempts < (row.max_attempts or 5) else ("permanently_failed" if failures else "succeeded")
        row.succeeded_at = datetime.now(timezone.utc) if row.status == "succeeded" else None
        row.failed_at = datetime.now(timezone.utc) if row.status != "succeeded" else None
    return result


async def delete_user_data(session: AsyncSession, user_id: str) -> Dict[str, int]:
    """Delete all learning data for a user while retaining the account."""
    memory_ids = select(Memory.id).where(Memory.user_id == user_id)
    session_ids = select(ChatSession.id).where(ChatSession.user_id == user_id)

    statements = (
        ("variant_generations", delete(VariantGeneration).where(VariantGeneration.user_id == user_id)),
        ("profile_evidence", delete(ProfileEvidence).where(ProfileEvidence.user_id == user_id)),
        ("memory_evidence", delete(MemoryEvidence).where(MemoryEvidence.user_id == user_id)),
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
        ("learning_goals", delete(LearningGoal).where(LearningGoal.user_id == user_id)),
        ("learning_plan_tasks", delete(LearningPlanTask).where(LearningPlanTask.user_id == user_id)),
        ("learning_plans", delete(LearningPlan).where(LearningPlan.user_id == user_id)),
        ("proactive_learning_actions", delete(ProactiveLearningAction).where(ProactiveLearningAction.user_id == user_id)),
        ("learning_automation_preferences", delete(LearningAutomationPreference).where(LearningAutomationPreference.user_id == user_id)),
        ("ai_interaction_runs", delete(AIInteractionRun).where(AIInteractionRun.user_id == user_id)),
        ("refresh_tokens", delete(RefreshToken).where(RefreshToken.user_id == user_id)),
        ("review_schedule_actions", delete(ReviewScheduleAction).where(ReviewScheduleAction.user_id == user_id)),
        ("learning_activity_sessions", delete(LearningActivitySession).where(LearningActivitySession.user_id == user_id)),
        ("legacy_client_imports", delete(LegacyClientImport).where(LegacyClientImport.user_id == user_id)),
        ("practice_diagnostic_events", delete(PracticeDiagnosticEvent).where(PracticeDiagnosticEvent.user_id == user_id)),
        ("subjective_evaluations", delete(SubjectiveEvaluation).where(SubjectiveEvaluation.user_id == user_id)),
        ("mastery_correction_events", delete(MasteryCorrectionEvent).where(MasteryCorrectionEvent.user_id == user_id)),
        ("practice_session_draft_answers", delete(PracticeSessionDraftAnswer).where(PracticeSessionDraftAnswer.user_id == user_id)),
        ("assessment_blueprints", delete(AssessmentBlueprint).where(AssessmentBlueprint.user_id == user_id)),
        ("practice_attempts", delete(PracticeAttempt).where(PracticeAttempt.user_id == user_id)),
        ("student_paper_questions", delete(StudentPaperQuestion).where(StudentPaperQuestion.paper_id.in_(select(StudentPaper.id).where(StudentPaper.user_id == user_id)))),
        ("practice_sessions", delete(PracticeSession).where(PracticeSession.user_id == user_id)),
        ("student_papers", delete(StudentPaper).where(StudentPaper.user_id == user_id)),
        ("note_knowledge_links", delete(NoteKnowledgeLink).where(NoteKnowledgeLink.user_id == user_id)),
        ("note_ai_runs", delete(NoteAiRun).where(NoteAiRun.user_id == user_id)),
        ("note_revisions", delete(NoteRevision).where(NoteRevision.user_id == user_id)),
        ("note_assets", delete(NoteAsset).where(NoteAsset.user_id == user_id)),
        ("note_pages", delete(NotePage).where(NotePage.user_id == user_id)),
        ("study_notes", delete(StudyNote).where(StudyNote.user_id == user_id)),
        (
            "chat_messages",
            delete(ChatMessage).where(ChatMessage.session_id.in_(session_ids)),
        ),
        ("chat_sessions", delete(ChatSession).where(ChatSession.user_id == user_id)),
        ("error_review_events", delete(ErrorReviewEvent).where(ErrorReviewEvent.user_id == user_id)),
        ("error_items", delete(ErrorItem).where(ErrorItem.user_id == user_id)),
        ("review_schedules", delete(ReviewSchedule).where(ReviewSchedule.user_id == user_id)),
        ("user_knowledge_states", delete(UserKnowledgeState).where(UserKnowledgeState.user_id == user_id)),
        (
            "learning_records",
            delete(LearningRecord).where(LearningRecord.user_id == user_id),
        ),
    )

    from app.services.note_cleanup import queue_user_note_purge

    counts: Dict[str, int] = {}
    counts["note_storage_objects"] = await queue_user_note_purge(session, user_id)
    for name, statement in statements:
        result = await session.execute(statement)
        counts[name] = max(result.rowcount or 0, 0)
    return counts
