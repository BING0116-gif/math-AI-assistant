# -*- coding: utf-8 -*-
"""Step 1.1-C2 PostgreSQL Runtime Verification（真实 PostgreSQL，非 SQLite）。

在真实 PG（已 `alembic upgrade head`）上执行最小 Content Ingestion 业务链：
  SourceDocument -> ImportBatch -> ContentImportCandidate -> supported candidate
  -> QuestionImporter -> Question(draft)

验证：
  - create_import / parse_import（quick 模式真实学校 PDF）
  - candidates 持久化（新 session 重查）
  - supported candidate -> draft（复用 QuestionImporter）
  - provenance：Question.source_candidate_id -> Candidate -> ImportBatch -> SourceDocument 真实可查
  - original_answer / original_solution 保留（update_candidate 后转 draft）
  - 同 candidate 重复 draft 幂等（不创建第二道 Question）
  - PG 层 UNIQUE / FK / RESTRICT 真正生效（非 SQLite 行为）

用法：
    python scripts/_c2_pg_runtime_verify.py
"""
import asyncio
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

PG_SYNC = os.environ.get(
    "PG_SYNC_URL", "postgresql://mathai:mathai_test@localhost:5432/math_ai_c2_empty"
)
PG_ASYNC = PG_SYNC.replace("postgresql://", "postgresql+asyncpg://", 1)

os.environ["ASYNC_DATABASE_URL"] = PG_ASYNC
os.environ["DATABASE_URL"] = PG_SYNC
os.environ["AI_ENABLED"] = "false"
os.environ["MINERU_EXECUTABLE"] = ""  # 本脚本只用 quick 模式
os.environ["CONTENT_STORAGE_ROOT"] = str(Path(tempfile.mkdtemp(prefix="c2_pg_content_")))

PDF_PATH = ROOT / "math_question_bank_pdf_demo" / "uploads" / "第一章自测题2010-1-20.pdf"

PASS = "PASS"
FAIL = "FAIL"
_results = []


def report(section, ok, detail=""):
    _results.append((section, ok, detail))
    print(f"[{'✓' if ok else '✗'}] {section}  {detail}")


