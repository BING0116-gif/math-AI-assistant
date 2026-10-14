"""演示学生 8 周学习数据种子脚本。

为可登录的演示账号 demo_student 灌入 8 周真实感学习数据，让画像页、学习看板、
错题本、知识图谱个性化、今日复习/提醒、记忆面板全部有内容可演示。

设计原则（变更安全）：
- 所有学习事实走正式 service 链路：create_session → start_session → submit_attempt
  → complete_session。submit_attempt 内部完成判分、错题捕获（capture_wrong_attempt）、
  learning_records 写入、学习投影重建，保证与真实练习完全同口径。
- 时间戳回拨：service 写入用当前时间，脚本在每场练习后把该场次所有行
  （session/attempt/learning_record/error_item/error_review_event）回拨到计划日期；
  最后重跑一次 rebuild_learning_projections，复习排期按回拨后的时间重算，
  旧知识点自然产生"逾期待复习"。
- 幂等：练习会话/作答用确定性幂等键，活动会话用确定性 client_session_id，
  记忆按内容去重；重跑整个脚本结果一致。
- 数据归属：全部挂在通过 register_user 创建的真实 users.id 上，无默认用户。

运行：venv/Scripts/python.exe scripts/seed_demo_student.py
"""

from __future__ import annotations

import asyncio
import os
import random
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DEMO_USERNAME = "demo_student"
DEMO_PASSWORD = "demo123456"
DEMO_SEED = 20261011
COURSE_CODE = "advanced-calculus"
ALL_TYPES = ["choice", "judge", "numeric_fill", "expression_fill"]

# 各周正确率（进步曲线），弱项知识点额外降低
WEEK_ACCURACY = [0.55, 0.60, 0.65, 0.68, 0.72, 0.75, 0.80, 0.85]
STRONG_KPS = {"function-definition", "function-domain-range", "important-limits",
              "squeeze-theorem", "limit-arithmetic-laws", "elementary-functions"}
WEAK_KPS = {"equivalent-infinitesimal", "monotone-convergence",
            "discontinuity-classification", "left-right-limit", "infinitesimal"}

# 8 周学习旅程：按章节推进，第 4/6/8 周穿插间隔复习（spaced_review 证据）
JOURNEY = [
    # week 0：函数基础
    [("function-definition",), ("function-domain-range",), ("function-definition", "elementary-functions")],
    # week 1：函数性质与运算
    [("function-properties",), ("composite-function",), ("piecewise-function", "function-arithmetic")],
    # week 2：极限概念
    [("sequence-limit",), ("function-limit",), ("left-right-limit",)],
    # week 3：极限性质与无穷小
    [("limit-properties",), ("infinitesimal",), ("limit-arithmetic-laws", "function-limit")],
    # week 4：极限计算 + 首次间隔复习
    [("important-limits",), ("equivalent-infinitesimal",), ("REVIEW", "important-limits"), ("squeeze-theorem",)],
    # week 5：连续性
    [("continuity-definition",), ("discontinuity-classification",), ("composite-continuity", "continuity-properties")],
    # week 6：闭区间性质 + 间隔复习
    [("intermediate-value-theorem",), ("REVIEW", "squeeze-theorem"), ("closed-interval-properties",), ("discontinuity-classification",)],
    # week 7：弱项综合 + 间隔复习（最近一周，看板 7d 有数据）
    [("equivalent-infinitesimal", "monotone-convergence"), ("REVIEW", "limit-arithmetic-laws"),
     ("left-right-limit", "continuity-definition"), ("monotone-convergence",)],
]

TIME_BY_DIFF = {1: (50, 90), 2: (80, 140), 3: (110, 200), 4: (160, 280)}

