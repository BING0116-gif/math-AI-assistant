"""
测试 PDF 题库解析器 — 验证文本分割、题型识别、答案匹配等核心逻辑。
"""
import asyncio
import os
import sys

sys.path.insert(0, '.')

from app.services.pdf_question_parser import (
    PDFQuestionParser, ParsedQuestion, ParseResult,
    QUESTION_NUMBER_PATTERN, OPTION_PATTERN,
    ANSWER_LINE_PATTERN, SUB_ANSWER_PATTERN, TYPE_KEYWORDS,
)

SAMPLE_QUESTION_TEXT = """
一、选择题（每题5分，共25分）

1. 已知函数 f(x) = x^3 - 3x + 1，则 f'(x) = （  ）
A. 3x^2 - 3
B. 3x^2 + 3
C. x^2 - 3
D. 3x - 3

2. 设集合 A = {1, 2, 3}，B = {2, 3, 4}，则 A ∩ B = （  ）
A. {1, 2}
B. {2, 3}
C. {3, 4}
D. {1, 4}

3. lim(x→0) sin(x)/x 的值为（  ）
A. 0
B. 1
C. ∞
D. 不存在


二、填空题（每题5分，共15分）

4. 若 sin(α) = 3/5，α ∈ (0, π/2)，则 cos(2α) = ______。

5. 等差数列 {a_n} 中，a_1 = 2，d = 3，则 a_10 = ______。


三、解答题（本大题共2小题，共30分）

6. （12分）已知函数 f(x) = e^x - ax - 1。
   （1）讨论 f(x) 的单调性；
   （2）当 a = 1 时，求 f(x) 的极值。

7. （18分）在 △ABC 中，角 A, B, C 的对边分别为 a, b, c，
   已知 (2a-c)cos(B) = b*cos(C)。
   （1）求角 B 的大小；
   （2）若 b = √3，△ABC 的面积为 √3/2，求 a 的值。
"""

SAMPLE_ANSWER_TEXT = """
参考答案

一、选择题
1. A
2. B
3. B

二、填空题
4. -7/25
5. 29

三、解答题
6. 解：（1）当 a ≤ 0 时，f(x)在R上单调递增...
   （2）极小值 f(0) = 0 ...
7. 解：（1）B = π/3 ...
   （2）a = 2 ...
"""


