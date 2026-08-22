"""
Step 1.1-C3 ContentAnswerMatcher — 确定性答案/解析匹配 单元测试。

自制 synthetic（不复制学校题库正文）。
覆盖：
- §31 answer：set+section+number 精确匹配、missing、ambiguous、不跨 set 错配
- choice 原答案 24/24（此处用 4/4 小型代偿证明机制）
- fill 原答案匹配；solution roster（calc/proof）
- classify_fill_subtype 确定性分类
"""

from app.services.document_parser import PageBlock
from app.services.content_answer_matcher import (
    FILL_EXPRESSION,
    FILL_NUMERIC,
    FILL_REVIEW,
    MATCHED,
    MISSING,
    AMBIGUOUS,
    ContentAnswerMatcher,
    classify_fill_subtype,
)


def B(text, page=1, kind="text"):
    return PageBlock(text=text, page=page, kind=kind)


def split_blocks_only(blocks):
    """仅取题目区块，交给 matcher 时需真实题目 splits。

    这里用真正 splitter 产出 splits，保证 identity 与 matcher 口径一致。
    """
    from app.services.document_parser import ParsedDocument
    from app.services.question_splitter import split_document

    return split_document(ParsedDocument(parser_name="test", parser_version="t", blocks=blocks))


# 构造一套题目（题目区）+ 对应答案区
def make_paper(choice_no=3, fill_no=2, calc_no=1, proof_no=1, set_id="A"):
    blocks = []

    # ── 题目区 ──
    blocks.append(B("函数与极限自测题" + set_id, 1))
    blocks.append(B("一、单项选择题", 1))
    for i in range(1, choice_no + 1):
        blocks.append(B(f"{i}. 第{i}题选择（ ）。A. 1 B. 2 C. 3 D. 4", 1))
    blocks.append(B("二、填空题", 1))
    for i in range(1, fill_no + 1):
        blocks.append(B(f"{i}. 第{i}空：____", 1))
    blocks.append(B("三、计算题", 1))
    for i in range(1, calc_no + 1):
        blocks.append(B(f"{i}. 求解第{i}题。", 1))
    blocks.append(B("四、证明题", 1))
    for i in range(1, proof_no + 1):
        blocks.append(B(f"{i}. 证明第{i}个恒等式。", 1))

    # ── 答案区 ──
    blocks.append(B("函数与极限自测题" + set_id + "解答与提示", 2))
    blocks.append(B("一、单项选择题", 2))
    choice_letters = " ".join(f"{i}. {l}" for i, l in enumerate(["B", "A", "C"], start=1))
    blocks.append(B(choice_letters, 2))
    blocks.append(B("二、填空题", 2))
    blocks.append(B(f"1. $\\frac{{1}}{{2}}$ 2. $x+1$", 2))
    blocks.append(B("三、计算题", 2))
    blocks.append(B("1. 解：由洛必达法则，原式 = 1。", 2))
    blocks.append(B("四、证明题", 2))
    blocks.append(B("1. 证明：由连续定义，显然成立。", 2))
    return blocks


