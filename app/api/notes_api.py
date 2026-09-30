"""Authenticated handwritten note API; ownership always comes from request state."""
from __future__ import annotations

from typing import Any
from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from app.config.settings import settings
from app.services.note_service import NoteServiceError, archive_note, copy_page, create_asset, create_note, create_page, delete_note, delete_page, get_asset_content, get_current_revision, get_note, list_assets, list_notes, list_pages, reorder_pages, restore_note, save_revision, update_note
from app.services.note_storage import NoteStorageError, serialize_payload
from app.services.note_ai_service import create_run, get_run
from app.services.note_knowledge_service import confirm_link, list_links, reject_link

router = APIRouter(prefix="/api/notes", tags=["notes"])


class CreateNoteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(default="未命名笔记", min_length=1, max_length=200)
    course_id: str | None = Field(default=None, min_length=1, max_length=36)
    knowledge_point_id: str | None = Field(default=None, min_length=1, max_length=36)


class UpdateNoteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=200)


class SaveRevisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    base_revision: int = Field(ge=0)
    idempotency_key: str = Field(min_length=8, max_length=128)
    stroke_payload: dict[str, Any]
class ReorderPagesRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    page_ids: list[str] = Field(min_length=1, max_length=200)
class CreateAiRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    idempotency_key: str = Field(min_length=8, max_length=128)
    model: str = Field(default="qwen-vl-plus", max_length=100)
    prompt_version: str = Field(default="v1", max_length=40)
class ConfirmAiSuggestionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    knowledge_point_id: str | None = Field(default=None, min_length=1, max_length=36)


def _user(request: Request) -> str:
    value = getattr(request.state, "user_id", None)
    if not value: raise HTTPException(status_code=401, detail={"code": "UNAUTHENTICATED", "message": "请先登录"})
    return str(value)


def _raise(error: NoteServiceError):
    mapping = {"NOTE_NOT_FOUND": 404, "NOTE_REVISION_CONFLICT": 409, "IDEMPOTENCY_CONFLICT": 409, "NOTE_LINK_CONFLICT": 409, "NOTE_STORAGE_FAILED": 503, "NOTE_STORAGE_UNAVAILABLE": 503, "NOTE_ASSET_INVALID": 422}
    raise HTTPException(status_code=mapping.get(error.code, 422), detail={"code": error.code, "message": error.message, **error.extra})


@router.get("")
async def get_notes(request: Request, limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0), status_filter: str = Query("active", alias="status"), course_id: str | None = None, knowledge_point_id: str | None = None):
    if status_filter not in {"active", "archived", "deleted"}: raise HTTPException(status_code=422, detail={"code":"NOTE_STATUS_INVALID","message":"无效笔记状态"})
    return {"code": 0, "data": await list_notes(_user(request), limit, offset, status_filter, course_id, knowledge_point_id)}


@router.post("", status_code=status.HTTP_201_CREATED)
async def post_note(request: Request, body: CreateNoteRequest):
    return {"code": 0, "data": await create_note(
        _user(request), body.title,
        course_id=body.course_id,
        knowledge_point_id=body.knowledge_point_id,
    )}


@router.get("/{note_id}")
async def get_note_detail(request: Request, note_id: str):
    try: return {"code": 0, "data": await get_note(_user(request), note_id)}
    except NoteServiceError as error: _raise(error)


@router.patch("/{note_id}")
async def patch_note(request: Request, note_id: str, body: UpdateNoteRequest):
    try: return {"code": 0, "data": await update_note(_user(request), note_id, body.title)}
    except NoteServiceError as error: _raise(error)


