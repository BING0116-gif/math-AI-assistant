from __future__ import annotations

import asyncio
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import delete, select

from app.data.database import close_db, get_db_session, init_db
from app.data.models import Question
from app.services.pdf_question_parser import PDFQuestionParser
from app.services.question_importer import QuestionImporter

ROOT = Path(r"C:\Users\HUAWEI\Desktop\高数题＋答案pdf")
TARGETS = {
    "第五章定积分.pdf": ("定积分与应用", "第五章定积分.pdf"),
    "第六章多元函数.pdf": ("多元函数微分与二重积分", "第六章多元函数.pdf"),
    "第八章微分方程自测题.pdf": ("微分方程", "第八章微分方程自测题 答案与提示.pdf"),
}
MARKER = re.compile(r"^\s*\d+\s*[．.、)]\s*(答案|解|证明)\s*[:：]?\s*(.*)$")


def entries(path: Path) -> list[tuple[str, str]]:
    import pdfplumber
    with pdfplumber.open(path) as pdf:
        text = "\n".join((p.extract_text() or "") for p in pdf.pages)
    found: list[tuple[str, str]] = []
    current: tuple[str, list[str]] | None = None
    for line in text.splitlines():
        m = MARKER.match(line)
        if m:
            if current:
                found.append((current[0], "\n".join(current[1]).strip()))
            current = (m.group(1), [m.group(2).strip()])
        elif current:
            # Stop an entry at a new section/version heading; ordinary formula
            # lines remain part of the worked solution.
            if re.match(r"^自测题\s*[ABC]", line) and "答案" in line:
                continue
            current[1].append(line.strip())
    if current:
        found.append((current[0], "\n".join(current[1]).strip()))
    return [(kind, body) for kind, body in found if body]


def mistakes(kind: str, chapter: str) -> list[dict[str, str]]:
    if kind == "选择题":
        return [{"type": "选项判断", "description": "只凭结论或忽略定义域、适用条件。", "suggestion": "先写出定义、条件和排除项，再核对选项。"}]
    if kind == "填空题":
        return [{"type": "计算细节", "description": "漏写常数、区间端点或等价条件。", "suggestion": "完成后检查定义域、边界和量纲。"}]
    if "证明" in kind:
        return [{"type": "证明结构", "description": "只写结论，未交代定理条件和关键中间步骤。", "suggestion": "按条件、定理、推导、结论四步书写。"}]
    return [{"type": "方法选择", "description": f"未先识别{chapter}的适用条件，直接套用公式。", "suggestion": "先标注已知条件和目标，再选择定理或换元方法。"}]


async def main() -> None:
    await init_db()
    parser = PDFQuestionParser(default_category="高等数学一")
    importer = QuestionImporter()
    report = []
    for filename, (chapter, answer_filename) in TARGETS.items():
        source = ROOT / filename
        parsed = await parser.parse(str(source))
        answers = entries(ROOT / answer_filename)
        rows = []
        for i, q in enumerate(parsed.questions, 1):
            digest = hashlib.sha256(f"{filename}:{i}:{q.content}".encode()).hexdigest()[:19]
            qtype = q.question_type.rstrip("：:")
            body = answers[i - 1][1] if i <= len(answers) else ""
            answer = body.splitlines()[0][:500] if body else "待人工审核"
            analysis = body[:5000] if body else f"{chapter}综合题。应先识别题型与适用定理，列出关键步骤并复核边界条件。原题答案未能从 PDF 稳定提取，需人工复核。"
            kp = ["高等数学一", chapter]
            if "极限" in q.content or "lim" in q.content: kp.append("极限与连续")
            if "导数" in q.content or "偏导" in q.content: kp.append("导数与微分")
            if "积分" in q.content or "∫" in q.content: kp.append("积分")
            difficulty = 2 if "选择" in qtype else 3 if "填空" in qtype else 5 if "证明" in qtype else 4
            rows.append({
                "id": f"P{digest}", "content": q.content, "question_type": qtype,
                "options": json.dumps(q.options, ensure_ascii=False), "answer": answer,
                "analysis": analysis, "category": "高等数学一", "sub_categories": chapter,
                "knowledge_points": json.dumps(list(dict.fromkeys(kp)), ensure_ascii=False),
                "difficulty": difficulty, "estimated_time": 2 if difficulty <= 2 else 8 if difficulty >= 5 else 5,
                "source": f"PDF:{filename}", "common_mistakes": json.dumps(mistakes(qtype, chapter), ensure_ascii=False),
                "answer_spec": json.dumps({"kind": "pdf_extraction", "verification_status": "needs_human_review"}, ensure_ascii=False),
                "review_status": "draft", "needs_review": True,
            })
        source_name = f"PDF:{filename}"
        async with get_db_session() as db:
            old = (await db.execute(select(Question).where(Question.source == source_name))).scalars().all()
            for q in old:
                await db.delete(q)
            await db.commit()
        result = await importer.import_from_dict_list(rows, trusted=False)
        report.append({"source": filename, "parsed": len(rows), "answers_extracted": len(answers), "success": result.success, "failed": result.failed, "errors": result.errors[:5]})
    Path("tmp/embedded_answer_enrichment.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    await close_db()


asyncio.run(main())
