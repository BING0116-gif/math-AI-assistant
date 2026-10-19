import asyncio
import inspect

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.tasks.scheduled_tasks import MemoryScheduledTasks


@pytest.mark.asyncio
async def test_scheduled_database_jobs_keep_application_loop(monkeypatch):
    from app.services import proactive_learning, feature_flags

    loop = asyncio.get_running_loop()
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    calls = []

    async def database_job():
        assert asyncio.get_running_loop() is loop
        async with engine.connect() as connection:
            assert await connection.scalar(text("SELECT 1")) == 1
        calls.append(True)
        return {}

    ids = ["generate_due_reviews", "refresh_daily_plans", "detect_learning_stall",
           "detect_repeated_errors", "send_goal_deadline_reminder",
           "reconcile_plan_task_status"]
    for name in ids:
        monkeypatch.setattr(proactive_learning, name, database_job)
    monkeypatch.setattr(feature_flags, "evaluate_flag_guardrails", database_job)
    tasks = MemoryScheduledTasks()
    try:
        tasks.start_scheduler()
        for job in tasks._scheduler.get_jobs():
            assert inspect.iscoroutinefunction(job.func), job.id
        for _ in range(3):
            for name in ids + ["evaluate_flag_guardrails"]:
                await tasks._scheduler.get_job(name).func()
        assert len(calls) == 21
    finally:
        tasks.stop_scheduler()
        await asyncio.sleep(0)
        await engine.dispose()
