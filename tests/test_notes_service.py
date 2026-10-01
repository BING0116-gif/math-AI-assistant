import pytest
import pytest_asyncio
from pydantic import ValidationError
from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config.settings import settings
from app.data.models import Base, Chapter, Course, KnowledgeGraphVersion, KnowledgePoint, NoteAiRun, NoteAsset, User
from app.services import note_storage
from app.services.note_service import NoteServiceError, archive_note, copy_page, create_asset, create_note, create_page, delete_note, delete_page, get_asset_content, get_current_revision, get_note, list_assets, list_notes, list_pages, reorder_pages, restore_note, save_revision
from app.services.note_cleanup import process_note_cleanup_tasks, queue_note_cleanup, reconcile_note_storage
from app.services.user_data_deletion import delete_user_data
from app.api.notes_api import ConfirmAiSuggestionRequest, CreateNoteRequest, SaveRevisionRequest
from app.services.note_knowledge_service import confirm_link, list_links, materialize_ai_suggestions, reject_link


@pytest_asyncio.fixture
async def notes_db(monkeypatch, tmp_path):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    @event.listens_for(engine.sync_engine, "connect")
    def foreign_keys(connection, _): connection.execute("PRAGMA foreign_keys=ON")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    import app.data.database as database
    monkeypatch.setattr(database, "async_session_factory", factory)
    monkeypatch.setattr(settings, "NOTE_STORAGE_ROOT", str(tmp_path / "notes"))
    async with engine.begin() as connection: await connection.run_sync(Base.metadata.create_all)
    async with factory() as db:
        db.add_all([User(id="note-a", username="note-a", email="note-a@example.test", password_hash="x"), User(id="note-b", username="note-b", email="note-b@example.test", password_hash="x")])
        db.add(Course(id="course-a", code="course-a", name="课程 A", subject="math", status="active"))
        db.add(KnowledgeGraphVersion(id="version-a", course_id="course-a", version="v1", name="V1", status="published"))
        db.add(Chapter(id="chapter-a", course_id="course-a", version_id="version-a", code="chapter-a", name="第一章", status="published"))
        db.add(KnowledgePoint(id="point-a", course_id="course-a", version_id="version-a", chapter_id="chapter-a", code="POINT_A", name="知识点 A", status="active"))
        db.add(KnowledgePoint(id="point-b", course_id="course-a", version_id="version-a", chapter_id="chapter-a", code="POINT_B", name="知识点 B", status="active"))
        await db.commit()
    yield engine
    await engine.dispose()


@pytest.mark.asyncio
async def test_notes_are_owner_scoped_idempotent_and_recover_payload(notes_db):
    note = await create_note("note-a", "极限推导")
    assert (await list_notes("note-b", 20, 0))["items"] == []
    with pytest.raises(NoteServiceError, match="不存在"): await get_note("note-b", note["note_id"])
    page_id = note["page"]["page_id"]
    payload = {"strokes": [{"id": "stroke-1", "points": [{"x": 1, "y": 2, "pressure": .5, "timestamp": 1, "tiltX": 0, "tiltY": 0}]}]}
    first = await save_revision("note-a", note["note_id"], page_id, base_revision=0, idempotency_key="note-revision-0001", stroke_payload=payload)
    replay = await save_revision("note-a", note["note_id"], page_id, base_revision=0, idempotency_key="note-revision-0001", stroke_payload=payload)
    assert first["current_revision"] == replay["current_revision"] == 1 and replay["idempotent_replay"]
    restored = await get_current_revision("note-a", note["note_id"], page_id)
    assert restored["stroke_payload"] == payload
    with pytest.raises(NoteServiceError) as conflict:
        await save_revision("note-a", note["note_id"], page_id, base_revision=0, idempotency_key="note-revision-0002", stroke_payload=payload)
    assert conflict.value.code == "NOTE_REVISION_CONFLICT"
    assert conflict.value.extra == {"base_revision": 0, "current_revision": 1}
    with pytest.raises(NoteServiceError, match="不存在"): await get_current_revision("note-b", note["note_id"], page_id)


@pytest.mark.asyncio
async def test_storage_failure_never_advances_revision(notes_db, monkeypatch):
    note = await create_note("note-a", "失败回归")
    page_id = note["page"]["page_id"]
    def fail(**_): raise note_storage.NoteStorageError("disk unavailable")
    monkeypatch.setattr(note_storage, "publish_revision", fail)
    with pytest.raises(NoteServiceError) as result:
        await save_revision("note-a", note["note_id"], page_id, base_revision=0, idempotency_key="note-storage-failure", stroke_payload={"strokes": []})
    assert result.value.code == "NOTE_STORAGE_FAILED"
    assert (await get_current_revision("note-a", note["note_id"], page_id))["current_revision"] == 0


