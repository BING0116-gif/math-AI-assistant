from __future__ import annotations
import asyncio, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import select
from app.data.database import init_db, close_db, get_db_session
from app.data.models import Question

CHAPTERS = {
    "第一章": "函数与极限", "第二章": "导数与微分", "第三章": "导数的应用",
    "第四章": "不定积分", "第五章": "定积分与应用", "第六章": "多元函数微分与二重积分",
    "第七章": "无穷级数", "第八章": "微分方程", "第九章": "无穷级数",
}

def chapter(source: str) -> str:
    for k, v in CHAPTERS.items():
        if k in source: return v
    return "高等数学一综合复习"

def qtype(value: str, content: str) -> str:
    v = (value or "").strip().rstrip("：:")
    if v.startswith("模块") or v.startswith("2025") or v in {"综合题", "综合计算题"}: return "综合题"
    if "选择" in v: return "选择题"
    if "填空" in v: return "填空题"
    if "证明" in v and "计算" not in v: return "证明题"
    if "应用" in v: return "应用题"
    if "计算" in v or "解答" in v: return "计算题"
    if any(x in content for x in ("证明", "求证")): return "证明题"
    return "解答题"

def mistakes(kind: str, ch: str):
    if kind == "选择题": desc, sug = "忽略定义、适用条件或定义域，凭熟悉选项作答。", "先列条件和定义域，再逐项验证。"
    elif kind == "填空题": desc, sug = "漏写积分常数、边界端点、分支或等价条件。", "检查定义域、端点、常数和结果的可代入性。"
    elif kind == "证明题": desc, sug = "只写结论，未交代定理条件和中间推导。", "按条件、定理、推导、结论四步完成证明。"
    else: desc, sug = f"未先识别{ch}的题型和适用定理，直接套公式。", "先写已知与目标，再选择定理、换元或计算路径。"
    return [{"type": "高数一常见错误", "description": desc, "suggestion": sug}]

async def main():
    await init_db()
    async with get_db_session() as db:
        rows = (await db.execute(select(Question).where(Question.id.like("P%")))).scalars().all()
        for q in rows:
            ch = chapter(q.source or "")
            kind = qtype(q.question_type, q.content or "")
            q.category = "高等数学一"
            q.question_type = kind
            q.sub_categories = ch
            try: old = json.loads(q.knowledge_points or "[]")
            except Exception: old = []
            if not isinstance(old, list): old = [str(old)]
            q.knowledge_points = json.dumps(list(dict.fromkeys(["高等数学一", ch, *[str(x) for x in old if x]])), ensure_ascii=False)
            if q.common_mistakes is None: q.common_mistakes = mistakes(kind, ch)
            if q.answer_spec is None: q.answer_spec = {"kind": "pdf_extraction", "verification_status": "needs_human_review"}
            if not q.analysis or q.analysis.startswith("待人工审核"):
                q.analysis = f"本题归入高等数学一“{ch}”。解题时应先识别题型，写出相关定义或定理，完成关键变形/计算，并用定义域、边界条件或代回结果复核。原始 PDF 未提供可稳定核验的完整解析，当前记录保留待人工复核标记。"
        await db.commit()
    await close_db()

asyncio.run(main())
