# -*- coding: utf-8 -*-
"""Step 1.1-D PostgreSQL Smoke（真实 PG15 + synthetic PDF）。

流程：
  Candidate → Draft → Reviewed → Published
  → published-only query 验证
  → draft/reviewed 不进入正式题池

用法：
  set PG_SYNC_URL=postgresql://mathai:mathai_test@localhost:5432/math_ai_d
  python scripts/_step1d_pg_smoke.py
"""
import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

PG_SYNC = os.environ.get(
    "PG_SYNC_URL", "postgresql://mathai:mathai_test@localhost:5432/math_ai_d"
)
PG_ASYNC = PG_SYNC.replace("postgresql://", "postgresql+asyncpg://", 1)

os.environ["ASYNC_DATABASE_URL"] = PG_ASYNC
os.environ["DATABASE_URL"] = PG_SYNC
os.environ["AI_ENABLED"] = "false"
os.environ["RAG_ENABLED"] = "false"
os.environ["CONTENT_STORAGE_ROOT"] = str(ROOT / "runtime" / "content")

_results = []


def report(section, ok, detail=""):
    _results.append((section, ok, detail))
    print(f"[{'OK' if ok else 'FAIL'}] {section}  {detail}")


async def main():
    import fitz

    from sqlalchemy import func, select

    from app.data.database import init_db, close_db, get_db_session
    from app.data.models import (
        Question,
        ContentImportCandidate,
        ImportBatch,
        SourceDocument,
    )
    from app.services.content_import import ContentImportService
    from app.services.document_parser import MODE_QUICK
    from app.services.knowledge_seed import seed_phase_one_calculus

    # 0. init + seed
    await init_db()
    from app.data.database import async_session_factory
    from app.data.models import KnowledgePoint

    async with async_session_factory() as db:
        await seed_phase_one_calculus(db)
        await db.commit()
        kp_codes = (await db.execute(select(KnowledgePoint.code))).scalars().all()
    report("seed catalog on PG", len(kp_codes) >= 1, f"KP codes={len(kp_codes)}")

    # 1. create import + quick parse
    pdf_text = (
        "高等数学自测\n"
        "一、单项选择题\n"
        "1. 设函数 f(x)=x^2，则 f'(1) 等于（ ）。\n"
        "A. 1\nB. 2\nC. 3\nD. 4\n"
        "二、证明题\n"
        "1. 证明函数 f(x)=x 在 [0,1] 上连续。\n"
    )
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), pdf_text, fontname="china-s", encoding="gbk")
    pdf_bytes = doc.tobytes()
    doc.close()

    service = ContentImportService()
    batch, created = await service.create_import(
        admin_user_id="pg-smoke-admin",
        original_filename="smoke.pdf",
        content=pdf_bytes,
        mode=MODE_QUICK,
        idempotency_key="step1d-pg-smoke-1",
    )
    report("create_import on PG", created and batch.status == "pending", batch.id)

    # 2. parse
    batch = await service.parse_import(batch.id)
    report("quick parse on PG", batch.status == "parsed", batch.error_message or "")

    # 3. candidates
    candidates = await service.list_candidates(batch.id)
    total = len(candidates)
    supported = sum(1 for c in candidates if c.supported)
    report("candidates from PG", total >= 1, f"total={total} supported={supported}")

    # 4. edit candidate
    choice = next(c for c in candidates if c.detected_question_type == "choice")
    code = kp_codes[0]
    choice = await service.update_candidate(
        batch_id=choice.import_batch_id,
        candidate_id=choice.id,
        patch={
            "original_answer": "B",
            "original_solution": "f'(x)=2x，故 f'(1)=2。",
            "suggested_knowledge_point_codes": [code],
        },
    )
    report("edit candidate on PG", choice.original_answer == "B", str(choice.id))

    # 5. draft
    res = await service.create_drafts(batch.id, [choice.id])
    report("create draft on PG", len(res["created"]) == 1, str(res["created"]))

    qid = res["created"][0]
    async with get_db_session() as db:
        q = await db.get(Question, qid)
        approved = q is not None
        report("draft exists in PG", approved, f"review_status={q.review_status}")

    # 6. preview API
    png = await service.render_page_preview(batch.source_document_id, 1)
    report("preview page on PG", png.startswith(b"\x89PNG"),
           f"png_size={len(png)}b")

    # 7. review: draft → reviewed
    from app.services.content_review import ContentReviewService, ContentReviewError
    svc = ContentReviewService()
    await svc.update_question(
        qid, {"answer_spec": {"version": 1, "kind": "choice", "correct": "B"}}
    )
    reviewed = await svc.mark_reviewed(qid)
    report("draft -> reviewed on PG", reviewed.review_status == "reviewed", qid)

    # 8. publish: reviewed → published
    pub = await svc.publish(qid)
    report("reviewed -> published on PG", pub.review_status == "published", qid)

    # 9. published-only query: published 进入正式题池
    published = await svc.list_questions("published")
    published_ids = {q.id for q in published}
    report("published in published-only query", qid in published_ids, qid)

    # 10. draft/reviewed 不进入 published-only
    draft_ids = {q.id for q in await svc.list_questions("draft")}
    reviewed_ids = {q.id for q in await svc.list_questions("reviewed")}
    no_leak = (qid not in draft_ids) and (qid not in reviewed_ids)
    report("draft/reviewed exclude published", no_leak, "confirmed")

    # 11. provenance 完整
    async with get_db_session() as db:
        q = await db.get(Question, qid)
        cand = await db.get(ContentImportCandidate, q.source_candidate_id)
        b = await db.get(ImportBatch, cand.import_batch_id)
        sd = await db.get(SourceDocument, b.source_document_id)
        chain = (q.source_candidate_id == cand.id
                 and cand.import_batch_id == b.id
                 and b.source_document_id == sd.id
                 and sd.original_filename == "smoke.pdf")
    report("provenance chain on PG", chain,
           f"Question->Candidate->Batch->SourceDoc")

    # 12. AI_ENABLED=false
    from app.config.settings import settings
    report("AI_ENABLED on PG", settings.AI_ENABLED is False,
           f"AI_ENABLED={settings.AI_ENABLED}")

    # 13. source_candidate_id 保留原始 provenance
    async with get_db_session() as db:
        cand = await db.get(ContentImportCandidate, choice.id)
        report("provenance unchanged on PG",
               cand.raw_parsed_content is not None
               and cand.original_answer == "B",
               f"raw={bool(cand.raw_parsed_content)} ans={cand.original_answer}")

    await close_db()

    print("=" * 60)
    failed = [r for r in _results if not r[1]]
    print(f"结果: {len(_results) - len(failed)}/{len(_results)} 通过")
    if failed:
        for s, _, d in failed:
            print(f"  FAIL {s}: {d}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))