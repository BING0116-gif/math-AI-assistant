"""
Step 1.1-C3 QuestionSplitter — section-aware state machine 单元测试。

不复制学校真实题库正文；全部使用自制 synthetic Markdown/PageBlock fixture。
覆盖：
- §31 section：A/B/C set 识别、section 识别、section 切换
- splitting：公式内数字不切题、(1)(2) 子问题不产生顶层题、8 题节得到 8 题、
  跨页拼接、页眉/页脚移除
- type：choice / fill / calculation unsupported / proof unsupported 的确定性映射
- options：inline A/B/C/D、跨行、畸形 -> warning/unsupported
- provenance：page start/end、raw 只读保留
"""

import pytest

from app.services.document_parser import (
    BLOCK_KIND_EQUATION,
    BLOCK_KIND_HEADER,
    BLOCK_KIND_PAGE_NUMBER,
    PageBlock,
    ParsedDocument,
)
from app.services.question_splitter import (
    SECTION_CALC,
    SECTION_CHOICE,
    SECTION_FILL,
    SECTION_PROOF,
    normalize_section,
    split_document,
)


# ── fixture helpers ──
def B(text, page=1, kind="text"):
    return PageBlock(text=text, page=page, kind=kind)


def doc_of(blocks):
    return ParsedDocument(parser_name="test", parser_version="test", blocks=blocks)


def identities(splits):
    return [s.identity for s in splits]


# ══════════════════════════════════════════════════════════════════
# § section：set / section / transition
# ══════════════════════════════════════════════════════════════════
class TestSectionDetection:
    def test_normalize_section_aliases(self):
        assert normalize_section("单项选择题") == SECTION_CHOICE
        assert normalize_section("选择题") == SECTION_CHOICE
        assert normalize_section("填空题") == SECTION_FILL
        assert normalize_section("计算题") == SECTION_CALC
        assert normalize_section("证明题") == SECTION_PROOF
        assert normalize_section("其他篇幅") is None
        assert normalize_section("") is None

    def test_set_a_b_c_detected(self):
        expected_sets = {"A", "B", "C"}
        found = set()
        for set_id in expected_sets:
            blocks = [
                B(f"函数与极限自测题{set_id}", 1),
                B("一、单项选择题", 1),
                B("1. 已知极限存在，则其值为（ ）。", 1),
                B("A. 1", 1),
                B("B. 2", 1),
                B("C. 3", 1),
                B("D. 4", 1),
            ]
            splits = split_document(doc_of(blocks))
            assert len(splits) == 1
            assert splits[0].set == set_id
            found.add(set_id)
        assert found == expected_sets

    def test_section_transition_by_section_header(self):
        blocks = [
            B("函数与极限自测题A", 1),
            B("一、单项选择题", 1),
            B("1. 选（ ）。", 1),
            B("A. 1", 1),
            B("B. 2", 1),
            B("C. 3", 1),
            B("D. 4", 1),
            B("二、填空题", 1),
            B("1. 填空____", 1),
            B("三、计算题", 1),
            B("1. 求解计算。", 1),
            B("四、证明题", 1),
            B("1. 证明恒等式。", 1),
        ]
        splits = split_document(doc_of(blocks))
        ids = identities(splits)
        assert ids == [
            "A-choice-1",
            "A-fill-1",
            "A-calculation-1",
            "A-proof-1",
        ]
        types = {s.detected_question_type for s in splits}
        assert types == {"choice", "fill_candidate", "calculation", "proof"}


# ══════════════════════════════════════════════════════════════════
# § splitting：数字不切题 / 子问题 / 8 题节 / 跨页 / 页眉页脚
# ══════════════════════════════════════════════════════════════════
class TestSplitting:
    def test_formula_numbers_do_not_split(self):
        """块内公式/正文里的 1. / 2. 不应产生新顶层题（只认块首行首题号）。"""
        blocks = [
            B("函数与极限自测题A", 1),
            B("三、计算题", 1),
            B(
                "1. 求极限 $\\lim_{n\\to\\infty}(\\frac{1}{n}+\\frac{2}{n})$，"
                "其中项 1. 表示首项，2. 表示第二项。",
                1,
            ),
        ]
        splits = split_document(doc_of(blocks))
        assert len(splits) == 1
        assert splits[0].identity == "A-calculation-1"

    def test_subquestions_not_split(self):
        blocks = [
            B("函数与极限自测题A", 1),
            B("四、证明题", 1),
            B("1. 证明：（1）f 在 0 处连续；（2）f 在 0 处可导；（3）求 f'。", 1),
        ]
        splits = split_document(doc_of(blocks))
        assert len(splits) == 1
        assert "contains_subquestions" in splits[0].warnings

    def test_eight_question_section_yields_eight(self):
        blocks = [B("函数与极限自测题A", 1), B("二、填空题", 1)]
        for i in range(1, 9):
            blocks.append(B(f"{i}. 第{i}空：____", 1))
        splits = split_document(doc_of(blocks))
        assert len(splits) == 8
        assert identities(splits) == [f"A-fill-{i}" for i in range(1, 9)]

    def test_cross_page_question_merged(self):
        """跨页题：page N 开始，下一页无新 section/题号 -> 拼接，记录 N..N+1。"""
        blocks = [
            B("函数与极限自测题A", 1),
            B("三、计算题", 1),
            B("1. 求解第一问：", 1),
            B("续：继续推导……", 2),  # 无新题号，但翻页
            B("2. 第二题。", 3),
        ]
        splits = split_document(doc_of(blocks))
        assert len(splits) == 2
        first = splits[0]
        assert first.identity == "A-calculation-1"
        assert first.page_start == 1
        assert first.page_end == 2
        assert "第一问" in first.raw_text and "继续推导" in first.raw_text

    def test_header_footer_filtered(self):
        """页眉/页脚/页码块绝不进入 stem。"""
        blocks = [
            B("微积分学习辅导与提高 第一章 函数与极限", 1, kind=BLOCK_KIND_HEADER),
            B("函数与极限自测题A", 1),
            B("一、单项选择题", 1),
            B("1. 题干内容（ ）。", 1),
            B("A. 1", 1),
            B("B. 2", 1),
            B("C. 3", 1),
            B("D. 4", 1),
            B("第 1 页", 1, kind=BLOCK_KIND_PAGE_NUMBER),
        ]
        splits = split_document(doc_of(blocks))
        assert len(splits) == 1
        raw = splits[0].raw_text
        assert "微积分学习辅导与提高" not in raw
        assert "函数与极限" not in raw
        assert "第 1 页" not in raw


