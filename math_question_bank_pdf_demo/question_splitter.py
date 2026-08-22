import re
from typing import List, Dict

# 常见中文试卷题号：1. / 1、/ 1．/ 第1题
QUESTION_RE = re.compile(
    r"(?m)^\s*(?:(?:第\s*)?(\d+)\s*(?:题|[\.．、]))\s*"
)

def split_questions(text: str) -> List[str]:
    """按常见主问题号切分。若无法识别题号，则整段作为 1 道题返回。"""
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return []

    matches = list(QUESTION_RE.finditer(text))
    if not matches:
        return [text]

    parts = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        chunk = text[start:end].strip()
        if chunk:
            parts.append(chunk)
    return parts

def split_pages(page_texts: List[Dict]) -> List[Dict]:
    """
    page_texts: [{"page": 1, "text": "..."}]
    返回 [{"page": 1, "text": "..."}]
    Demo 版按页内题号切分，优点是来源页码可靠。
    """
    out = []
    for item in page_texts:
        page = int(item["page"])
        text = item.get("text", "")
        chunks = split_questions(text)
        for chunk in chunks:
            # 避免把很短的页眉/页脚当作题目
            cleaned = chunk.strip()
            if len(cleaned) >= 8:
                out.append({"page": page, "text": cleaned})
    return out
