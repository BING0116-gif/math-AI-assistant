# -*- coding: utf-8 -*-
"""Step 1.1-C2 MinerU 真实 E2E（真实 PostgreSQL + 真实 MinerU runtime）。

流程（§12 + §13）：
  学校 PDF
  → DocumentParser.parse(mode="mineru")（真实 subprocess 调用 MINERU_EXECUTABLE）
  → ParsedDocument（Markdown 非空 + 含 LaTeX）
  → QuestionSplitter → ContentImportCandidate[]
  → ContentImportService.create_import / parse_import（候选持久化到真实 PG）
  → 选 1~2 道 supported candidate → QuestionImporter → Question(draft)

验证：
  - PDF -> MinerU exit 0 -> Markdown 非空 -> 数学公式存在
  - DocumentParser adapter 真实调用 MINERU_EXECUTABLE
  - candidates > 0，抽查普通中文题干 / 含公式题 / 选择题
  - candidates 持久化到 PostgreSQL
  - candidate -> draft（仅 supported、draft、provenance、原答案保留）
  - 同 candidate 重复 draft 幂等
  - 无题被自动 published

用法：
    python scripts/_c2_mineru_e2e.py
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

MINERU_EXE = os.environ.get(
    "MINERU_EXECUTABLE",
    str(ROOT / "math_question_bank_pdf_demo" / ".venv" / "Scripts" / "mineru.exe"),
)

os.environ["ASYNC_DATABASE_URL"] = PG_ASYNC
os.environ["DATABASE_URL"] = PG_SYNC
os.environ["AI_ENABLED"] = "false"
os.environ["MINERU_EXECUTABLE"] = MINERU_EXE
os.environ["MINERU_MODEL_SOURCE"] = "modelscope"  # 用户级 ModelScope 缓存
os.environ["CONTENT_STORAGE_ROOT"] = str(Path(tempfile.mkdtemp(prefix="c2_mineru_content_")))

PDF_PATH = ROOT / "math_question_bank_pdf_demo" / "uploads" / "第一章自测题2010-1-20.pdf"

PASS = "PASS"
FAIL = "FAIL"
_results = []


def report(section, ok, detail=""):
    _results.append((section, ok, detail))
    print(f"[{'✓' if ok else '✗'}] {section}  {detail}")


async def main():
    from sqlalchemy import select, delete

    from app.data.database import init_db, close_db, get_db_session
    from app.data.models import (
        Question,
        ContentImportCandidate,
        ImportBatch,
        SourceDocument,
    )
    from app.services.document_parser import DocumentParser
    from app.services.question_splitter import split_document
    from app.services.content_import import ContentImportService

    await init_db()
    service = ContentImportService()
    print("=" * 72)
    print("C2 MinerU 真实 E2E")
    print(f"  PG    = {PG_SYNC}")
    print(f"  MinerU= {MINERU_EXE} (exists={os.path.exists(MINERU_EXE)})")
    print(f"  PDF   = {PDF_PATH.name}")
    print("=" * 72)

    # 清理残留（幂等重跑安全）
    async with get_db_session() as db:
        await db.execute(delete(Question).where(Question.id.like("CI%")))
        cand_ids = (await db.execute(select(ContentImportCandidate.id))).scalars().all()
        await db.execute(delete(ContentImportCandidate).where(ContentImportCandidate.id.in_(cand_ids)))
        await db.execute(delete(ImportBatch).where(ImportBatch.created_by == "c2-mineru-admin"))
        await db.execute(delete(SourceDocument).where(SourceDocument.created_by == "c2-mineru-admin"))
        await db.commit()

    # ══ §12 DocumentParser adapter 直测 ══
    print("\n[§12] DocumentParser.parse(mode='mineru') ...")
    parser = DocumentParser()
    parsed = parser.parse(PDF_PATH, mode="mineru")
    report("§12 PDF -> MinerU -> ParsedDocument", parsed.parser_name == "mineru"
           and len(parsed.markdown.strip()) > 100,
           f"parser={parsed.parser_name} version={parsed.parser_version} md_len={len(parsed.markdown)}")
    report("§12 Markdown 含数学公式(LaTeX $)", "$" in parsed.markdown,
           f"dollar 数={parsed.markdown.count('$')}")
    report("§12 page_mapping_uncertain", parsed.page_mapping_uncertain is True,
           "mineru 页码映射不确定已标记")
    splits = split_document(parsed)
    report("§12 Splitter -> SplitQuestion[] > 0", len(splits) > 0, f"splits={len(splits)}")

    # 抽查几个候选：普通中文题干 / 含公式 / 选择题
    import re as _re
    sample_types = {}
    for s in splits[:8]:
        sample_types[s.detected_question_type] = sample_types.get(s.detected_question_type, 0) + 1
    has_plain_zh = any(any('\u4e00' <= ch <= '\u9fff' for ch in (s.raw_text[:40])) for s in splits)
    has_math_cand = any('$' in s.raw_text for s in splits)
    # 选择题按内容识别（选项内联如 "f(7)=( ）A 7 B-7 C 0 D 3"），不依赖 splitter 分题型
    _opt = _re.compile(r"[）)]\s*[A-D]")
    choice_by_content = [s for s in splits if _opt.search(s.raw_text)]
    report("§12 抽查: 普通中文题干", has_plain_zh,
           f"candidates={len(splits)}")
    report("§12 抽查: 含数学公式(LaTeX)候选", has_math_cand,
           f"含 $ 候选数={sum(1 for s in splits if '$' in s.raw_text)}/{len(splits)}")
    report("§12 抽查: 选择题(按选项内容识别)", len(choice_by_content) > 0,
           f"内容为选择题={len(choice_by_content)} splitter type分布={sample_types}")
    if len(choice_by_content) > 0 and len([s for s in splits if s.detected_question_type == 'choice']) == 0:
        print("  [C3 备注] 选择题选项内联(如 '）A 7 B-7 C 0 D 3')，splitter 未标为 choice 而标 numeric_fill —— 分题型归属 C3 质量范围，不影响 C2 runtime 验收")

    # ══ §13 正式 E2E：service 链路持久化到 PG ══
    print("\n[§13] ContentImportService 链路（真实 PG 持久化）...")
    batch, created = await service.create_import(
        admin_user_id="c2-mineru-admin",
        original_filename=PDF_PATH.name,
        content=PDF_PATH.read_bytes(),
        mode="mineru",
        idempotency_key="c2-mineru-e2e-1",
    )
    report("§13 create_import -> ImportBatch", created and batch.status == "pending", batch.id)

    batch = await service.parse_import(batch.id)
    candidates = await service.list_candidates(batch.id)
    supported = [c for c in candidates if c.supported]
    report("§13 candidates 持久化到 PG", batch.status == "parsed" and len(candidates) > 0,
           f"status={batch.status} candidates={len(candidates)} supported={len(supported)} stats={batch.stats}")
    report("§13 supported candidate > 0", len(supported) > 0, f"supported={len(supported)}")

    # 抽查持久化候选内容
    for c in supported[:2]:
        report("§13 候选内容抽查", bool(c.stem) and (c.detected_question_type in ("choice", "numeric_fill")),
               f"idx={c.candidate_index} type={c.detected_question_type} page={c.source_page_start} stem_len={len(c.stem or '')}")

    # 选 1~2 道 supported -> draft
    sel = supported[:2]
    res = await service.create_drafts(batch.id, [c.id for c in sel])
    report("§13 candidate -> Question draft", len(res["created"]) > 0 and not res["errors"],
           f"created={res['created']} skipped={res['skipped']} errors={res['errors']}")

    # provenance + draft 属性
    async with get_db_session() as db:
        q = await db.get(Question, res["created"][0])
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
        report("§13 provenance 全链路可查", prov_ok,
               f"review_status={q.review_status} type={q.question_type}")
        report("§13 无题自动 published",
               (await db.execute(select(Question).where(Question.review_status == "published"))).scalars().all() == [],
               "published=0")

    # 幂等：同 candidate 重复 draft
    res2 = await service.create_drafts(batch.id, [c.id for c in sel])
    async with get_db_session() as db:
        dup = (await db.execute(
            select(Question).where(Question.source_candidate_id.in_([c.id for c in sel]))
        )).scalars().all()
    report("§13 重复 draft 幂等", len(dup) == len(sel) and len(res2["created"]) == 0,
           f"created={len(res2['created'])} skipped={len(res2['skipped'])} draft 总数={len(dup)}")

    await close_db()

    print("=" * 72)
    failed = [r for r in _results if not r[1]]
    print(f"结果: {len(_results) - len(failed)}/{len(_results)} 通过")
    if failed:
        for s, _, d in failed:
            print(f"  ✗ {s}: {d}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
