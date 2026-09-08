"""Paper generation service — WS-C 组卷内核（客观题限定，P0-7 边界）。

资格过滤（硬规则，组卷只消费这些题）：
- review_status = published
- exam_eligible = True AND auto_grading_eligible = True（发布时按题型派生）
- 版本匹配：模板 version_id 精确匹配；未限定版本时按 course_id 范围
- 若配置 kp_codes，题目必须关联其中至少一个知识点（硬过滤）
- 题型必须落在 config.type_mix 指定的题型内（choice / judge / numeric_fill / expression_fill）

卷内题目以快照写入 PaperQuestion：题库后续编辑/退役不影响已生成试卷。
"""

from __future__ import annotations

import logging
import random
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.data.database import get_db_session
from app.data.models import (
    KnowledgePoint,
    Paper,
    PaperQuestion,
    PaperTemplate,
    Question,
    QuestionKnowledgePoint,
)

logger = logging.getLogger(__name__)


class PaperGenerationError(Exception):
    """稳定 application error，携带稳定 code。"""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def normalize_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """校验并规整组卷规则（v1 契约）。"""
    cfg = dict(config or {})
    type_mix = cfg.get("type_mix")
    if not isinstance(type_mix, dict) or not type_mix:
        raise PaperGenerationError("VALIDATION_FAILED", "config.type_mix 必须为非空 dict（题型 -> 数量）")
    total = cfg.get("total")
    if total is None:
        total = sum(int(v) for v in type_mix.values())
    if int(total) <= 0:
        raise PaperGenerationError("VALIDATION_FAILED", "config.total 必须为正整数")
    cfg["total"] = int(total)
    cfg["random_seed"] = int(cfg.get("random_seed", 0))
    cfg["score_per_question"] = float(cfg.get("score_per_question", 10))
    difficulty = cfg.get("difficulty")
    if difficulty is not None and not isinstance(difficulty, dict):
        raise PaperGenerationError("VALIDATION_FAILED", "config.difficulty 必须为 dict（难度 -> 数量）")
    kp_codes = cfg.get("kp_codes") or []
    if not isinstance(kp_codes, list):
        raise PaperGenerationError("VALIDATION_FAILED", "config.kp_codes 必须为 list")
    cfg["kp_codes"] = [str(c) for c in kp_codes]
    return cfg


async def _load_eligible(
    course_id: Optional[str], version_id: Optional[str],
    qtypes: List[str], kp_codes: List[str],
) -> List[Question]:
    """资格过滤查询：published + 能力字段 + 版本 + 知识点（全部硬过滤）。"""
    conds = [
        Question.review_status == "published",
        Question.exam_eligible.is_(True),
        Question.auto_grading_eligible.is_(True),
        Question.question_type.in_(qtypes),
    ]
    if version_id:
        conds.append(Question.version_id == version_id)
    elif course_id:
        conds.append(Question.course_id == course_id)
    stmt = select(Question).where(*conds).options(
        selectinload(Question.knowledge_point_links)
    )
    async with get_db_session() as db:
        rows = list((await db.execute(stmt)).scalars().all())
        if kp_codes:
            kp_rows = (
                await db.execute(
                    select(QuestionKnowledgePoint.question_id, KnowledgePoint.code)
                    .join(KnowledgePoint, KnowledgePoint.id == QuestionKnowledgePoint.knowledge_point_id)
                    .where(KnowledgePoint.code.in_(kp_codes))
                )
            ).all()
            allowed = {qid for qid, _ in kp_rows}
            rows = [q for q in rows if q.id in allowed]
        return rows


def _select_by_quotas(
    pool: List[Question], type_mix: Dict[str, Any],
    difficulty: Optional[Dict[str, Any]], rng: random.Random,
) -> List[Question]:
    """按题型配额选题；difficulty 为软约束（优先满足难度分布，不足从同题型补足）。"""
    selected: List[Question] = []
    for qtype, quota in type_mix.items():
        tq = [q for q in pool if q.question_type == qtype]
        need = int(quota)
        chosen: List[Question] = []
        if difficulty:
            for lvl, cnt in sorted(difficulty.items(), key=lambda kv: int(kv[0])):
                take = min(int(cnt), need - len(chosen))
                if take <= 0:
                    continue
                lq = [q for q in tq if q.difficulty == int(lvl)]
                rng.shuffle(lq)
                chosen.extend(lq[:take])
                chosen_ids = {q.id for q in chosen}
                tq = [q for q in tq if q.id not in chosen_ids]
        rng.shuffle(tq)
        chosen.extend(tq[: need - len(chosen)])
        if len(chosen) < need:
            raise PaperGenerationError(
                "INSUFFICIENT_POOL",
                f"题型 {qtype} 可用题不足：需要 {need}，实际只有 {len(chosen)} 道",
            )
        selected.extend(chosen)
    rng.shuffle(selected)
    return selected


