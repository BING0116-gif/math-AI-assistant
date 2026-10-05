"""阶段五 7.1/7.3 学习路径规则引擎回归测试(确定性 DoD)。"""

import pytest

from app.services.learning_path import (
    build_point_steps,
    generate_learning_path,
    pick_weak_points,
    topological_order,
)


def make_state(code, mastery, *, attempts=3, mistakes=2, variant=0.2, prerequisites=None, name=None):
    return {
        "knowledge_point_code": code,
        "name": name or code,
        "attempts_count": attempts,
        "mastery": mastery,
        "mistake_count": mistakes,
        "variant_performance": variant,
        "next_review_at": None,
        "prerequisites": prerequisites or [],
    }


def test_weak_points_require_evidence_and_low_mastery():
    states = [
        make_state("A", 0.3),            # 薄弱:有证据且低掌握
        make_state("B", 0.9),            # 非薄弱:掌握度高
        make_state("C", 0.2, attempts=0),  # 非薄弱:无作答证据(置信不可用)
    ]
    weak = pick_weak_points(states, threshold=0.6)
    assert [item["code"] for item in weak] == ["A"]


def test_prerequisite_comes_before_dependent():
    states = [
        make_state("导数应用", 0.2, prerequisites=["导数定义"]),
        make_state("导数定义", 0.3),
    ]
    ordered = topological_order(pick_weak_points(states, threshold=0.6))
    codes = [item["code"] for item in ordered]
    assert codes.index("导数定义") < codes.index("导数应用")


def test_cycle_is_broken_deterministically():
    states = [
        make_state("X", 0.3, prerequisites=["Y"]),
        make_state("Y", 0.2, prerequisites=["X"]),
    ]
    first = [item["code"] for item in topological_order(pick_weak_points(states, threshold=0.6))]
    second = [item["code"] for item in topological_order(pick_weak_points(states, threshold=0.6))]
    assert first == second  # 同快照唯一输出
    assert sorted(first) == ["X", "Y"]


def test_prerequisite_outside_weak_set_is_ignored():
    states = [make_state("进阶点", 0.2, prerequisites=["未薄弱点"])]
    ordered = topological_order(pick_weak_points(states, threshold=0.6))
    assert [item["code"] for item in ordered] == ["进阶点"]


def test_week_plan_chunks_by_capacity():
    states = [make_state(f"P{i}", 0.2 + i * 0.01) for i in range(7)]
    path = generate_learning_path(states, threshold=0.6, capacity=3)
    assert path["weak_count"] == 7
    assert [week["week"] for week in path["weeks"]] == [1, 2, 3]
    assert len(path["weeks"][0]["points"]) == 3
    assert len(path["weeks"][2]["points"]) == 1


def test_same_snapshot_yields_identical_path():
    states = [
        make_state("B", 0.4, prerequisites=["A"]),
        make_state("A", 0.3),
        make_state("C", 0.5, prerequisites=["B"]),
    ]
    assert generate_learning_path(states) == generate_learning_path(list(reversed(states)))


def test_step_template_statuses_derive_from_data():
    strong = {"code": "S", "name": "S", "mastery": 0.7, "attempts_count": 5, "mistake_count": 0, "variant_performance": 0.8, "prerequisites": []}
    weak = {"code": "W", "name": "W", "mastery": 0.2, "attempts_count": 3, "mistake_count": 2, "variant_performance": 0.1, "prerequisites": []}
    strong_steps = build_point_steps(strong)
    weak_steps = build_point_steps(weak)
    assert [step["status"] for step in strong_steps] == ["in_progress", "done", "done", "done"]
    assert weak_steps[1]["status"] == "in_progress" and weak_steps[2]["status"] == "pending"
    # 路由含知识点 code 占位
    assert strong_steps[0]["route"] == "/knowledge/S"


@pytest.mark.asyncio
async def test_build_learning_path_from_db(tmp_path, monkeypatch):
    import app.data.database as database
    from sqlalchemy import create_engine, select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from app.data.models import Base, Course, KnowledgeGraphVersion, KnowledgePoint, User, UserKnowledgeState
    from app.services.learning_path import build_learning_path

    db_file = tmp_path / "path.db"
    sync_engine = create_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(sync_engine)
    sync_engine.dispose()
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_file}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(database, "async_session_factory", factory)

    async with factory() as db:
        db.add(User(id="path-user", username="pu", email="pu@e.test", password_hash="x"))
        db.add(Course(id="c1", code="MATH1", name="高等数学", subject="math"))
        db.add(KnowledgeGraphVersion(id="v1", course_id="c1", version="1", name="V1"))
        db.add(KnowledgePoint(id="kp-a", course_id="c1", version_id="v1", chapter_id="ch1", code="极限", name="极限概念", prerequisites=[], status="active"))
        db.add(KnowledgePoint(id="kp-b", course_id="c1", version_id="v1", chapter_id="ch1", code="导数", name="导数应用", prerequisites=["极限"], status="active"))
        db.add(UserKnowledgeState(user_id="path-user", knowledge_point_code="极限", attempts_count=5, correct_count=1, mastery=0.2, mistake_count=3))
        db.add(UserKnowledgeState(user_id="path-user", knowledge_point_code="导数", attempts_count=4, correct_count=1, mastery=0.3, mistake_count=2))
        await db.commit()

    path = await build_learning_path("path-user")
    assert path["weak_count"] == 2
    assert path["weeks"][0]["points"][0]["code"] == "极限"  # 前置在前
    all_steps = [step for point in path["weeks"][0]["points"] for step in point["steps"]]
    assert len(all_steps) == 8  # 每点四步
    await engine.dispose()
