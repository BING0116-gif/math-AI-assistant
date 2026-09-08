from __future__ import annotations
from pathlib import Path
import json
import shutil
import subprocess
import re

from question_splitter import split_pages

def extract_pdf_quick(pdf_path: str | Path):
    """快速模式：用 PyMuPDF 提取电子 PDF 的文字。"""
    import fitz  # PyMuPDF

    pdf_path = Path(pdf_path)
    doc = fitz.open(pdf_path)
    pages = []
    for i, page in enumerate(doc):
        text = page.get_text("text", sort=True)
        pages.append({"page": i + 1, "text": text})
    doc.close()
    return pages

def mineru_available() -> bool:
    return shutil.which("mineru") is not None

def extract_pdf_mineru(pdf_path: str | Path, output_root: str | Path = "parsed"):
    """
    数学增强模式：调用 MinerU CLI。
    返回 Markdown 文件路径和文本。
    """
    pdf_path = Path(pdf_path)
    output_root = Path(output_root)
    output_dir = output_root / pdf_path.stem
    output_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        "mineru",
        "-p", str(pdf_path),
        "-o", str(output_dir),
        "-b", "pipeline",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            "MinerU 解析失败。\n\nSTDOUT:\n"
            + proc.stdout[-3000:]
            + "\n\nSTDERR:\n"
            + proc.stderr[-3000:]
        )

    md_files = sorted(output_dir.rglob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not md_files:
        raise RuntimeError("MinerU 已运行，但没有找到生成的 Markdown 文件。")
    md_path = md_files[0]
    return md_path, md_path.read_text(encoding="utf-8", errors="replace")

def _guess_question_type(text: str):
    t = text or ""
    # 简单启发式，仅用于导入预填
    if re.search(r"(?m)^\s*[A-DＡ-Ｄ][\.．、:：]\s*", t) or all(x in t for x in ["A", "B", "C", "D"]):
        return "选择题"
    if "____" in t or "______" in t or "填空" in t:
        return "填空题"
    return "解答题"

def _guess_options(text: str):
    opts = []
    # 行首 A. / B. / C. / D.
    for m in re.finditer(r"(?m)^\s*([A-DＡ-Ｄ])\s*[\.．、:：]\s*(.+?)\s*$", text or ""):
        letter = m.group(1)
        content = m.group(2).strip()
        opts.append(f"{letter}. {content}")
    return opts

def make_import_records(pdf_path: str | Path, mode="quick"):
    """
    将 PDF 转成当前数据库可接受的题目记录。
    quick: PyMuPDF
    mineru: MinerU Markdown
    """
    pdf_path = Path(pdf_path)

    if mode == "quick":
        pages = extract_pdf_quick(pdf_path)
        chunks = split_pages(pages)
        records = []
        for idx, item in enumerate(chunks, 1):
            txt = item["text"].strip()
            records.append({
                "external_id": f"{pdf_path.stem}_{item['page']:03d}_{idx:03d}",
                "subject": "数学",
                "grade": "待分类",
                "chapter": "待分类",
                "difficulty": "待分类",
                "question_type": _guess_question_type(txt),
                "stem_markdown": txt,
                "answer_markdown": "",
                "solution_markdown": "",
                "formulas": [],
                "options": _guess_options(txt),
                "source_document": pdf_path.name,
                "source_page": item["page"],
                "review_status": "待复核",
            })
        return records

    if mode == "mineru":
        md_path, text = extract_pdf_mineru(pdf_path)
        # MinerU 输出含 LaTeX；Demo 版统一切分，页码暂记 1。
        from question_splitter import split_questions
        chunks = split_questions(text)
        records = []
        for idx, txt in enumerate(chunks, 1):
            records.append({
                "external_id": f"{pdf_path.stem}_mineru_{idx:03d}",
                "subject": "数学",
                "grade": "待分类",
                "chapter": "待分类",
                "difficulty": "待分类",
                "question_type": _guess_question_type(txt),
                "stem_markdown": txt,
                "answer_markdown": "",
                "solution_markdown": "",
                "formulas": [],
                "options": _guess_options(txt),
                "source_document": pdf_path.name,
                "source_page": 1,
                "review_status": "待复核",
            })
        return records

    raise ValueError(f"未知模式: {mode}")