async def main():
    from sqlalchemy import select, delete
    from sqlalchemy.exc import IntegrityError

    from app.data.database import init_db, close_db, get_db_session
    from app.data.models import (
        Question,
        ContentImportCandidate,
        ImportBatch,
        SourceDocument,
    )
    from app.services.content_import import ContentImportService

    await init_db()
    service = ContentImportService()
    print("=" * 70)
    print("C2 PostgreSQL Runtime Verification")
    print(f"  DB = {PG_SYNC}")
    print(f"  PDF = {PDF_PATH.name}")
    print("=" * 70)

    # 清理本脚本可能残留（幂等重跑安全）
    async with get_db_session() as db:
        await db.execute(delete(Question).where(Question.id.like("CI%")))
        cand_ids = (await db.execute(select(ContentImportCandidate.id))).scalars().all()
        await db.execute(delete(ContentImportCandidate).where(ContentImportCandidate.id.in_(cand_ids)))
        await db.execute(delete(ImportBatch).where(ImportBatch.created_by == "c2-pg-admin"))
        await db.execute(delete(SourceDocument).where(SourceDocument.created_by == "c2-pg-admin"))
        await db.commit()

    # ── 1. create_import ──
    pdf = PDF_PATH.read_bytes()
    batch, created = await service.create_import(
        admin_user_id="c2-pg-admin",
        original_filename=PDF_PATH.name,
        content=pdf,
        mode="quick",
        idempotency_key="c2-pg-idem-1",
    )
    report("create_import -> ImportBatch", created and batch.status == "pending", batch.id)

    # 幂等 create：同 admin+key 不重复
    batch2, created2 = await service.create_import(
        admin_user_id="c2-pg-admin",
        original_filename=PDF_PATH.name,
        content=pdf,
        mode="quick",
        idempotency_key="c2-pg-idem-1",
    )
    report("create_import 幂等", (not created2) and batch2.id == batch.id,
           f"batch 数唯一={not created2}")

    # ── 2. parse -> candidates ──
    batch = await service.parse_import(batch.id)
    candidates = await service.list_candidates(batch.id)
    supported = [c for c in candidates if c.supported]
    report("parse_import -> candidates 持久化", batch.status == "parsed" and len(candidates) > 0,
           f"status={batch.status} candidates={len(candidates)} supported={len(supported)}")
    report("supported candidate 存在", len(supported) > 0,
           f"choice/numeric_fill 等 supported={len(supported)}")

    # 新 session 重查（模拟重启）
    reloaded = await service.list_candidates(batch.id)
    report("candidates 重启后仍可查询", len(reloaded) == len(candidates),
           f"reload={len(reloaded)}")

    # ── 3. 选 1~2 道 supported；其中一道先 update_candidate 填原答案/解析 ──
    sel = supported[:2]
    for c in sel:
        report("candidate 元信息", c.source_question_number is not None or c.source_page_start is not None,
               f"idx={c.candidate_index} type={c.detected_question_type} page={c.source_page_start}")
    # 第一道填 original_answer / original_solution，验证原答案保留
    first = sel[0]
    await service.update_candidate(
        batch.id,
        first.id,
        {"original_answer": "B", "original_solution": "由极限运算法则可得答案"},
    )
    res = await service.create_drafts(batch.id, [c.id for c in sel])
    report("candidate -> Question draft 成功", len(res["created"]) > 0 and not res["errors"],
           f"created={res['created']} skipped={res['skipped']} errors={res['errors']}")

    # ── 4. draft 属性 + provenance 链 ──
    async with get_db_session() as db:
        q = await db.get(Question, res["created"][0])
        if q is not None:
            cand = await db.get(ContentImportCandidate, q.source_candidate_id)
            b = await db.get(ImportBatch, cand.import_batch_id)
            sd = await db.get(SourceDocument, b.source_document_id)
            prov_ok = (
                q.review_status == "draft"
                and q.source_candidate_id == cand.id
                and cand.import_batch_id == b.id
                and b.source_document_id == sd.id
                and sd.original_filename == PDF_PATH.name
            )
            report("provenance: Question->Candidate->Batch->SourceDocument 可查", prov_ok,
                   f"review_status={q.review_status} filename={sd.original_filename}")
            report("原答案保留（未覆盖）", q.answer == "B" and q.analysis == "由极限运算法则可得答案",
                   f"answer='{q.answer}' analysis='{q.analysis}'")
            qid0 = q.id

    # ── 5. 同 candidate 重复 draft -> 幂等（应用层 + PG UNIQUE）──
    res2 = await service.create_drafts(batch.id, [c.id for c in sel])
    async with get_db_session() as db:
        dup = (await db.execute(
            select(Question).where(Question.source_candidate_id.in_([c.id for c in sel]))
        )).scalars().all()
    report("重复 draft 幂等（应用层）", len(dup) == len(sel) and len(res2["created"]) == 0,
           f"created={len(res2['created'])} skipped={len(res2['skipped'])} draft 总数={len(dup)}")

    # ── 6. PG 层 UNIQUE 真正生效：直接 INSERT 第二道同 source_candidate_id 的题 ──
    try:
        async with get_db_session() as db:
            db.add(Question(
                id="CIXXXXUNIQUETEST01",
                content="违反 UNIQUE 的重复题",
                question_type="choice",
                options=[],
                answer="A",
                category="测试",
                difficulty=3,
                review_status="draft",
                source_candidate_id=sel[0].id,
            ))
            await db.commit()
        report("PG UNIQUE 约束阻止重复 source_candidate_id", False, "未触发 IntegrityError（异常）")
    except IntegrityError:
        report("PG UNIQUE 约束阻止重复 source_candidate_id", True,
               "duplicate key 被 PostgreSQL 拒绝")
    except Exception as e:  # noqa: BLE001
        report("PG UNIQUE 约束阻止重复 source_candidate_id", False, f"{type(e).__name__}: {e}")

    # ── 7. PG FK RESTRICT 真正生效：删除已有批次/候选的 source_document 应被拒绝 ──
    async with get_db_session() as db:
        sd = (await db.execute(
            select(SourceDocument).where(SourceDocument.created_by == "c2-pg-admin")
        )).scalars().first()
        sd_id = sd.id
    try:
        async with get_db_session() as db:
            sd = await db.get(SourceDocument, sd_id)
            await db.delete(sd)
            await db.commit()
        report("PG FK RESTRICT 阻止删除已关联 SourceDocument", False, "删除成功（异常）")
    except IntegrityError:
        report("PG FK RESTRICT 阻止删除已关联 SourceDocument", True,
               "update/delete on 违反外键，被 RESTRICT 拒绝")
    except Exception as e:  # noqa: BLE001
        report("PG FK RESTRICT 阻止删除已关联 SourceDocument", False, f"{type(e).__name__}: {e}")

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
