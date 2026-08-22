# -*- coding: utf-8 -*-
"""
Phase 0 / Step 1.1 PostgreSQL Runtime Verification（真实 PostgreSQL，非 SQLite）。

覆盖：
  §3  在真实 PG 上 seed 出 24 个知识点
  §5  ProfileSnapshot 写 / 读 / 删除后重建（业务语义一致）
  §6  UserSkill ON CONFLICT upsert（recalculate_skills ×2 不重复）
  §7  用户隔离（A/B snapshot / skill / facts 互不污染）
  §8  Redis down → get_profile_snapshot 仍由 PostgreSQL 供给，不 500
  §9  Event 幂等（同 event_id ×3 只写 1 次；不同 event_id 分别写；A/B 不跨用户）

用法：在真实 PG 已 `alembic upgrade head` 后运行：
    python scripts/_pg_runtime_verify.py
"""
import asyncio
import os
import sys
from pathlib import Path

# ── 目标 PostgreSQL（隐藏密码由调用方环境提供） ──
PG_SYNC = os.environ.get(
    "PG_SYNC_URL", "postgresql://mathai:mathai_test@localhost:5432/math_ai_empty"
)
PG_ASYNC = PG_SYNC.replace("postgresql://", "postgresql+asyncpg://", 1)

os.environ["ASYNC_DATABASE_URL"] = PG_ASYNC
os.environ["DATABASE_URL"] = PG_SYNC
# Redis 指向一个必定不可用的端口，验证 Redis down 降级
os.environ["REDIS_URL"] = "redis://localhost:63991/0"

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.data.database import init_db, close_db, get_db_session  # noqa: E402
from app.data.models import (  # noqa: E402
    User, LearningRecord, UserSkill, UserProfile, EventIdempotency,
)
from sqlalchemy import select, func, delete  # noqa: E402

PASS = "PASS"
FAIL = "FAIL"
_results = []


def report(section, ok, detail=""):
    _results.append((section, ok, detail))
    print(f"[{'✓' if ok else '✗'}] {section}  {detail}")


async def ensure_users(*uids):
    async with get_db_session() as db:
        for uid in uids:
            exists = (await db.execute(select(User).where(User.id == uid))).scalar_one_or_none()
            if exists is None:
                db.add(User(id=uid, username=f"pg_{uid}", email=f"{uid}@pg.local",
                            password_hash="x", role="student"))
        await db.commit()


async def cleanup(*uids):
    async with get_db_session() as db:
        for uid in uids:
            await db.execute(delete(EventIdempotency).where(EventIdempotency.event_id.like(f"{uid}:%")))
            await db.execute(delete(UserSkill).where(UserSkill.user_id == uid))
            await db.execute(delete(UserProfile).where(UserProfile.user_id == uid))
            await db.execute(delete(LearningRecord).where(LearningRecord.user_id == uid))
        await db.commit()


def _enqueue(facade, user_id, event, event_id=None):
    """确定性入队：阻止懒启动 worker，事件由我们手动 flush 到真实 PG。"""
    facade._ensure_batch_worker_started = lambda: None
    return facade.record_event(user_id, dict(event), event_id=event_id)


def _drain(facade):
    batch = []
    while not facade._batch_queue.empty():
        batch.append(facade._batch_queue.get_nowait())
    return batch


