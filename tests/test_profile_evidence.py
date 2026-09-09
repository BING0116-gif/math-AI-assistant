"""T07 记忆证据链：幂等、ownership 与 L1→L2→L3 可追溯性。"""
from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.requests import Request

from app.api import profile_api
from app.data.models import (
    Base,
    LearningRecord,
    Memory,
    MemoryEvidence,
    OutboxEvent,
    ProfileEvidence,
    Question,
    User,
)
from app.services.profile_application import ProfileSnapshot
from app.services.profile_evidence import ProfileEvidenceService


@pytest_asyncio.fixture
async def evidence_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    @event.listens_for(engine.sync_engine, "connect")
    def foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        yield factory
    finally:
        await engine.dispose()


def _snapshot(user_id: str, mastery: float = 0.42, count: int = 2) -> ProfileSnapshot:
    return ProfileSnapshot(
        user_id=user_id,
        skills=[{
            "skill_code": "limit",
            "display_name": "极限",
            "mastery_level": mastery,
            "evidence_count": count,
            "confidence_level": "medium",
            "status": "learning",
        }],
    )


async def _seed_records(factory, user_id: str = "user-1") -> list[int]:
    async with factory() as db:
        db.add(User(
            id=user_id,
            username=user_id,
            email=f"{user_id}@example.test",
            password_hash="x",
            role="student",
        ))
        db.add(Question(
            id="Q-LIMIT",
            content="求 lim x→0 sin(x)/x",
            question_type="short_answer",
            answer="1",
            category="高等数学",
        ))
        await db.flush()
        rows = [
            LearningRecord(
                user_id=user_id,
                question_id="Q-LIMIT",
                event_type="practice_answer",
                question_content="求 lim x→0 sin(x)/x",
                category="limit",
                user_answer="0",
                correct_answer="1",
                is_correct=False,
                metadata_={"attempt_id": "attempt-1", "knowledge_point_codes": ["limit"]},
            ),
            LearningRecord(
                user_id=user_id,
                question_id="Q-LIMIT",
                event_type="practice_answer",
                question_content="求 lim x→0 sin(x)/x",
                category="limit",
                user_answer="1",
                correct_answer="1",
                is_correct=True,
                metadata_={"attempt_id": "attempt-2", "knowledge_point_codes": ["limit"]},
            ),
        ]
        db.add_all(rows)
        await db.commit()
        return [row.id for row in rows]


@pytest.mark.asyncio
async def test_repeated_refresh_is_idempotent_and_chain_reaches_learning_records(evidence_db):
    record_ids = await _seed_records(evidence_db)
    service = ProfileEvidenceService(evidence_db)
    first = _snapshot("user-1")
    second = _snapshot("user-1")

    first_id = await service.record_snapshot(first)
    second_id = await service.record_snapshot(second)

    assert first_id == second_id == first.snapshot_id == second.snapshot_id
    async with evidence_db() as db:
        assert (await db.scalar(select(func.count()).select_from(Memory))) == 1
        memory = (await db.execute(select(Memory))).scalar_one()
        assert memory.expire_at == 2_147_483_647
        assert (await db.scalar(select(func.count()).select_from(MemoryEvidence))) == 2
        assert (await db.scalar(select(func.count()).select_from(ProfileEvidence))) == 1
        assert (await db.scalar(select(func.count()).select_from(OutboxEvent))) == 1

    explanation = await service.explain("user-1", "limit")
    assert explanation["profile_snapshot_id"] == first_id
    assert explanation["conclusion"] == "limit掌握度 0.42（弱）"
    events = explanation["supporting_memories"][0]["evidence_events"]
    assert [item["learning_record_id"] for item in events] == record_ids
    assert {item["event_type"] for item in events} == {"practice_answer"}


@pytest.mark.asyncio
async def test_history_uses_snapshot_id_without_rewriting_old_edges(evidence_db):
    await _seed_records(evidence_db)
    service = ProfileEvidenceService(evidence_db)
    old_id = await service.record_snapshot(_snapshot("user-1"))
    async with evidence_db() as db:
        db.add(LearningRecord(
            user_id="user-1",
            question_id="Q-LIMIT",
            event_type="practice_answer",
            question_content="再次求极限",
            category="limit",
            user_answer="1",
            correct_answer="1",
            is_correct=True,
            metadata_={"attempt_id": "attempt-3", "knowledge_point_codes": ["limit"]},
        ))
        await db.commit()
    new_id = await service.record_snapshot(_snapshot("user-1", mastery=0.63, count=3))

    assert new_id != old_id
    old = await service.explain("user-1", "limit", profile_snapshot_id=old_id)
    latest = await service.explain("user-1", "limit")
    assert len(old["supporting_memories"][0]["evidence_events"]) == 2
    assert len(latest["supporting_memories"][0]["evidence_events"]) == 3


def _request(user_id: str, role: str = "student") -> Request:
    request = Request({"type": "http", "method": "GET", "path": "/api/profile/why", "headers": []})
    request.state.user_id = user_id
    request.state.current_user = SimpleNamespace(id=user_id, role=role)
    return request


@pytest.mark.asyncio
async def test_non_owner_non_admin_is_rejected_before_data_access():
    with pytest.raises(HTTPException) as denied:
        await profile_api.get_profile_reason(
            _request("user-2"),
            dimension="limit",
            user_id="user-1",
            profile_snapshot_id=None,
        )
    assert denied.value.status_code == 403


@pytest.mark.asyncio
async def test_owner_endpoint_keeps_common_response_envelope(monkeypatch):
    class Facade:
        async def get_profile_snapshot(self, _user_id):
            return SimpleNamespace(snapshot_id="ps_current")

    async def fake_get_facade():
        return Facade()

    async def fake_explain(self, user_id, dimension, profile_snapshot_id=None):
        return {
            "profile_snapshot_id": "ps_current",
            "dimension": dimension,
            "conclusion": "limit掌握度 0.42（弱）",
            "supporting_memories": [],
        }

    monkeypatch.setattr(profile_api, "_get_facade", fake_get_facade)
    monkeypatch.setattr(ProfileEvidenceService, "explain", fake_explain)
    response = await profile_api.get_profile_reason(
        _request("user-1"),
        dimension="limit",
        user_id="user-1",
        profile_snapshot_id=None,
    )
    assert response["code"] == 0
    assert response["message"] == "ok"
    assert response["data"]["dimension"] == "limit"
