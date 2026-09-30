"""Post-commit note retention cleanup and storage reconciliation."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from sqlalchemy import select

from app.config.settings import settings
from app.data.database import get_db_session
from app.data.models import NoteAsset, NoteCleanupTask, NotePage, NoteRevision, StudyNote
from app.services import note_storage


async def _keys_for_notes(db, note_ids: list[str]) -> list[str]:
    if not note_ids: return []
    revision_keys = list((await db.scalars(select(NoteRevision.stroke_storage_key).join(NotePage).where(NotePage.note_id.in_(note_ids)))).all())
    asset_keys = list((await db.scalars(select(NoteAsset.storage_key).where(NoteAsset.note_id.in_(note_ids)))).all())
    return sorted(set(revision_keys + asset_keys))


async def queue_note_cleanup(db, user_id: str, note_ids: list[str]) -> int:
    keys = await _keys_for_notes(db, note_ids)
    if keys: db.add(NoteCleanupTask(user_id=user_id, storage_keys=keys))
    for note_id in note_ids:
        note = await db.scalar(select(StudyNote).where(StudyNote.id == note_id, StudyNote.user_id == user_id, StudyNote.status == "deleted"))
        if note: await db.delete(note)
    await db.flush()  # SQL deletion is confirmed before any worker can see its task.
    return len(keys)


async def queue_user_note_purge(db, user_id: str) -> int:
    note_ids = list((await db.scalars(select(StudyNote.id).where(StudyNote.user_id == user_id))).all())
    keys = await _keys_for_notes(db, note_ids)
    if keys: db.add(NoteCleanupTask(user_id=user_id, storage_keys=keys))
    for note_id in note_ids:
        note = await db.get(StudyNote, note_id)
        if note: await db.delete(note)
    await db.flush()
    return len(keys)


async def queue_expired_note_cleanup() -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=settings.NOTE_RETENTION_HOURS)
    async with get_db_session() as db:
        notes = list((await db.scalars(select(StudyNote).where(StudyNote.status == "deleted", StudyNote.deleted_at <= cutoff))).all())
        by_user: dict[str, list[str]] = {}
        for note in notes: by_user.setdefault(note.user_id, []).append(note.id)
        for user_id, note_ids in by_user.items(): await queue_note_cleanup(db, user_id, note_ids)
        return len(notes)


async def process_note_cleanup_tasks(limit: int = 50) -> dict[str, int]:
    result = {"completed": 0, "failed": 0}
    async with get_db_session() as db:
        tasks = list((await db.scalars(select(NoteCleanupTask).where(NoteCleanupTask.status == "pending").order_by(NoteCleanupTask.created_at).limit(limit))).all())
        for task in tasks:
            task.status, task.attempts = "processing", task.attempts + 1
        await db.flush()
    for task in tasks:
        try:
            for key in task.storage_keys: note_storage.remove_storage_key(key)
            async with get_db_session() as db:
                row = await db.get(NoteCleanupTask, task.id)
                if row: row.status, row.completed_at, row.last_error = "completed", datetime.now(timezone.utc), None
            result["completed"] += 1
        except Exception as exc:
            async with get_db_session() as db:
                row = await db.get(NoteCleanupTask, task.id)
                if row: row.status, row.last_error = "pending", str(exc)[:500]
            result["failed"] += 1
    return result


async def reconcile_note_storage() -> dict[str, list[str]]:
    async with get_db_session() as db:
        revisions = set((await db.scalars(select(NoteRevision.stroke_storage_key))).all())
        assets = set((await db.scalars(select(NoteAsset.storage_key))).all())
        queued = set(key for keys in (await db.scalars(select(NoteCleanupTask.storage_keys).where(NoteCleanupTask.status != "completed"))).all() for key in keys)
    disk = note_storage.iter_storage_keys()
    expected = revisions | assets
    return {"orphan_files": sorted(disk - expected - queued), "missing_files": sorted(expected - disk), "pending_cleanup_files": sorted(queued & disk)}
