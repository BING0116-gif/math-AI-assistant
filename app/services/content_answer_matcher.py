"""Content Answer Matcher — Step 1.1-C3 确定性答案/解析匹配。

旧（C2）：无独立答案匹配；错误区域被当成题目 candidate，答案需人工/最小编辑填。

新（C3）：独立模块，读取文档「解答与提示」答案区域，按

    set + section + question_number

确定性匹配到 candidate 的 original_answer / original_solution。

关键原则：
- 宁可不匹配，绝不猜 / 不错配。
- 答案区域绝不产生 Question candidate（QuestionSplitter 已过滤）。
- 官方 original_answer / original_solution 只来自学校原 PDF，绝不被 heuristic 覆盖。
- 无法可靠匹配 → status=ambiguous / missing，带明确 warning。

输入是 `ParsedDocument.blocks`（带真实页码/类型），与 QuestionSplitter 共享同一
结构化产物，因此页码与 set/section 识别口径一致。

本模块只做「读答案区 + 对账」；不写 Question、不改 candidate schema。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from app.services.document_parser import (
    BLOCK_KIND_EQUATION,
    PageBlock,
)
from app.services.question_splitter import (
    SECTION_CALC,
    SECTION_CHOICE,
    SECTION_FILL,
    SECTION_PROOF,
    SplitQuestion,
    _SECTION_HEADER_RE,
    _SET_RE,
    normalize_section,
)

# 答案区标记：文档级「解答与提示」或套级「…解答与提示」
_ANSWER_MARK_RE = re.compile(r"解答与提示|解答|答\s*案")
# 行首题号标记（解/证区）：1. / 1． / 1. 解：
# 用 re.S 使 `(.*)$` 可跨越内部换行——同一题解答常被 MinerU 拆成含多个换行的
# 单块；否则 .* 止步于首个 \n 且 $ 在中部无法锚定，导致整块匹配失败、把当前题
# 误并入上一题（see C3：C 套证明题第2题被并进第1题）。
_SOL_LEAD_RE = re.compile(r"^\s*(\d+)[．.]\s*(.*)$", re.S)
# 内联编号标记：1. / 1． （选/填单行列举；防止小数结尾误判，前置非数字）
_INLINE_MARK_RE = re.compile(r"(?<!\d)(\d+)[．.]\s*")
# 填空题内联举例防误判小数（2.5、1.5 等不应作为上一题标记的延续，用于校验兜底）
# 页脚页码
_PAGE_NUM_RE = re.compile(r"^\s*第\s*\d+\s*页\s*$")

# identity 命名：A-choice-1 （与 SplitQuestion.identity 一致约定）
IDENTITY_SEP = "-"


# ── 结果类型 ──
MATCHED = "matched"
MISSING = "missing"
AMBIGUOUS = "ambiguous"


# ── 填空第二级分类（确定性，不得强行分类）──
FILL_REVIEW = "fill"  # 需人工复核（unsupported）
FILL_NUMERIC = "numeric_fill"  # supported
FILL_EXPRESSION = "expression_fill"  # supported


@dataclass
class AnswerMatch:
    """一道候选的答案匹配结果。key = (set, section, question_number)。"""

    set: Optional[str]
    section: Optional[str]
    question_number: Optional[str]
    original_answer: Optional[str] = None  # choice 字母 / fill 内容
    original_solution: Optional[str] = None  # calc / proof 解答原文
    status: str = MISSING
    warnings: List[str] = field(default_factory=list)

    @property
    def identity(self) -> str:
        parts = []
        if self.set:
            parts.append(str(self.set))
        parts.append(self.section or "?")
        parts.append(self.question_number or "?")
        return IDENTITY_SEP.join(parts)


@dataclass
class AnswerRoster:
    """一个 (set, section) 答案桶，含按题号解析出的原文。"""

    set: Optional[str]
    section: Optional[str]
    # 题号 -> 原文切片（choice=字母、fill=内容、calc/proof=解答）
    by_number: Dict[str, str] = field(default_factory=dict)
    # 答案区原始块（保留顺序，含公式块），provenance 只读不改
    raw_chunks: List[str] = field(default_factory=list)
    complete: bool = False


class ContentAnswerMatcher:
    """确定性答案匹配器。"""

    def match(
        self,
        blocks: List[PageBlock],
        splits: List[SplitQuestion],
    ) -> Dict[str, AnswerMatch]:
        """对 splits 逐一按 identity 对账答案区。返回 {identity: AnswerMatch}。"""
        rosters = self._collect_answer_rosters(blocks)

        # 期望的每 (set, section) 题号集合
        expected_by_key: Dict[tuple, set] = {}
        for sq in splits:
            key = (sq.set, sq.section)
            if sq.question_number:
                expected_by_key.setdefault(key, set()).add(sq.question_number)

        result: Dict[str, AnswerMatch] = {}
        for sq in splits:
            am = AnswerMatch(set=sq.set, section=sq.section, question_number=sq.question_number)
            if not sq.set or not sq.section or not sq.question_number:
                am.status = MISSING
                am.warnings.append("answer_match_key_incomplete")
                result[am.identity] = am
                continue

            roster = rosters.get((sq.set, sq.section))
            if roster is None:
                am.status = MISSING
                am.warnings.append("answer_match_missing")
                result[am.identity] = am
                continue

            expected = expected_by_key.get((sq.set, sq.section), set())
            # 该 section 若答案桶不完整且轮次与期望不符 → 整段不可信，逐题标记
            if not roster.complete:
                am.status = AMBIGUOUS if roster.by_number else MISSING
                am.warnings.append("answer_roster_incomplete")
                result[am.identity] = am
                continue

            value = roster.by_number.get(sq.question_number)
            if value is None:
                am.status = MISSING if expected else AMBIGUOUS
                am.warnings.append("answer_match_missing")
                result[am.identity] = am
                continue

            am.status = MATCHED
            if sq.section == SECTION_CHOICE:
                letter = value.strip()
                if re.fullmatch(r"[A-Da-d]", letter):
                    am.original_answer = letter.upper()
                else:
                    am.status = AMBIGUOUS
                    am.warnings.append("choice_answer_ambiguous")
                    am.original_answer = None
            elif sq.section == SECTION_FILL:
                am.original_answer = _clean_fill_value(value)
            elif sq.section in (SECTION_CALC, SECTION_PROOF):
                am.original_solution = value
            result[am.identity] = am
        return result

    # ── 收集答案区 => 套/节 roster ──
    def _collect_answer_rosters(self, blocks: List[PageBlock]) -> Dict[tuple, AnswerRoster]:
        rosters: Dict[tuple, AnswerRoster] = {}
        in_answer = False
        set_id: Optional[str] = None
        section: Optional[str] = None
        cur: Optional[AnswerRoster] = None

        def finalize(cur_roster):
            if cur_roster is not None:
                key = (cur_roster.set, cur_roster.section)
                rosters[key] = cur_roster
            return None

        for block in blocks:
            text = (block.text or "").strip("\n")
            if not text and block.kind != BLOCK_KIND_EQUATION:
                continue

            if not in_answer:
                if _ANSWER_MARK_RE.search(text or ""):
                    in_answer = True
                    # 文档级「…解答与提示」可能同时是套头；交给下面统一 detect_set
                    s = _SET_RE.search(text or "")
                    if s:
                        set_id = s.group(1).upper()
                    continue
                continue

            # 1) 套头：函数与极限自测题{A|B|C}解答与提示
            s = _SET_RE.search(text or "")
            if s:
                cur = finalize(cur)
                set_id = s.group(1).upper()
                section = None
                continue

            # 2) 节头：一、单项选择题 / 二、填空题 / 三、计算题 / 四、证明题
            sm = _SECTION_HEADER_RE.match(text or "")
            if sm:
                nsec = normalize_section(sm.group(2))
                if nsec:
                    cur = finalize(cur)
                    section = nsec
                    cur = AnswerRoster(set=set_id, section=section)
                    rest = sm.group(2)  # 内联情形：「选择题 1. A 2. D ...」
                    # 去掉节名残余（选择题/填空题等标签已被头屏剥离，剩余即内联内容）
                    inline = _strip_leading_section_label(rest)
                    if inline and inline.strip():
                        cur.raw_chunks.append(inline.strip())
                continue

            # 3) 内容块（含公式块）
            if cur is not None:
                if block.kind == BLOCK_KIND_EQUATION:
                    # 解/证区的独立公式块，并入当前解答
                    cur.raw_chunks.append((text or "").strip())
                else:
                    ct = _clean_content(text)
                    if ct and not _PAGE_NUM_RE.match(ct):
                        cur.raw_chunks.append(ct)

        if cur is not None:
            finalize(cur)

        # 解析每个 roster
        for key, roster in rosters.items():
            self._resolve_roster(roster)
        return rosters

    def _resolve_roster(self, roster: AnswerRoster) -> None:
        sec = roster.section
        if sec == SECTION_CHOICE:
            roster.by_number, roster.complete = _parse_choice_roster(roster.raw_chunks)
        elif sec == SECTION_FILL:
            roster.by_number, roster.complete = _parse_fill_roster(roster.raw_chunks)
        elif sec in (SECTION_CALC, SECTION_PROOF):
            roster.by_number, roster.complete = _parse_solution_roster(roster.raw_chunks)


# ── 各类 roster 解析 ──
def _guess_expected_max(roster_numbers) -> int:
    # 期望为 1..N 连续自然数；取 roster 最大序号，供完整性校验
    nums = [int(n) for n in roster_numbers if isinstance(n, str) and n.isdigit()]
    return max(nums) if nums else 0


def _complete_and_valid(by_number: Dict[str, str]) -> bool:
    nums = [int(n) for n in by_number if n.isdigit()]
    if not nums:
        return False
    n = len(nums)
    return sorted(nums) == list(range(1, n + 1))


def _parse_choice_roster(chunks: List[str]):
    """选填单行列举：'1. B 2. A 3. B ...' → {1:'B',...}。"""
    by_number: Dict[str, str] = {}
    for ch in chunks:
        for m in _INLINE_MARK_RE.finditer(ch):
            num = m.group(1)
            rest = ch[m.end():]
            after = re.match(r"\s*([A-Da-d])\b", rest)
            if after:
                # 若该处已是某题答案开头，且不与后续数字重叠，记录字母
                by_number[num] = after.group(1).upper()
    # 过滤明显小数的误判：只保留答案是单个字母且序号连续的
    complete = _complete_and_valid(by_number) if by_number else False
    return by_number, complete


def _parse_fill_roster(chunks: List[str]):
    """填空题 inline：'1. $\\frac1{1-x}$ 2. ...' → 按标记切分。"""
    by_number: Dict[str, str] = {}
    joined = "\n".join(chunks)
    marks = list(_INLINE_MARK_RE.finditer(joined))
    for i, m in enumerate(marks):
        num = m.group(1)
        end = marks[i + 1].start() if i + 1 < len(marks) else len(joined)
        seg = joined[m.end():end]
        by_number[num] = seg.strip()
    complete = _complete_and_valid(by_number) if by_number else False
    # 兜底：小节类型确为 fill 且至少切出 1..N 才视为可靠
    return by_number, complete


def _parse_solution_roster(chunks: List[str]):
    """解/证区：块首 'N. 解：/证明：/...' 作为解答边界；后续块并入直至下一标记。"""
    by_number: Dict[str, str] = {}
    cur_num: Optional[str] = None
    parts: List[str] = []
    for ch in chunks:
        m = _SOL_LEAD_RE.match(ch)
        if m:
            if cur_num is not None and parts:
                by_number[cur_num] = _join_parts(parts)
            cur_num = m.group(1)
            tail = (m.group(2) or "").strip()
            parts = [tail] if tail else []
        elif cur_num is not None:
            ct = (ch or "").strip()
            if ct:
                parts.append(ct)
    if cur_num is not None and parts:
        by_number[cur_num] = _join_parts(parts)

    complete = _complete_and_valid(by_number) if by_number else False
    return by_number, complete


def _join_parts(parts: List[str]) -> str:
    return "\n".join(p for p in parts if p).strip()


def _clean_content(text: str) -> str:
    return (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()


def _strip_leading_section_label(inline: str) -> str:
    """去掉内联内容的节名残余：'选择题 1. A…' → '1. A…'；'填空题1. …' → '1. …'。"""
    s = (inline or "").strip()
    stripped = re.sub(r"^(单选|选择|填充|填空|计算题|证明题|计算|证明)+", "", s)
    return stripped.strip("、 ．.").strip()


def _clean_fill_value(value: str) -> str:
    v = (value or "").strip()
    # 去掉首尾多余标点
    return v.strip(" .,，．；;：:")


# 填空第二级分类（供 content_import 接线；独立、确定性；不得强行分类）
def classify_fill_subtype(original_answer: Optional[str]) -> str:
    """根据官方原答案判定填空支持类型。

    - numeric_fill   ：归一为单一数值（整数/小数/分数/带符号）
    - expression_fill：受限数学表达式（函数表达式、区间、简单代数/极限式）
    - fill           ：需人工复核（分段/矩阵/无法可靠判定）——不做自动发布
    """
    a = (original_answer or "").strip()
    if not a:
        return FILL_REVIEW
    # 分段/矩阵这类复杂结构，绝不强行分类
    if "\\begin{array}" in a or "\\begin" in a:
        return FILL_REVIEW
    # 去掉 LaTeX 定界与空白
    inner = a.replace(" ", "").replace("\t", "").replace("$$", "").replace("$", "")
    # 纯数值：整数 / 分数 / 小数 / 带符号
    if re.fullmatch(r"[+-]?\d+(?:/\d+)?(?:\.\d+)?", inner):
        return FILL_NUMERIC
    # 去掉 LaTeX 命令 token（如 \pi、\sqrt、\frac），再判是否存在裸字母（变量）
    # 或逗号（区间/元组）。变量 -> 表达式；区间 -> 表达式。
    body = re.sub(r"\\[A-Za-z]+", "", inner)
    if re.search(r"[A-Za-z,]", body):
        return FILL_EXPRESSION
    # 其余（π / √2 / e 等单一数学常量，无变量且非区间）可归一为单一数值
    return FILL_NUMERIC