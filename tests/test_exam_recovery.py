"""T11 recovery contract tests: replay IDs and owner isolation."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.api.exam_api import RecoverySnapshotRequest
from app.services.exam_service import _deadline
from app.services.sse_replay import SSEReplayBuffer


def test_exam_deadline_is_server_derived_and_client_clock_fields_are_rejected():
    started_at = datetime(2026, 9, 12, 10, 0, tzinfo=timezone.utc)
    session = SimpleNamespace(started_at=started_at, duration_limit_seconds=1800)
    assert _deadline(session) == started_at + timedelta(minutes=30)
    with pytest.raises(ValidationError):
        RecoverySnapshotRequest.model_validate({
            "current_question_id": "q-1",
            "remaining_seconds": 999999,
            "client_time": "2099-01-01T00:00:00Z",
        })


@pytest.mark.asyncio
async def test_sse_replay_resumes_after_last_event_id_without_duplicates():
    buffer = SSEReplayBuffer()
    async def source():
        for content in ("A", "B", "C"):
            yield f'data: {{"type":"content","content":"{content}"}}\n\n'

    stream_id = await buffer.start(source(), "student-1", "chat-1")
    first_connection = buffer.subscribe(stream_id, "student-1", "chat-1")
    opening = await anext(first_connection)
    first = await anext(first_connection)
    await first_connection.aclose()  # simulate the browser going offline
    await buffer._streams[stream_id].task
    assert opening.startswith("id: 0\n") and first.startswith("id: 1\n")

    resumed = [event async for event in buffer.subscribe(stream_id, "student-1", "chat-1", 1)]
    assert [event.splitlines()[0] for event in resumed] == ["id: 2", "id: 3"]
    assert "\"B\"" in resumed[0] and "\"C\"" in resumed[1]


@pytest.mark.asyncio
async def test_sse_replay_is_scoped_to_the_real_user_and_session():
    buffer = SSEReplayBuffer()
    stream_id = await buffer.create("student-1", "chat-1")
    await buffer.append(stream_id, "student-1", "chat-1", 'data: {}\n\n')
    with pytest.raises(LookupError):
        await buffer.replay(stream_id, "student-2", "chat-1", -1)
    with pytest.raises(LookupError):
        await buffer.replay(stream_id, "student-1", "chat-2", -1)
