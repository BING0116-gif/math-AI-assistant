"""阶段四 6.4 记忆冲突检测与仲裁回归测试。"""

import pytest

from app.services.memory_policy import (
    CONFIDENCE_AUTO_EXTRACTED,
    MEMORY_KIND_FACT,
    MEMORY_KIND_MISCONCEPTION,
    MEMORY_KIND_PREFERENCE,
)
from app.services.memory_store import MemoryStore


def test_decide_conflict_merge_on_high_similarity():
    action, status = MemoryStore.decide_conflict(
        kind=MEMORY_KIND_FACT, similarity=0.95, old_confidence=0.6, new_confidence=CONFIDENCE_AUTO_EXTRACTED
    )
    assert action == "merge" and status == "merged"


def test_decide_conflict_below_detect_line_keeps_both():
    action, status = MemoryStore.decide_conflict(
        kind=MEMORY_KIND_FACT, similarity=0.5, old_confidence=0.6, new_confidence=CONFIDENCE_AUTO_EXTRACTED
    )
    assert action == "keep_both" and status == "none"


def test_decide_conflict_preference_new_wins():
    action, status = MemoryStore.decide_conflict(
        kind=MEMORY_KIND_PREFERENCE, similarity=0.88, old_confidence=0.9, new_confidence=CONFIDENCE_AUTO_EXTRACTED
    )
    assert action == "supersede_old" and status == "superseded"


def test_decide_conflict_fact_higher_confidence_wins_and_close_goes_review():
    # 新记忆自动置信 0.5 < 旧 0.9 → 旧胜,双保留
    action, status = MemoryStore.decide_conflict(
        kind=MEMORY_KIND_FACT, similarity=0.88, old_confidence=0.9, new_confidence=CONFIDENCE_AUTO_EXTRACTED
    )
    assert action == "keep_old" and status == "none"
    # 置信接近 → 不可自动裁定,双保留进人工复核
    action, status = MemoryStore.decide_conflict(
        kind=MEMORY_KIND_FACT, similarity=0.88, old_confidence=0.55, new_confidence=CONFIDENCE_AUTO_EXTRACTED
    )
    assert action == "keep_review" and status == "review"


def test_decide_conflict_misconception_always_keeps_both():
    action, status = MemoryStore.decide_conflict(
        kind=MEMORY_KIND_MISCONCEPTION, similarity=0.88, old_confidence=0.6, new_confidence=CONFIDENCE_AUTO_EXTRACTED
    )
    assert action == "keep_both" and status == "none"


def test_cosine_similarity_handles_zero_and_mismatched():
    assert MemoryStore._cosine_similarity([1, 0], [1, 0]) == pytest.approx(1.0)
    assert MemoryStore._cosine_similarity([1, 0], [0, 1]) == pytest.approx(0.0)
    assert MemoryStore._cosine_similarity([1], [1, 0]) == 0.0
    assert MemoryStore._cosine_similarity([], []) == 0.0


@pytest.mark.asyncio
async def test_arbitration_disabled_by_default_is_noop(monkeypatch, tmp_path):
    import app.data.database as database
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from app.data.models import Base

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'conflict.db'}")
    monkeypatch.setattr(database, "async_session_factory", async_sessionmaker(engine, expire_on_commit=False))
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    store = MemoryStore()
    action = await store.arbitrate_memory_write(
        user_id="u1", memory_id=1, memory_type="conversation", content="内容"
    )
    assert action == "disabled"
    await engine.dispose()