@pytest.mark.asyncio
async def test_soft_deleted_note_is_not_readable(notes_db):
    note = await create_note("note-a", "待删除")
    await delete_note("note-a", note["note_id"])
    assert (await list_notes("note-a", 20, 0))["items"] == []
    with pytest.raises(NoteServiceError, match="不存在"): await get_note("note-a", note["note_id"])


def test_note_request_models_reject_client_owned_user_id():
    with pytest.raises(ValidationError): CreateNoteRequest.model_validate({"title": "越权", "user_id": "note-b"})
    with pytest.raises(ValidationError): SaveRevisionRequest.model_validate({"base_revision": 0, "idempotency_key": "note-payload-0001", "stroke_payload": {}, "user_id": "note-b"})
    with pytest.raises(ValidationError): ConfirmAiSuggestionRequest.model_validate({"knowledge_point_id": "point-a", "user_id": "note-b"})


@pytest.mark.asyncio
async def test_ai_note_links_require_human_review_and_human_outcomes_win(notes_db):
    note = await create_note("note-a", "AI 归类")
    import app.data.database as database
    async with database.get_db_session() as db:
        db.add(NoteAiRun(id="run-1", note_id=note["note_id"], page_id=note["page"]["page_id"], user_id="note-a", source_revision=0, status="needs_review", model="test", prompt_version="v1", attempt_no=1, idempotency_key="ai-run-key-0001"))
    await materialize_ai_suggestions("note-a", note["note_id"], "run-1", [
        {"knowledge_point_code": "POINT_A", "confidence": .95, "reason": "high"},
        {"knowledge_point_code": "POINT_B", "confidence": .70, "reason": "medium"},
        {"knowledge_point_code": "MISSING", "confidence": .99, "reason": "invalid"},
        {"knowledge_point_code": "POINT_A", "confidence": .20, "reason": "low"},
    ])
    links = await list_links("note-a", note["note_id"])
    assert {(item["knowledge_point_code"], item["status"]) for item in links} == {("POINT_A", "confirmed"), ("POINT_B", "suggested")}
    medium = next(item for item in links if item["knowledge_point_code"] == "POINT_B")
    confirmed = await confirm_link("note-a", note["note_id"], medium["link_id"])
    assert confirmed["source"] == "manual" and confirmed["status"] == "confirmed" and confirmed["confirmed_by_user_at"]
    # A later AI run cannot remove or downgrade the explicit human classification.
    await materialize_ai_suggestions("note-a", note["note_id"], "run-1", [{"knowledge_point_code": "POINT_B", "confidence": .65, "reason": "later run"}])
    point_b = next(item for item in await list_links("note-a", note["note_id"]) if item["knowledge_point_code"] == "POINT_B")
    assert point_b["source"] == "manual" and point_b["status"] == "confirmed"
    high = next(item for item in links if item["knowledge_point_code"] == "POINT_A")
    revoked = await reject_link("note-a", note["note_id"], high["link_id"])
    assert revoked["source"] == "manual" and revoked["status"] == "rejected"
    assert await list_links("note-b", note["note_id"]) == []


@pytest.mark.asyncio
async def test_note_can_be_created_for_a_published_course_point(notes_db):
    note = await create_note("note-a", "知识点推导", course_id="course-a", knowledge_point_id="point-a")
    assert note["course_id"] == "course-a"
    assert note["knowledge_point_id"] == "point-a"
    assert (await list_notes("note-a", 20, 0, knowledge_point_id="point-a"))["total"] == 1
    assert (await list_notes("note-b", 20, 0, knowledge_point_id="point-a"))["total"] == 0
    with pytest.raises(NoteServiceError) as mismatch:
        await create_note("note-a", "错误关联", course_id="other-course", knowledge_point_id="point-a")
    assert mismatch.value.code == "NOTE_CONTEXT_INVALID"
    with pytest.raises(NoteServiceError) as partial:
        await create_note("note-a", "不完整关联", course_id="course-a")
    assert partial.value.code == "NOTE_CONTEXT_INVALID"