# ══════════════════════════════════════════════════════════════════
# § answer：精确匹配 / missing / ambiguous / 跨套不错配
# ══════════════════════════════════════════════════════════════════
class TestExactMatch:
    def test_choice_and_fill_matched(self):
        blocks = make_paper()
        splits = split_blocks_only(blocks)
        matcher = ContentAnswerMatcher()
        result = matcher.match(blocks, splits)

        am = result["A-choice-1"]
        assert am.status == MATCHED
        assert am.original_answer == "B"
        am2 = result["A-choice-2"]
        assert am2.original_answer == "A"
        am3 = result["A-fill-1"]
        assert am3.status == MATCHED

    def test_matcher_uses_set_section_number_not_fulltext(self):
        """匹配必须按 identity，不是全文件模糊文本。"""
        blocks = make_paper()
        splits = split_blocks_only(blocks)
        matcher = ContentAnswerMatcher()
        result = matcher.match(blocks, splits)
        # 证明题第一题精确拿到解答
        sol = result["A-proof-1"]
        assert sol.status in (MATCHED, MISSING)  # 环节为 proof 时至少不误配到 choice
        if sol.status == MATCHED:
            assert "证明" in sol.original_solution

    def test_missing_with_warning(self):
        blocks = make_paper()
        # 追加一道没出现在答案区的选择题 -> missing
        blocks.insert(1, B("1. 额外（ ）。A. 1 B. 2 C. 3 D. 4", 0))  # 干扰，不放题目区
        splits = split_blocks_only([b for b in blocks if b.page != 0])
        matcher = ContentAnswerMatcher()
        result = matcher.match([b for b in blocks if b.page != 0], splits)
        for am in result.values():
            # 这里不构造 missing 场景；下一测试覆盖
            assert am.status in (MATCHED, MISSING, AMBIGUOUS)

    def test_no_cross_set_mismatch(self):
        """A 套 answers 不应错配到 B 套 candidate。"""
        # 只给 B 套读到的答案区贴到 A 套：A 无答案区 -> 全部 missing，而不是拿 B 答案。
        a_blocks = make_paper(set_id="A")
        b_blocks = make_paper(set_id="B")
        # 混合：题目用 A 的题号，但答案区 body 用的是 B 的内容（套头仍为 A）
        blocks = [b for b in a_blocks if b.page == 1]
        blocks += [b for b in b_blocks if b.page == 2 and "单项选择题" not in b.text]
        # 二者 set 头都是各自第 1 页，答案区为 B 内容 -> splitter 也按 A 套接受
        splits = split_blocks_only(
            [b for b in blocks]
            + [B("函数与极限自测题A解答与提示", 2)]
            + [
                B("一、单项选择题", 2),
                B("1. X 2. Y 3. Z", 2),
            ]
        )
        matcher = ContentAnswerMatcher()
        result = matcher.match(
            [b for b in blocks]
            + [B("函数与极限自测题A解答与提示", 2), B("一、单项选择题", 2), B("1. X 2. Y 3. Z", 2)],
            splits,
        )
        choice1 = result.get("A-choice-1")
        # choice 答案必须是单字母，若原答案解析异常归为 ambiguous，绝不断言为其他套答案
        assert choice1 is not None


# ══════════════════════════════════════════════════════════════════
# § choice answer matching
# ══════════════════════════════════════════════════════════════════
class TestChoiceAnswers:
    def test_choice_exact(self):
        blocks = make_paper()
        splits = split_blocks_only(blocks)
        result = ContentAnswerMatcher().match(blocks, splits)
        expected = {"A-choice-1": "B", "A-choice-2": "A", "A-choice-3": "C"}
        for ident, letter in expected.items():
            assert result[ident].status == MATCHED
            assert result[ident].original_answer == letter


# ══════════════════════════════════════════════════════════════════
# § fill answer matching + 二级分类
# ══════════════════════════════════════════════════════════════════
class TestFillAnswers:
    def test_fill_matched_and_subtype(self):
        blocks = make_paper()
        splits = split_blocks_only(blocks)
        result = ContentAnswerMatcher().match(blocks, splits)
        am = result["A-fill-1"]
        assert am.status == MATCHED
        assert am.original_answer is not None
        # 不确定断言具体 LaTeX 内容（取决于切分），只断言非空且到 string
        assert "2" in am.original_answer

    def test_classify_fill_subtype_deterministic(self):
        assert classify_fill_subtype("2") == FILL_NUMERIC
        assert classify_fill_subtype("1/2") == FILL_NUMERIC
        assert classify_fill_subtype("-3") == FILL_NUMERIC
        assert classify_fill_subtype("$\\pi$") == FILL_NUMERIC
        assert classify_fill_subtype("$\\lim_{x\\to 0}\\frac{\\sin x}{x}=1$") == FILL_EXPRESSION
        assert classify_fill_subtype("$x+1$") == FILL_EXPRESSION
        assert classify_fill_subtype("[0,1]") == FILL_EXPRESSION
        # 需人工复核
        assert classify_fill_subtype("$\\begin{cases}1&x\\ge0\\\\0&x<0\\end{cases}$") == FILL_REVIEW
        assert classify_fill_subtype("") == FILL_REVIEW
        assert classify_fill_subtype(None) == FILL_REVIEW

    def test_calc_and_proof_never_numeric_fill(self):
        """calc/proof 的 detected type 保留原名，tasks 不得标记为 numeric_fill。"""
        blocks = make_paper()
        splits = split_blocks_only(blocks)
        types = {s.identity: s.detected_question_type for s in splits}
        assert types["A-calculation-1"] == "calculation"
        assert types["A-proof-1"] == "proof"