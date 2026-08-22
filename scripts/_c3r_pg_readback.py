# -*- coding: utf-8 -*-
"""Step 1.1-C3-R 只读对账：从真实 PostgreSQL 读取已持久化的验收数据。

不写任何数据；复用 _c3r_pg_persistence_acceptance.py 的 set 分组逻辑，
输出最终报告所需的 A/B/C 对账、类型对账、答案/页面覆盖率、draft provenance。
"""
import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

PG_SYNC = os.environ.get(
    "PG_SYNC_URL", "postgresql://mathai:mathai_test@localhost:5432/math_ai_c3"
)
PG_ASYNC = PG_SYNC.replace("postgresql://", "postgresql+asyncpg://", 1)

os.environ["ASYNC_DATABASE_URL"] = PG_ASYNC
os.environ["DATABASE_URL"] = PG_SYNC
os.environ["AI_ENABLED"] = "false"
os.environ["RAG_ENABLED"] = "false"

EXPECTED_SET_SECTION = {
    "A": {"choice": 8, "fill": 8, "calculation": 8, "proof": 2},
    "B": {"choice": 8, "fill": 8, "calculation": 8, "proof": 2},
    "C": {"choice": 8, "fill": 8, "calculation": 8, "proof": 4},
}
SECTION_OF_TYPE = {
    "choice": "choice",
    "numeric_fill": "fill",
    "expression_fill": "fill",
    "fill": "fill",
    "calculation": "calculation",
    "proof": "proof",
}
EXPECTED_TYPES = {
    "choice": 24,
    "numeric_fill": 13,
    "expression_fill": 8,
    "fill": 3,
    "calculation": 24,
    "proof": 8,
}
SUPPORTED_EXPECTED = {"choice": True, "numeric_fill": True, "expression_fill": True,
                      "fill": False, "calculation": False, "proof": False}


def _group_sets_by_number(cands):
    """与验收脚本一致：同 section 按 source_question_number 重置分成 set 组。"""
    groups = []
    letter_iter = iter(["A", "B", "C"])
    prev = None
    for c in cands:
        try:
            num = int(c["source_question_number"] or "0")
        except (TypeError, ValueError):
            num = 0
        if prev is None or num <= prev:
            groups.append((next(letter_iter, "?"), [c]))
        else:
            groups[-1][1].append(c)
        prev = num
    return groups


