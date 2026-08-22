"""知微 Step 1.1-E gate 种子题库导入脚本。

通过正式链路把一批「开发用种子题」以 draft 落库，再走审核发布为 published，
以满足 Step 1.2 进入 gate：published >= 100 + 首版 4 题型 + 24 知识点合理覆盖。

- 题型仅用 Step 1.4 判题引擎确定支持的 4 种：choice / judge / numeric_fill / expression_fill。
  （注：content_import.SUPPORTED_TYPES 已含 calculation/proof/short_answer，但那是面向 PDF
   导入的有意产品变更；本种子刻意只用 4 种，保证练习选池纯净、判题可达。）
- 每题都带合法 answer_spec（发布校验强制要求）并挂载至少一个知识点。
- 幂等：重复运行会跳过已存在题、跳过已发布题。

运行：venv/Scripts/python.exe scripts/seed_gate_bank.py
"""

from __future__ import annotations

import asyncio
import sys

# ── 题目构造辅助：保证 answer_spec 契约正确 ──
COURSE_CODE = "advanced-calculus"
CATEGORY = "高等数学"
SOURCE = "知微种子题库(开发用)"


def choice(kp, qid, content, opts, correct, analysis, difficulty=2):
    """opts: list[str]（按 A/B/C/D 顺序）；correct: 'A'..."""
    options = [{"id": chr(65 + i), "text": t} for i, t in enumerate(opts)]
    return {
        "id": qid,
        "content": content,
        "question_type": "choice",
        "options": options,
        "answer": correct,
        "analysis": analysis,
        "category": CATEGORY,
        "difficulty": difficulty,
        "source": SOURCE,
        "review_status": "draft",
        "knowledge_point_codes": [kp],
        "course_code": COURSE_CODE,
        "answer_spec": {"version": 1, "kind": "choice", "correct": correct},
    }


def judge(kp, qid, content, correct_bool, analysis, difficulty=2):
    return {
        "id": qid,
        "content": content,
        "question_type": "judge",
        "options": [],
        "answer": "正确" if correct_bool else "错误",
        "analysis": analysis,
        "category": CATEGORY,
        "difficulty": difficulty,
        "source": SOURCE,
        "review_status": "draft",
        "knowledge_point_codes": [kp],
        "course_code": COURSE_CODE,
        "answer_spec": {"version": 1, "kind": "judge", "correct": bool(correct_bool)},
    }


def numfill(kp, qid, content, value, analysis, difficulty=2):
    return {
        "id": qid,
        "content": content,
        "question_type": "numeric_fill",
        "options": [],
        "answer": str(value),
        "analysis": analysis,
        "category": CATEGORY,
        "difficulty": difficulty,
        "source": SOURCE,
        "review_status": "draft",
        "knowledge_point_codes": [kp],
        "course_code": COURSE_CODE,
        "answer_spec": {"version": 1, "kind": "numeric_fill", "value": value},
    }


def exprfill(kp, qid, content, canonical, variables, analysis, difficulty=2):
    return {
        "id": qid,
        "content": content,
        "question_type": "expression_fill",
        "options": [],
        "answer": canonical,
        "analysis": analysis,
        "category": CATEGORY,
        "difficulty": difficulty,
        "source": SOURCE,
        "review_status": "draft",
        "knowledge_point_codes": [kp],
        "course_code": COURSE_CODE,
        "answer_spec": {
            "version": 1,
            "kind": "expression_fill",
            "canonical": canonical,
            "variables": variables,
        },
    }


# ── 24 知识点，每点 4 题（choice/judge/numeric/expression）──
Q = []
i = 0


def add(q):
    global i
    i += 1
    q["id"] = q.get("id") or f"SEED{i:04d}"
    Q.append(q)


# 1) function-definition 函数的定义
add(choice("function-definition", None, "下列方程中，y 不是 x 的函数的是（  ）。",
           ["y = 2x + 1", "y = x²", "x² + y² = 1", "y = √x"], "C",
           "垂直线检验：对同一个 x，圆 x²+y²=1 通常对应两个 y 值，不满足「唯一确定」的函数定义；其余三者对每个 x 都唯一确定 y。"))
add(judge("function-definition", None, "若对定义域内每一个 x，都有唯一确定的 y 与之对应，则 y 是 x 的函数。", True,
          "这正是函数的定义：定义域中每个自变量对应唯一的函数值。"))