MEMORIES = [
    (48, "mastery_evidence", "知识点掌握", "function-definition",
     "已系统掌握函数定义与定义域求解，定义域类题目正确率稳定在 90% 以上。",
     "函数定义与定义域：已掌握，正确率 90%+", 0.8, "mastery"),
    (41, "mastery_evidence", "知识点掌握", "composite-function",
     "复合函数与分段函数的复合运算熟练，能正确处理分层代入与定义域传递。",
     "复合函数分层代入：熟练", 0.75, "mastery"),
    (34, "mastery_evidence", "知识点掌握", "important-limits",
     "两个重要极限及其变形运用自如，1^∞ 型极限处理正确率高。",
     "重要极限与 1^∞ 型：掌握扎实", 0.85, "mastery"),
    (27, "mastery_evidence", "学习表现", "squeeze-theorem",
     "夹逼定理使用规范，能主动构造上下界处理振荡型极限。",
     "夹逼定理：能主动构造上下界", 0.7, "mastery"),
    (20, "mastery_evidence", "薄弱环节", "equivalent-infinitesimal",
     "等价无穷小替换时偶尔忽略适用条件，涉及高阶展开的题目易错。",
     "等价无穷小：复杂展开易错，需巩固", 0.75, "mastery"),
    (13, "mastery_evidence", "薄弱环节", "monotone-convergence",
     "递推数列「先估界、再定单调方向」的论证步骤仍需巩固，方向易判反。",
     "递推数列：单调方向易判反", 0.65, "mastery"),
    (9, "mastery_evidence", "学习表现", "discontinuity-classification",
     "间断点分类判定进步明显，第二类无穷间断点与可去间断点区分准确。",
     "间断点分类：近期进步明显", 0.7, "mastery"),
    (6, "conversation", "学习偏好", "study-habit",
     "偏好先自己尝试再查看解析；习惯晚上 8-11 点练习，单次 20-40 分钟。",
     "学习习惯：晚间练习，先做后看解析", 0.6, "context"),
    (3, "conversation", "学习目标", "goal",
     "目标：期末高等数学 90 分以上，重点补强极限计算综合题与证明题表述。",
     "目标：期末 90+，主攻极限计算", 0.65, "context"),
]


def build_plan(rng: random.Random):
    """生成 21 场练习的时间与知识点计划：(days_ago, kps, is_review)。"""
    plan = []
    for week, week_plan in enumerate(JOURNEY):
        base = 55 - 7 * week
        offsets = sorted(rng.sample(range(0, 7), len(week_plan)))
        for offset, entry in zip(offsets, week_plan):
            is_review = entry[0] == "REVIEW"
            kps = tuple(entry[1:]) if is_review else entry
            days_ago = max(0, base - offset)
            plan.append({"days_ago": days_ago, "kps": kps, "is_review": is_review, "week": week})
    # 保证最近有一场"今天"的练习（看板今日卡片有内容）
    plan[-1]["days_ago"] = 0
    return plan


def wrong_answer_for(spec: dict, options: list) -> object:
    kind = (spec or {}).get("kind")
    if kind == "choice":
        correct = str(spec.get("correct"))
        ids = [o["id"] for o in (options or []) if o.get("id") != correct]
        return ids[0] if ids else "Z"
    if kind == "judge":
        return not bool(spec.get("correct"))
    if kind == "numeric_fill":
        return "999999"
    return "0"


def correct_answer_for(spec: dict) -> object:
    kind = (spec or {}).get("kind")
    if kind == "choice":
        return str(spec.get("correct"))
    if kind == "judge":
        return bool(spec.get("correct"))
    if kind == "numeric_fill":
        return str(spec.get("value"))
    return str(spec.get("canonical"))


def session_base_time(now: datetime, days_ago: int, local: random.Random) -> datetime:
    """场次基准时间：只依赖 (days_ago, 每场独立随机源)，重跑结果一致。"""
    base = now - timedelta(days=days_ago)
    if days_ago == 0:
        base = now - timedelta(hours=3)
    base = base.replace(minute=10 * local.randint(0, 5), second=0, microsecond=0)
    if base >= now - timedelta(minutes=10):  # 未来时间裁剪（今天的场次）
        base = now - timedelta(minutes=90)
    return base


