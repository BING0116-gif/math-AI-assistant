"""学习路径规则引擎(路线图 7.1,阶段五主交付)。

v1 刻意零 LLM:路径是确定性规则产物,可解释、可测试、可回放——
给定状态快照 → 唯一路径输出(7.3 DoD)。

规则:
1. 薄弱点 = 有作答证据(attempts ≥ 1)且 mastery < 阈值(默认 0.6)的知识点;
2. 依赖排序 = 按知识点 prerequisites 在薄弱集内做拓扑排序(环按 mastery 升序、
   code 字典序破环,保证确定性);
3. 路径模板 = 每知识点四步:讲解 → 基础题 → 变式题 → 错题复盘;
4. 周计划 = 排序后切片 × 每周容量(默认 5 知识点/周,env 可配);
5. 步骤状态由既有数据确定性推导,不新建进度表。
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List

from app.config.settings import settings

STEP_EXPLAIN = "explain"
STEP_PRACTICE = "practice"
STEP_VARIANT = "variant"
STEP_REVIEW = "review"

_STEP_TEMPLATES = (
    (STEP_EXPLAIN, "知识点讲解", "按讲解梳理概念与关键公式", "/knowledge/{code}"),
    (STEP_PRACTICE, "基础题巩固", "做一组该知识点基础题", "/practice?knowledge_point_codes={code}"),
    (STEP_VARIANT, "变式题迁移", "完成变式练习检验迁移能力", "/practice?knowledge_point_codes={code}&variant=true"),
    (STEP_REVIEW, "错题复盘", "复盘该知识点错题并核对复习计划", "/error-book"),
)


def mastery_weak_threshold(default: float = 0.6) -> float:
    try:
        value = float(getattr(settings, "LEARNING_PATH_MASTERY_THRESHOLD"))
        return value if 0 < value < 1 else default
    except Exception:
        return default


def week_capacity(default: int = 5) -> int:
    try:
        value = int(getattr(settings, "LEARNING_PATH_WEEK_CAPACITY"))
        return value if 1 <= value <= 20 else default
    except Exception:
        return default


def pick_weak_points(
    states: Iterable[Dict[str, Any]],
    *,
    threshold: float,
) -> List[Dict[str, Any]]:
    """薄弱点筛选:有作答证据且 mastery 低于阈值。输入为状态快照字典。"""
    weak = []
    for state in states:
        attempts = int(state.get("attempts_count") or 0)
        mastery = float(state.get("mastery") or 0.0)
        if attempts < 1 or mastery >= threshold:
            continue
        weak.append({
            "code": str(state.get("knowledge_point_code") or ""),
            "mastery": round(mastery, 4),
            "attempts_count": attempts,
            "mistake_count": int(state.get("mistake_count") or 0),
            "variant_performance": float(state.get("variant_performance") or 0.0),
            "next_review_at": state.get("next_review_at"),
            "prerequisites": list(state.get("prerequisites") or []),
            "name": str(state.get("name") or state.get("knowledge_point_code") or ""),
        })
    return weak


def topological_order(weak: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """薄弱集内的依赖拓扑排序;不在薄弱集里的前置不参与排序。

    环按 (mastery 升序, code 字典序) 破环,保证同快照输出唯一。
    """
    by_code = {item["code"]: item for item in weak if item["code"]}
    ordered: List[Dict[str, Any]] = []
    visited: Dict[str, str] = {}  # code -> "visiting" | "done"

    def visit(code: str) -> None:
        state = visited.get(code)
        if state == "done" or code not in by_code:
            return
        if state == "visiting":
            return  # 环:由外层排序兜底
        visited[code] = "visiting"
        for prerequisite in by_code[code].get("prerequisites") or []:
            visit(str(prerequisite))
        visited[code] = "done"
        ordered.append(by_code[code])

    for item in sorted(weak, key=lambda x: (x["mastery"], x["code"])):  # 确定性入口
        visit(item["code"])
    # Kahn 语义下前置在前已保证;环内节点保持 (mastery, code) 相对序
    return ordered


def build_point_steps(point: Dict[str, Any]) -> List[Dict[str, Any]]:
    """路径模板:讲解→基础题→变式题→错题复盘;状态由数据推导。"""
    mastery = float(point.get("mastery") or 0.0)
    variant_performance = float(point.get("variant_performance") or 0.0)
    mistake_count = int(point.get("mistake_count") or 0)
    steps = []
    for step_type, title, description, route in _STEP_TEMPLATES:
        if step_type == STEP_EXPLAIN:
            status = "in_progress"
        elif step_type == STEP_PRACTICE:
            status = "done" if mastery >= 0.45 else "in_progress"
        elif step_type == STEP_VARIANT:
            status = "done" if variant_performance >= 0.6 else ("in_progress" if mastery >= 0.45 else "pending")
        else:  # review
            status = "done" if mistake_count == 0 and mastery >= 0.45 else "in_progress"
        steps.append({
            "type": step_type,
            "title": title,
            "description": description,
            "route": route.format(code=point["code"]),
            "status": status,
        })
    return steps


def build_weekly_plan(ordered: List[Dict[str, Any]], *, capacity: int) -> List[Dict[str, Any]]:
    """排序后切片 × 每周容量,生成周计划。"""
    weeks = []
    for index, start in enumerate(range(0, len(ordered), max(1, capacity)), start=1):
        chunk = ordered[start:start + max(1, capacity)]
        weeks.append({
            "week": index,
            "focus": "、".join(item["name"] for item in chunk[:3]) + ("等" if len(chunk) > 3 else ""),
            "points": [serialize_point(item) for item in chunk],
        })
    return weeks


def serialize_point(point: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "code": point["code"],
        "name": point["name"],
        "mastery": point["mastery"],
        "attempts_count": point["attempts_count"],
        "mistake_count": point["mistake_count"],
        "prerequisites": point.get("prerequisites") or [],
        "steps": build_point_steps(point),
    }


def generate_learning_path(
    states: Iterable[Dict[str, Any]],
    *,
    threshold: float | None = None,
    capacity: int | None = None,
) -> Dict[str, Any]:
    """确定性入口:状态快照 → 唯一路径输出。"""
    resolved_threshold = threshold if threshold is not None else mastery_weak_threshold()
    resolved_capacity = capacity if capacity is not None else week_capacity()
    weak = pick_weak_points(states, threshold=resolved_threshold)
    ordered = topological_order(weak)
    weeks = build_weekly_plan(ordered, capacity=resolved_capacity)
    return {
        "schema_version": "1.0",
        "generator": "rules-v1",
        "weak_threshold": resolved_threshold,
        "week_capacity": resolved_capacity,
        "weak_count": len(ordered),
        "weeks": weeks,
    }


async def build_learning_path(user_id: str) -> Dict[str, Any]:
    """从数据库装载状态快照并生成路径(user_id 隔离)。"""
    from sqlalchemy import select

    from app.data.database import get_db_session
    from app.data.models import KnowledgePoint, UserKnowledgeState

    async with get_db_session() as db:
        state_rows = list((await db.execute(
            select(UserKnowledgeState).where(UserKnowledgeState.user_id == user_id)
        )).scalars())
        codes = sorted({row.knowledge_point_code for row in state_rows})
        points: Dict[str, KnowledgePoint] = {}
        if codes:
            # 同 code 多版本时取 id 最大(最新导入),保证确定性
            point_rows = list((await db.execute(
                select(KnowledgePoint).where(
                    KnowledgePoint.code.in_(codes),
                    KnowledgePoint.status == "active",
                ).order_by(KnowledgePoint.code, KnowledgePoint.id)
            )).scalars())
            for row in point_rows:
                points[row.code] = row  # 同 code 后写覆盖前写 → id 最大者保留

        snapshot = []
        for row in state_rows:
            point = points.get(row.knowledge_point_code)
            snapshot.append({
                "knowledge_point_code": row.knowledge_point_code,
                "name": point.name if point else row.knowledge_point_code,
                "attempts_count": row.attempts_count,
                "mastery": row.mastery,
                "mistake_count": row.mistake_count,
                "variant_performance": row.variant_performance,
                "next_review_at": row.next_review_at.isoformat() if row.next_review_at else None,
                "prerequisites": (point.prerequisites if point else []) or [],
            })

    path = generate_learning_path(snapshot)
    path["user_scope"] = "owner"
    return path