add(numfill("function-definition", None, "设函数 f(x) = x²，则 f(3) = ？", 9,
            "f(3) = 3² = 9。"))
add(exprfill("function-definition", None, "若函数 f(x) = 2x + 1，则 f(x + 1) = ？", "2*x+3", ["x"],
             "f(x+1) = 2(x+1) + 1 = 2x + 3。"))

# 2) function-domain-range 定义域与值域
add(choice("function-domain-range", None, "函数 f(x) = 1/(x - 2) 的定义域是（  ）。",
           ["(-∞, 2)", "(2, +∞)", "(-∞, 2) ∪ (2, +∞)", "[2, +∞)"], "C",
           "分母不能为零，故 x - 2 ≠ 0，即 x ≠ 2，定义域为 (-∞, 2) ∪ (2, +∞)。"))
add(judge("function-domain-range", None, "函数 f(x) = √x 的定义域是 [0, +∞)。", True,
          "偶次根式要求被开方数非负，故 x ≥ 0。"))
add(numfill("function-domain-range", None, "函数 f(x) = √(x - 1) 的定义域下界（最小值）是？", 1,
            "由 x - 1 ≥ 0 得 x ≥ 1，下界为 1。"))
add(exprfill("function-domain-range", None, "设 f(x) = 1/x（x ≠ 0），则 f(f(x)) = ？", "x", ["x"],
             "f(f(x)) = 1 / (1/x) = x（x ≠ 0）。"))

# 3) function-properties 函数的基本性质
add(choice("function-properties", None, "函数 f(x) = x³ 是（  ）。",
           ["偶函数", "奇函数", "非奇非偶", "既是奇函数又是偶函数"], "B",
           "f(-x) = (-x)³ = -x³ = -f(x)，满足奇函数定义；且非零函数不可能既奇又偶。"))
add(judge("function-properties", None, "函数 f(x) = x² 是偶函数。", True,
          "f(-x) = (-x)² = x² = f(x)，满足偶函数定义。"))
add(numfill("function-properties", None, "设 f(x) = x²，则 f(-3) = ？", 9,
            "f(-3) = (-3)² = 9。"))
add(exprfill("function-properties", None, "若 f(x) 为奇函数且 f(2) = 5，则 f(-2) = ？", "-5", [],
             "奇函数满足 f(-x) = -f(x)，故 f(-2) = -f(2) = -5。"))

# 4) elementary-functions 基本初等函数
add(choice("elementary-functions", None, "函数 y = ln x 的定义域是（  ）。",
           ["ℝ", "(0, +∞)", "[0, +∞)", "(-∞, 0)"], "B",
           "对数函数要求真数大于 0，故定义域为 (0, +∞)。"))
add(judge("elementary-functions", None, "指数函数 y = aˣ（a>0 且 a≠1）的值域是 (0, +∞)。", True,
          "对任意实数 x，aˣ 恒为正，且可取到所有正实数。"))
add(numfill("elementary-functions", None, "2³ = ？", 8,
            "2³ = 2×2×2 = 8。"))
add(exprfill("elementary-functions", None, "化简 ln(e⁵) = ？", "5", [],
             "由对数恒等式 ln(eᵘ) = u，得 ln(e⁵) = 5。"))

# 5) composite-function 复合函数
add(choice("composite-function", None, "若 f(x) = x²，g(x) = x + 1，则 f(g(x)) = （  ）。",
           ["x² + 1", "(x + 1)²", "x² + x", "x + 1"], "B",
           "f(g(x)) = f(x+1) = (x+1)²。"))
add(judge("composite-function", None, "复合函数 f∘g 的定义域一定等于 g 的定义域。", False,
          "还需保证 g(x) 落在 f 的定义域内，故 f∘g 的定义域通常是 g 定义域的子集。"))
add(numfill("composite-function", None, "设 f(x) = x + 1，g(x) = 2x，则 f(g(2)) = ？", 5,
            "g(2) = 4，f(4) = 4 + 1 = 5。"))
add(exprfill("composite-function", None, "若 f(x) = x²，g(x) = x + 1，则 g(f(x)) = ？", "x^2+1", ["x"],
             "g(f(x)) = g(x²) = x² + 1。"))

