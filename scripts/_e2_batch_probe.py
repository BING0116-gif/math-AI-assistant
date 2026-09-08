# -*- coding: utf-8 -*-
"""Step 1.1-E2-1 只读探针：确认 math_ai_c3 基线，并列出适合首批 5 道 Batch selection 的 supported candidate。

不修改任何数据；只读。最终 KP / analysis / review / publish 由用户在 Content Review Tool 执行。
"""
import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

PG_SYNC = os.environ.get(
    "PG_SYNC_URL", "postgresql://mathai:mathai_test@localhost:5432/math_ai_c3"
)
PG_ASYNC = PG_SYNC.replace("postgresql://", "postgresql+asyncpg://", 1)
os.environ["ASYNC_DATABASE_URL"] = PG_ASYNC
os.environ["DATABASE_URL"] = PG_SYNC
os.environ["AI_ENABLED"] = "false"
os.environ["RAG_ENABLED"] = "false"

from sqlalchemy import text

from app.data.database import init_db, close_db, get_db_session
from app.data.models import (
    ContentImportCandidate,
    ImportBatch,
    SourceDocument,
    Question,
    QuestionKnowledgePoint,
)
from app.services.content_import import SUPPORTED_TYPES

BLOCKING = {
    "option_parse_uncertain", "possible_answer_leak", "answer_match_missing",
    "answer_match_key_incomplete", "answer_roster_incomplete",
    "choice_answer_ambiguous", "fill_type_needs_review", "page_mapping_uncertain",
}


def _blocking(warnings):
    return sorted({w for w in (warnings or []) if w in BLOCKING})


async def main() -> None:
    await init_db()
    try:
        async with get_db_session() as db:
            # 基线
            qrows = (await db.execute(text(
                "select review_status, count(*) from questions group by review_status"
            ))).all()
            print("== questions_by_status ==", dict(qrows))
            kp_count = (await db.execute(text(
                "select count(*) from knowledge_points"
            ))).scalar_one()
            qkp = (await db.execute(text(
                "select count(*) from question_knowledge_points"
            ))).scalar_one()
            print(f"knowledge_points={kp_count} question_knowledge_points={qkp}")

            # 全部 candidates + provenance 链
            cands = (await db.execute(text(
                "select c.*, ib.source_document_id as sd_id, sd.original_filename as sd_name "
                "from content_import_candidates c "
                "join import_batches ib on ib.id = c.import_batch_id "
                "join source_documents sd on sd.id = ib.source_document_id "
                "order by c.candidate_index"
            ))).mappings().all()

        print("\n== candidates total =", len(cands), "==")
        eligible = []
        for c in cands:
            supported = c["supported"]
            status = c["status"]
            qtype = c["detected_question_type"]
            blocking = _blocking(c["warnings"])
            has_page = c["source_page_start"] is not None and c["source_page_end"] is not None
            has_answer = bool((c["original_answer"] or "").strip())
            has_solution = bool((c["original_solution"] or "").strip())
            prov_ok = has_page and c["source_question_number"] and c["raw_parsed_content"]
            eligible.append({
                "id": c["id"],
                "qnum": c["source_question_number"],
                "page": f"{c['source_page_start']}-{c['source_page_end']}",
                "type": qtype,
                "supported": supported,
                "status": status,
                "answer": (c["original_answer"] or "").strip(),
                "has_solution": has_solution,
                "blocking": blocking,
                "prov_ok": prov_ok,
                "sd": c["sd_name"],
            })

        pick = [e for e in eligible
                if e["supported"] and e["status"] in ("parsed", "edited")
                and e["prov_ok"] and e["answer"] and not e["blocking"] and e["type"] in SUPPORTED_TYPES]
        print(f"\neligible for Batch (supported + parsed/edited + prov + answer + no-blocking + supported-type): {len(pick)}")
        type_counts = {}
        for e in pick:
            type_counts[e["type"]] = type_counts.get(e["type"], 0) + 1
        print("by_type:", type_counts)

        want_types = ["choice", "numeric_fill", "expression_fill"]
        ordered = sorted(pick, key=lambda e: (want_types.index(e["type"]) if e["type"] in want_types else 9,
                                              e["qnum"] and not str(e["qnum"]).isnumeric(),
                                              0 if e["has_solution"] else 1,
                                              e["qnum"]))
        print("\n== eligible candidates (type choice/numeric_fill/expression_fill first, by qnum) ==")
        for i, e in enumerate(ordered, 1):
            print(f"[{i:2d}] type={e['type']:15s} q={e['qnum']} page={e['page']:5s} "
                  f"sol={1 if e['has_solution'] else 0} answer={e['answer'][:24]!r} sd={e['sd']}")

        # 显示含解析的候选（原 PDF 有明确解析优先）
        with_sol = [e for e in pick if e["has_solution"]]
        print(f"\n-- candidates WITH original_solution = {len(with_sol)} --")
        for e in with_sol:
            print(f"  type={e['type']:15s} q={e['qnum']} page={e['page']:5s} ans={e['answer'][:24]!r}")
    finally:
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())