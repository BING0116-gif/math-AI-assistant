import sys
import os
import asyncio

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.services.event_buffer import EnhancedEventBuffer, BufferedEvent
from app.data.database import init_db
from agent_core.memory_persistence import MemoryPersistenceFacade


async def test_buffer():
    buf = EnhancedEventBuffer(batch_size=2)
    await buf.add(BufferedEvent("u1", "q", "t1", "x", {}))
    await buf.add(BufferedEvent("u1", "q", "t2", "x", {}))
    await asyncio.sleep(0.2)
    assert buf.buffer_size == 0, f"Expected 0, got {buf.buffer_size}"
    print(f"Buffer flush: OK")

    buf2 = EnhancedEventBuffer(batch_size=10)
    assert await buf2.add(BufferedEvent("u1", "q", "same", "x", {}))
    assert not await buf2.add(BufferedEvent("u1", "q", "same", "x", {}))
    assert buf2.buffer_size == 1
    print(f"Dedup: OK")

    buf3 = EnhancedEventBuffer(batch_size=100)
    for i in range(5):
        await buf3.add(BufferedEvent("u1", "q", f"t{i}", "x", {}))
    assert buf3.buffer_size == 5
    count = await buf3.force_flush()
    assert count == 5
    assert buf3.buffer_size == 0
    print(f"Force flush: OK")

    print("EventBuffer tests PASSED")


async def test_facade_no_db():
    f = MemoryPersistenceFacade()
    assert f.should_persist("problem_solving") == True
    assert f.should_persist("casual_chat") == False
    print("Intent persist map: OK")

    config = f.get_persistence_config("error_analysis")
    assert config["ttl_days"] == 180
    assert config["persist"] == True
    print("Persistence config: OK")

    print("Facade (no-DB) tests PASSED")


async def test_facade_with_db():
    f = MemoryPersistenceFacade()
    p = await f.get_profile("test_user")
    d = p.to_dict()
    required = ["total_questions", "correct_rate", "weak_points",
                "strong_points", "skills", "error_patterns"]
    for field in required:
        assert field in d, f"Missing field: {field}"
    print(f"Profile fields: OK ({len(d)} fields)")

    c = p.to_compact_json(1000)
    assert len(c) <= 1000
    print(f"Compact JSON: OK (len={len(c)})")

    ok = await f.record_event("test", {
        "event_type": "answer_correct",
        "question_content": "test",
        "category": "test",
        "is_correct": True,
    })
    print(f"Record event: {'OK' if ok else 'FAILED'}")
    assert ok

    print("Facade (with-DB) tests PASSED")


async def test_dag():
    from app.services.math_skill_dag import MathSkillDAG
    dag = MathSkillDAG()
    codes = dag.get_all_skill_codes()
    assert len(codes) >= 20
    assert dag.can_learn("basic_operations", set())
    assert not dag.can_learn("trig_sum_formula", set())
    print(f"MathSkillDAG OK: {len(codes)} nodes")

    unlocks = dag.get_unlocks("basic_operations")
    assert "linear_equations" in unlocks
    print(f"Unlocks: OK ({len(unlocks)} unlocked)")


async def test_difficulty():
    from app.services.difficulty_estimator import DifficultyEstimator
    est = DifficultyEstimator()
    d = await est.estimate("test", "三角函数", "和角公式")
    assert 1 <= d <= 5
    print(f"DifficultyEstimator OK: d={d}")

    d2 = await est.estimate("test", "极限", "",
                             profile={"correct_rate": 0.95})
    assert d2 >= d
    print(f"High rate: d={d2} (>= {d})")


async def test_classification():
    from app.services.memory import LongTermMemory, EventClassification
    from app.data.database import get_db_session
    ltm = LongTermMemory(get_db_session)
    r = ltm._classify_fallback({
        "question_content": "求积分 x dx",
        "is_correct": True,
    })
    assert r.category == "积分", f"Expected 积分, got {r.category}"
    print(f"Classification fallback: OK (category={r.category})")


async def main():
    print("=" * 50)
    print("A03 Quick Verification")
    print("=" * 50)

    await test_buffer()
    await test_dag()
    await test_difficulty()
    await test_classification()

    await init_db()
    print("DB initialized")

    await test_facade_no_db()
    await test_facade_with_db()

    print("=" * 50)
    print("All tests PASSED!")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())