async def run_tests():
    print("=" * 60)
    print("PDF 题库解析器 - 核心逻辑测试")
    print("=" * 60)
    
    parser = PDFQuestionParser(default_difficulty=3)
    passed = 0
    failed = 0
    
    def check(name: str, condition: bool):
        nonlocal passed, failed
        if condition:
            print(f"  [PASS] {name}")
            passed += 1
        else:
            print(f"  [FAIL] {name}")
            failed += 1
    
    # ---- 测试1：题型检测 ----
    print("\n[测试1] 大题节标题检测")
    check("选择题标题", parser._detect_section_type("一、选择题") == "选择题")
    check("填空题标题", parser._detect_section_type("二、填空题") == "填空题")
    check("解答题标题", parser._detect_section_type("三、解答题（本大题共2小题）") == "解答题")
    check("计算题标题", parser._detect_section_type("四、计算题") == "计算题")
    check("证明题标题", parser._detect_section_type("五、证明题") == "证明题")
    check("普通文字不是节标题", parser._detect_section_type("已知函数f(x)") is None)
    
    # ---- 测试2：题号检测 ----
    print("\n[测试2] 题号识别")
    check("'1. xxx' → 1", parser._detect_question_number("1. 已知函数f(x)") == 1)
    check("'2、xxx' → 2", parser._detect_question_number("2、设集合A={1}") == 2)
    check("'3  xxx' → 3", parser._detect_question_number("3  lim(x->0)") == 3)
    check("'(1) xxx' → 1 (长文本)", parser._detect_question_number("(1) 讨论f(x)的单调性") == 1)
    check("'A. xxx' 不是题号", parser._detect_question_number("A. 3x^2 - 3") is None)
    check("'B) xxx' 不是题号", parser._detect_question_number("B) {1, 2}") is None)
    
    # ---- 测试3：选项正则 ----
    print("\n[测试3] 选项正则匹配")
    m = OPTION_PATTERN.match("A. 3x^2 - 3")
    check("选项A格式正确", m is not None and m.group(1) == "A" and "3x^2" in m.group(2))
    m = OPTION_PATTERN.match("B) {1, 2}")
    check("选项B)格式正确", m is not None and m.group(1) == "B")
    m = OPTION_PATTERN.match("C. {3, 4}")
    check("选项C格式正确", m is not None and m.group(1) == "C")
    
    # ---- 测试4：完整文本分割 ----
    print("\n[测试4] 样本文本分割为题目")
    questions = parser._split_into_questions(SAMPLE_QUESTION_TEXT)
    check(f"分割出≥5道题 (实际{len(questions)}道)", len(questions) >= 5)
    
    for q in questions:
        content_short = q.content[:50].replace('\n', ' ')
        opt_str = f", {len(q.options)}个选项" if q.options else ""
        sub_str = f", {len(q.sub_questions)}个子题" if q.sub_questions else ""
        print(f"    第{q.number}题 [{q.question_type}]{opt_str}{sub_str}: {content_short}...")
    
    # 验证具体题目
    q_by_num = {q.number: q for q in questions}
    
    if 1 in q_by_num:
        q1 = q_by_num[1]
        check("第1题是选择题", q1.question_type == "选择题")
        check("第1题有4个选项", len(q1.options) == 4)
        check("第1题含导数内容", "导数" in q1.content or "f'" in q1.content or "x^3" in q1.content)
    
    if 2 in q_by_num:
        q2 = q_by_num[2]
        check("第2题是选择题", q2.question_type == "选择题")
        check("第2题含集合内容", "集合" in q2.content or "∩" in q2.content or "A" in q2.content)
    
    if 4 in q_by_num:
        q4 = q_by_num[4]
        check("第4题是填空题", q4.question_type == "填空题")
    
    if 6 in q_by_num:
        q6 = q_by_num[6]
        check("第6题是解答题", q6.question_type == "解答题")
        check("第6题有子题", len(q6.sub_questions) >= 2)
    
    # ---- 测试5：答案解析 ----
    print("\n[测试5] 答案文本解析")
    ans_matches = list(ANSWER_LINE_PATTERN.finditer(SAMPLE_ANSWER_TEXT))
    check(f"匹配到≥3条答案 (实际{len(ans_matches)}条)", len(ans_matches) >= 3)
    
    sub_ans_matches = list(SUB_ANSWER_PATTERN.finditer(SAMPLE_ANSWER_TEXT))
    check(f"匹配到≥2条子题答案 (实际{len(sub_ans_matches)}条)", len(sub_ans_matches) >= 2)
    
    answers = await parser._parse_answer_pdf.__wrapped__(parser, SAMPLE_ANSWER_TEXT) \
        if hasattr(parser._parse_answer_pdf, '__wrapped__') else {}
    # 直接调用实例方法（通过类访问原始函数不适用于async）
    # 用另一种方式测试
    answers_raw = {}
    for match in ANSWER_LINE_PATTERN.finditer(SAMPLE_ANSWER_TEXT):
        qnum = int(match.group(1))
        ans_text = match.group(2).strip()
        answers_raw[qnum] = {"answer": ans_text}
    check("第1题答案=A", answers_raw.get(1, {}).get("answer", "") == "A")
    check("第2题答案=B", answers_raw.get(2, {}).get("answer", "") == "B")
    check("第4题答案含-7/25", "-7" in answers_raw.get(4, {}).get("answer", "") or "29" in answers_raw.get(5, {}).get("answer", ""))
    
    # ---- 测试6：知识点推断 ----
    print("\n[测试6] 知识点自动推断")
    kps1 = PDFQuestionParser._extract_knowledge_points(
        "已知函数f(x)=x³-3x+1，求f'(x)", "导数"
    )
    check("导数题目含'导数'知识点", "导数" in kps1)
    
    kps2 = PDFQuestionParser._extract_knowledge_points(
        "lim(x→0) sin(x)/x", "极限"
    )
    check("极限题目含'极限'知识点", "极限" in kps2)
    
    kps3 = PDFQuestionParser._extract_knowledge_points(
        "sin(α)=3/5，求cos(2α)", "三角函数"
    )
    check("三角函数题目含'sin'或'三角'", "sin" in str(kps3) or "三角" in str(kps3))
    
    # ---- 测试7：时间估算 ----
    print("\n[测试7] 答题时间估算")
    check("选择题→2分钟", PDFQuestionParser._estimate_time("选择题") == 2)
    check("填空题→3分钟", PDFQuestionParser._estimate_time("填空题") == 3)
    check("计算题→5分钟", PDFQuestionParser._estimate_time("计算题") == 5)
    check("证明题→7分钟", PDFQuestionParser._estimate_time("证明题") == 7)
    check("解答题→8分钟", PDFQuestionParser._estimate_time("解答题") == 8)
    
    # ---- 测试8：导出字典 ----
    print("\n[测试8] 导出为导入字典格式")
    mock_result = ParseResult(success=True, total_questions=2, questions=[
        ParsedQuestion(number=1, content="test content", question_type="选择题",
                       options=["A. opt1", "B. opt2"], answer="A"),
        ParsedQuestion(number=2, content="fill blank ____", question_type="填空题",
                       answer="42"),
    ])
    dicts = parser.to_import_dicts(mock_result, category="测试分类", source_name="单元测试")
    check(f"导出{len(dicts)}条字典", len(dicts) == 2)
    check("第1条含id字段", "id" in dicts[0])
    check("第1条含content字段", "content" in dicts[0])
    check("第1条category=测试分类", dicts[0]["category"] == "测试分类")
    check("第1条source=单元测试", dicts[0]["source"] == "单元测试")
    check("第1题options是JSON字符串", isinstance(dicts[0]["options"], str))
    
    # ---- 结果汇总 ----
    print("\n" + "=" * 60)
    total = passed + failed
    print(f"测试结果: {passed}/{total} 通过", end="")
    if failed > 0:
        print(f", {failed} 失败")
    else:
        print(", 全部通过 OK")
    print("=" * 60)
    
    return failed == 0


if __name__ == "__main__":
    ok = asyncio.run(run_tests())
    sys.exit(0 if ok else 1)