async def ensure_user():
    from app.middleware.auth import authenticate_user, register_user
    user = await register_user(DEMO_USERNAME, DEMO_PASSWORD)
    if user is None:
        user = await authenticate_user(DEMO_USERNAME, DEMO_PASSWORD)
    if user is None:
        raise RuntimeError("演示用户创建/登录失败")
    return user


async def get_course(db):
    from sqlalchemy import select
    from app.data.models import Course, KnowledgePoint
    course = (await db.execute(
        select(Course).where(Course.code == COURSE_CODE, Course.status == "active")
    )).scalars().first()
    if course is None or not course.default_version_id:
        raise RuntimeError("课程 advanced-calculus 不存在或没有默认知识版本")
    points = (await db.execute(select(KnowledgePoint).where(
        KnowledgePoint.course_id == course.id,
        KnowledgePoint.version_id == course.default_version_id))).scalars().all()
    return course, {p.code for p in points}


async def seed_one_session(user_id, idx, item, course, kp_codes, rng, now):
    """创建 → 开始 → 逐题提交 → 完成一场练习；返回回拨所需信息。

    每场会话用独立随机源（seed 含 idx）；已完成会话走重放分支，从既有判分
    快照重建回拨目标（时间按同一确定性序列重算），任意次重跑结果一致。
    """
    from app.services.practice_service import complete_session, create_session, start_session, submit_attempt
    from sqlalchemy import select
    from app.data.database import get_db_session
    from app.data.models import PracticeSession, Question, ReviewSchedule

    local = random.Random(f"{DEMO_SEED}:{idx}")
    kps = list(item["kps"])
    unknown = set(kps) - set(kp_codes)
    if unknown:
        print(f"  [skip] 场次{idx}: 知识点不存在 {unknown}")
        return None

    # 重放判定：按幂等键直查既有会话（绕开 create_session 的配置比对）
    from sqlalchemy.orm import selectinload
    prior = None
    async with get_db_session() as db:
        prior = (await db.execute(
            select(PracticeSession).where(
                PracticeSession.user_id == user_id,
                PracticeSession.idempotency_key == f"demo-seed:s{idx:02d}",
            ).options(selectinload(PracticeSession.questions),
                      selectinload(PracticeSession.attempts)))).scalars().first()

    is_replay = prior is not None
    base = session_base_time(now, item["days_ago"], local)
    attempt_times = []
    cursor = base

    if is_replay:
        session_id = prior.id
        for row in sorted(prior.questions, key=lambda r: r.position):
            attempt = next((a for a in prior.attempts if a.session_question_id == row.id), None)
            if attempt is None:
                continue
            snap = attempt.grading_snapshot or {}
            time_spent = int(((snap.get("learning_signals") or {}).get("time_spent_seconds")) or 120)
            cursor += timedelta(seconds=time_spent + local.randint(15, 60))
            attempt_times.append({"attempt_id": attempt.id, "at": cursor,
                                  "question_id": attempt.question_id,
                                  "time_spent": time_spent, "correct": bool(attempt.correct)})
    else:
        count = 3 if item["is_review"] else local.choice([4, 5])
        config = {
            "course_id": course.id, "version_id": course.default_version_id,
            "knowledge_point_codes": kps, "question_types": list(ALL_TYPES),
            "question_count": count, "random_seed": DEMO_SEED + idx,
            "idempotency_key": f"demo-seed:s{idx:02d}",
        }
        if item["is_review"]:
            async with get_db_session() as db:
                schedule = (await db.execute(
                    select(ReviewSchedule).where(
                        ReviewSchedule.user_id == user_id,
                        ReviewSchedule.knowledge_point_code == kps[0],
                    ).order_by(ReviewSchedule.id.desc()).limit(1))).scalars().first()
            if schedule is None:
                print(f"  [fallback] 场次{idx}: 无复习排期，改普通练习")
            else:
                config["review_schedule_id"] = schedule.id
                config["review_kind"] = "spaced_correct"

        payload = await create_session(user_id, config)
        session_id = payload["session_id"]
        await start_session(user_id, session_id)

        # 学生快照不含 answer_spec，从题目表取，用于生成对/错答案
        qids = [q["question_id"] for q in payload["questions"]]
        async with get_db_session() as db:
            rows = (await db.execute(
                select(Question).where(Question.id.in_(qids)))).scalars().all()
        spec_by_qid = {q.id: {"spec": q.answer_spec, "options": q.options} for q in rows}

        for q_pos, entry in enumerate(payload["questions"]):
            qid = entry["question_id"]
            info = spec_by_qid.get(qid)
            if not info or not info["spec"]:
                continue
            diff = int(entry.get("difficulty") or 3)
            lo, hi = TIME_BY_DIFF.get(diff, TIME_BY_DIFF[3])
            time_spent = local.randint(lo, hi)
            acc = WEEK_ACCURACY[item["week"]]
            if set(kps) & WEAK_KPS:
                acc -= 0.25
            if set(kps) & STRONG_KPS:
                acc += 0.12
            acc = min(0.95, max(0.3, acc))
            is_correct = rng.random() < acc
            if not is_correct:
                time_spent = int(time_spent * 1.4)
            answer = correct_answer_for(info["spec"]) if is_correct else wrong_answer_for(info["spec"], info["options"])
            signals = {
                "time_spent_seconds": time_spent,
                "hint_used": bool(not is_correct and local.random() < 0.3),
                "solution_viewed": bool(not is_correct and local.random() < 0.35),
            }
            result = await submit_attempt(
                user_id, session_id, qid, answer,
                key=f"demo-seed:s{idx:02d}:q{q_pos}", learning_signals=signals,
            )
            cursor += timedelta(seconds=time_spent + local.randint(15, 60))
            attempt_times.append({"attempt_id": result.get("attempt_id"), "at": cursor,
                                  "question_id": qid, "time_spent": time_spent,
                                  "correct": bool(is_correct)})

        await complete_session(user_id, session_id)
    total_active = sum(a["time_spent"] for a in attempt_times)
    correct_count = sum(1 for a in attempt_times if a["correct"])
    print(f"  [session {idx:02d}] {'复习' if item['is_review'] else '练习'} "
          f"{'+'.join(kps)} @ {base:%m-%d} 题数={len(attempt_times)} 正确={correct_count}"
          f"{'（重放）' if is_replay else ''}")
    return {"session_id": session_id, "base": base, "attempts": attempt_times,
            "total_active": total_active, "key": f"demo-seed:s{idx:02d}"}