# 6) inverse-function 反函数
add(choice("inverse-function", None, "函数 y = 2x + 3 的反函数是（  ）。",
           ["y = (x - 3)/2", "y = 2x - 3", "y = x/2 - 3", "y = (x + 3)/2"], "A",
           "由 y = 2x + 3 解得 x = (y - 3)/2，互换 x,y 得反函数 y = (x - 3)/2。"))
add(judge("inverse-function", None, "严格单调的函数一定存在反函数。", True,
          "严格单调保证一一对应，从而存在反函数。"))
add(numfill("inverse-function", None, "若 f(2) = 5 且 f 可逆，则 f⁻¹(5) = ？", 2,
            "反函数将原像与像互换，故 f⁻¹(5) = 2。"))
add(exprfill("inverse-function", None, "函数 y = 3x - 2 的反函数表达式为 y = ？", "(x+2)/3", ["x"],
             "由 y = 3x - 2 得 x = (y + 2)/3，互换得 y = (x + 2)/3。"))

# 7) piecewise-function 分段函数
add(choice("piecewise-function", None, "设 f(x) = { x, x≥0; -x, x<0 }（即 |x|），则 f(-2) = （  ）。",
           ["2", "-2", "0", "4"], "A",
           "f(-2) = | -2 | = 2（因 -2 < 0，取 -x = 2）。"))
add(judge("piecewise-function", None, "分段函数在分段点处一定不连续。", False,
          "分段函数在分段点处可能连续也可能不连续，需按定义检验极限与函数值。"))
add(numfill("piecewise-function", None, "设 f(x) = { x+1, x≥0; x-1, x<0 }，则 f(0) = ？", 1,
            "x = 0 落在区间 x≥0，故 f(0) = 0 + 1 = 1。"))
add(exprfill("piecewise-function", None, "设 f(x) = { 2x, x≥1; x, x<1 }，则 f(2) = ？", "4", [],
             "x = 2 ≥ 1，取 2x = 4。"))

# 8) function-arithmetic 函数的四则运算
add(choice("function-arithmetic", None, "若 f(x) = x，g(x) = x²，则 (f·g)(x) = （  ）。",
           ["x³", "2x", "x²", "x"], "A",
           "(f·g)(x) = f(x)·g(x) = x·x² = x³。"))
add(judge("function-arithmetic", None, "(f + g)(x) 的定义域等于 f 与 g 定义域的交集。", True,
          "和函数在两点都有定义处才有定义，故定义域为二者定义域的交集。"))
add(numfill("function-arithmetic", None, "设 f(x) = x + 1，g(x) = x - 1，则 (f - g)(2) = ？", 2,
            "(f-g)(2) = f(2) - g(2) = 3 - 1 = 2。"))
add(exprfill("function-arithmetic", None, "设 f(x) = x²，g(x) = x（x ≠ 0），则 (f/g)(x) 化简为？", "x", ["x"],
             "(f/g)(x) = x² / x = x（x ≠ 0）。"))

# 9) sequence-limit 数列极限
add(choice("sequence-limit", None, "数列 aₙ = 1/n 的极限是（  ）。",
           ["0", "1", "∞", "不存在"], "A",
           "当 n→∞ 时 1/n → 0。"))
add(judge("sequence-limit", None, "若数列收敛，则其极限唯一。", True,
          "收敛数列的极限必唯一，这是极限的基本性质。"))
add(numfill("sequence-limit", None, "lim_{n→∞} (2n + 1)/n = ？", 2,
            "(2n+1)/n = 2 + 1/n → 2。"))
add(exprfill("sequence-limit", None, "lim_{n→∞} (3n + 1)/(n + 2) = ？", "3", [],
             "分子分母同除以 n：(3 + 1/n)/(1 + 2/n) → 3。"))

# 10) function-limit 函数极限
add(choice("function-limit", None, "lim_{x→2} (x² - 4)/(x - 2) = （  ）。",
           ["0", "4", "2", "不存在"], "B",
           "(x²-4)/(x-2) = (x-2)(x+2)/(x-2) = x+2（x≠2），极限为 2+2 = 4。"))
add(judge("function-limit", None, "若 lim_{x→a} f(x) 存在，则 f(a) 必有定义。", False,
          "极限描述趋近过程，不要求函数在该点有定义（如可去间断点）。"))
add(numfill("function-limit", None, "lim_{x→0} sin x / x = ？", 1,
            "这是第一个重要极限，结果为 1。"))