async def main() -> int:
    from sqlalchemy import func, select

    from app.data.database import init_db, close_db, get_db_session
    from app.data.models import (
        ContentImportCandidate,
        ImportBatch,
        Question,
        SourceDocument,
    )

    await init_db()

    # ── 1. candidates 总量 + 类型对账 ──
    async with get_db_session() as db:
        cands = (await db.execute(
            select(ContentImportCandidate)
            .order_by(ContentImportCandidate.candidate_index)
        )).scalars().all()
    rows = [
        {
            "source_question_number": c.source_question_number,
            "detected_question_type": c.detected_question_type,
            "supported": c.supported,
            "original_answer": c.original_answer,
            "page_start": c.source_page_start,
            "page_end": c.source_page_end,
            "raw": c.raw_parsed_content,
        }
        for c in cands
    ]
    print(f"== candidates total = {len(rows)} ==")

    type_counts: dict = {}
    for r in rows:
        t = r["detected_question_type"]
        type_counts[t] = type_counts.get(t, 0) + 1
    print("-- detected_question_type --")
    for t in ["choice", "numeric_fill", "expression_fill", "fill", "calculation", "proof"]:
        got = type_counts.get(t, 0)
        exp = EXPECTED_TYPES.get(t)
        print(f"  {t:15s} got={got:2d} expected={exp}  {'OK' if got == exp else 'MISMATCH'}")

    # supported 期望
    print("-- supported 期望 --")
    ok_sup = True
    for t, exp in SUPPORTED_EXPECTED.items():
        vals = {r["detected_question_type"] == t for r in rows}
        got_all = all(r["supported"] == exp for r in rows if r["detected_question_type"] == t)
        print(f"  {t:15s} supported={exp}  实际一致={got_all}")
        ok_sup = ok_sup and got_all

    # ── 2. 分 section 的 set 分组对账 ──
    print("-- per-set / section --")
    ok_set = True
    for sec in ["choice", "fill", "calculation", "proof"]:
        sec_rows = [r for r in rows if SECTION_OF_TYPE.get(r["detected_question_type"]) == sec]
        groups = _group_sets_by_number(sec_rows)
        print(f"  section={sec:12s} groups={[ (g[0], len(g[1])) for g in groups ]}")
        # 只校验 A/B/C 三组
        for letter, exp in EXPECTED_SET_SECTION.items():
            got = next((len(g[1]) for g in groups if g[0] == letter), 0)
            if got != exp[sec]:
                ok_set = False
                print(f"    MISMATCH {letter}.{sec}: got={got} expected={exp[sec]}")

    # ── 3. 答案 / 页面覆盖率 ──
    print("-- answer / page coverage --")
    choice = [r for r in rows if r["detected_question_type"] == "choice"]
    fills = [r for r in rows if SECTION_OF_TYPE.get(r["detected_question_type"]) == "fill"]
    calc = [r for r in rows if r["detected_question_type"] == "calculation"]
    c_ans = sum(1 for r in choice if r["original_answer"])
    f_ans = sum(1 for r in fills if r["original_answer"])
    calc_ans = sum(1 for r in calc if r["original_answer"])
    page_cov = sum(1 for r in rows if r["page_start"] is not None and r["page_end"] is not None)
    raw_cov = sum(1 for r in rows if r["raw"])
    print(f"  choice original_answer = {c_ans}/{len(choice)}")
    print(f"  fill   original_answer = {f_ans}/{len(fills)}")
    print(f"  calculation original_answer (应=0) = {calc_ans}/{len(calc)}")
    print(f"  page provenance (start+end) = {page_cov}/{len(rows)}")
    print(f"  raw_parsed_content = {raw_cov}/{len(rows)}")

    # ── 4. draft smoke：provenance + published 状态 ──
    print("-- draft smoke (Question) --")
    async with get_db_session() as db:
        qs = (await db.execute(
            select(Question).where(Question.source_candidate_id.isnot(None))
        )).scalars().all()
    print(f"  Question(source_candidate) 总数 = {len(qs)}")
    for q in qs:
        print(f"    id={q.id[:8]} review_status={q.review_status} published={getattr(q, 'published', '?')} "
              f"candidate_id={str(q.source_candidate_id)[:8]}")
        cand = next((r for r in rows if False), None)  # placeholder
    # 从 DB 取 provenance 链
    async with get_db_session() as db:
        qs2 = (await db.execute(
            select(Question).where(Question.source_candidate_id.isnot(None))
        )).scalars().all()
        for q in qs2:
            cand = await db.get(ContentImportCandidate, q.source_candidate_id)
            batch = await db.get(ImportBatch, cand.import_batch_id) if cand else None
            doc = await db.get(SourceDocument, batch.source_document_id) if batch else None
            print(f"    chain: Question({q.id[:8]}) -> candidate({cand.id[:8] if cand else '?'}) "
                  f"-> batch({batch.id[:8] if batch else '?'}, status={batch.status if batch else '?'}) "
                  f"-> source_document({doc.id[:8] if doc else '?'}, name={doc.original_filename if doc else '?'})")

    await close_db()

    final = (len(rows) == 80 and ok_set and ok_sup and c_ans == 24 and f_ans == 24
             and calc_ans == 0 and page_cov == 80 and raw_cov == 80)
    print("\n== 汇总 ==")
    print("READBACK " + ("PASS" if final else "FAIL"))
    return 0 if final else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
