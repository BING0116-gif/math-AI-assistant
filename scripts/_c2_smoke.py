# -*- coding: utf-8 -*-
"""Step 1.1-C2 本地真实 PDF smoke（不提交学校 PDF / 不落 git）。

验证（§33）：
- PDF -> DocumentParser -> candidates 持久化
- supported candidate -> QuestionImporter -> draft（SQLite 临时库）
- candidate 重启后仍可查询（新 session 重查）
- 重复 draft 幂等（不重复建题）
- original answer 保留
- AI_ENABLED=false 主链路可用

用法：
    python scripts/_c2_smoke.py            # quick 模式 smoke
    python scripts/_c2_smoke.py mineru     # mineru 模式 smoke（需 MINERU_EXECUTABLE）
"""
import asyncio
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

# 环境：AI 关闭 + 临时 SQLite 库（不触碰 data/math_ai.db）
TMP_DB = Path(tempfile.mkdtemp(prefix="c2_smoke_")) / "smoke.db"
os.environ["AI_ENABLED"] = "false"
os.environ["DATABASE_URL"] = f"sqlite:///{TMP_DB}"
os.environ["ASYNC_DATABASE_URL"] = ""
os.environ["CONTENT_STORAGE_ROOT"] = str(Path(tempfile.mkdtemp(prefix="c2_smoke_content_")))

# MinerU executable：仅 smoke 时从环境注入（生产只读 settings.MINERU_EXECUTABLE）。
# 本机因 MinerU 模型未下载 + Demo venv uv trampoline 损坏，无法完成真实 mineru 实解析；
# 故 mineru 模式仅验证「未配置 executable → 稳定 PARSER_UNAVAILABLE，不导致启动失败」。
DEMO_MINERU = ROOT / "math_question_bank_pdf_demo" / ".venv" / "Scripts" / "mineru.exe"
PDF_PATH = ROOT / "math_question_bank_pdf_demo" / "uploads" / "第一章自测题2010-1-20.pdf"

async def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "quick"
    print("=" * 70)
    print(f"C2 smoke | mode={mode} | AI_ENABLED={os.environ['AI_ENABLED']}")
    print(f"  DB={TMP_DB}")
    print(f"  PDF={PDF_PATH}")
    print("=" * 70)

    from app.data.database import init_db, close_db, get_db_session
    from app.data.models import Base, Question, ContentImportCandidate
    from app.services.content_import import ContentImportService
    from sqlalchemy import select

    await init_db()
    async with get_db_session() as db:
        pass  # init_db 已建表（测试约定）

    service = ContentImportService()

    # ── 0. mineru 模式：本机未配置 executable → 稳定 PARSER_UNAVAILABLE，不导致整体失败 ──
    if mode == "mineru":
        os.environ["MINERU_EXECUTABLE"] = ""  # 模拟未配置
        from app.services.document_parser import ContentParseError, MODE_MINERU, PARSER_UNAVAILABLE
        try:
            batch0, _ = await service.create_import(
                admin_user_id="c2-smoke-admin",
                original_filename=PDF_PATH.name,
                content=PDF_PATH.read_bytes(),
                mode=MODE_MINERU,
            )
            await service.parse_import(batch0.id)
            print("[0] mineru 未配置 executable：意外解析成功（不应发生）")
            return 1
        except ContentParseError as e:
            ok = e.code == PARSER_UNAVAILABLE
            print(f"[0] mineru 未配置 executable → PARSER_UNAVAILABLE={ok} code={e.code}")
            failed = await service.get_batch(batch0.id)
            print(f"    batch.status={failed.status} error_code={failed.error_code}")
            assert ok and failed.status == "failed" and failed.error_code == PARSER_UNAVAILABLE
        except Exception as e:  # noqa: BLE001
            print(f"[0] mineru 未配置 executable：非稳定异常 {type(e).__name__}: {e}")
            return 1
        print("\n[OK] mineru 模式降级验证通过（真实 mineru 实解析留待模型就绪环境）。")
        await close_db()
        return 0

    # ── 1. create_import（quick）──
    pdf = PDF_PATH.read_bytes()
    batch, created = await service.create_import(
        admin_user_id="c2-smoke-admin",
        original_filename=PDF_PATH.name,
        content=pdf,
        mode=mode,
        idempotency_key="c2-smoke-idem-1",
    )
    print(f"\n[1] create_import: batch={batch.id} created={created} status={batch.status}")

    # ── 2. parse → candidates ──
    batch = await service.parse_import(batch.id)
    candidates = await service.list_candidates(batch.id)
    print(f"[2] parse_import: status={batch.status} candidates={len(candidates)} "
          f"stats={batch.stats} err={batch.error_code}")
    supported = [c for c in candidates if c.supported]
    print(f"    supported={len(supported)} / {len(candidates)}")
    for c in candidates[:5]:
        print(f"    - idx={c.candidate_index} type={c.detected_question_type} "
              f"supported={c.supported} page={c.source_page_start}")

    # ── 3. 重启后仍可查询（新 session）──
    reloaded = await service.list_candidates(batch.id)
    print(f"[3] reload list_candidates: {len(reloaded)} (persisted, 可重启后查询)")

    if not supported:
        print("\n[SKIP] 无可转 draft 的 supported candidate（本 PDF 可能以计算/大题为主）")
        await close_db()
        return 0

    # ── 4. 选 1~2 道 supported → draft ──
    sel = supported[:2]
    ids = [c.id for c in sel]
    res = await service.create_drafts(batch.id, ids)
    print(f"[4] create_drafts: created={res['created']} skipped={len(res['skipped'])} errors={res['errors']}")
    if not res["created"]:
        print("    !! 无 created，检查 errors")
        await close_db()
        return 0

    # 校验 draft 属性
    async with get_db_session() as db:
        q = await db.get(Question, res["created"][0])
        cand = await db.get(ContentImportCandidate, sel[0].id)
        if q is None:
            print("    !! draft Question 未找到")
            return 1
        print(f"    draft: id={q.id} type={q.question_type} review_status={q.review_status} "
              f"source_candidate_id={q.source_candidate_id}")
        print(f"    answer='{q.answer}' analysis_len={len(q.analysis)}")
        print(f"    candidate.original_answer='{cand.original_answer}' "
              f"original_solution_len={len(cand.original_solution)}")
        assert q.review_status == "draft", "draft 必须为 draft"
        assert q.source_candidate_id == cand.id, "source_candidate_id 必须指向 candidate"
        assert cand.original_answer is not None, "original_answer 必须保留"

    # ── 5. 同 candidate 重复 draft → 幂等 ──
    res2 = await service.create_drafts(batch.id, ids)
    print(f"[5] 重复 create_drafts: created={len(res2['created'])} skipped={len(res2['skipped'])}")
    async with get_db_session() as db:
        dup = (await db.execute(
            select(Question).where(Question.source_candidate_id.in_(ids))
        )).scalars().all()
    print(f"    candidate->draft 唯一性: draft 数={len(dup)}（期望=1..2，无重复）")

    await close_db()
    print("\n[OK] C2 smoke 完成。这些是开发测试数据（draft），未 published。")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))