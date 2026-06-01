"""
A03 开发验证门禁 — 每次提交前必须运行并通过
用法: python scripts/a03_verify.py --level V0|V1|V2|V3

V0 = 基础设施 (T0 完成后)
V1 = 核心功能 (T1+T2 完成后)
V2 = 增强层 (T3+T4 完成后)
V3 = 全量 (所有 Task 完成后)
"""

import sys
import os
import asyncio
import traceback

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def check_import(module_path: str, name: str) -> bool:
    try:
        __import__(module_path)
        print(f"  [PASS] {name}")
        return True
    except Exception as e:
        print(f"  [FAIL] {name}: {e}")
        return False


async def check_db_table(table_name: str) -> bool:
    try:
        from app.data.database import get_db_session

        async with get_db_session() as db:
            from sqlalchemy import text
            result = await db.execute(
                text(f"SELECT COUNT(*) FROM {table_name}")
            )
            count = result.scalar()
            return True
    except Exception as e:
        if "does not exist" in str(e).lower() or "no such table" in str(e).lower():
            print(f"  [WARN] Table {table_name} does not exist (migration may not have run)")
            return False
        raise


async def run_v0():
    print("\n[CHECK] V0: Infrastructure")
    results = []
    results.append(check_import("app.data.models", "UserSkill ORM"))
    results.append(await check_db_table("user_skills"))
    return all(results)


async def run_v1():
    print("\n[CHECK] V1: Core Features")
    results = []
    results.append(await run_v0())
    results.append(check_import("agent_core.memory_persistence", "MemoryPersistenceFacade"))
    results.append(check_import("agent_core.memory_persistence", "UserProfile"))

    try:
        from agent_core.memory_persistence import MemoryPersistenceFacade
        facade = MemoryPersistenceFacade()
        profile = await facade.get_profile("__verify_test__")
        assert hasattr(profile, 'to_dict')
        assert 'total_questions' in profile.to_dict()
        assert len(profile.to_compact_json(1000)) <= 1000
        print("  [PASS] Facade.get_profile() OK")
        results.append(True)
    except Exception as e:
        print(f"  [FAIL] Facade error: {e}")
        results.append(False)

    try:
        from app.services.memory import LongTermMemory
        from app.data.database import get_db_session
        ltm = LongTermMemory(get_db_session)
        r = ltm._classify_fallback({
            'question_content': '求积分 x dx',
            'is_correct': True,
        })
        assert r.category == "积分"
        print("  [PASS] _classify_fallback keyword fallback OK")
        results.append(True)
    except Exception as e:
        print(f"  [FAIL] Classification fallback: {e}")
        results.append(False)

    return all(results)


async def run_v2():
    print("\n[CHECK] V2: Enhanced Layer")
    results = []
    results.append(await run_v1())

    results.append(check_import("app.services.event_buffer", "EnhancedEventBuffer"))
    try:
        from app.services.event_buffer import EnhancedEventBuffer, BufferedEvent
        buf = EnhancedEventBuffer(batch_size=3)
        for i in range(3):
            await buf.add(BufferedEvent("v", "q", f"t{i}", "x", {}))
        await asyncio.sleep(0.15)
        assert buf.buffer_size == 0
        print("  [PASS] EventBuffer batch flush OK")
        results.append(True)
    except Exception as e:
        print(f"  [FAIL] EventBuffer: {e}")
        results.append(False)

    results.append(check_import("app.services.skill_aggregator", "SkillAggregator"))
    results.append(check_import("app.services.math_skill_dag", "MathSkillDAG"))
    results.append(check_import("app.services.difficulty_estimator", "DifficultyEstimator"))

    try:
        from app.services.math_skill_dag import MathSkillDAG
        dag = MathSkillDAG()
        codes = dag.get_all_skill_codes()
        assert len(codes) >= 20
        assert dag.can_learn("basic_operations", set())
        assert not dag.can_learn("trig_sum_formula", set())
        print(f"  [PASS] MathSkillDAG ({len(codes)} nodes)")
        results.append(True)
    except Exception as e:
        print(f"  [FAIL] MathSkillDAG: {e}")
        results.append(False)

    try:
        from app.services.difficulty_estimator import DifficultyEstimator
        est = DifficultyEstimator()
        d = await est.estimate("__verify__", "三角函数", "和角公式")
        assert 1 <= d <= 5
        print(f"  [PASS] DifficultyEstimator -> d={d}")
        results.append(True)
    except Exception as e:
        print(f"  [FAIL] DifficultyEstimator: {e}")
        results.append(False)

    return all(results)


async def run_v3():
    print("\n[CHECK] V3: Full Verification")
    results = []
    results.append(await run_v2())

    results.append(check_import("agent_core.metrics", "get_metrics_response"))

    try:
        from agent_core.memory_persistence import MemoryPersistenceFacade
        facade = MemoryPersistenceFacade()
        assert facade.should_persist("problem_solving") == True
        assert facade.should_persist("casual_chat") == False
        assert facade.get_persistence_config("error_analysis")["ttl_days"] == 180
        print("  [PASS] Intent->Persistence mapping OK")
        results.append(True)
    except Exception as e:
        print(f"  [FAIL] Intent mapping: {e}")
        results.append(False)

    print("\n[INFO] V3 suggestion: run pytest tests/test_memory_persistence.py -v")

    return all(results)


LEVELS = {
    "V0": ("After T0", run_v0),
    "V1": ("After T1+T2", run_v1),
    "V2": ("After T3+T4", run_v2),
    "V3": ("After ALL tasks", run_v3),
}


async def main():
    args = sys.argv[1:]
    level = "V3"
    for i, a in enumerate(args):
        if a in ("--level", "-l") and i + 1 < len(args):
            level = args[i + 1]
        elif a.upper() in LEVELS:
            level = a.upper()

    if level not in LEVELS:
        print(f"[ERROR] Invalid level: {level}, options: {list(LEVELS.keys())}")
        sys.exit(1)

    desc, fn = LEVELS[level]
    print("=" * 50)
    print(f"A03 Verification Gate — Level {level} ({desc})")
    print("=" * 50)

    from app.data.database import init_db
    await init_db()
    print("[INFO] Database initialized")

    try:
        passed = await fn()
        print(f"\n{'=' * 50}")
        if passed:
            print(f"[PASS] Level {level} ALL PASSED — safe to commit")
            print("=" * 50)
            sys.exit(0)
        else:
            print(f"[FAIL] Level {level} FAILED — fix before commit")
            print("=" * 50)
            sys.exit(1)
    except Exception as e:
        print(f"\n[FATAL] Verify script exception: {e}")
        traceback.print_exc()
        sys.exit(2)


if __name__ == "__main__":
    asyncio.run(main())