def _snapshot(q: Question, kp_codes: List[str]) -> Dict[str, Any]:
    return {
        "question_id": q.id,
        "content": q.content,
        "question_type": q.question_type,
        "options": q.options,
        "answer_spec": q.answer_spec,
        "analysis": q.analysis,
        "difficulty": q.difficulty,
        "estimated_time": q.estimated_time,
        "knowledge_point_codes": kp_codes,
    }


# ── 学生端自动判分（仅确定性题型，answer_spec 契约）──
def _norm_bool(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    s = str(value or "").strip().lower()
    if s in ("true", "t", "对", "√", "1"):
        return True
    if s in ("false", "f", "错", "×", "0"):
        return False
    return None


def _num_close(student: str, expected: Any) -> bool:
    try:
        a = float(str(student).strip().replace(",", ""))
        b = float(str(expected).strip().replace(",", ""))
    except (TypeError, ValueError):
        return False
    return abs(a - b) <= max(1e-6, 1e-4 * abs(b))


def _expr_equiv(student: str, canonical: Any, variables: Any = None) -> bool:
    try:
        from app.services.safe_math import expressions_equivalent
        return expressions_equivalent(str(student), str(canonical), variables or [])
    except Exception:  # noqa: BLE001
        return False


def _grade_one(snapshot: Dict[str, Any], answer: Any) -> Dict[str, Any]:
    """按快照 answer_spec 判单题，返回 {correct, correct_answer}（确定性题型）。"""
    spec = snapshot.get("answer_spec") or {}
    kind = spec.get("kind")
    correct = False
    if kind == "choice":
        correct = str(spec.get("correct")) == str(answer)
    elif kind == "judge":
        norm = _norm_bool(answer)
        correct = norm is not None and norm == bool(spec.get("correct"))
    elif kind == "numeric_fill":
        correct = _num_close(str(answer or ""), spec.get("value"))
    elif kind == "expression_fill":
        correct = _expr_equiv(str(answer or ""), spec.get("canonical"), spec.get("variables"))
    return {
        "correct": correct,
        "correct_answer": {
            "choice": spec.get("correct"),
            "judge": "对" if spec.get("correct") else "错",
            "numeric_fill": spec.get("value"),
            "expression_fill": spec.get("canonical"),
        }.get(kind, ""),
    }


async def grade_paper_submission(paper: Paper, answers: Dict[str, Any]) -> Dict[str, Any]:
    """学生端判分：answers = {question_id: answer}，按卷内快照逐题判定。"""
    results: List[Dict[str, Any]] = []
    score = 0.0
    max_score = 0.0
    for pq in (paper.questions or []):
        snap = pq.snapshot or {}
        max_score += float(pq.score or 0)
        student_answer = answers.get(pq.question_id)
        graded = _grade_one(snap, student_answer)
        if graded["correct"]:
            score += float(pq.score or 0)
        results.append(
            {
                "position": pq.position,
                "question_id": pq.question_id,
                "question_type": snap.get("question_type"),
                "your_answer": student_answer if student_answer not in (None, "") else "（未作答）",
                "correct": graded["correct"],
                "correct_answer": graded["correct_answer"],
                "analysis": snap.get("analysis") or "",
                "score": pq.score,
            }
        )
    return {
        "score": round(score, 2),
        "max_score": round(max_score, 2),
        "correct": sum(1 for r in results if r["correct"]),
        "total": len(results),
        "results": results,
    }


async def _kp_codes_map(question_ids: List[str]) -> Dict[str, List[str]]:
    if not question_ids:
        return {}
    async with get_db_session() as db:
        rows = (
            await db.execute(
                select(QuestionKnowledgePoint.question_id, KnowledgePoint.code)
                .join(KnowledgePoint, KnowledgePoint.id == QuestionKnowledgePoint.knowledge_point_id)
                .where(QuestionKnowledgePoint.question_id.in_(question_ids))
            )
        ).all()
    mapping: Dict[str, List[str]] = {}
    for qid, code in rows:
        mapping.setdefault(qid, []).append(code)
    return mapping


class PaperGenerator:
    """组卷生成服务。"""

    async def _resolve(
        self, template_id: Optional[str], config: Optional[Dict[str, Any]]
    ) -> Tuple[Optional[PaperTemplate], Dict[str, Any], Optional[str], Optional[str]]:
        tpl: Optional[PaperTemplate] = None
        course_id = version_id = None
        if template_id:
            async with get_db_session() as db:
                tpl = await db.get(PaperTemplate, template_id)
            if tpl is None:
                raise PaperGenerationError("NOT_FOUND", "模板不存在")
            if not tpl.is_active:
                raise PaperGenerationError("STATE", "模板已停用")
            course_id, version_id = tpl.course_id, tpl.version_id
            config = tpl.config
        cfg = normalize_config(config)
        if template_id is None:
            course_id = cfg.get("course_id") or None
            version_id = cfg.get("version_id") or None
        return tpl, cfg, course_id, version_id

    async def _select(self, cfg: Dict[str, Any], course_id: Optional[str], version_id: Optional[str]):
        pool = await _load_eligible(
            course_id, version_id, list(cfg["type_mix"].keys()), cfg["kp_codes"]
        )
        rng = random.Random(cfg["random_seed"])
        return _select_by_quotas(pool, cfg["type_mix"], cfg.get("difficulty"), rng)

    async def preview(
        self, template_id: Optional[str] = None, config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """按规则选题并返回快照列表（不落库），供预览/人工调整。"""
        tpl, cfg, course_id, version_id = await self._resolve(template_id, config)
        questions = await self._select(cfg, course_id, version_id)
        codes = await _kp_codes_map([q.id for q in questions])
        return {
            "template_id": tpl.id if tpl else None,
            "total": len(questions),
            "questions": [_snapshot(q, codes.get(q.id, [])) for q in questions],
        }

    async def generate(
        self,
        template_id: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
        title: Optional[str] = None,
    ) -> Paper:
        """按模板/规则生成试卷并落库（题目快照固化）。"""
        tpl, cfg, course_id, version_id = await self._resolve(template_id, config)
        questions = await self._select(cfg, course_id, version_id)
        codes = await _kp_codes_map([q.id for q in questions])

        async with get_db_session() as db:
            paper = Paper(
                template_id=tpl.id if tpl else None,
                title=title or (tpl.name if tpl else "未命名试卷"),
                course_id=course_id,
                version_id=version_id,
                status="generated",
                random_seed=cfg["random_seed"],
            )
            db.add(paper)
            await db.flush()
            for i, q in enumerate(questions):
                db.add(
                    PaperQuestion(
                        paper_id=paper.id,
                        question_id=q.id,
                        position=i + 1,
                        score=cfg["score_per_question"],
                        snapshot=_snapshot(q, codes.get(q.id, [])),
                    )
                )
            await db.commit()
            # 会话内带 eager load 重新查询，避免关闭后惰性加载
            stmt = (
                select(Paper)
                .where(Paper.id == paper.id)
                .options(selectinload(Paper.questions))
            )
            return (await db.execute(stmt)).scalar_one()

    async def get_paper(self, paper_id: str) -> Optional[Paper]:
        async with get_db_session() as db:
            stmt = (
                select(Paper)
                .where(Paper.id == paper_id)
                .options(
                    selectinload(Paper.questions)
                )
            )
            return (await db.execute(stmt)).scalar_one_or_none()


def serialize_paper(paper: Paper) -> Dict[str, Any]:
    return {
        "id": paper.id,
        "template_id": paper.template_id,
        "title": paper.title,
        "course_id": paper.course_id,
        "version_id": paper.version_id,
        "status": paper.status,
        "random_seed": paper.random_seed,
        "created_at": paper.created_at.isoformat() if paper.created_at else None,
        "questions": [
            {
                "position": pq.position,
                "score": pq.score,
                "question_id": pq.question_id,
                "snapshot": pq.snapshot,
            }
            for pq in (paper.questions or [])
        ],
    }