add(exprfill("function-limit", None, "lim_{x→1} (x³ - 1)/(x - 1) = ？", "3", [],
             "x³-1 = (x-1)(x²+x+1)，约去后取极限得 1+1+1 = 3。"))

# 11) left-right-limit 左右极限
add(choice("left-right-limit", None, "设 f(x) = { 1, x>0; -1, x<0 }，则 lim_{x→0} f(x) = （  ）。",
           ["1", "-1", "0", "不存在"], "D",
           "右极限为 1，左极限为 -1，左右不相等，故极限不存在。"))
add(judge("left-right-limit", None, "函数在一点的极限存在，当且仅当左右极限都存在且相等。", True,
          "这是极限存在的充要条件。"))
add(numfill("left-right-limit", None, "设 f(x) = { x, x≥0; -x, x<0 }，则 lim_{x→0⁻} f(x) = ？", 0,
            "左极限 x→0⁻ 时 f(x) = -x → 0。"))
add(exprfill("left-right-limit", None, "设 f(x) = { 2, x≥0; x, x<0 }，则 lim_{x→0⁺} f(x) = ？", "2", [],
             "右极限取 x≥0 一支，恒为 2。"))

# 12) limit-properties 极限的性质
add(choice("limit-properties", None, "若 lim f(x) = 2 且 lim g(x) = 3，则 lim(f + g)(x) = （  ）。",
           ["5", "6", "1", "0"], "A",
           "由极限四则运算法则，lim(f+g) = lim f + lim g = 2 + 3 = 5。"))
add(judge("limit-properties", None, "若 lim_{x→a} f(x) = A > 0，则在 a 的某去心邻域内 f(x) > 0（局部保号性）。", True,
          "这是极限的局部保号性。"))
add(numfill("limit-properties", None, "若 lim f = 4，lim g = 2，则 lim(f·g) = ？", 8,
            "lim(f·g) = 4 × 2 = 8。"))
add(exprfill("limit-properties", None, "若 lim_{x→a} f(x) = L，则 lim_{x→a} 2f(x) = ？", "2*L", ["L"],
             "由数乘法则，常数可提出：lim 2f = 2L。"))

# 13) infinitesimal 无穷小与无穷大
add(choice("infinitesimal", None, "当 x→0 时，下列函数中是无穷小的是（  ）。",
           ["1/x", "sin x", "x² + 1", "eˣ"], "B",
          "x→0 时 sin x → 0，是无穷小；其余均不趋于 0。"))
add(judge("infinitesimal", None, "当 x→0 时，x 与 2x 是等价无穷小。", False,
          "等价要求比值极限为 1，而 (2x)/x = 2 ≠ 1，二者是同阶无穷小而非等价无穷小。"))
add(numfill("infinitesimal", None, "当 x→0 时，lim sin x / x = ？", 1,
            "重要极限，结果为 1。"))
add(exprfill("infinitesimal", None, "当 x→0 时，sin(2x) 等价于？", "2*x", ["x"],
             "由 sin u ~ u（u→0），取 u = 2x 得 sin(2x) ~ 2x。"))

# 14) monotone-convergence 单调有界准则
add(choice("monotone-convergence", None, "单调且有界的数列一定（  ）。",
           ["发散", "收敛", "振荡", "无界"], "B",
           "单调有界准则是实数系基本定理之一：单调有界数列必收敛。"))
add(judge("monotone-convergence", None, "单调有界数列必收敛。", True,
          "这是单调有界收敛准则。"))
add(numfill("monotone-convergence", None, "数列 a₁=1，aₙ₊₁=√(aₙ+2) 收敛，设极限为 L，则 L = ？", 2,
            "对递推式取极限得 L = √(L+2)，即 L² = L + 2，解得 L = 2（舍负）。"))
add(exprfill("monotone-convergence", None, "若单调有界数列极限 L 满足 L = √(L + 2)，则 L = ？", "2", [],
             "平方得 L² - L - 2 = 0，正根为 L = 2。"))

# 15) limit-arithmetic-laws 极限四则运算法则
add(choice("limit-arithmetic-laws", None, "lim_{x→1} (3x² - 2x) = （  ）。",
           ["1", "3", "5", "0"], "A",
           "多项式连续，直接代入得 3·1 - 2·1 = 1。"))