async def backdate_session(session_info, user_id):
    """把一场练习产生的所有时间戳回拨到计划日期（幂等：目标值确定性）。"""
    from sqlalchemy import select
    from app.data.database import get_db_session
    from app.data.models import (ErrorItem, ErrorReviewEvent, LearningRecord,
                                 PracticeAttempt, PracticeSession)

    attempts = session_info["attempts"]
    if not attempts:
        return
    attempt_ids = [a["attempt_id"] for a in attempts if a["attempt_id"]]
    time_by_attempt = {a["attempt_id"]: a["at"] for a in attempts if a["attempt_id"]}
    last_time = max(time_by_attempt.values())
    async with get_db_session() as db:
        for attempt in (await db.execute(
                select(PracticeAttempt).where(PracticeAttempt.id.in_(attempt_ids)))).scalars():
            t = time_by_attempt[attempt.id]
            attempt.submitted_at = t
            snap = dict(attempt.grading_snapshot or {})
            for sub in snap.get("submissions") or []:
                sub["submitted_at"] = t.isoformat()
            attempt.grading_snapshot = snap
        for record in (await db.execute(
                select(LearningRecord).where(
                    LearningRecord.user_id == user_id,
                    LearningRecord.event_type == "practice_answer"))).scalars():
            aid = (record.metadata_ or {}).get("attempt_id")
            if aid in time_by_attempt:
                record.created_at = time_by_attempt[aid]
                record.time_spent = next(a["time_spent"] for a in attempts if a["attempt_id"] == aid)
        for err in (await db.execute(
                select(ErrorItem).where(
                    ErrorItem.user_id == user_id,
                    ErrorItem.last_attempt_id.in_(attempt_ids)))).scalars():
            t = time_by_attempt.get(err.last_attempt_id)
            if t:
                err.added_at = t.isoformat()
                err.created_at = t
                err.updated_at = t
                interval = int(err.review_interval_days or 1)
                err.next_review_at = t + timedelta(days=interval)
        if attempt_ids:
            for event in (await db.execute(
                    select(ErrorReviewEvent).where(
                        ErrorReviewEvent.attempt_id.in_(attempt_ids)))).scalars():
                t = time_by_attempt.get(event.attempt_id)
                if t:
                    event.created_at = t
        session = await db.get(PracticeSession, session_info["session_id"])
        if session:
            session.created_at = session_info["base"] - timedelta(minutes=10)
            session.started_at = session_info["base"]
            session.completed_at = last_time + timedelta(minutes=3)
            session.updated_at = session.completed_at
        await db.commit()