# ══════════════════════════════════════════════════════════════════
# § type：确定性映射
# ══════════════════════════════════════════════════════════════════
class TestTypeMapping:
    def test_detected_types_deterministic(self):
        blocks = [
            B("函数与极限自测题A", 1),
            B("一、单项选择题", 1),
            B("1. 选（ ）。", 1),
            B("A. 1", 1),
            B("B. 2", 1),
            B("C. 3", 1),
            B("D. 4", 1),
            B("二、填空题", 1),
            B("1. 填空____", 1),
            B("三、计算题", 1),
            B("1. 计算。", 1),
            B("四、证明题", 1),
            B("1. 证明。", 1),
        ]
        splits = split_document(doc_of(blocks))
        types = {}
        for s in splits:
            key = (s.set, s.section)
            types[f"{key[0]}-{key[1]}"] = s.detected_question_type
        assert types["A-choice"] == "choice"
        assert types["A-fill"] == "fill_candidate"
        assert types["A-calculation"] == "calculation"
        assert types["A-proof"] == "proof"


# ══════════════════════════════════════════════════════════════════
# § options：inline / 跨行 / 畸形
# ══════════════════════════════════════════════════════════════════
class TestOptions:
    def test_inline_options(self):
        blocks = [
            B("函数与极限自测题A", 1),
            B("一、单项选择题", 1),
            B("1. 若极限存在（ ）。A. 1 B. 2 C. 3 D. 4", 1),
        ]
        splits = split_document(doc_of(blocks))
        assert len(splits) == 1
        opts = splits[0].options
        assert opts is not None
        assert [o["id"] for o in opts] == ["A", "B", "C", "D"]
        assert opts[0]["text"] == "1"

    def test_multiline_options(self):
        blocks = [
            B("函数与极限自测题A", 1),
            B("一、单项选择题", 1),
            B("1. 某某某（ ）。", 1),
            B("A. 1", 1),
            B("B. 2", 1),
            B("C. 3", 1),
            B("D. 4", 1),
        ]
        splits = split_document(doc_of(blocks))
        opts = splits[0].options
        assert opts is not None
        assert [o["id"] for o in opts] == ["A", "B", "C", "D"]

    def test_malformed_options_uncertain(self):
        """选项残缺（不足 A..D）-> option_parse_uncertain，不伪造。"""
        blocks = [
            B("函数与极限自测题A", 1),
            B("一、单项选择题", 1),
            B("1. 只有两个选项（ ）。A. 1 B. 2", 1),
        ]
        splits = split_document(doc_of(blocks))
        assert splits[0].options is None
        assert "option_parse_uncertain" in splits[0].warnings

    def test_option_math_reconstructed(self):
        """选项内公式占位符需还原为真实 LaTeX，而非保留 ⟦M{n}⟧。"""
        blocks = [
            B("函数与极限自测题A", 1),
            B("一、单项选择题", 1),
            B(
                "1. 下列极限正确的是（ ）。A. $\\lim_{n\\to\\infty}\\frac1n=0$ "
                "B. 2 C. 3 D. 4",
                1,
            ),
        ]
        splits = split_document(doc_of(blocks))
        opts = splits[0].options
        assert opts is not None
        assert "⟦M" not in opts[0]["text"]
        assert "\\frac1n" in opts[0]["text"]


# ══════════════════════════════════════════════════════════════════
# § provenance：raw 保留 / page start/end
# ══════════════════════════════════════════════════════════════════
class TestProvenance:
    def test_raw_retained_and_page_provenance(self):
        blocks = [
            B("函数与极限自测题A", 1),
            B("三、计算题", 1),
            B("1. 求解：", 1),
            B("补充条件……", 2),
        ]
        splits = split_document(doc_of(blocks))
        assert len(splits) == 1
        s = splits[0]
        assert s.page_start == 1
        assert s.page_end == 2
        assert "求解：" in s.raw_text and "补充条件" in s.raw_text

    def test_equation_block_merged_no_split(self):
        """独立公式块（equation）并入当前题，不新起 candidate。"""
        blocks = [
            B("函数与极限自测题A", 1),
            B("三、计算题", 1),
            B("1. 求解下列极限：", 1),
            B("$\\lim_{x\\to 0}\\frac{\\sin x}{x}=1$", 1, kind=BLOCK_KIND_EQUATION),
            B("2. 再算一题：", 2),
        ]
        splits = split_document(doc_of(blocks))
        assert len(splits) == 2
        assert splits[0].identity == "A-calculation-1"
        assert "\\lim" in splits[0].raw_text  # 公式并入第一题
        assert splits[1].identity == "A-calculation-2"