add(judge("limit-arithmetic-laws", None, "若 lim f 与 lim g 都存在，则 lim(f/g) 存在当且仅当 lim g ≠ 0。", True,
          "分母极限非零时才能用商的法则。"))
add(numfill("limit-arithmetic-laws", None, "lim_{x→2} (x² + 1) = ？", 5,
            "直接代入得 4 + 1 = 5。"))
add(exprfill("limit-arithmetic-laws", None, "lim_{x→a} (x² - a²)/(x - a) = ？", "2*a", ["a"],
             "分子 = (x-a)(x+a)，约去后极限为 a + a = 2a。"))

# 16) important-limits 两个重要极限
add(choice("important-limits", None, "lim_{x→0} sin x / x = （  ）。",
           ["0", "1", "∞", "2"], "B",
           "第一个重要极限，结果为 1。"))
add(judge("important-limits", None, "lim_{x→∞} (1 + 1/x)ˣ = e。", True,
          "这是第二个重要极限的标准形式。"))
add(numfill("important-limits", None, "lim_{x→0} sin(3x)/x = ？", 3,
            "sin(3x)/x = 3·sin(3x)/(3x) → 3·1 = 3。"))
add(exprfill("important-limits", None, "lim_{x→0} sin(kx)/x = ？", "k", ["k"],
             "= k·sin(kx)/(kx) → k（k 为常数）。"))

# 17) equivalent-infinitesimal 等价无穷小替换
add(choice("equivalent-infinitesimal", None, "当 x→0 时，下列等价无穷小正确的是（  ）。",
           ["sin x ~ x", "1 - cos x ~ x", "ln(1+x) ~ x²", "eˣ - 1 ~ x²"], "A",
           "当 x→0 时 sin x ~ x；而 1-cos x ~ x²/2，ln(1+x) ~ x，eˣ-1 ~ x。"))
add(judge("equivalent-infinitesimal", None, "当 x→0 时，ln(1 + x) ~ x。", True,
          "这是常用的等价无穷小关系。"))
add(numfill("equivalent-infinitesimal", None, "lim_{x→0} ln(1 + 2x)/x = ？", 2,
            "ln(1+2x) ~ 2x，故极限为 2。"))
add(exprfill("equivalent-infinitesimal", None, "lim_{x→0} (eˣ - 1)/x = ？", "1", [],
             "由 eˣ - 1 ~ x，极限为 1。"))

# 18) squeeze-theorem 夹逼定理
add(choice("squeeze-theorem", None, "由 |sin x| ≤ 1，lim_{x→0} x·sin(1/x) = （  ）。",
           ["1", "0", "∞", "不存在"], "B",
           "|x·sin(1/x)| ≤ |x| → 0，由夹逼定理极限为 0。"))
add(judge("squeeze-theorem", None, "夹逼定理要求被夹函数在极限点附近有相同上、下界极限。", True,
          "若 g(x) ≤ f(x) ≤ h(x) 且 lim g = lim h = L，则 lim f = L。"))
add(numfill("squeeze-theorem", None, "lim_{x→∞} sin x / x = ？", 0,
            "|sin x / x| ≤ 1/|x| → 0，由夹逼定理得 0。"))
add(exprfill("squeeze-theorem", None, "若 0 ≤ f(x) ≤ x² 且 x→0，则 lim_{x→0} f(x) = ？", "0", [],
             "上下界极限均为 0，由夹逼定理得 0。"))

# 19) continuity-definition 连续的定义
add(choice("continuity-definition", None, "函数 f 在 x = a 处连续等价于（  ）。",
           ["lim_{x→a} f(x) = f(a)", "极限存在即可", "f(a) 有定义即可", "可导"], "A",
           "连续的充要条件：f(a) 有定义、极限存在且二者相等。"))
add(judge("continuity-definition", None, "若 f 在 a 处连续，则 f 在 a 处必有定义。", True,
          "连续的前提就是函数在该点有定义。"))
add(numfill("continuity-definition", None, "f(x) = x² 在 x = 2 处连续，则 f(2) = ？", 4,
            "f(2) = 2² = 4。"))
add(exprfill("continuity-definition", None, "f(x) = x + 1 在 x = 3 处的极限值 = ？", "4", [],
             "多项式连续，极限等于函数值 3 + 1 = 4。"))

