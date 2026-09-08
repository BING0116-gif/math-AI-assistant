"""QuestionSplitter — Step 1.1-C3 section-aware 状态机切分。

旧（C2）：使用全局题号 regex 决定所有边界 -> 公式/解析内部出现的
`1.`/`2.`/`3.` 会被误判为新题，导致真实题库 over-split（114 candidates）。

新（C3）：section-aware state machine，消费 `ParsedDocument.blocks`（带真实页码）：
- 先识别「函数与极限自测题 {A|B|C}」为 set（A/B/C）；
- 再区分 QUESTION_REGION / ANSWER_REGION（出现「解答与提示」即进入答案区）；
- 在 QUESTION_REGION 内识别大题节（一、单项选择题 / 二、填空题 / 三、计算题 / 四、证明题）；
- 只有在明确 section 内、行首出现的顶层题号 `1..N` 才闭合一条通用 question boundary；
- 子问题 `(1)(2)`、公式内数字不再产生顶层 candidate；
- 正确答案/解析区域交给 AnswerMatcher，绝不再被当成题目 candidate。

C3 约定：
- section -> detected_question_type 为**确定性**映射（不靠猜题干）。
- 答案区过滤、页眉/页脚过滤（header / page_number 块）。
- set + section + question_number 唯一 identity（重复边界合并，防止同一题被拆成多个）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from app.services.document_parser import (
    BLOCK_KIND_EQUATION,
    BLOCK_KIND_HEADER,
    BLOCK_KIND_PAGE_NUMBER,
    PageBlock,
    ParsedDocument,
)

# ── section 名称 -> 归一化 section key ──
# input 允许「单项选择题」「选择题」都映射到 choice
SECTION_CHOICE = "choice"
SECTION_FILL = "fill"
SECTION_CALC = "calculation"
SECTION_PROOF = "proof"
KNOWN_SECTIONS = {SECTION_CHOICE, SECTION_FILL, SECTION_CALC, SECTION_PROOF}

_SECTION_ALIASES = (
    (SECTION_CHOICE, ("单选", "选择")),
    (SECTION_FILL, ("填空",)),
    (SECTION_CALC, ("计算",)),
    (SECTION_PROOF, ("证明",)),
)


def normalize_section(name: str) -> Optional[str]:
    """把大题节标题字符串归一到 4 个稳定 section key；无法识别返回 None。"""
    if not name:
        return None
    for key, kws in _SECTION_ALIASES:
        if any(k in name for k in kws):
            return key
    return None


_SECTION_HEADER_RE = re.compile(r"^\s*([一二三四五六七八九十]+)[、．.]\s*(.+?)\s*$")
# 顶层题号：1. / 1、 / 1． / 1)  （要求行首）
_TOP_NUM_RE = re.compile(r"^\s*(\d+)\s*[\.．、)]\s*")
# set 识别：函数与极限自测题A / ...B / ...C
_SET_RE = re.compile(r"函数与极限自测题\s*([A-Ca-c])")
_ANSWER_MARK_RE = re.compile(r"解答与提示|解答|答\s*案")
# 子问题 (1) (2)
_SUBQ_RE = re.compile(r"[（(]\s*\d+\s*[）)]")
# 页脚页码：第 X 页
_PAGE_NUM_RE = re.compile(r"^\s*第\s*\d+\s*页\s*$")
# 已知页眉
_KNOWN_HEADERS = ("微积分学习辅导与提高", "第一章 函数与极限")


@dataclass
class SplitQuestion:
    """切分后的一个顶层候选题。字段用于构建 ContentImportCandidate。"""

    raw_text: str
    question_number: Optional[str] = None
    page_start: Optional[int] = None
    page_end: Optional[int] = None
    # 归一化 section key：choice / fill / calculation / proof
    section: Optional[str] = None
    # set：A / B / C（无 set 时为 None）
    set: Optional[str] = None
    detected_question_type: Optional[str] = None
    # choice 候选解析出的选项列表：[{"id": "A", "text": "..."}, ...]
    options: Optional[List[Dict[str, str]]] = None
    warnings: List[str] = field(default_factory=list)

    @property
    def identity(self) -> str:
        parts = []
        if self.set:
            parts.append(str(self.set))
        parts.append(self.section or "?")
        parts.append(self.question_number or "?")
        return "-".join(parts)


def _detect_section_type(section_key: Optional[str]) -> Optional[str]:
    """section -> detected_question_type（确定映射）。

    - choice                           -> choice（supported 由 options 是否可靠决定）
    - calculation / proof              -> 保留原名，均 unsupported
    - fill                             -> fill_candidate（第二级在 AnswerMatcher 判定）
    """
    if section_key == "choice":
        return "choice"
    if section_key == SECTION_CALC:
        return "calculation"
    if section_key == SECTION_PROOF:
        return "proof"
    if section_key == SECTION_FILL:
        return "fill_candidate"
    return None


def _is_discard_block(block: PageBlock) -> bool:
    """页眉/页脚/页码块，绝不进入 stem。"""
    if block.kind in (BLOCK_KIND_HEADER, BLOCK_KIND_PAGE_NUMBER):
        return True
    text = (block.text or "").strip()
    if not text:
        return True
    if _PAGE_NUM_RE.match(text):
        return True
    if text in _KNOWN_HEADERS or text.startswith(_KNOWN_HEADERS[0]):
        return True
    return False


def _detect_set(text: str) -> Optional[str]:
    m = _SET_RE.search(text or "")
    if not m:
        return None
    return m.group(1).upper()


def _is_answer_region_block(text: str) -> bool:
    return bool(_ANSWER_MARK_RE.search(text or ""))


def _clean_block_text(text: str) -> str:
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    # 页脚页码行（块内可能混入）移除
    lines = [ln for ln in lines if not _PAGE_NUM_RE.match(ln)]
    return "\n".join(lines).strip()


def _parse_inline_options(stem_text: str):
    """尽力解析 choice 选项（A..B..C..D）。

    返回 (options, warnings, possible_leak)。
    - options: 每项 {"id": "A", "text": "..."}（数学片段为真实 LaTeX 原文）
    - possible_leak: 题干末尾检测到疑似外泄答案（单个 A/B/C/D 标签）
    无法可靠拆解时返回 (None, [option_parse_uncertain], False)。
    """
    warnings: List[str] = []
    text = stem_text or ""

    # 先掩蔽 LaTeX 数学串，避免公式内的字母干扰选项标签；位置确定后在原文切文字
    math_spans = []
    masked = re.sub(
        r"\$\$.*?\$\$|\$.*?\$",
        lambda m: _append_math(math_spans, m.group(0)),
        text,
        flags=re.S,
    )

    # 定位题目后的选项区：取第一个闭合括号「（ ）」之后的内容
    closing = re.search(r"[）)]", masked)
    options_region_start = closing.end() if closing else 0
    possible_leak = False

    # 结构泄漏：`（ ）BA` / `（ ）B A…` ——括号后紧接的孤立 [A-D] 是泄漏答案，
    # 真正的选项从下一个标签开始；跳过它，否则会吞掉选项 A 的标签。
    m_leak = re.match(r"([A-D])(?=\s*[A-D])", masked[options_region_start:])
    if m_leak:
        # 确认紧随其后的确实是一组 A/B/C/D 选项（而非题干残余）才跳过
        rest = masked[options_region_start + m_leak.end():]
        if re.search(r"\bA\b.*\bB\b.*\bC\b.*\bD\b", rest, flags=re.S):
            options_region_start += m_leak.end()
            possible_leak = True
            warnings.append("possible_answer_leak")

    labels = ["A", "B", "C", "D"]
    pos = options_region_start
    positions: Dict[str, int] = {}
    for lab in labels:
        found = re.search(rf"(?<![A-Za-z0-9]){lab}(?![A-Za-z0-9])", masked[pos:])
        if found:
            positions[lab] = pos + found.start()
            pos = pos + found.end()
        else:
            break

    if len(positions) < 3:
        # 无法在题干找到完整 A..B..C..D 标签
        warnings.append("option_parse_uncertain")
        return None, warnings, False

    order = sorted(positions.items(), key=lambda kv: kv[1])
    # 校验顺序必须是 A B C D
    seq = [k for k, _ in order]
    if seq != labels[: len(seq)]:
        warnings.append("option_parse_uncertain")
        return None, warnings, possible_leak

    # 切分选项文本，并把掩蔽的数学片段还原为真实 LaTeX
    opts: List[Dict[str, str]] = []
    for i, (lab, start) in enumerate(order):
        end = order[i + 1][1] if i + 1 < len(order) else len(masked)
        seg = _unmask_math(masked[start + 1:end], math_spans)
        # 去掉标签与正文间的分隔符（". " / "．" / "、" 等），避免 options.text 带残余
        seg = re.sub(r"^\s*[.．。、；;,:：]\s*", "", seg)
        seg = seg.strip().strip("。； ;").strip()
        opts.append({"id": lab, "text": seg})
    return opts, warnings, possible_leak


def _unmask_math(segment: str, math_spans: list) -> str:
    """把掩蔽标记 ⟦M{i}⟧ 还原为原始 LaTeX 片段。"""
    def _rep(m):
        idx = m.group(1)
        i = int(idx)
        if 0 <= i < len(math_spans):
            return math_spans[i]
        return m.group(0)
    return re.sub(r"⟦M(\d+)⟧", _rep, segment)


def _append_math(spans: list, s: str) -> str:
    spans.append(s)
    return f" ⟦M{len(spans) - 1}⟧ "


def split_document(doc: ParsedDocument) -> List[SplitQuestion]:
    """把 ParsedDocument 切分为 section-aware 顶层题目列表。

    输入优先使用 doc.blocks（带真实页码）。若 blocks 为空（手动构造的
    ParsedDocument / content_list 缺失），回退到逐页文本解析。
    """
    if doc.blocks:
        return _split_blocks(doc.blocks)
    if doc.pages:
        blocks: List[PageBlock] = []
        for page in doc.pages:
            for line in page.text.splitlines():
                if (line or "").strip():
                    blocks.append(PageBlock(text=line, page=page.page, kind="text"))
        return _split_blocks(blocks)
    # 兜底：单篇文本（无页码），标记不确定
    blocks = [PageBlock(text=ln, page=None, kind="text")
              for ln in (doc.markdown or "").splitlines() if ln.strip()]
    splits = _split_blocks(blocks)
    for s in splits:
        s.page_start = None
        s.page_end = None
        if "page_mapping_uncertain" not in s.warnings:
            s.warnings.append("page_mapping_uncertain")
    return splits


def _split_blocks(blocks: List[PageBlock]) -> List[SplitQuestion]:
    splits: List[SplitQuestion] = []
    # 状态
    region: str = "question"  # question | answer | idle
    set_id: Optional[str] = None
    section: Optional[str] = None
    cur: Optional[SplitQuestion] = None  # 正在收集的顶层题
    seen_identity: set = set()

    for block in blocks:
        if block.kind == BLOCK_KIND_EQUATION and region != "answer":
            # 题目区独立公式块：并入当前顶层题（跨行/跨页公式不新起题）
            _append_to_current(cur, block)
            continue
        if _is_discard_block(block):
            continue

        text = _clean_block_text(block.text)
        if not text:
            continue

        # 1) 答案区标记优先
        if _is_answer_region_block(text):
            if cur is not None:
                splits.append(_finalize(cur))
                cur = None
            region = "answer"
            set_id = None
            section = None
            continue

        # 2) set 识别（题目区）
        s = _detect_set(text)
        if s:
            if region == "question":
                if cur is not None:
                    splits.append(_finalize(cur))
                    cur = None
                set_id = s
                section = None
            continue

        if region != "question":
            continue  # 答案区内容不产生 candidate

        # 3) section 头
        sm = _SECTION_HEADER_RE.match(text)
        if sm:
            nsec = normalize_section(sm.group(2))
            if nsec:
                if cur is not None and cur.section != nsec:
                    splits.append(_finalize(cur))
                    cur = None
                if section != nsec:
                    section = nsec
                continue

        # 4) 顶层题号边界（仅限已知 section 内、行首数字）
        tn = _TOP_NUM_RE.match(text)
        if tn and section:
            num = tn.group(1)
            # 同 identity 去重：同一 set+section+question -> 合并到当前题（防换行拆题）
            identity = f"{set_id}-{section}-{num}"
            if cur is not None and cur.identity == identity:
                _append_to_current(cur, block)
                continue
            if cur is not None:
                splits.append(_finalize(cur))
            cur = SplitQuestion(
                raw_text=text,
                question_number=num,
                page_start=block.page,
                page_end=block.page,
                section=section,
                set=set_id,
                detected_question_type=_detect_section_type(section),
            )
            seen_identity.add(identity)
            continue

        # 5) 其余：并入当前顶层题（题目续行）
        _append_to_current(cur, block)

    if cur is not None:
        splits.append(_finalize(cur))

    # 后处理：子问题、fill 警告、choice options
    _postprocess(splits)
    return splits


def _append_to_current(cur: Optional[SplitQuestion], block: PageBlock) -> None:
    if cur is None:
        return
    if block.page is not None:
        if cur.page_start is None:
            cur.page_start = block.page
        if cur.page_end is None or block.page > cur.page_end:
            cur.page_end = block.page
    chunk = _clean_block_text(block.text)
    if not chunk:
        return
    if cur.raw_text:
        # 跨块拼接：若上一块与本块各为独立句子则换行
        cur.raw_text = cur.raw_text.rstrip() + "\n" + chunk
    else:
        cur.raw_text = chunk


def _finalize(cur: SplitQuestion) -> SplitQuestion:
    return cur


def _postprocess(splits: List[SplitQuestion]) -> None:
    for sq in splits:
        if not sq.raw_text:
            continue
        if _SUBQ_RE.search(sq.raw_text):
            if "contains_subquestions" not in sq.warnings:
                sq.warnings.append("contains_subquestions")
        if sq.section == SECTION_CHOICE:
            opts, warnings, leak = _parse_inline_options(sq.raw_text)
            sq.options = opts
            for w in warnings:
                if w not in sq.warnings:
                    sq.warnings.append(w)
            if leak:
                if "possible_answer_leak" not in sq.warnings:
                    sq.warnings.append("possible_answer_leak")


# 兼容旧调用：content_import 曾用 guess_option_letters 预填 options。
def guess_option_letters(text: str) -> List[str]:
    """兼容 C2 旧签名：返回每项 "<ID>. <text>" 字符串列表（无则可空）。"""
    opts, _w, _leak = _parse_inline_options(text or "")
    if not opts:
        return []
    return [f"{o['id']}. {o['text']}" for o in opts]