async def seed_activities(user_id, session_infos, rng):
    """学习活动会话：练习日 + 额外自学/答疑日（时长/热力图事实源）。"""
    from sqlalchemy import select
    from app.data.database import get_db_session
    from app.data.models import LearningActivitySession
    from datetime import timedelta

    now = datetime.now(timezone.utc)
    practice_days = {s["base"].date() for s in session_infos if s and s["base"]}
    practice_seconds = {}
    for s in session_infos:
        if s and s["base"]:
            practice_seconds[s["base"].date()] = practice_seconds.get(s["base"].date(), 0) + s["total_active"] + rng.randint(120, 420)

    entries = []
    for date in sorted(practice_days):
        entries.append((date, "practice", practice_seconds[date]))
    used = set(practice_days)
    extra_needed = 10
    for days_ago in range(55, -1, -1):
        if extra_needed <= 0:
            break
        date = (now - timedelta(days=days_ago)).date()
        if date in used or rng.random() < 0.75:
            continue
        used.add(date)
        context = "chat" if rng.random() < 0.5 else "knowledge"
        entries.append((date, context, rng.randint(600, 1800)))
        extra_needed -= 1

    created = 0
    async with get_db_session() as db:
        existing = set((await db.execute(
            select(LearningActivitySession.client_session_id).where(
                LearningActivitySession.user_id == user_id))).scalars())
        for i, (date, context, seconds) in enumerate(entries):
            client_sid = f"demo-seed-act-{date.isoformat()}-{context}"
            if client_sid in existing:
                continue
            start = datetime(date.year, date.month, date.day, 11, 30, tzinfo=timezone.utc) \
                + timedelta(minutes=rng.randint(0, 300))
            if start > now - timedelta(minutes=10):
                start = now - timedelta(minutes=30 + rng.randint(0, 60))
            end = start + timedelta(seconds=seconds + rng.randint(120, 600))
            db.add(LearningActivitySession(
                user_id=user_id, client_session_id=client_sid,
                context_type=context, context_id=None,
                started_at=start, last_heartbeat_at=end, ended_at=end,
                active_seconds=seconds, status="ended",
            ))
            created += 1
        await db.commit()
    print(f"[activity] 学习活动会话 +{created}（总计 {len(entries)} 天）")