# 20) discontinuity-classification 间断点及其分类
add(choice("discontinuity-classification", None, "函数 f(x) = 1/(x - 1) 在 x = 1 处是（  ）。",
           ["可去间断点", "跳跃间断点", "无穷间断点", "连续"], "C",
           "x→1 时 |f(x)|→∞，属无穷间断点。"))
add(judge("discontinuity-classification", None, "若 lim_{x→a} f(x) 存在，但 f(a) 无定义或不等于该极限，则 x=a 为可去间断点。", True,
          "这正是可去间断点的定义。"))
add(numfill("discontinuity-classification", None, "设 f(x) = { x, x≠0; 1, x=0 }，则 lim_{x→0} f(x) = ？", 0,
            "x→0 时 f(x)=x→0，但 f(0)=1，故为可去间断点，极限为 0。"))
add(exprfill("discontinuity-classification", None, "设 f(x) = { 1, x≥0; -1, x<0 }，在 x=0 处的左极限 = ？", "-1", [],
             "左极限取 x<0 一支，恒为 -1。"))

# 21) continuity-properties 连续函数的局部性质
add(choice("continuity-properties", None, "若 f、g 在 a 处连续，则 f + g 在 a 处（  ）。",
           ["连续", "不一定连续", "间断", "无定义"], "A",
          "连续函数的和仍连续。"))
add(judge("continuity-properties", None, "两个连续函数的复合函数仍连续。", True,
          "连续函数经复合仍保持连续性。"))
add(numfill("continuity-properties", None, "f(x)=x²、g(x)=sin x 均在 0 处连续，则 (f+g)(0) = ？", 0,
            "f(0)+g(0) = 0 + 0 = 0。"))
add(exprfill("continuity-properties", None, "已知 f(x)=√x 在 x=4 处连续，则 lim_{x→4} √x = ？", "2", [],
             "连续则可代值：√4 = 2。"))

# 22) composite-continuity 复合函数与初等函数的连续性
add(choice("composite-continuity", None, "初等函数在其定义域内（  ）。",
           ["连续", "不一定连续", "间断", "可导"], "A",
           "基本初等函数及其复合（初等函数）在定义区间内连续。"))
add(judge("composite-continuity", None, "若 g 在 a 处连续，f 在 g(a) 处连续，则 f∘g 在 a 处连续。", True,
          "复合函数的连续性定理。"))
add(numfill("composite-continuity", None, "利用连续性，lim_{x→0} e^{sin x} = ？", 1,
            "sin 0 = 0，e⁰ = 1，因初等函数连续可直接代值。"))
add(exprfill("composite-continuity", None, "lim_{x→0} ln(1 + x) = ？", "0", [],
             "ln 在 1 处连续，ln(1+0) = 0。"))

# 23) intermediate-value-theorem 介值定理
add(choice("intermediate-value-theorem", None, "连续函数 f 在 [a,b] 上满足 f(a) < 0 < f(b)，则（  ）。",
           ["存在 ξ∈(a,b) 使 f(ξ)=0", "f 一定单调", "f 无零点", "最值必在中点"], "A",
           "由零点定理（介值定理推论），连续函数在异号端点间至少有一个零点。"))
add(judge("intermediate-value-theorem", None, "介值定理可用来证明方程实根的存在性。", True,
          "通过构造连续函数并验证端点异号即可证根存在。"))
add(numfill("intermediate-value-theorem", None, "f(x) = x² - 1 在 [-2,2] 上，f(0) = ？", -1,
            "f(0) = 0 - 1 = -1，而 f(2) = 3 > 0，故 (0,2) 内有根。"))
add(exprfill("intermediate-value-theorem", None, "对 f(x) = x - 2，在 [0,3] 上使 f(ξ)=0 的 ξ = ？", "2", [],
             "f(ξ)=0 ⇒ ξ - 2 = 0 ⇒ ξ = 2 ∈ [0,3]。"))

# 24) closed-interval-properties 闭区间上连续函数的性质
add(choice("closed-interval-properties", None, "闭区间上的连续函数一定（  ）。",
           ["有界且有最大、最小值", "单调", "可导", "无零点"], "A",
           "最值定理：闭区间上连续函数必有界且能取到最大值与最小值。"))
add(judge("closed-interval-properties", None, "闭区间上的连续函数必有最大值和最小值。", True,
          "这是最值定理。"))
add(numfill("closed-interval-properties", None, "f(x) = x² 在 [-1,1] 上的最大值为？", 1,
            "x² 在端点 ±1 处取最大值 1。"))