@pytest.mark.asyncio
async def test_pages_can_be_copied_reordered_and_deleted_by_owner(notes_db):
    note = await create_note("note-a", "多页")
    first = note["page"]["page_id"]
    await save_revision("note-a", note["note_id"], first, base_revision=0, idempotency_key="page-source-0001", stroke_payload={"strokes": [{"id": "a", "points": []}]})
    copied = await copy_page("note-a", note["note_id"], first)
    extra = await create_page("note-a", note["note_id"])
    ordered = await reorder_pages("note-a", note["note_id"], [extra["page_id"], copied["page_id"], first])
    assert [page["page_number"] for page in ordered] == [1, 2, 3]
    assert (await get_current_revision("note-a", note["note_id"], copied["page_id"]))["stroke_payload"]["strokes"][0]["id"] == "a"
    await delete_page("note-a", note["note_id"], extra["page_id"])
    assert len(await list_pages("note-a", note["note_id"])) == 2


@pytest.mark.asyncio
async def test_assets_are_validated_owner_scoped_and_delayed_on_page_delete(notes_db):
    note = await create_note("note-a", "含图片笔记")
    page_id = note["page"]["page_id"]
    png = b"\x89PNG\r\n\x1a\nimage"
    asset = await create_asset("note-a", note["note_id"], page_id, "question.png", "image/png", png)
    assert (await list_assets("note-a", note["note_id"], page_id))[0]["asset_id"] == asset["asset_id"]
    content, media_type, _ = await get_asset_content("note-a", note["note_id"], asset["asset_id"])
    assert content == png and media_type == "image/png"
    with pytest.raises(NoteServiceError): await get_asset_content("note-b", note["note_id"], asset["asset_id"])
    with pytest.raises(NoteServiceError): await create_asset("note-a", note["note_id"], page_id, "escape.png", "image/png", b"not-a-png")
    with pytest.raises(NoteServiceError): await create_asset("note-a", note["note_id"], page_id, "../escape.png", "image/png", png)
    extra = await create_page("note-a", note["note_id"])
    await delete_page("note-a", note["note_id"], page_id)
    import app.data.database as database
    async with database.get_db_session() as db:
        row = await db.get(NoteAsset, asset["asset_id"])
        assert row.status == "pending_cleanup" and row.cleanup_after is not None and row.storage_key.startswith("assets/")


@pytest.mark.asyncio
async def test_archive_recycle_restore_and_post_commit_cleanup(notes_db):
    note = await create_note("note-a", "可恢复")
    archived = await archive_note("note-a", note["note_id"])
    assert archived["status"] == "archived"
    assert (await restore_note("note-a", note["note_id"]))["status"] == "active"
    page_id = note["page"]["page_id"]
    await save_revision("note-a", note["note_id"], page_id, base_revision=0, idempotency_key="recycle-revision-0001", stroke_payload={"strokes": []})
    await delete_note("note-a", note["note_id"])
    import app.data.database as database
    async with database.get_db_session() as db:
        assert await queue_note_cleanup(db, "note-a", [note["note_id"]]) == 1
    # SQL is gone before the worker is permitted to touch the immutable file.
    assert await get_note_count(notes_db, note["note_id"]) == 0
    result = await process_note_cleanup_tasks()
    assert result == {"completed": 1, "failed": 0}
    report = await reconcile_note_storage()
    assert report["orphan_files"] == [] and report["missing_files"] == []


async def get_note_count(engine, note_id):
    from sqlalchemy import select, func
    from app.data.models import StudyNote
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        return await db.scalar(select(func.count()).select_from(StudyNote).where(StudyNote.id == note_id))


@pytest.mark.asyncio
async def test_user_purge_queues_note_files_then_removes_them_after_sql_commit(notes_db):
    note = await create_note("note-a", "账号删除")
    page_id = note["page"]["page_id"]
    await save_revision("note-a", note["note_id"], page_id, base_revision=0, idempotency_key="purge-note-revision-01", stroke_payload={"strokes": []})
    await create_asset("note-a", note["note_id"], page_id, "question.png", "image/png", b"\x89PNG\r\n\x1a\nimage")
    import app.data.database as database
    async with database.get_db_session() as db:
        counts = await delete_user_data(db, "note-a")
        assert counts["note_storage_objects"] == 2
    assert await get_note_count(notes_db, note["note_id"]) == 0
    assert (await process_note_cleanup_tasks())["completed"] == 1
    report = await reconcile_note_storage()
    assert report["orphan_files"] == [] and report["missing_files"] == []