async def seed_memories(user_id):
    """记忆面板数据：mastery_evidence 供画像证据链，conversation 供偏好展示。"""
    from sqlalchemy import select
    from app.data.database import get_db_session
    from app.data.models import Memory

    created = 0
    async with get_db_session() as db:
        existing = set((await db.execute(
            select(Memory.content).where(Memory.user_id == user_id))).scalars())
        now_epoch = int(datetime.now(timezone.utc).timestamp())
        for days_ago, mem_type, high_cat, cat, content, summary, importance, kind in MEMORIES:
            if content in existing:
                continue
            created_epoch = now_epoch - days_ago * 86400
            db.add(Memory(
                user_id=user_id, memory_type=mem_type, high_category=high_cat,
                category=cat, content=content, embedding_summary=summary,
                importance=importance, difficulty=None, status="active",
                expire_at=created_epoch + 180 * 86400, memory_strength=min(0.9, importance),
                source_id="demo-seed", created_at=created_epoch,
                last_accessed=created_epoch, access_count=rng_access(days_ago),
                confidence=0.85, memory_kind=kind, conflict_status="none",
            ))
            created += 1
        await db.commit()
    print(f"[memory] 记忆 +{created}（总计 {len(MEMORIES)} 条）")


def rng_access(days_ago: int) -> int:
    return max(1, 10 - days_ago // 7)


async def verify(user_id, course):
    from sqlalchemy import select, func
    from app.data.database import get_db_session
    from app.data.models import (ErrorItem, LearningActivitySession,
                                 LearningRecord, PracticeAttempt, ReviewSchedule)
    from app.services.learning_hub import due_reviews, unified_dashboard, unified_profile
    from app.services.reminders import build_reminders
    from app.services.knowledge_learning_map import build_learning_map
    from app.services.learning_path import build_learning_path
    from app.services.memory_store import get_memory_store

    checks = []

    async def check(name, ok, detail=""):
        checks.append((name, bool(ok), detail))
        print(f"  {'PASS' if ok else 'FAIL'}  {name} {detail}")

    d7 = await unified_dashboard(user_id, period="7d")
    metrics = d7.get("metrics") or {}
    active = (metrics.get("active_seconds") or {}).get("value") or 0
    accuracy = (metrics.get("accuracy") or {}).get("value") or 0
    await check("看板 7d 学习时长 > 0", active > 0, f"active_seconds={active}")
    await check("看板 7d 正确率 > 0", accuracy > 0, f"accuracy={accuracy}%")
    dims = d7.get("dimensions") or {}
    await check("看板 维度数据非空", bool(dims),
                f"mastery={dims.get('mastery')}")
    trend = d7.get("trend") or []
    await check("看板 7d 趋势非空", len(trend) > 0, f"points={len(trend)}")
    d30 = await unified_dashboard(user_id, period="30d")
    heat = (d30.get("heatmap") or d30.get("heat_map") or [])
    await check("看板 30d 热力图非空", len(heat) > 0, f"cells={len(heat)}")

    prof = await unified_profile(user_id)
    fc = prof.get("forgetting_curve") or {}
    insights = prof.get("insights") or []
    await check("画像 维度/复习计划非空", bool(prof.get("dimensions")) and bool(prof.get("review_plan")),
                f"forgetting_curve_status={fc.get('status') if isinstance(fc, dict) else fc}")
    await check("画像 洞察非空", bool(insights), f"insights={len(insights)}")

    due = await due_reviews(user_id)
    due_items = due.get("items") or due.get("schedules") or []
    await check("今日复习 到期项 > 0", len(due_items) > 0, f"due={len(due_items)}")
    reminders = await build_reminders(user_id)
    rem_items = reminders.get("items") or reminders.get("reminders") or []
    await check("提醒中心 非空", len(rem_items) > 0, f"reminders={len(rem_items)}")

    path = await build_learning_path(user_id)
    weeks = path.get("weeks") or []
    await check("学习路径 非空", len(weeks) > 0 and (path.get("weak_count") or 0) > 0,
                f"weeks={len(weeks)}, weak_points={path.get('weak_count')}")

    async with get_db_session() as db:
        attempts = (await db.execute(select(func.count()).select_from(PracticeAttempt)
                                     .where(PracticeAttempt.user_id == user_id))).scalar_one()
        records = (await db.execute(select(func.count()).select_from(LearningRecord)
                                    .where(LearningRecord.user_id == user_id))).scalar_one()
        errors = (await db.execute(select(func.count()).select_from(ErrorItem)
                                   .where(ErrorItem.user_id == user_id))).scalar_one()
        now = datetime.now(timezone.utc)
        due_errors = (await db.execute(select(func.count()).select_from(ErrorItem)
                                       .where(ErrorItem.user_id == user_id,
                                              ErrorItem.is_mastered.is_(False),
                                              ErrorItem.next_review_at <= now))).scalar_one()
        acts = (await db.execute(select(func.count()).select_from(LearningActivitySession)
                                 .where(LearningActivitySession.user_id == user_id))).scalar_one()
        schedules = (await db.execute(select(func.count()).select_from(ReviewSchedule)
                                      .where(ReviewSchedule.user_id == user_id))).scalar_one()
        lm = await build_learning_map(db, course.id, user_id)
    await check("错题本 非空且含逾期复习", errors > 0 and due_errors > 0,
                f"errors={errors}, due_errors={due_errors}")
    await check("学习图谱 个性化数据非空", lm is not None and bool(lm.get("points")),
                f"points={len((lm or {}).get('points') or [])}")
    await check("事实表行数", attempts > 50 and records > 50 and acts > 10 and schedules > 5,
                f"attempts={attempts}, records={records}, activities={acts}, schedules={schedules}")

    mems = await get_memory_store().list_user_memories(user_id)
    await check("记忆面板 非空", len(mems) > 0, f"memories={len(mems)}")

    from agent_core.memory_persistence import MemoryPersistenceFacade
    snap = await MemoryPersistenceFacade().get_profile_snapshot(user_id)
    skills = (snap.get("skills") if isinstance(snap, dict) else None) or getattr(snap, "skills", None)
    await check("画像快照 /api/profile/me 数据非空", bool(skills) or bool(snap),
                f"skills={len(skills) if hasattr(skills, '__len__') else 'n/a'}")

    ok = all(ok for _, ok, _ in checks)
    print(f"\nVERIFY = {'OK' if ok else 'FAILED'}")
    return ok


async def main():
    rng = random.Random(DEMO_SEED)
    from app.data.database import close_db, init_db, get_db_session
    from app.services.learning_projection import rebuild_learning_projections

    await init_db()
    user = await ensure_user()
    print(f"[user] 演示账号 user_id = {user.id}")
    async with get_db_session() as db:
        course, kp_codes = await get_course(db)
    print(f"[course] {course.name} version={course.default_version_id} 知识点 {len(kp_codes)} 个")

    plan = build_plan(rng)
    print(f"[plan] {len(plan)} 场练习，跨 8 周")
    now = datetime.now(timezone.utc)

    session_infos = []
    for idx, item in enumerate(plan):
        info = await seed_one_session(user.id, idx, item, course, kp_codes, rng, now)
        session_infos.append(info)
        if info:
            await backdate_session(info, user.id)

    await rebuild_learning_projections(user.id)
    print("[projection] 学习投影重建完成（掌握度 + 复习排期按回拨时间重算）")

    await seed_activities(user.id, session_infos, rng)
    await seed_memories(user.id)

    print("\n[verify] 按界面逐一验证：")
    ok = await verify(user.id, course)
    print(f"\n演示账号：{DEMO_USERNAME} / {DEMO_PASSWORD}（登录后即可看全部界面）")
    await close_db()
    return ok


if __name__ == "__main__":
    passed = asyncio.run(main())
    sys.exit(0 if passed else 1)
