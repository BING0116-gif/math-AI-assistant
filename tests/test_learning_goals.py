import asyncio
import os
import tempfile
from datetime import datetime, timezone

import pytest


@pytest.fixture(scope="module", autouse=True)
def goal_db():
    folder = tempfile.mkdtemp(prefix="learning_goals_")
    os.environ["ASYNC_DATABASE_URL"] = f"sqlite+aiosqlite:///{folder}/goals.db"
    from app.data.database import close_db, init_db
    asyncio.run(init_db())
    yield
    asyncio.run(close_db())


@pytest.mark.asyncio
async def test_goal_progress_is_owner_scoped_and_fact_derived():
    from app.data.database import get_db_session
    from app.data.models import LearningActivitySession, LearningGoal, PracticeAttempt, User
    from app.services.learning_goals import create_goal, list_goals

    async with get_db_session() as db:
        db.add_all([
            User(id="goal-a", username="goal-a", email="goal-a@test", password_hash="x"),
            User(id="goal-b", username="goal-b", email="goal-b@test", password_hash="x"),
            LearningGoal(id="goal-minutes", user_id="goal-a", title="今天学习", goal_type="minutes", target_value=30),
        ])
        await db.commit()
    async with get_db_session() as db:
        db.add(LearningActivitySession(
            id="activity-goal-a", user_id="goal-a", client_session_id="goal-client-1",
            context_type="practice", started_at=datetime.now(timezone.utc),
            last_heartbeat_at=datetime.now(timezone.utc), active_seconds=900, status="ended",
        ))
        await db.commit()
    items = await list_goals("goal-a")
    assert items[0]["current_value"] == 15
    assert items[0]["percent"] == 50
    assert await list_goals("goal-b") == []
    created = await create_goal("goal-a", title="做题", goal_type="attempts", target_value=2)
    assert created["title"] == "做题"