add(exprfill("closed-interval-properties", None, "f(x) = sin x 在 [0,π] 上的最大值为？", "1", [],
             "sin x 在 x = π/2 处取最大值 1。"))

# ── 8 道额外题，使总数达到 104（覆盖的知识点均已在上文出现）──
add(choice("function-domain-range", None, "函数 f(x) = √(4 - x²) 的定义域是（  ）。",
           ["[-2, 2]", "(-2, 2)", "[0, 2]", "(-∞, 4]"], "A",
           "由 4 - x² ≥ 0 得 x² ≤ 4，即 -2 ≤ x ≤ 2，定义域为 [-2, 2]。"))
add(numfill("limit-arithmetic-laws", None, "lim_{x→3} (2x - 1) = ？", 5,
            "直接代入得 2·3 - 1 = 5。"))
add(exprfill("important-limits", None, "lim_{x→0} tan x / x = ？", "1", [],
             "tan x / x = sin x/(x cos x) → 1·1 = 1。"))
add(judge("elementary-functions", None, "对数函数 y = log_a x（a>0 且 a≠1）的定义域是 (0, +∞)。", True,
          "真数必须大于 0。"))
add(choice("continuity-definition", None, "函数 f(x) = |x| 在 x = 0 处（  ）。",
           ["连续但不可导", "不连续", "可导", "无定义"], "A",
           "lim_{x→0}|x| = 0 = f(0)，故连续；但左右导数分别为 -1 与 1，不相等，故不可导。"))
add(numfill("composite-function", None, "设 f(x) = x²，g(x) = x + 2，则 f(g(1)) = ？", 9,
            "g(1) = 3，f(3) = 9。"))
add(exprfill("equivalent-infinitesimal", None, "lim_{x→0} (1 - cos x)/x² = ？", "1/2", [],
             "由 1 - cos x ~ x²/2，极限为 1/2。"))
add(judge("squeeze-theorem", None, "若 g(x) ≤ f(x) ≤ h(x) 且 lim g = lim h = L，则 lim f = L。", True,
          "这正是夹逼定理的结论。"))

assert len(Q) == 104, f"期望 104 道题，实际 {len(Q)}"


async def main():
    from app.data.database import init_db
    from app.services.question_importer import QuestionImporter
    from app.services.content_review import ContentReviewService

    # 初始化引擎并幂等迁移到 head（不破坏已有数据）
    await init_db()

    importer = QuestionImporter()
    import_result = await importer.import_from_dict_list(Q)
    print(f"[import] total={import_result.total} success={import_result.success} "
          f"failed={import_result.failed} errors={import_result.errors[:5]}")

    review = ContentReviewService()
    ids = [q["id"] for q in Q]
    pub = await review.batch_publish(ids)
    print(f"[publish] published={len(pub['published'])} skipped={len(pub['skipped'])} "
          f"errors={len(pub['errors'])}")
    if pub["errors"]:
        for e in pub["errors"][:10]:
            print("  ERR", e)

    # 验证 gate
    from sqlalchemy import select, func
    from app.data.database import get_db_session
    from app.data.models import Question, QuestionKnowledgePoint

    async with get_db_session() as db:
        published = (await db.execute(
            select(func.count()).select_from(Question).where(Question.review_status == "published")
        )).scalar_one()
        by_type = (await db.execute(
            select(Question.question_type, func.count())
            .where(Question.review_status == "published")
            .group_by(Question.question_type)
        )).all()
        covered = (await db.execute(
            select(func.count(func.distinct(QuestionKnowledgePoint.knowledge_point_id)))
            .join(Question, Question.id == QuestionKnowledgePoint.question_id)
            .where(Question.review_status == "published")
        )).scalar_one()

    print("[gate]")
    print(f"  published_total     = {published}  (要求 >= 100)")
    print(f"  published_by_type   = {dict(by_type)}  (要求首版 4 题型)")
    print(f"  kp_coverage         = {covered}/24  (要求合理覆盖)")

    ok = published >= 100 and covered >= 24 and set(t for t, _ in by_type).issubset(
        {"choice", "judge", "numeric_fill", "expression_fill"}
    )
    print("  GATE_PASS =", ok)
    return ok


if __name__ == "__main__":
    passed = asyncio.run(main())
    sys.exit(0 if passed else 1)