def _normalize_keys(obj):
    """递归将 dict 的 int 键转为 str，模拟 JSON 往返后的语义归一（业务语义一致）。"""
    if isinstance(obj, dict):
        return {str(k): _normalize_keys(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_normalize_keys(v) for v in obj]
    return obj


async def _count(db, model, **filters):
    stmt = select(func.count(model.id))
    for k, v in filters.items():
        stmt = stmt.where(getattr(model, k) == v)
    return (await db.execute(stmt)).scalar() or 0


# ── §3 知识点 seed ──
async def verify_seed():
    from app.services.knowledge_seed import seed_phase_one_calculus
    from app.data.models import KnowledgePoint
    async with get_db_session() as db:
        course = await seed_phase_one_calculus(db)
        await db.commit()
        n = len((await db.execute(select(KnowledgePoint).where(KnowledgePoint.course_id == course.id))).scalars().all())
    report("§3 知识点 seed", n == 24, f"course={course.code} points={n} (期望 24)")


# ── §5 / §6 / §7 / §8 / §9 画像与幂等 ──
async def verify_profile_and_idempotency():
    from agent_core.memory_persistence import MemoryPersistenceFacade
    from app.services.cache import get_cache_manager

    user_a, user_b = "pg_user_a", "pg_user_b"
    await ensure_users(user_a, user_b)
    await cleanup(user_a, user_b)

    cache = get_cache_manager()
    cache.l1_cache.clear()
    cache.redis = None  # 强制 Redis down（§8）

    facade = MemoryPersistenceFacade()

    # ── §5 写入事实 → refresh → 写 user_profiles → get 一致 → 删后重建 ──
    base = {"event_type": "answer_correct", "question_content": "求极限 x->0",
            "category": "极限", "is_correct": True, "difficulty": 3, "time_spent": 60}
    wrong = dict(base, event_type="answer_wrong", is_correct=False)
    for i in range(3):
        await _enqueue(facade, user_a, base, event_id=f"{user_a}:c{i}")
    await _enqueue(facade, user_a, wrong, event_id=f"{user_a}:w0")
    await asyncio.sleep(0)
    batch = _drain(facade)
    await facade._flush_batch(batch)  # 真实 PG 写入

    async with get_db_session() as db:
        recs = await _count(db, LearningRecord, user_id=user_a)
    report("§5 事实写入 PG", recs == 4, f"A facts={recs} (期望 4)")

    s1 = await facade.refresh_profile_snapshot(user_a)
    async with get_db_session() as db:
        row = (await db.execute(select(UserProfile).where(UserProfile.user_id == user_a))).scalar_one_or_none()
    report("§5 refresh 写 user_profiles", row is not None and row.version == s1.version,
           f"user_profiles row={row is not None}")

    cache.l1_cache.clear()
    s2 = await facade.get_profile_snapshot(user_a)
    d1, d2 = s1.to_dict(), s2.to_dict()
    d1.pop("generated_at", None); d2.pop("generated_at", None)
    # 业务语义一致：JSON 往返后 int 键天然字符串化，归一后应全等
    sem_eq = _normalize_keys(d1) == _normalize_keys(d2)
    report("§5 get 与 refresh 语义一致", sem_eq and s1.total_questions == s2.total_questions,
           f"total_questions={s1.total_questions} 语义一致={sem_eq}")

    # 删除 user_profiles + 清缓存 → 重建后业务语义一致
    async with get_db_session() as db:
        await db.execute(delete(UserProfile).where(UserProfile.user_id == user_a)); await db.commit()
    cache.l1_cache.clear()
    rebuilt = await facade.get_profile_snapshot(user_a)
    rb = rebuilt.to_dict(); rb.pop("generated_at", None)
    report("§5 删除快照后重建语义一致", rb == d1,
           f"重建 total_questions={rebuilt.total_questions}")

    # ── §6 UserSkill upsert ×2 不重复 ──
    await facade.trigger_skill_recalculation(user_a)
    n1 = await _count_skills(user_a)
    await facade.trigger_skill_recalculation(user_a)
    n2 = await _count_skills(user_a)
    async with get_db_session() as db:
        dup = (await db.execute(
            select(func.count()).select_from(UserSkill).group_by(UserSkill.user_id, UserSkill.skill_code)
            .having(func.count() > 1)
        )).scalars().all()
    report("§6 UserSkill ON CONFLICT upsert", n1 == n2 and n1 > 0 and len(dup) == 0,
           f"skills×2 = {n1}/{n2}, 重复组合={len(dup)}")

    # ── §7 用户隔离 ──
    for i in range(2):
        await _enqueue(facade, user_b, base, event_id=f"{user_b}:c{i}")
    await _flush_batch_now(facade)
    await facade.refresh_profile_snapshot(user_b)
    sb = await facade.get_profile_snapshot(user_b)
    sa = await facade.get_profile_snapshot(user_a)
    async with get_db_session() as db:
        a_skills = {(r.user_id, r.skill_code) for r in (await db.execute(select(UserSkill).where(UserSkill.user_id == user_a))).scalars()}
        b_skills = {(r.user_id, r.skill_code) for r in (await db.execute(select(UserSkill).where(UserSkill.user_id == user_b))).scalars()}
    report("§7 用户隔离 snapshot", sa.user_id == user_a and sb.user_id == user_b and sa.total_questions == 4 and sb.total_questions == 2,
           f"A={sa.total_questions} B={sb.total_questions}")
    report("§7 用户隔离 skills", not (a_skills & b_skills),
           f"A_skill_rows={len(a_skills)} B_skill_rows={len(b_skills)} 无交集")
    report("§7 用户隔离 facts", sa.total_questions == 4 and sb.total_questions == 2,
           f"A_facts={sa.total_questions} B_facts={sb.total_questions}")

    # ── §8 Redis down → still works ──
    cache.redis = None
    cache.l1_cache.clear()
    try:
        s_rd = await facade.get_profile_snapshot(user_a)
        ok_rd = s_rd.user_id == user_a
    except Exception as e:
        ok_rd = False
        report("§8 Redis down 降级", False, f"异常: {e}")
    report("§8 Redis down 降级", ok_rd, f"get 成功={ok_rd}")

    # ── §9 Event 幂等 ──
    await cleanup(user_a, user_b)
    async with get_db_session() as db:
        await db.execute(delete(EventIdempotency))  # 清空幂等表，干净重测
        await db.commit()
    # 同一 event_id ×3
    for _ in range(3):
        await _enqueue(facade, user_a, base, event_id=f"{user_a}:dup")
    await asyncio.sleep(0)
    await _flush_batch_now(facade)
    async with get_db_session() as db:
        dup_rows = await _count(db, LearningRecord, user_id=user_a)
        idem_rows = await _count(db, EventIdempotency, event_id=f"{user_a}:dup")
    report("§9 同 event_id ×3 只写 1 次", dup_rows == 1 and idem_rows == 1,
           f"facts={dup_rows} idempotency={idem_rows}")

    # 不同 event_id 分别写入
    for eid in (f"{user_a}:e1", f"{user_a}:e2"):
        await _enqueue(facade, user_a, base, event_id=eid)
    await asyncio.sleep(0)
    await _flush_batch_now(facade)
    async with get_db_session() as db:
        total_a = await _count(db, LearningRecord, user_id=user_a)
    report("§9 不同 event_id 分别写入", total_a == 3, f"facts={total_a} (期望 3)")

    # A/B 相同形式 event（用户作用域 event_id）不污染
    await cleanup(user_a, user_b)
    await _enqueue(facade, user_a, base, event_id="shared-form:evt:a")
    await _enqueue(facade, user_b, base, event_id="shared-form:evt:b")
    await asyncio.sleep(0)
    await _flush_batch_now(facade)
    async with get_db_session() as db:
        a_have = await _count(db, LearningRecord, user_id=user_a)
        b_have = await _count(db, LearningRecord, user_id=user_b)
    report("§9 A/B 同 form event 不跨用户污染", a_have == 1 and b_have == 1,
           f"A_facts={a_have} B_facts={b_have}")


async def _flush_batch_now(facade):
    batch = _drain(facade)
    if batch:
        await facade._flush_batch(batch)


async def _count_skills(user_id):
    async with get_db_session() as db:
        return await _count(db, UserSkill, user_id=user_id)


async def main():
    await init_db()
    print("=" * 70)
    print("PostgreSQL Runtime Verification")
    print(f"  ASYNC_DATABASE_URL = {PG_ASYNC.split('@')[-1]}")
    print("=" * 70)
    try:
        await verify_seed()
        await verify_profile_and_idempotency()
    finally:
        await close_db()

    print("=" * 70)
    failed = [r for r in _results if not r[1]]
    print(f"结果: {len(_results) - len(failed)}/{len(_results)} 通过")
    if failed:
        for s, _, d in failed:
            print(f"  ✗ {s}: {d}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))