@router.delete("/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_note_endpoint(request: Request, note_id: str):
    try: await delete_note(_user(request), note_id)
    except NoteServiceError as error: _raise(error)

@router.post("/{note_id}/archive")
async def post_archive_note(request: Request, note_id: str):
    try: return {"code": 0, "data": await archive_note(_user(request), note_id)}
    except NoteServiceError as error: _raise(error)

@router.post("/{note_id}/restore")
async def post_restore_note(request: Request, note_id: str):
    try: return {"code": 0, "data": await restore_note(_user(request), note_id)}
    except NoteServiceError as error: _raise(error)

@router.get("/{note_id}/pages")
async def get_pages(request: Request, note_id: str):
    try: return {"code": 0, "data": {"items": await list_pages(_user(request), note_id)}}
    except NoteServiceError as error: _raise(error)
@router.post("/{note_id}/pages", status_code=status.HTTP_201_CREATED)
async def post_page(request: Request, note_id: str):
    try: return {"code": 0, "data": await create_page(_user(request), note_id)}
    except NoteServiceError as error: _raise(error)
@router.post("/{note_id}/pages/{page_id}/copy", status_code=status.HTTP_201_CREATED)
async def post_copy_page(request: Request, note_id: str, page_id: str):
    try: return {"code": 0, "data": await copy_page(_user(request), note_id, page_id)}
    except NoteServiceError as error: _raise(error)
@router.put("/{note_id}/pages/order")
async def put_page_order(request: Request, note_id: str, body: ReorderPagesRequest):
    try: return {"code": 0, "data": {"items": await reorder_pages(_user(request), note_id, body.page_ids)}}
    except NoteServiceError as error: _raise(error)
@router.delete("/{note_id}/pages/{page_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_page_endpoint(request: Request, note_id: str, page_id: str):
    try: await delete_page(_user(request), note_id, page_id)
    except NoteServiceError as error: _raise(error)

@router.post("/{note_id}/pages/{page_id}/assets", status_code=status.HTTP_201_CREATED)
async def post_asset(request: Request, note_id: str, page_id: str, file: UploadFile = File(...), asset_kind: str = Query("image")):
    data = await file.read(settings.NOTE_MAX_ASSET_BYTES + 1)
    try: return {"code": 0, "data": await create_asset(_user(request), note_id, page_id, file.filename or "upload", file.content_type or "", data, asset_kind)}
    except NoteServiceError as error: _raise(error)

@router.get("/{note_id}/pages/{page_id}/assets")
async def get_assets(request: Request, note_id: str, page_id: str):
    return {"code": 0, "data": {"items": await list_assets(_user(request), note_id, page_id)}}

@router.get("/{note_id}/assets/{asset_id}/content")
async def get_asset(request: Request, note_id: str, asset_id: str):
    try:
        data, media_type, filename = await get_asset_content(_user(request), note_id, asset_id)
        return Response(content=data, media_type=media_type, headers={"Content-Disposition": f'inline; filename="{filename}"', "X-Content-Type-Options": "nosniff"})
    except NoteServiceError as error: _raise(error)


@router.get("/{note_id}/pages/{page_id}/revisions/current")
async def get_current_page_revision(request: Request, note_id: str, page_id: str):
    try: return {"code": 0, "data": await get_current_revision(_user(request), note_id, page_id)}
    except NoteServiceError as error: _raise(error)


@router.put("/{note_id}/pages/{page_id}/revisions")
async def put_page_revision(request: Request, note_id: str, page_id: str, body: SaveRevisionRequest):
    try:
        # Pydantic validates shape; this exact byte check enforces the stricter
        # T02 per-revision limit below the global request-body cap.
        serialize_payload(body.stroke_payload)
    except NoteStorageError as error:
        raise HTTPException(status_code=413, detail={"code": "NOTE_PAYLOAD_TOO_LARGE", "message": "单页笔迹不能超过 5 MiB"}) from error
    try:
        return {"code": 0, "data": await save_revision(_user(request), note_id, page_id, base_revision=body.base_revision, idempotency_key=body.idempotency_key, stroke_payload=body.stroke_payload)}
    except NoteServiceError as error: _raise(error)

@router.post("/{note_id}/pages/{page_id}/ai-runs", status_code=status.HTTP_201_CREATED)
async def post_ai_run(request: Request, note_id: str, page_id: str, body: CreateAiRunRequest):
    try: return {"code":0,"data":await create_run(_user(request),note_id,page_id,body.idempotency_key,body.model,body.prompt_version)}
    except NoteServiceError as error: _raise(error)
@router.get("/{note_id}/ai-runs/{run_id}")
async def get_ai_run(request: Request, note_id: str, run_id: str):
    try: return {"code":0,"data":await get_run(_user(request),note_id,run_id)}
    except NoteServiceError as error: _raise(error)

@router.get("/{note_id}/ai-suggestions")
async def get_ai_suggestions(request: Request, note_id: str, status_filter: str | None = Query(None, alias="status")):
    if status_filter not in {None, "suggested", "confirmed", "rejected"}:
        raise HTTPException(status_code=422, detail={"code":"NOTE_LINK_STATUS_INVALID", "message":"无效关联状态"})
    try: return {"code": 0, "data": {"items": await list_links(_user(request), note_id, status_filter)}}
    except NoteServiceError as error: _raise(error)

@router.post("/{note_id}/ai-suggestions/{link_id}/confirm")
async def post_confirm_ai_suggestion(request: Request, note_id: str, link_id: str, body: ConfirmAiSuggestionRequest):
    try: return {"code": 0, "data": await confirm_link(_user(request), note_id, link_id, body.knowledge_point_id)}
    except NoteServiceError as error: _raise(error)

@router.post("/{note_id}/ai-suggestions/{link_id}/reject")
async def post_reject_ai_suggestion(request: Request, note_id: str, link_id: str):
    try: return {"code": 0, "data": await reject_link(_user(request), note_id, link_id)}
    except NoteServiceError as error: _raise(error)
