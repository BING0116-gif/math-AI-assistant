"""Owner-scoped handwritten note CRUD and immutable revision publishing."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.data.database import get_db_session
from app.data.models import Course, KnowledgeGraphVersion, KnowledgePoint, NoteAsset, NotePage, NoteRevision, StudyNote
from app.config.settings import settings
from app.services import note_storage


class NoteServiceError(Exception):
    def __init__(self, code: str, message: str, extra: dict[str, Any] | None = None):
        self.code, self.message, self.extra = code, message, extra or {}
        super().__init__(message)


def _note_query(user_id: str, note_id: str, *, include_pages: bool = False):
    query = select(StudyNote).where(StudyNote.id == note_id, StudyNote.user_id == user_id, StudyNote.status == "active")
    return query.options(selectinload(StudyNote.pages)) if include_pages else query


def _note_data(note: StudyNote, *, include_page: bool = False) -> dict[str, Any]:
    data = {"note_id": note.id, "title": note.title, "note_type": note.note_type, "status": note.status, "course_id": note.primary_course_id, "knowledge_point_id": note.primary_knowledge_point_id, "current_revision": note.current_revision, "created_at": note.created_at, "updated_at": note.updated_at}
    if include_page:
        page = sorted(note.pages, key=lambda item: item.page_number)[0]
        data["page"] = {"page_id": page.id, "page_number": page.page_number, "width": page.width, "height": page.height, "background_type": page.background_type, "current_revision": page.current_revision}
    return data

def _page_data(page: NotePage) -> dict[str, Any]:
    return {"page_id": page.id, "page_number": page.page_number, "width": page.width, "height": page.height, "background_type": page.background_type, "current_revision": page.current_revision}

def _asset_data(asset: NoteAsset) -> dict[str, Any]:
    return {"asset_id": asset.id, "page_id": asset.page_id, "filename": asset.original_filename, "media_type": asset.media_type, "size_bytes": asset.size_bytes, "asset_kind": asset.asset_kind, "url": f"/api/notes/{asset.note_id}/assets/{asset.id}/content"}


async def create_note(
    user_id: str,
    title: str,
    *,
    course_id: str | None = None,
    knowledge_point_id: str | None = None,
) -> dict[str, Any]:
    async with get_db_session() as db:
        if bool(course_id) != bool(knowledge_point_id):
            raise NoteServiceError("NOTE_CONTEXT_INVALID", "课程和知识点必须同时关联")
        if knowledge_point_id:
            point = await db.scalar(
                select(KnowledgePoint)
                .join(Course, Course.id == KnowledgePoint.course_id)
                .join(KnowledgeGraphVersion, KnowledgeGraphVersion.id == KnowledgePoint.version_id)
                .where(
                    KnowledgePoint.id == knowledge_point_id,
                    KnowledgePoint.course_id == course_id,
                    KnowledgePoint.status == "active",
                    Course.status == "active",
                    KnowledgeGraphVersion.status == "published",
                )
            )
            if not point:
                raise NoteServiceError("NOTE_CONTEXT_INVALID", "知识点不存在、未发布或不属于该课程")
        note = StudyNote(
            user_id=user_id,
            title=title.strip() or "未命名笔记",
            primary_course_id=course_id,
            primary_knowledge_point_id=knowledge_point_id,
        )
        db.add(note); await db.flush()
        page = NotePage(note_id=note.id, user_id=user_id, page_number=1)
        db.add(page); await db.flush()
        return {**_note_data(note), "page": {"page_id": page.id, "page_number": page.page_number, "width": page.width, "height": page.height, "background_type": page.background_type, "current_revision": page.current_revision}}


async def list_notes(user_id: str, limit: int, offset: int, status: str = "active", course_id: str | None = None, knowledge_point_id: str | None = None) -> dict[str, Any]:
    async with get_db_session() as db:
        query = select(StudyNote).where(StudyNote.user_id == user_id, StudyNote.status == status)
        if course_id: query = query.where(StudyNote.primary_course_id == course_id)
        if knowledge_point_id: query = query.where(StudyNote.primary_knowledge_point_id == knowledge_point_id)
        rows = list((await db.execute(query.order_by(StudyNote.updated_at.desc()).offset(offset).limit(limit))).scalars())
        count_query = select(func.count()).select_from(StudyNote).where(StudyNote.user_id == user_id, StudyNote.status == status)
        if course_id: count_query = count_query.where(StudyNote.primary_course_id == course_id)
        if knowledge_point_id: count_query = count_query.where(StudyNote.primary_knowledge_point_id == knowledge_point_id)
        total = await db.scalar(count_query)
        return {"items": [_note_data(note) for note in rows], "limit": limit, "offset": offset, "total": total}


async def get_note(user_id: str, note_id: str) -> dict[str, Any]:
    async with get_db_session() as db:
        note = (await db.execute(_note_query(user_id, note_id, include_pages=True))).scalar_one_or_none()
        if not note: raise NoteServiceError("NOTE_NOT_FOUND", "笔记不存在")
        return _note_data(note, include_page=True)

async def list_pages(user_id: str, note_id: str) -> list[dict[str, Any]]:
    async with get_db_session() as db:
        rows = list((await db.execute(select(NotePage).join(StudyNote).where(NotePage.note_id == note_id, NotePage.user_id == user_id, StudyNote.user_id == user_id, StudyNote.status == "active").order_by(NotePage.page_number))).scalars())
        if not rows: raise NoteServiceError("NOTE_NOT_FOUND", "笔记不存在")
        return [_page_data(page) for page in rows]

async def create_page(user_id: str, note_id: str) -> dict[str, Any]:
    async with get_db_session() as db:
        note = (await db.execute(_note_query(user_id, note_id).with_for_update())).scalar_one_or_none()
        if not note: raise NoteServiceError("NOTE_NOT_FOUND", "笔记不存在")
        number = (await db.scalar(select(func.max(NotePage.page_number)).where(NotePage.note_id == note_id)) or 0) + 1
        page = NotePage(note_id=note_id, user_id=user_id, page_number=number); db.add(page); await db.flush()
        return _page_data(page)

async def copy_page(user_id: str, note_id: str, page_id: str) -> dict[str, Any]:
    source = await get_current_revision(user_id, note_id, page_id)
    copied = await create_page(user_id, note_id)
    if source["current_revision"]:
        await save_revision(user_id, note_id, copied["page_id"], base_revision=0, idempotency_key=f"page-copy-{uuid4()}", stroke_payload=source["stroke_payload"])
        copied["current_revision"] = 1
    return copied

async def reorder_pages(user_id: str, note_id: str, page_ids: list[str]) -> list[dict[str, Any]]:
    async with get_db_session() as db:
        pages = list((await db.execute(select(NotePage).join(StudyNote).where(NotePage.note_id == note_id, NotePage.user_id == user_id, StudyNote.user_id == user_id, StudyNote.status == "active").with_for_update())).scalars())
        if len(pages) != len(page_ids) or {page.id for page in pages} != set(page_ids): raise NoteServiceError("NOTE_PAGE_ORDER_INVALID", "页面排序包含无效页面")
        for index, page in enumerate(pages, 1): page.page_number = 100000 + index
        await db.flush()
        by_id = {page.id: page for page in pages}
        for index, page_id in enumerate(page_ids, 1): by_id[page_id].page_number = index
        await db.flush(); return [_page_data(by_id[page_id]) for page_id in page_ids]

async def delete_page(user_id: str, note_id: str, page_id: str) -> None:
    async with get_db_session() as db:
        pages = list((await db.execute(select(NotePage).join(StudyNote).where(NotePage.note_id == note_id, NotePage.user_id == user_id, NotePage.id == page_id, StudyNote.user_id == user_id, StudyNote.status == "active").with_for_update())).scalars())
        if not pages: raise NoteServiceError("NOTE_NOT_FOUND", "笔记页面不存在")
        count = await db.scalar(select(func.count()).select_from(NotePage).where(NotePage.note_id == note_id))
        if count <= 1: raise NoteServiceError("NOTE_LAST_PAGE", "至少保留一个页面")
        await db.execute(
            NoteAsset.__table__.update().where(NoteAsset.note_id == note_id, NoteAsset.page_id == page_id, NoteAsset.user_id == user_id, NoteAsset.status == "active").values(status="pending_cleanup", cleanup_after=datetime.now(timezone.utc) + timedelta(hours=settings.NOTE_ASSET_CLEANUP_DELAY_HOURS))
        )
        await db.delete(pages[0])


async def create_asset(user_id: str, note_id: str, page_id: str, filename: str, media_type: str, data: bytes, asset_kind: str = "image") -> dict[str, Any]:
    if asset_kind not in {"image", "preview"}: raise NoteServiceError("NOTE_ASSET_INVALID", "无效附件类型")
    safe_name = filename.replace("\\", "/").split("/")[-1]
    if not safe_name or safe_name != filename or any(ord(char) < 32 for char in safe_name):
        raise NoteServiceError("NOTE_ASSET_INVALID", "无效附件文件名")
    async with get_db_session() as db:
        page = await db.scalar(select(NotePage).join(StudyNote).where(NotePage.id == page_id, NotePage.note_id == note_id, NotePage.user_id == user_id, StudyNote.user_id == user_id, StudyNote.status == "active"))
        if not page: raise NoteServiceError("NOTE_NOT_FOUND", "笔记页面不存在")
        try: stored = note_storage.publish_asset(note_id=note_id, page_id=page_id, filename=safe_name, media_type=media_type, data=data)
        except note_storage.NoteStorageError as exc: raise NoteServiceError("NOTE_ASSET_INVALID", str(exc)) from exc
        asset = NoteAsset(note_id=note_id, page_id=page_id, user_id=user_id, storage_key=stored.storage_key, original_filename=safe_name, media_type=media_type, size_bytes=stored.size_bytes, sha256=stored.sha256, asset_kind=asset_kind)
        db.add(asset); await db.flush()
        return _asset_data(asset)


async def list_assets(user_id: str, note_id: str, page_id: str) -> list[dict[str, Any]]:
    async with get_db_session() as db:
        rows = list((await db.execute(select(NoteAsset).join(StudyNote).where(NoteAsset.note_id == note_id, NoteAsset.page_id == page_id, NoteAsset.user_id == user_id, NoteAsset.status == "active", StudyNote.user_id == user_id, StudyNote.status == "active").order_by(NoteAsset.created_at))).scalars())
        return [_asset_data(asset) for asset in rows]


async def get_asset_content(user_id: str, note_id: str, asset_id: str) -> tuple[bytes, str, str]:
    async with get_db_session() as db:
        asset = await db.scalar(select(NoteAsset).join(StudyNote).where(NoteAsset.id == asset_id, NoteAsset.note_id == note_id, NoteAsset.user_id == user_id, NoteAsset.status == "active", StudyNote.user_id == user_id, StudyNote.status == "active"))
        if not asset: raise NoteServiceError("NOTE_NOT_FOUND", "附件不存在")
        try: data = note_storage.read_asset(asset.storage_key, asset.sha256, asset.size_bytes)
        except note_storage.NoteStorageError as exc: raise NoteServiceError("NOTE_STORAGE_UNAVAILABLE", "附件文件不可用") from exc
        return data, asset.media_type, asset.original_filename


async def update_note(user_id: str, note_id: str, title: str) -> dict[str, Any]:
    async with get_db_session() as db:
        note = (await db.execute(_note_query(user_id, note_id).with_for_update())).scalar_one_or_none()
        if not note: raise NoteServiceError("NOTE_NOT_FOUND", "笔记不存在")
        note.title = title.strip(); await db.flush()
        return _note_data(note)


async def delete_note(user_id: str, note_id: str) -> None:
    async with get_db_session() as db:
        note = (await db.execute(_note_query(user_id, note_id).with_for_update())).scalar_one_or_none()
        if not note: raise NoteServiceError("NOTE_NOT_FOUND", "笔记不存在")
        note.status, note.deleted_at = "deleted", datetime.now(timezone.utc)


async def archive_note(user_id: str, note_id: str) -> dict[str, Any]:
    async with get_db_session() as db:
        note = await db.scalar(select(StudyNote).where(StudyNote.id == note_id, StudyNote.user_id == user_id, StudyNote.status == "active").with_for_update())
        if not note: raise NoteServiceError("NOTE_NOT_FOUND", "笔记不存在或无法归档")
        note.status = "archived"
        await db.flush()
        return _note_data(note)


async def restore_note(user_id: str, note_id: str) -> dict[str, Any]:
    async with get_db_session() as db:
        note = await db.scalar(select(StudyNote).where(StudyNote.id == note_id, StudyNote.user_id == user_id, StudyNote.status.in_(("archived", "deleted"))).with_for_update())
        if not note: raise NoteServiceError("NOTE_NOT_FOUND", "笔记不存在、已到期清理或无需恢复")
        note.status, note.deleted_at = "active", None
        await db.flush()
        return _note_data(note)


async def get_current_revision(user_id: str, note_id: str, page_id: str) -> dict[str, Any]:
    async with get_db_session() as db:
        page = await db.scalar(select(NotePage).join(StudyNote).where(NotePage.id == page_id, NotePage.note_id == note_id, NotePage.user_id == user_id, StudyNote.user_id == user_id, StudyNote.status == "active"))
        if not page: raise NoteServiceError("NOTE_NOT_FOUND", "笔记页面不存在")
        if not page.current_revision: return {"page_id": page.id, "current_revision": 0, "stroke_payload": {"strokes": []}}
        revision = await db.scalar(select(NoteRevision).where(NoteRevision.page_id == page.id, NoteRevision.user_id == user_id, NoteRevision.revision_number == page.current_revision))
        if not revision: raise NoteServiceError("NOTE_STORAGE_UNAVAILABLE", "笔记版本元数据不完整")
        try: payload = note_storage.read_revision(revision.stroke_storage_key, revision.sha256, revision.size_bytes)
        except note_storage.NoteStorageError as exc: raise NoteServiceError("NOTE_STORAGE_UNAVAILABLE", "笔记文件不可用") from exc
        return {"page_id": page.id, "current_revision": revision.revision_number, "base_revision": revision.base_revision, "stroke_payload": payload, "created_at": revision.created_at}


async def save_revision(user_id: str, note_id: str, page_id: str, *, base_revision: int, idempotency_key: str, stroke_payload: dict) -> dict[str, Any]:
    stored = None
    try:
        async with get_db_session() as db:
            existing = await db.scalar(select(NoteRevision).where(NoteRevision.user_id == user_id, NoteRevision.idempotency_key == idempotency_key))
            if existing:
                if existing.page_id != page_id: raise NoteServiceError("IDEMPOTENCY_CONFLICT", "幂等键已用于其他页面")
                return {"page_id": page_id, "current_revision": existing.revision_number, "idempotent_replay": True}
            page = await db.scalar(select(NotePage).join(StudyNote).where(NotePage.id == page_id, NotePage.note_id == note_id, NotePage.user_id == user_id, StudyNote.user_id == user_id, StudyNote.status == "active").with_for_update())
            if not page: raise NoteServiceError("NOTE_NOT_FOUND", "笔记页面不存在")
            if page.current_revision != base_revision:
                raise NoteServiceError(
                    "NOTE_REVISION_CONFLICT",
                    "笔记已在其他位置更新",
                    {"base_revision": base_revision, "current_revision": page.current_revision},
                )
            number = page.current_revision + 1
            try: stored = note_storage.publish_revision(note_id=note_id, page_id=page_id, revision_number=number, payload=stroke_payload)
            except note_storage.NoteStorageError as exc: raise NoteServiceError("NOTE_STORAGE_FAILED", "笔记文件保存失败") from exc
            revision = NoteRevision(page_id=page.id, user_id=user_id, revision_number=number, base_revision=base_revision, stroke_storage_key=stored.storage_key, sha256=stored.sha256, size_bytes=stored.size_bytes, idempotency_key=idempotency_key)
            db.add(revision); page.current_revision = number
            note = await db.get(StudyNote, note_id); note.current_revision = number
            await db.flush()
            return {"page_id": page_id, "current_revision": number, "idempotent_replay": False}
    except IntegrityError as exc:
        if stored: note_storage.remove_revision(stored.storage_key)
        raise NoteServiceError("NOTE_REVISION_CONFLICT", "笔记版本并发冲突") from exc
    except Exception:
        if stored: note_storage.remove_revision(stored.storage_key)
        raise
