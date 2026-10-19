from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.pdf_question_parser import PDFQuestionParser
from app.services.question_importer import QuestionImporter
from app.data.database import init_db, close_db

ROOT = Path(r"C:\Users\HUAWEI\Desktop\高数题＋答案pdf")
OUT = Path("tmp/pdf_import_manifest.json")


def answer_for(source: Path) -> Path | None:
    stem = source.stem
    candidates = [p for p in ROOT.glob("*.pdf") if ("答案" in p.name or "提示" in p.name) and any(token in p.stem for token in stem.split())]
    # Chapter number is the most stable pairing signal for these files.
    import re
    m = re.search(r"第([一二三四五六七八九十]+)章", stem)
    if m:
        candidates = [p for p in ROOT.glob("*.pdf") if ("答案" in p.name or "提示" in p.name) and f"第{m.group(1)}章" in p.name]
    return candidates[0] if candidates else None


async def main() -> None:
    await init_db()
    parser = PDFQuestionParser(default_category="高等数学")
    importer = QuestionImporter()
    manifest = {"schema_version": "pdf-import-v2", "status": "draft_only", "files": [], "total": 0, "success": 0, "failed": 0}
    for source in sorted(ROOT.glob("*.pdf")):
        if "答案" in source.name or "提示" in source.name or source.name.startswith("4e"):
            continue
        result = await parser.parse(str(source), str(answer_for(source)) if answer_for(source) else None)
        rows = parser.to_import_dicts(result, category="高等数学", source_name=f"PDF:{source.name}")
        for index, row in enumerate(rows, 1):
            digest = hashlib.sha256(f"{source.name}:{index}:{row['content']}".encode("utf-8")).hexdigest()[:20]
            # questions.id is varchar(20) in the current schema.
            row["id"] = f"P{digest[:19]}"
            row["review_status"] = "draft"
            row["needs_review"] = True
            row["answer"] = row.get("answer") or "待人工审核"
            row["analysis"] = row.get("analysis") or "待人工审核；来源页需复核。"
            row["answer_spec"] = json.dumps({"kind": "pdf_extraction", "verification_status": "needs_human_review"}, ensure_ascii=False)
            row["source"] = f"PDF:{source.name}"
        imported = await importer.import_from_dict_list(rows, trusted=False) if rows else None
        item = {"source": source.name, "parsed": len(rows), "parser_errors": result.errors, "parser_warnings": result.warnings}
        if imported:
            item.update({"success": imported.success, "failed": imported.failed, "errors": imported.errors[:20]})
            manifest["total"] += imported.total; manifest["success"] += imported.success; manifest["failed"] += imported.failed
        manifest["files"].append(item)
        OUT.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        print(source.name, len(rows), item.get("success", 0), item.get("failed", 0), flush=True)
    OUT.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    await close_db()


if __name__ == "__main__":
    asyncio.run(main())
