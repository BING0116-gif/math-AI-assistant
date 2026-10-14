"""《微积分学习辅导与提高》第一章（函数与极限）自测题导入脚本。

来源：第一章自测题2010-1-20.pdf（§1.5 自测题 A/B/C 共 80 题 + §1.6 解答与提示）。
导入方式：人工逐题结构化后走正式链路 QuestionImporter → mark_reviewed → batch_publish，
全程零 LLM（不用系统 DeepSeek 管道），幂等可重跑。

- 题型只用判题引擎支持的 4 种：choice / judge / numeric_fill / expression_fill。
  原卷证明题、定性计算题（间断点分类、分段结论等）转为判断题/选择题，
  原题完整解答写入 analysis，保证练习选池纯净、判分可达。
- numeric_fill 仅用于整数答案（判分按浮点近似比较）；分数/表达式一律
  expression_fill（sympy 等价判分，canonical 用 safe_math 语法）。
- 运行：venv/Scripts/python.exe scripts/import/import_ch1_functions_limits.py
"""

from __future__ import annotations

import asyncio
import os
import sys

# 允许从任意目录直接运行：把仓库根目录加入 sys.path 以导入 app 包
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

COURSE_CODE = "advanced-calculus"
CATEGORY = "高等数学"
SOURCE = "《微积分学习辅导与提高》第一章 §1.5 自测题（PDF 导入）"


def choice(kp, qid, content, opts, correct, analysis, difficulty=3, minutes=3, sub=""):
    options = [{"id": chr(65 + i), "text": t} for i, t in enumerate(opts)]
    return {
        "id": qid, "content": content, "question_type": "choice",
        "options": options, "answer": correct, "analysis": analysis,
        "category": CATEGORY, "sub_categories": sub, "difficulty": difficulty,
        "estimated_time": minutes, "source": SOURCE, "review_status": "draft",
        "knowledge_point_codes": kp if isinstance(kp, list) else [kp],
        "course_code": COURSE_CODE,
        "answer_spec": {"version": 1, "kind": "choice", "correct": correct},
    }


def judge(kp, qid, content, correct_bool, analysis, difficulty=4, minutes=5, sub=""):
    return {
        "id": qid, "content": content, "question_type": "judge",
        "options": [], "answer": "正确" if correct_bool else "错误",
        "analysis": analysis, "category": CATEGORY, "sub_categories": sub,
        "difficulty": difficulty, "estimated_time": minutes, "source": SOURCE,
        "review_status": "draft",
        "knowledge_point_codes": kp if isinstance(kp, list) else [kp],
        "course_code": COURSE_CODE,
        "answer_spec": {"version": 1, "kind": "judge", "correct": bool(correct_bool)},
    }


def numfill(kp, qid, content, value, analysis, difficulty=3, minutes=3, sub=""):
    return {
        "id": qid, "content": content, "question_type": "numeric_fill",
        "options": [], "answer": str(value), "analysis": analysis,
        "category": CATEGORY, "sub_categories": sub, "difficulty": difficulty,
        "estimated_time": minutes, "source": SOURCE, "review_status": "draft",
        "knowledge_point_codes": kp if isinstance(kp, list) else [kp],
        "course_code": COURSE_CODE,
        "answer_spec": {"version": 1, "kind": "numeric_fill", "value": value},
    }


def exprfill(kp, qid, content, canonical, variables, answer, analysis, difficulty=3, minutes=4, sub=""):
    return {
        "id": qid, "content": content, "question_type": "expression_fill",
        "options": [], "answer": answer, "analysis": analysis,
        "category": CATEGORY, "sub_categories": sub, "difficulty": difficulty,
        "estimated_time": minutes, "source": SOURCE, "review_status": "draft",
        "knowledge_point_codes": kp if isinstance(kp, list) else [kp],
        "course_code": COURSE_CODE,
        "answer_spec": {
            "version": 1, "kind": "expression_fill",
            "canonical": canonical, "variables": variables,
        },
    }


SUB_A = "第一章 函数与极限 · 自测题A"
SUB_B = "第一章 函数与极限 · 自测题B"
SUB_C = "第一章 函数与极限 · 自测题C"

Q = []

# ═══════════════════════ 自测题 A ═══════════════════════

Q.append(choice("function-definition", "CH1A-C01",
    "下列选项中两个函数相同的是（  ）。",
    ["y = arcsin x + arccos x 与 y = π/2",
     "y = sin²x + cos²x 与 y = 1",
     "y = lg x² 与 y = 2lg x",
     "y = eˣ 与 y = e^√(x²)"],
    "B",
    "两函数相同要求定义域与对应法则都相同。A：arcsin x + arccos x = π/2 仅在 x ∈ [-1, 1] 内成立，而 y = π/2 对全体实数有定义，定义域不同；C：lg x² 的定义域为 x ≠ 0，2lg x 的定义域为 x > 0，定义域不同；D：e^√(x²) = e^|x| ≠ eˣ，对应法则不同。B：sin²x + cos²x = 1 对一切实数成立，定义域与对应法则都相同。",
    difficulty=2, minutes=2, sub=SUB_A))

Q.append(choice("composite-function", "CH1A-C02",
    "设 g(x) = x − 1，且 f[g(x)] = (x − 1)/(x + 1)，则 f(1/2) =（  ）。",
    ["1/5", "−1/3", "3/5", "−3/5"],
    "A",
    "令 u = g(x) = x − 1，则 x = u + 1，代入得 f(u) = (x − 1)/(x + 1) = u/(u + 2)。故 f(1/2) = (1/2)/(1/2 + 2) = (1/2)/(5/2) = 1/5。",
    difficulty=2, minutes=3, sub=SUB_A))

Q.append(choice("sequence-limit", "CH1A-C03",
    "若在 A 的 ε 邻域内（ε 为任意正数）有无穷多个数列 {uₙ} 中的点，是否可以说 A 是数列 {uₙ} 的极限？（  ）",
    ["可以", "不可以", "ε 很小的时候可以", "ε 很大的时候可以"],
    "B",
    "不可以。「任意 ε 邻域内含无穷多项」不足以保证 uₙ → A，还需要这些项从某一项起全部落在邻域内。反例：u₂ₙ₋₁ = 1/n，u₂ₙ = 1，取 A = 0：对任意 ε > 0，奇数项有无穷多个落在 (−ε, ε) 内，但偶数项恒为 1，数列 {uₙ} 不收敛，更不以 0 为极限。",
    difficulty=3, minutes=3, sub=SUB_A))

Q.append(choice("function-limit", "CH1A-C04",
    "f(x₀) 存在是 lim_{x→x₀} f(x) 存在的（  ）。",
    ["充分条件", "必要条件", "充要条件", "非充分非必要条件"],
    "D",
    "极限刻画 x → x₀ 过程中函数值的变化趋势，与 f(x₀) 是否有定义无关。f(x₀) 存在推不出极限存在（如 f(x) = sgn x 在 x₀ = 0 处有定义但极限不存在）；极限存在也不要求 f(x₀) 有定义（如可去间断点处）。故既非充分也非必要。",
    difficulty=2, minutes=2, sub=SUB_A))

Q.append(choice("sequence-limit", "CH1A-C05",
    "若数列 {xₙ} 有界，则 {xₙ}（  ）。",
    ["收敛", "发散", "收敛于零", "不一定收敛"],
    "D",
    "数列有界是收敛的必要条件而非充分条件。反例：xₙ = (−1)ⁿ 有界但不收敛；xₙ = sin n 有界且发散。故选「不一定收敛」。",
    difficulty=2, minutes=2, sub=SUB_A))

Q.append(choice("limit-properties", "CH1A-C06",
    "已知 lim_{x→x₀} [f₂(x) − f₁(x)] = 0，则（  ）。",
    ["必有 lim_{x→x₀} f₂(x) = lim_{x→x₀} f₁(x)",
     "必有 lim_{x→x₀} f₂(x) ≠ lim_{x→x₀} f₁(x)",
     "lim_{x→x₀} f₂(x)，lim_{x→x₀} f₁(x) 都不一定存在",
     "lim_{x→x₀} f₂(x) = 0 且 lim_{x→x₀} f₁(x) = 0"],
    "C",
    "差的极限为 0 不能保证两个极限各自存在。反例：取 f₁(x) = f₂(x) = 1/x（x₀ = 0），则 f₂ − f₁ ≡ 0，差的极限为 0，但两函数在 x → 0 时极限都不存在。只有当其中一个极限存在时，才能由差的极限推出另一个极限存在且相等。",
    difficulty=3, minutes=3, sub=SUB_A))

Q.append(choice("function-properties", "CH1A-C07",
    "设 f(x) 是以 3 为周期的偶函数，且 f(−1) = 7，则 f(7) =（  ）。",
    ["7", "−7", "0", "3"],
    "A",
    "利用周期性与偶性逐步化简：f(7) = f(7 − 9) = f(−2)（周期 3）= f(2)（偶函数）= f(2 − 3) = f(−1) = 7。",
    difficulty=2, minutes=2, sub=SUB_A))

Q.append(choice("left-right-limit", "CH1A-C08",
    "设 f(x) = { arctan(1/x)，x < 0；(π/2)cos x，x ≥ 0 }，则 lim_{x→0} f(x) =（  ）。",
    ["π/2", "−π/2", "0", "不存在"],
    "D",
    "左极限：x → 0⁻ 时 1/x → −∞，arctan(1/x) → −π/2；右极限：x → 0⁺ 时 f(x) → (π/2)cos 0 = π/2。左右极限存在但不相等，故 lim_{x→0} f(x) 不存在。",
    difficulty=3, minutes=3, sub=SUB_A))

Q.append(choice("function-domain-range", "CH1A-F01",
    "若 f(x) 的定义域为 [0, 2a]（a > 0），则 f(x + a) 的定义域为（  ）。",
    ["[−a, a]", "[0, a]", "[−2a, 0]", "[−a, 2a]"],
    "A",
    "复合函数定义域：内层函数取值须落在 f 的定义域内，即 0 ≤ x + a ≤ 2a，解得 −a ≤ x ≤ a，故 f(x + a) 的定义域为 [−a, a]。注意自变量是 x，要把对 x + a 的限制翻译成对 x 的限制。",
    difficulty=2, minutes=2, sub=SUB_A))

Q.append(choice("piecewise-function", "CH1A-F02",
    "设 f(x) = { 2 + x，x < 0；2，x ≥ 0 }，则 f[f(x)] =（  ）。",
    ["{ 4 + x，x < −2；2，x ≥ −2 }",
     "{ 4 + x，x < 0；2，x ≥ 0 }",
     "{ 2 + x，x < −2；2，x ≥ −2 }",
     "{ 4 − x，x < −2；2，x ≥ −2 }"],
    "A",
    "分层代入：当 x < −2 时 f(x) = 2 + x < 0，f[f(x)] = 2 + (2 + x) = 4 + x；当 −2 ≤ x < 0 时 f(x) = 2 + x ≥ 0，f[f(x)] = 2；当 x ≥ 0 时 f(x) = 2，f[f(x)] = f(2) = 2。综上 f[f(x)] = { 4 + x，x < −2；2，x ≥ −2 }。关键在于内层函数值的正负决定走外层哪一段。",
    difficulty=3, minutes=4, sub=SUB_A))

Q.append(exprfill("composite-function", "CH1A-F03",
    "已知 f(sin(x/2)) = 1 + cos x，求 f(cos(x/2))（用 x 表示）。",
    "1-cos(x)", ["x"], "1 − cos x",
    "1 + cos x = 2cos²(x/2) = 2 − 2sin²(x/2)。令 u = sin(x/2) 得 f(u) = 2 − 2u²。故 f(cos(x/2)) = 2 − 2cos²(x/2) = 2sin²(x/2) = 1 − cos x。",
    difficulty=2, minutes=3, sub=SUB_A))

Q.append(numfill("limit-arithmetic-laws", "CH1A-F04",
    "求 lim_{x→0} (x⁴ − x + 6)/(3x⁴ + 2x + 1)。",
    6,
    "x → 0 时分子 → 6，分母 → 1，分母极限不为零，由商的法则直接代入得极限 = 6/1 = 6。",
    difficulty=1, minutes=2, sub=SUB_A))

Q.append(choice("inverse-function", "CH1A-F05",
    "函数 f(x) = { x²，x ≤ 0；1 − 2ˣ，x > 0 } 的反函数是（  ）。",
    ["y = { −√x，x ≥ 0；log₂(1 − x)，x < 0 }",
     "y = { √x，x ≥ 0；log₂(1 − x)，x < 0 }",
     "y = { −√x，x ≥ 0；log₂(1 + x)，x < 0 }",
     "y = { −x²，x ≥ 0；1 − log₂x，x < 0 }"],
    "A",
    "分段求反函数：x ≤ 0 段 y = x² 的值域为 [0, +∞)，由 y = x²、x ≤ 0 解得 x = −√y；x > 0 段 y = 1 − 2ˣ 的值域为 (−∞, 0)，由 2ˣ = 1 − y 解得 x = log₂(1 − y)。互换 x、y 并合并，反函数为 y = { −√x，x ≥ 0；log₂(1 − x)，x < 0 }。两段值域 [0, +∞) 与 (−∞, 0) 不交，故反函数存在。",
    difficulty=3, minutes=4, sub=SUB_A))

Q.append(numfill("equivalent-infinitesimal", "CH1A-F06",
    "当 x → ∞ 时，无穷小量 1/xᵏ 与 1/x³ + 1/x² 等价，则 k = ？",
    2,
    "x → ∞ 时 1/x³ + 1/x² = (1/x²)(1 + 1/x) ~ 1/x²（等价无穷小只看最低次主部）。故 1/xᵏ 与 1/x² 等价，即 k = 2。",
    difficulty=2, minutes=3, sub=SUB_A))

Q.append(numfill("limit-arithmetic-laws", "CH1A-F07",
    "求 lim_{x→∞} (x + 1)²(3x − 1)³ / (x⁴(x + 2))。",
    27,
    "x → ∞ 的多项式商看最高次项：分子最高次项为 x²·(3x)³ = 27x⁵，分母最高次项为 x⁴·x = x⁵。故极限 = 27/1 = 27。",
    difficulty=2, minutes=2, sub=SUB_A))

Q.append(numfill("continuity-definition", "CH1A-F08",
    "设 f(x) = { (e^(2x) − 1)/(kx)，x ≠ 0；1，x = 0 } 在 x = 0 点处连续，则 k = ？",
    2,
    "连续要求 lim_{x→0} f(x) = f(0) = 1。由 eᵘ − 1 ~ u，x → 0 时 e^(2x) − 1 ~ 2x，故 lim_{x→0} (e^(2x) − 1)/(kx) = 2/k。令 2/k = 1 得 k = 2。",
    difficulty=3, minutes=3, sub=SUB_A))

Q.append(choice("sequence-limit", "CH1A-K01",
    "求 lim_{n→∞} (1/nᵏ + 2/nᵏ + ⋯ + n/nᵏ)（k 为常数），下列结论正确的是（  ）。",
    ["k > 2 时极限为 0，k = 2 时极限为 1/2，k < 2 时极限为 ∞",
     "k > 2 时极限为 0，k = 2 时极限为 1，k < 2 时极限为 ∞",
     "对任意 k 极限均为 0",
     "对任意 k 极限均为 ∞"],
    "A",
    "项数随 n 变化，不能逐项取极限，必须先求和：1/nᵏ + 2/nᵏ + ⋯ + n/nᵏ = n(n + 1)/(2nᵏ) = (1 + 1/n)/(2n^(k−2))。k > 2 时 n^(k−2) → ∞，极限为 0；k = 2 时极限为 1/2；k < 2 时趋于 ∞。",
    difficulty=3, minutes=4, sub=SUB_A))

Q.append(choice("left-right-limit", "CH1A-K02",
    "求 lim_{x→0} tan 3x / √(1 − cos 2x)，下列结论正确的是（  ）。",
    ["极限为 3/√2", "极限为 −3/√2", "极限为 0", "极限不存在"],
    "D",
    "√(1 − cos 2x) = √(2sin²x) = √2·|sin x|，含绝对值必须分侧讨论。x → 0⁺ 时 tan 3x/(√2·sin x) → 3x/(√2·x) = 3/√2；x → 0⁻ 时 tan 3x/(√2·(−sin x)) → −3/√2。左右极限存在但不相等，故极限不存在。",
    difficulty=3, minutes=4, sub=SUB_A))

Q.append(numfill("limit-arithmetic-laws", "CH1A-K03",
    "求 lim_{n→∞} (√(n² + a²)/n + arctan n / n + n·tan(3/n))（a ≠ 0 为常数）。",
    4,
    "三项分别取极限：√(n² + a²)/n = √(1 + a²/n²) → 1；arctan n / n → 0（arctan n 有界而 1/n → 0）；n·tan(3/n) = 3·tan(3/n)/(3/n) → 3·1 = 3。由极限四则运算法则，和的极限 = 1 + 0 + 3 = 4。",
    difficulty=3, minutes=4, sub=SUB_A))

Q.append(exprfill("equivalent-infinitesimal", "CH1A-K04",
    "求 lim_{x→0} x·(sin(1/x²) − csc 2x)。",
    "-1/2", [], "-1/2",
    "拆成两项：lim_{x→0} x·sin(1/x²) = 0（无穷小乘有界量）；lim_{x→0} x/sin 2x = 1/2（sin 2x ~ 2x）。故原式 = 0 − 1/2 = −1/2。注意 x·sin(1/x²) 是振荡有界型，只能用「无穷小 × 有界量」处理。",
    difficulty=3, minutes=5, sub=SUB_A))

Q.append(numfill("limit-arithmetic-laws", "CH1A-K05",
    "求 lim_{x→−8} (√(1 − x) − 3)/(2 + ∛x)。",
    -2,
    "分子有理化：(√(1 − x) − 3)(√(1 − x) + 3) = (1 − x) − 9 = −(x + 8)；分母用立方和公式 (2 + ∛x)(4 − 2∛x + ∛x²) = 8 + x。故原式 = lim_{x→−8} −(4 − 2∛x + ∛x²)/(√(1 − x) + 3) = −(4 + 4 + 4)/(3 + 3) = −12/6 = −2（∛(−8) = −2，√(1 − (−8)) = 3）。注：原卷印刷趋近点为 8，但 1 − 8 < 0 时 √(1 − x) 无实意义，按题意应为 x → −8。",
    difficulty=3, minutes=5, sub=SUB_A))

Q.append(numfill("limit-arithmetic-laws", "CH1A-K06",
    "求 lim_{n→∞} (√(n² + n) − n)/(√(n(n + 1)) − √(n² − 1))。",
    1,
    "分子分母同时有理化：分子 = n/(√(n² + n) + n) → 1/2；分母 = (n + 1)/(√(n² + n) + √(n² − 1)) → 1/2。故原式 = (1/2)/(1/2) = 1。",
    difficulty=3, minutes=5, sub=SUB_A))

Q.append(choice("limit-arithmetic-laws", "CH1A-K07",
    "设 lim_{x→3} (x² − 2x + b)/(x − 3) 存在，则 b 与此极限值分别为（  ）。",
    ["b = −3，极限值为 4", "b = 3，极限值为 4",
     "b = −3，极限值为 −4", "b = 3，极限值为 −4"],
    "A",
    "分母 x → 3 时趋于 0，分式极限存在要求分子同趋于 0：9 − 6 + b = 0，得 b = −3。此时 (x² − 2x − 3)/(x − 3) = (x − 3)(x + 1)/(x − 3) = x + 1 → 4。",
    difficulty=3, minutes=5, sub=SUB_A))

Q.append(choice("discontinuity-classification", "CH1A-K08",
    "设函数 f(x) = { 2^(1/(x − 1))，x > 0；√2，x = 0；(sin x)/x − 1/2，x < 0 }，则其间断点及类型为（  ）。",
    ["x = 0 为可去间断点，x = 1 为无穷间断点",
     "x = 0 为无穷间断点，x = 1 为可去间断点",
     "x = 0 与 x = 1 均为可去间断点",
     "x = 0 与 x = 1 均为无穷间断点"],
    "A",
    "x = 0 处：lim_{x→0⁺} 2^(1/(x−1)) = 2^(−1) = 1/2，lim_{x→0⁻} (sin x/x − 1/2) = 1 − 1/2 = 1/2，左右极限相等，但 f(0) = √2 ≠ 1/2，故 x = 0 为可去间断点。x = 1 处：x → 1⁺ 时 1/(x − 1) → +∞，2^(1/(x−1)) → +∞，故 x = 1 为无穷间断点。",
    difficulty=4, minutes=6, sub=SUB_A))

Q.append(judge("intermediate-value-theorem", "CH1A-P01",
    "判断：命题「方程 xeˣ = x + cos(πx/2) 至少有一个正实根」及证明思路「令 f(x) = xeˣ − x − cos(πx/2)，则 f 在 [0, 2] 上连续，且 f(0) = −1 < 0，f(2) = 2e² − 1 > 0，由零点定理知 f 在 (0, 2) 内至少有一个零点」是否正确。",
    True,
    "正确。移项构造 f(x) = xeˣ − x − cos(πx/2)，它是初等函数，在 [0, 2] 上连续；f(0) = 0 − 0 − cos 0 = −1 < 0，f(2) = 2e² − 2 − cos π = 2e² − 1 > 0。由闭区间上连续函数的零点定理，存在 ξ ∈ (0, 2) 使 f(ξ) = 0，即方程 xeˣ = x + cos(πx/2) 至少有一个正实根。（原卷为证明题，此处转化为判断题考查零点定理的规范应用。）",
    difficulty=4, minutes=6, sub=SUB_A))

Q.append(judge("intermediate-value-theorem", "CH1A-P02",
    "判断：命题「方程 sin x + x + 1 = 0 在区间 (−π/2, π/2) 内至少有一个实根」及证明思路「令 f(x) = sin x + x + 1，则 f 在 [−π/2, π/2] 上连续，f(−π/2) < 0，f(π/2) > 0，由零点定理知 f 在 (−π/2, π/2) 内至少有一个零点」是否正确。",
    True,
    "正确。f(x) = sin x + x + 1 在 [−π/2, π/2] 上连续；f(−π/2) = −1 − π/2 + 1 = −π/2 < 0，f(π/2) = 1 + π/2 + 1 = π/2 + 2 > 0。端点异号，由零点定理存在 ξ ∈ (−π/2, π/2) 使 f(ξ) = 0，即方程在该区间内至少有一个实根。（原卷为证明题。）",
    difficulty=4, minutes=6, sub=SUB_A))

# ═══════════════════════ 自测题 B ═══════════════════════

Q.append(choice("composite-function", "CH1B-C01",
    "设 f(x) = 1/(1 + e^(−x))，φ(x) = x/(1 + x)，则下列等式中成立的是（  ）。",
    ["f(x) = φ(e^(−x))", "f(e^(−x)) = φ(e^(−x))",
     "f(x) = φ(eˣ)", "f(eˣ) = φ(eˣ)"],
    "C",
    "φ(eˣ) = eˣ/(1 + eˣ)，分子分母同除以 eˣ 得 1/(1 + e^(−x)) = f(x)，故 C 成立。检验其他选项：φ(e^(−x)) = e^(−x)/(1 + e^(−x)) = 1/(1 + eˣ) ≠ f(x)；f(e^(−x)) = 1/(1 + e^(−e^(−x)))，与 φ(e^(−x))、φ(eˣ) 均不相同。",
    difficulty=3, minutes=3, sub=SUB_B))

Q.append(choice("function-properties", "CH1B-C02",
    "设函数 f(x) 在 (−∞, +∞) 内有定义且为奇函数，若当 x ∈ (0, +∞) 时 f(x) = x(x − 1)，则当 x ∈ (−∞, 0) 时 f(x) =（  ）。",
    ["x(x − 1)", "x(x + 1)", "−x(x + 1)", "−x(x − 1)"],
    "C",
    "设 x < 0，则 −x > 0，f(−x) = (−x)(−x − 1) = x(x + 1)。由奇函数定义 f(x) = −f(−x) = −x(x + 1)。",
    difficulty=2, minutes=3, sub=SUB_B))

Q.append(choice("equivalent-infinitesimal", "CH1B-C03",
    "当 x → ∞ 时，2/x³ + 1/(2x²) 是 1 − cos(1/x) 的（  ）。",
    ["高阶无穷小", "低阶无穷小", "等价无穷小", "同阶但不等价无穷小"],
    "C",
    "x → ∞ 时 1 − cos(1/x) ~ (1/2)(1/x)² = 1/(2x²)（由 1 − cos u ~ u²/2，u = 1/x → 0）。而 2/x³ + 1/(2x²) = (1/(2x²))(1 + 4/x) ~ 1/(2x²)。两者之比的极限为 1，故为等价无穷小。",
    difficulty=3, minutes=3, sub=SUB_B))

Q.append(choice("infinitesimal", "CH1B-C04",
    "已知 f(x) 在 x₀ = 0 的一个邻域内有界，若 lim_{x→0} g(x)f(x) = 0，则必有（  ）。",
    ["lim_{x→0} g(x) = 0", "lim_{x→0} g(x) ≠ 0",
     "不能确定 lim_{x→0} g(x) = 0", "极限 lim_{x→0} g(x) 不存在"],
    "C",
    "「有界 × 无穷小 = 无穷小」，但乘积极限为 0 反推不出 g 是无穷小。反例：取 f(x) ≡ 0（有界），则对任意 g（如 g(x) = 1）都有 g(x)f(x) = 0，但 lim g(x) = 1 ≠ 0。故只能确定「不能确定」。",
    difficulty=3, minutes=3, sub=SUB_B))

Q.append(choice("limit-properties", "CH1B-C05",
    "若 f(x) 与 f(x)g(x) 的极限均存在，则 g(x) 的极限如何？（  ）",
    ["必存在", "必不存在", "不一定存在", "极限必为零"],
    "C",
    "当 lim f(x) ≠ 0 时，g(x) = [f(x)g(x)]/f(x)，由商的法则其极限必存在；但当 lim f(x) = 0 时无此保证。反例：f(x) = x，g(x) = sin(1/x)（x → 0），f(x)g(x) = x·sin(1/x) → 0 存在，而 g(x) 的极限不存在。故「不一定存在」。",
    difficulty=3, minutes=3, sub=SUB_B))

Q.append(choice("important-limits", "CH1B-C06",
    "下列极限正确的是（  ）。",
    ["lim_{x→0} x·sin(1/x) = 1", "lim_{x→∞} (sin x)/x = 1",
     "lim_{x→0} (1/x)·sin x = 1", "lim_{x→∞} x·sin(1/x) = 0"],
    "C",
    "C 正确，这是第一个重要极限 sin x/x → 1。A：x·sin(1/x) 是无穷小乘有界量，极限为 0 而非 1；B：sin x 有界、1/x → 0，极限为 0；D：x·sin(1/x) = sin(1/x)/(1/x)，令 t = 1/x → 0⁺，极限为 1 而非 0。",
    difficulty=2, minutes=3, sub=SUB_B))

Q.append(choice("discontinuity-classification", "CH1B-C07",
    "函数 f(x) = 1/(e^(x/(x−1)) − 1)，则（  ）。",
    ["x = 0, x = 1 都是 f(x) 的第一类间断点",
     "x = 0, x = 1 都是 f(x) 的第二类间断点",
     "x = 0 是 f(x) 的第一类间断点，x = 1 是 f(x) 的第二类间断点",
     "x = 0 是 f(x) 的第二类间断点，x = 1 是 f(x) 的第一类间断点"],
    "D",
    "x = 0：x/(x−1) → 0，故 e^(x/(x−1)) − 1 ~ x/(x−1) → 0，|f(x)| → ∞，为第二类（无穷）间断点。x = 1：x → 1⁺ 时 x/(x−1) → +∞，e^(+∞) − 1 → +∞，f(x) → 0；x → 1⁻ 时 x/(x−1) → −∞，e^(−∞) − 1 → −1，f(x) → 1/(−1) = −1。左右极限都存在但不相等，为第一类（跳跃）间断点。故选 D。",
    difficulty=4, minutes=5, sub=SUB_B))

Q.append(choice("continuity-definition", "CH1B-C08",
    "函数 f(x) = { x/(1 + arccot(1/x))，x ≠ 0；0，x = 0 } 在 [−5, 5] 上（  ）。",
    ["有一个间断点", "有两个间断点", "连续有界", "连续但无界"],
    "C",
    "考察 x = 0：x → 0⁺ 时 1/x → +∞，arccot(1/x) → 0，f(x) = x/(1 + arccot(1/x)) → 0；x → 0⁻ 时 1/x → −∞，arccot(1/x) → π，f(x) = x/(1 + π) → 0。左右极限都存在且等于 f(0) = 0，故 f 在 x = 0 连续，从而在 [−5, 5] 上连续。闭区间上的连续函数必有界，故选「连续有界」。",
    difficulty=3, minutes=4, sub=SUB_B))

Q.append(exprfill("composite-function", "CH1B-F01",
    "设 f(x + 1/x) = x² + 1/x²，求 f(x)（用 x 表示）。",
    "x^2-2", ["x"], "x² − 2",
    "x² + 1/x² = (x + 1/x)² − 2。令 u = x + 1/x，得 f(u) = u² − 2，故 f(x) = x² − 2。",
    difficulty=3, minutes=3, sub=SUB_B))

Q.append(choice("equivalent-infinitesimal", "CH1B-F02",
    "当 x → 0 时，1 − cos(e^(x²) − 1) 与 2ᵐ·xⁿ 是等价无穷小，则（  ）。",
    ["m = −1，n = 4", "m = 1，n = 4", "m = −1，n = 2", "m = 1，n = 2"],
    "A",
    "由 eᵘ − 1 ~ u，e^(x²) − 1 ~ x²；再由 1 − cos u ~ u²/2（u = e^(x²) − 1），得 1 − cos(e^(x²) − 1) ~ (1/2)(e^(x²) − 1)² ~ (1/2)x⁴ = 2^(−1)·x⁴。对照 2ᵐ·xⁿ 得 m = −1，n = 4。",
    difficulty=4, minutes=4, sub=SUB_B))

Q.append(exprfill("important-limits", "CH1B-F03",
    "求 lim_{x→3⁻} (1/(x − 2))^(1/(x − 3))。",
    "exp(-1)", [], "e^(−1)",
    "这是 1^∞ 型。设极限为 L，则 ln L = lim_{x→3⁻} (1/(x − 3))·ln(1/(x − 2))。令 t = x − 3 → 0⁻，则 x − 2 = 1 + t，ln L = lim_{t→0⁻} −ln(1 + t)/t = −1。故 L = e^(−1)。",
    difficulty=4, minutes=4, sub=SUB_B))

Q.append(exprfill("squeeze-theorem", "CH1B-F04",
    "求 lim_{n→∞} (1/(n² + n + 1) + 2/(n² + n + 2) + ⋯ + n/(n² + n + n))。",
    "1/2", [], "1/2",
    "用夹逼定理：对第 k 项有 k/(n² + 2n) ≤ k/(n² + n + k) ≤ k/(n² + n + 1)。求和得 [n(n + 1)/2]/(n² + 2n) ≤ Sₙ ≤ [n(n + 1)/2]/(n² + n + 1)，两端极限均为 1/2，故 Sₙ → 1/2。",
    difficulty=3, minutes=5, sub=SUB_B))

Q.append(numfill("equivalent-infinitesimal", "CH1B-F05",
    "若 lim_{x→0} (a·tan x + b(1 − cos x))/(ln(1 − 2x) + c(1 − e^(−x²))) = 2，则 a = ？",
    -4,
    "分子中最低阶项为 a·tan x ~ a·x（b(1 − cos x) 是二阶），分母中最低阶项为 ln(1 − 2x) ~ −2x（c(1 − e^(−x²)) 是二阶）。极限存在且为非零常数，要求分子分母同阶，比值 = a/(−2) = 2，故 a = −4。二阶项不影响一阶比值。",
    difficulty=4, minutes=4, sub=SUB_B))

Q.append(numfill("important-limits", "CH1B-F06",
    "求 lim_{x→+∞} x·[ln(1 + x) − ln x]。",
    1,
    "x[ln(1 + x) − ln x] = x·ln(1 + 1/x) = ln(1 + 1/x)/(1/x)。令 t = 1/x → 0⁺，得 lim_{t→0⁺} ln(1 + t)/t = 1（ln(1 + t) ~ t）。",
    difficulty=2, minutes=3, sub=SUB_B))

Q.append(choice("sequence-limit", "CH1B-F07",
    "求 lim_{n→∞} (1 − 2^(−nx))/(1 + 2^(−nx))（x 为参数），下列结论正确的是（  ）。",
    ["x < 0 时为 −1，x = 0 时为 0，x > 0 时为 1",
     "x < 0 时为 1，x = 0 时为 0，x > 0 时为 −1",
     "对任意 x 极限均为 0",
     "对任意 x 极限均为 1"],
    "A",
    "含参极限按参数分类：x > 0 时 2^(−nx) → 0，极限 = 1/1 = 1；x = 0 时分子分母为 (1 − 1)/(1 + 1) = 0，极限为 0；x < 0 时 2^(−nx) = 2^(n|x|) → +∞，分子分母同除以 2^(−nx) 得 (2^(nx) − 1)/(2^(nx) + 1) → −1。",
    difficulty=3, minutes=4, sub=SUB_B))

Q.append(choice("continuity-definition", "CH1B-F08",
    "函数 f(x) = { 2x，|x| ≤ 1；x + 1，|x| > 1 } 的连续区间为（  ）。",
    ["(−∞, −1) ∪ (−1, +∞)", "(−∞, +∞)",
     "(−∞, −1) ∪ (−1, 1) ∪ (1, +∞)", "(−∞, 1) ∪ (1, +∞)"],
    "A",
    "分段点 x = 1：左极限 2·1 = 2，右极限 1 + 1 = 2，且 f(1) = 2，连续。x = −1：左极限 (x + 1)|_{x→−1⁻} = 0，右极限 2x|_{x→−1⁺} = −2，f(−1) = −2，左极限 ≠ 右极限，为跳跃间断点。故连续区间为 (−∞, −1) ∪ (−1, +∞)。",
    difficulty=3, minutes=4, sub=SUB_B))

Q.append(numfill("limit-arithmetic-laws", "CH1B-K01",
    "求 lim_{x→0} (eˣ + e^(−x) − 2)/(2x)。",
    0,
    "拆项：(eˣ + e^(−x) − 2)/(2x) = (eˣ − 1)/(2x) + (e^(−x) − 1)/(2x)。由 eᵘ − 1 ~ u：第一项 → 1/2，第二项 → −1/2。故极限 = 1/2 − 1/2 = 0。",
    difficulty=3, minutes=4, sub=SUB_B))

Q.append(exprfill("limit-arithmetic-laws", "CH1B-K02",
    "求 lim_{x→1} (x + x² + ⋯ + xⁿ − n)/(x − 1)（n 为正整数）。",
    "n*(n+1)/2", ["n"], "n(n + 1)/2",
    "分子拆为 (x − 1) + (x² − 1) + ⋯ + (xⁿ − 1)，除以 (x − 1) 后得 1 + (x + 1) + (x² + x + 1) + ⋯ + (x^(n−1) + ⋯ + 1)。x → 1 时每个括号趋于项数 k，故极限 = 1 + 2 + ⋯ + n = n(n + 1)/2。（也可用 xᵏ − 1 ~ k(x − 1)。）",
    difficulty=3, minutes=4, sub=SUB_B))

Q.append(exprfill("equivalent-infinitesimal", "CH1B-K03",
    "求 lim_{x→0} (1 − cos x·√(cos 2x))/x²。",
    "3/2", [], "3/2",
    "拆项：1 − cos x·√(cos 2x) = (1 − cos x) + cos x·(1 − √(cos 2x))。第一项除以 x² → 1/2。第二项：1 − √(cos 2x) = (1 − cos 2x)/(1 + √(cos 2x))，而 1 − cos 2x ~ 2x²，故第二项除以 x² → 2/2 = 1（cos x → 1）。故原式 = 1/2 + 1 = 3/2。",
    difficulty=4, minutes=5, sub=SUB_B))

Q.append(numfill("important-limits", "CH1B-K04",
    "求极限 lim_{x→π/2} (sin x)^(tan x)。",
    1,
    "1^∞ 型。设极限为 L，ln L = lim_{x→π/2} tan x·ln(sin x) = lim (sin x·ln(sin x))/cos x。令 t = sin x → 1，则 ln L = lim t·ln t/√(1 − t²)（左右两侧取绝对值同号处理）。由 ln t ~ −(1 − t) 与 √(1 − t²) = √((1 − t)(1 + t))，得 ln L = lim −t·√(1 − t)/√(1 + t) = 0。故 L = e⁰ = 1。",
    difficulty=4, minutes=5, sub=SUB_B))

Q.append(numfill("equivalent-infinitesimal", "CH1B-K05",
    "求 lim_{x→0} (cos(xeˣ) − cos(xe^(−x)))/x³。",
    -2,
    "和差化积：cos A − cos B = −2·sin((A + B)/2)·sin((A − B)/2)，其中 A = xeˣ，B = xe^(−x)。(A + B)/2 = x(eˣ + e^(−x))/2 = x·cosh x ~ x；(A − B)/2 = x(eˣ − e^(−x))/2 = x·sinh x ~ x²。故分子 ~ −2·x·x² = −2x³，原式 → −2。",
    difficulty=4, minutes=5, sub=SUB_B))

Q.append(exprfill("equivalent-infinitesimal", "CH1B-K06",
    "求 lim_{x→+∞} ln(1 + 2ˣ)·ln(1 + 3/x)。",
    "3*log(2)", [], "3ln2",
    "x → +∞ 时：ln(1 + 2ˣ) = ln[2ˣ(1 + 2^(−x))] = x·ln 2 + ln(1 + 2^(−x)) ~ x·ln 2（第二项有界相对 x 可忽略…准确地 ln(1 + 2^(−x)) → 0）；ln(1 + 3/x) ~ 3/x。故原式 ~ x·ln 2·(3/x) = 3ln 2。",
    difficulty=4, minutes=5, sub=SUB_B))

Q.append(choice("discontinuity-classification", "CH1B-K07",
    "已知 f(x) = (1/x − 1/(x + 1))/(1/(x − 1) + 1/x)，求 f(x) 的间断点并判断类型，下列结论正确的是（  ）。",
    ["x = 0, x = 1 为可去间断点；x = −1, x = 1/2 为无穷间断点",
     "x = −1, x = 1/2 为可去间断点；x = 0, x = 1 为无穷间断点",
     "x = 0, x = −1 为可去间断点；x = 1, x = 1/2 为无穷间断点",
     "四个间断点均为无穷间断点"],
    "A",
    "化简：分子 = 1/(x(x + 1))，分母 = (2x − 1)/(x(x − 1))，故 f(x) = (x − 1)/((x + 1)(2x − 1))。间断点候选为 x = 0, −1, 1, 1/2（原式无定义处）。x = 0：f → (−1)/((1)(−1)) = 1，可去；x = 1：f → 0/(2·1) = 0，可去；x = −1：分子 −2 ≠ 0、分母 → 0，无穷；x = 1/2：分子 −1/2 ≠ 0、分母 → 0，无穷。",
    difficulty=4, minutes=6, sub=SUB_B))

Q.append(choice("limit-arithmetic-laws", "CH1B-K08",
    "若 lim_{x→∞} [(x² + 1)/(x + 1) − ax − b] = 0，则 a, b 的值为（  ）。",
    ["a = 1，b = −1", "a = 1，b = 1", "a = −1，b = −1", "a = −1，b = 1"],
    "A",
    "通分：(x² + 1)/(x + 1) − ax − b = [x² + 1 − (ax + b)(x + 1)]/(x + 1) = [(1 − a)x² − (a + b)x + (1 − b)]/(x + 1)。分母 ~ x，极限为 0 要求分子次数低于 1 且恒为零：1 − a = 0 且 a + b = 0，得 a = 1，b = −1（此时分子恒为 0）。",
    difficulty=4, minutes=5, sub=SUB_B))

Q.append(judge("intermediate-value-theorem", "CH1B-P01",
    "判断：命题「设 f(x) 在 [a, b] 上连续，a < x₁ < x₂ < ⋯ < xₙ < b，c₁, c₂, …, cₙ 为任意正数，则存在 ξ ∈ (a, b)，使 f(ξ) = (c₁f(x₁) + c₂f(x₂) + ⋯ + cₙf(xₙ))/(c₁ + c₂ + ⋯ + cₙ)」及证明思路「设 m、M 分别为 f 在 [a, b] 上的最小值与最大值，则 m ≤ 加权平均 ≤ M，由介值定理即得结论」是否正确。",
    True,
    "正确。由 f(xᵢ) ≥ m 得加权平均 ≥ m(c₁ + ⋯ + cₙ)/(c₁ + ⋯ + cₙ) = m；同理 ≤ M。记加权平均为 W ∈ [m, M]。若 W = m 或 W = M，取对应的最值点为 ξ 即可；否则由介值定理，在取到最小值与最大值的两点之间存在 ξ 使 f(ξ) = W，且 ξ ∈ (a, b)。（原卷为证明题。）",
    difficulty=4, minutes=6, sub=SUB_B))

Q.append(judge("intermediate-value-theorem", "CH1B-P02",
    "判断：命题「方程 a₁/(x − λ₁) + a₂/(x − λ₂) + a₃/(x − λ₃) = 0 有分别包含在区间 (λ₁, λ₂) 和 (λ₂, λ₃) 内的两个实根，其中 aᵢ > 0（i = 1, 2, 3），且 λ₁ < λ₂ < λ₃」及证明思路「通分后令分子为 f(x) = a₁(x − λ₂)(x − λ₃) + a₂(x − λ₁)(x − λ₃) + a₃(x − λ₁)(x − λ₂)，则 f(λ₁) > 0，f(λ₂) < 0，f(λ₃) > 0，在 [λ₁, λ₂] 与 [λ₂, λ₃] 上分别用零点定理」是否正确。",
    True,
    "正确。f(λ₁) = a₁(λ₁ − λ₂)(λ₁ − λ₃) > 0（两个负因数之积为正）；f(λ₂) = a₂(λ₂ − λ₁)(λ₂ − λ₃) < 0；f(λ₃) = a₃(λ₃ − λ₁)(λ₃ − λ₂) > 0。f 为多项式、处处连续，故 [λ₁, λ₂] 端点异号给出根 ξ₁ ∈ (λ₁, λ₂)，[λ₂, λ₃] 端点异号给出根 ξ₂ ∈ (λ₂, λ₃)。在这两个开区间内分母 (x − λ₁)(x − λ₂)(x − λ₃) ≠ 0，故分子零点就是原方程的根。（原卷为证明题。）",
    difficulty=4, minutes=6, sub=SUB_B))

# ═══════════════════════ 自测题 C ═══════════════════════

Q.append(choice("function-properties", "CH1C-C01",
    "函数 f(x) = |x|·sin(x − 2)/(x(x − 1)(x − 2)²) 在下列哪个区间内有界？（  ）",
    ["(−1, 0)", "(0, 1)", "(1, 2)", "(2, 3)"],
    "A",
    "候选无界点是分母的零点 x = 0, 1, 2。x → 0 时 |x|·sin(x − 2)/(x(x − 1)(x − 2)²) → sin(−2)/((±1)(−1)(4))，极限有限（|x| 与分母中的 x 同阶抵消），x = 0 是可去奇点；而 x = 1、x = 2 处分子不趋于 0、分母趋于 0，函数在其附近无界。四个开区间中只有 (−1, 0) 不含使函数无界的点（端点 0 处极限有限），故 f 在 (−1, 0) 内有界。",
    difficulty=3, minutes=4, sub=SUB_C))

Q.append(choice("squeeze-theorem", "CH1C-C02",
    "设对任意 x，总有 φ(x) ≤ f(x) ≤ g(x)，且 lim_{x→∞} [g(x) − φ(x)] = 0，则 lim_{x→∞} f(x)（  ）。",
    ["存在且等于零", "存在但不一定等于零", "一定不存在", "不一定存在"],
    "D",
    "夹逼定理要求上下界的极限存在且相等，仅有 g − φ → 0 不够。反例：φ(x) = sin²x，g(x) = sin²x + 1/x²，则 g − φ = 1/x² → 0，取 f(x) = sin²x 夹在中间，但 lim_{x→∞} sin²x 不存在。故极限不一定存在。",
    difficulty=3, minutes=3, sub=SUB_C))

Q.append(choice("left-right-limit", "CH1C-C03",
    "lim_{x→0} (e^(1/x) − 1)/(e^(1/x) + 1) =（  ）。",
    ["不存在", "1", "−1", "0"],
    "A",
    "x → 0⁺ 时 1/x → +∞，e^(1/x) → +∞，分子分母同除以 e^(1/x) 得 (1 − e^(−1/x))/(1 + e^(−1/x)) → 1；x → 0⁻ 时 1/x → −∞，e^(1/x) → 0，原式 → (0 − 1)/(0 + 1) = −1。左右极限存在但不相等，故极限不存在。",
    difficulty=3, minutes=3, sub=SUB_C))

Q.append(choice("continuity-definition", "CH1C-C04",
    "设 f(x) 在 (−∞, +∞) 内有定义，且 lim_{x→∞} f(x) = a，g(x) = { f(1/x)，x ≠ 0；0，x = 0 }，则（  ）。",
    ["x = 0 必是 g(x) 的第一类间断点",
     "x = 0 必是 g(x) 的第二类间断点",
     "x = 0 必是 g(x) 的连续点",
     "g(x) 在点 x = 0 处的连续性与 a 的取值有关"],
    "D",
    "x → 0 时 1/x → ∞，故 lim_{x→0} g(x) = lim_{x→∞} f(x) = a。当 a = 0 时极限等于 g(0) = 0，g 在 x = 0 连续；当 a ≠ 0 时极限存在但不等于函数值，x = 0 为可去间断点（第一类）。两种情形都可能，故连续性与 a 的取值有关。",
    difficulty=3, minutes=4, sub=SUB_C))

Q.append(choice("squeeze-theorem", "CH1C-C05",
    "极限 lim_{x→+∞} sin(π[x] + π²/x) =（  ），其中 [x] 表示不超过 x 的最大整数。",
    ["不存在", "0", "1", "π"],
    "B",
    "π[x] 是 π 的整数倍，故 sin(π[x] + π²/x) = (−1)^[x]·sin(π²/x)。虽然 (−1)^[x] 振荡，但 |sin(π²/x)| ≤ π²/x → 0，振幅趋于零，由夹逼知极限为 0。",
    difficulty=4, minutes=4, sub=SUB_C))

Q.append(choice("limit-properties", "CH1C-C06",
    "下列命题不正确的是（  ）。",
    ["lim_{x→a} (f(x) − g(x)) = 0 ⟺ lim_{x→a} f(x) = lim_{x→a} g(x)",
     "lim_{x→a} f(x) = A ⟺ lim_{x→a} |f(x) − A| = 0",
     "lim_{x→a} f(x) = A ⟹ lim_{x→a} |f(x)| = |A|",
     "lim_{x→a} f(x) = A ⟹ lim_{x→a} f²(x) = A²"],
    "A",
    "A 不正确：「⟸」方向成立，但「⟹」在两个极限都不存在时不成立。反例：f(x) = g(x) = 1/x（x → 0），f − g ≡ 0，差的极限为 0，但 lim f 与 lim g 都不存在。B 是极限的语言等价刻画；C 可由 ||f(x)| − |A|| ≤ |f(x) − A| 得；D 由极限乘法法则得。",
    difficulty=3, minutes=4, sub=SUB_C))

Q.append(choice("sequence-limit", "CH1C-C07",
    "设 f(x) = lim_{n→∞} 3nx/(1 − nx)，则它的连续区间是（  ）。",
    ["(−∞, +∞)", "(−∞, −1) ∪ (1, +∞)",
     "(−∞, 0) ∪ (0, +∞)", "(−∞, 0) ∪ (0, 1) ∪ (1, +∞)"],
    "C",
    "先求极限函数：x ≠ 0 时分子分母同除以 n，3nx/(1 − nx) = 3x/(1/n − x) → 3x/(−x) = −3；x = 0 时极限为 0。故 f(x) = { −3，x ≠ 0；0，x = 0 }，仅在 x = 0 处间断，连续区间为 (−∞, 0) ∪ (0, +∞)。",
    difficulty=4, minutes=5, sub=SUB_C))

Q.append(choice("function-properties", "CH1C-C08",
    "设 f(x) 是定义在 [−a, a]（a > 0）上的连续函数，又 g(x) = (f(x) + f(−x))/(x − l)（l > a），则 g(x) 是（  ）。",
    ["连续奇函数", "连续偶函数", "连续的非奇非偶函数", "不连续函数"],
    "C",
    "分子 h(x) = f(x) + f(−x) 满足 h(−x) = f(−x) + f(x) = h(x)，是连续偶函数；在 [−a, a] 上 |x| ≤ a < l，分母 x − l ≠ 0，故 g 在 [−a, a] 上连续。但 g(−x) = h(x)/(−x − l) = −h(x)/(x + l)，它既不等于 −g(x) = h(x)/(x − l)（因 l ≠ 0），也不等于 g(x)，故 g 非奇非偶。注意奇偶性要在关于原点对称的定义域上讨论。",
    difficulty=3, minutes=4, sub=SUB_C))

Q.append(exprfill("composite-function", "CH1C-F01",
    "已知函数 f₁(x) = (2x − 1)/(x + 1)，对于 n = 1, 2, 3, …，定义 f_{n+1}(x) = f₁(fₙ(x))。若 f₃₅(x) = f₅(x)，求 f₂₈(x)（用 x 表示）。",
    "1/(1-x)", ["x"], "1/(1 − x)",
    "分式线性变换的迭代有周期性。逐次计算：f₁²(x) = (x − 1)/x，f₁³(x) = (x − 2)/(2x − 1)，f₁⁴(x) = 1/(1 − x)，f₁⁵(x) = (x + 1)/(2 − x)，f₁⁶(x) = x，即 f₁⁶ = 恒等变换。故 f₃₅ = f₁^(35 mod 6) = f₁⁵，与 f₅ 恒相同（条件自动成立）；f₂₈ = f₁^(28 mod 6) = f₁⁴ = 1/(1 − x)。",
    difficulty=4, minutes=5, sub=SUB_C))

Q.append(exprfill("limit-arithmetic-laws", "CH1C-F02",
    "求 lim_{x→+∞} [(x³ − x² + x/2)·e^(1/x) − √(x⁶ + 1)]。",
    "1/6", [], "1/6",
    "泰勒展开：e^(1/x) = 1 + 1/x + 1/(2x²) + 1/(6x³) + O(1/x⁴)。乘开后 (x³ − x² + x/2)e^(1/x) = x³ + 1/6 + O(1/x)（x²、x 项恰好相消）；√(x⁶ + 1) = x³·√(1 + 1/x⁶) = x³ + O(1/x⁵)。故原式 → 1/6。",
    difficulty=4, minutes=5, sub=SUB_C))

Q.append(exprfill("equivalent-infinitesimal", "CH1C-F03",
    "求 lim_{x→0} (3sin x + x³·cos(1/x))/((1 + cos x)·ln(1 + x))。",
    "3/2", [], "3/2",
    "拆项处理。第一部分：3sin x/((1 + cos x)ln(1 + x)) ~ 3x/(2x) = 3/2（sin x ~ x，ln(1 + x) ~ x，1 + cos x → 2）；第二部分：x³·cos(1/x)/((1 + cos x)ln(1 + x)) 中 cos(1/x) 有界，x³/(2x) = x²/2 → 0。故原式 = 3/2 + 0 = 3/2。",
    difficulty=3, minutes=4, sub=SUB_C))

Q.append(exprfill("important-limits", "CH1C-F04",
    "已知函数 f(x) = { (cos x)^(1/x²)，x ≠ 0；a，x = 0 } 在 x = 0 处连续，则 a = ？",
    "exp(-1/2)", [], "e^(−1/2)",
    "1^∞ 型：设 L = lim_{x→0} (cos x)^(1/x²)，则 ln L = lim ln(cos x)/x²。由 ln(cos x) = ln(1 + (cos x − 1)) ~ cos x − 1 ~ −x²/2，得 ln L = −1/2，L = e^(−1/2)。连续要求 a = lim_{x→0} f(x) = e^(−1/2)。",
    difficulty=4, minutes=5, sub=SUB_C))

Q.append(exprfill("equivalent-infinitesimal", "CH1C-F05",
    "当 x → 0 时，α(x) = kx² 与 β(x) = √(1 + x·arcsin x) − √(cos x) 是等价无穷小，则 k = ？",
    "3/4", [], "3/4",
    "分子有理化：β = (1 + x·arcsin x − cos x)/(√(1 + x·arcsin x) + √(cos x))。分母 → 2。分子中 x·arcsin x ~ x²，1 − cos x ~ x²/2，故分子 ~ (3/2)x²。于是 β ~ (3/2)x²/2 = (3/4)x²。由 α 与 β 等价得 k = 3/4。",
    difficulty=4, minutes=5, sub=SUB_C))

Q.append(exprfill("left-right-limit", "CH1C-F06",
    "设函数 f(x) = { sin(ax)/√(1 − cos x)，x < 0；(1/x)·[ln x − ln(x + x²)]，x > 0 }，当 x → 0 时的极限存在，则 a = ？",
    "sqrt(2)/2", [], "√2/2",
    "右极限：(1/x)·ln(x/(x + x²)) = −ln(1 + x)/x → −1。左极限：x → 0⁻ 时 1 − cos x ~ x²/2，√(1 − cos x) ~ |x|/√2 = −x/√2，sin(ax) ~ ax，故 sin(ax)/√(1 − cos x) → ax/(−x/√2) = −a√2。极限存在要求左右相等：−a√2 = −1，即 a = 1/√2 = √2/2。",
    difficulty=4, minutes=5, sub=SUB_C))

Q.append(exprfill("limit-arithmetic-laws", "CH1C-F07",
    "求 lim_{x→∞} x⁴·(arctan((2x² + 5)/(x² + 1)) − arctan((2x² + 7)/(x² + 2)))。",
    "3/5", [], "3/5",
    "记 u = (2x² + 5)/(x² + 1)，v = (2x² + 7)/(x² + 2)，则 u、v → 2，且 u − v = [(2x² + 5)(x² + 2) − (2x² + 7)(x² + 1)]/[(x² + 1)(x² + 2)] = 3/((x² + 1)(x² + 2)) ~ 3/x⁴。由 arctan u − arctan v = arctan((u − v)/(1 + uv))，且 (u − v)/(1 + uv) ~ 3/(5x⁴)，arctan t ~ t（t → 0），故原式 = x⁴·3/(5x⁴) = 3/5。",
    difficulty=4, minutes=5, sub=SUB_C))

Q.append(exprfill("squeeze-theorem", "CH1C-F08",
    "求 lim_{n→∞} (ln(1 + 1/n)/(n + 1/n) + ln(1 + 2/n)/(n + 2/n) + ⋯ + ln(1 + n/n)/(n + n/n))。",
    "2*log(2)-1", [], "2ln2 − 1",
    "第 k 项 = ln(1 + k/n)/(n(1 + k/n²)) = (1/n)·ln(1 + k/n)/(1 + k/n²)。由于 0 ≤ k/n² ≤ 1/n → 0，因子 1/(1 + k/n²) 一致趋于 1，和式与黎曼和 (1/n)·Σₖ₌₁ⁿ ln(1 + k/n) 之差趋于 0。而 (1/n)Σₖ₌₁ⁿ ln(1 + k/n) → ∫₀¹ ln(1 + x)dx = [(1 + x)ln(1 + x) − (1 + x)]₀¹ = (2ln2 − 2) − (−1) = 2ln 2 − 1。",
    difficulty=4, minutes=6, sub=SUB_C))

Q.append(exprfill("limit-arithmetic-laws", "CH1C-K01",
    "已知有整数 n（n > 4）使极限 lim_{x→+∞} [(xⁿ + 7x⁴ + 2)^α − x] 存在且不为零，求 α。",
    "1/5", [], "1/5",
    "(xⁿ + 7x⁴ + 2)^α = x^(nα)·(1 + 7x^(4−n) + 2x^(−n))^α = x^(nα)·(1 + 7α·x^(4−n) + o(x^(4−n)))。要使「原式 − x」的极限存在，必须 nα = 1（否则首项发散或抵不掉）；此时 (xⁿ + 7x⁴ + 2)^α = x·(1 + 7α·x^(4−n) + ⋯)，减 x 后主导项为 7α·x^(5−n)。极限不为零要求 5 − n = 0，即 n = 5，极限值 = 7α = 7/5 ≠ 0。故 α = 1/n = 1/5。",
    difficulty=4, minutes=5, sub=SUB_C))

Q.append(exprfill("important-limits", "CH1C-K02",
    "求 lim_{n→∞} tanⁿ(π/4 + 2/n)。",
    "exp(4)", [], "e⁴",
    "1^∞ 型。tan(π/4 + t) = (1 + tan t)/(1 − tan t)，当 t = 2/n → 0 时 = (1 + t + o(t))/(1 − t + o(t)) = 1 + 2t + o(t) = 1 + 4/n + o(1/n)。故原式 = lim (1 + 4/n + o(1/n))ⁿ = e⁴。",
    difficulty=4, minutes=5, sub=SUB_C))

Q.append(exprfill("equivalent-infinitesimal", "CH1C-K03",
    "求 lim_{x→0} (1/x³)·[((2 + cos x)/3)ˣ − 1]。",
    "-1/6", [], "-1/6",
    "((2 + cos x)/3)ˣ = e^(x·ln((2 + cos x)/3))。ln((2 + cos x)/3) = ln(1 − (1 − cos x)/3) ~ −(1 − cos x)/3 ~ −x²/6。故 x·ln((2 + cos x)/3) ~ −x³/6，由 eᵘ − 1 ~ u 得原式 → (−x³/6)/x³ = −1/6。",
    difficulty=4, minutes=6, sub=SUB_C))

Q.append(numfill("limit-arithmetic-laws", "CH1C-K04",
    "求 lim_{x→−∞} (√(4x² + x − 1) + x + 1)/√(x² + sin x)。",
    1,
    "x → −∞ 时 √(x²) = |x| = −x，必须带负号提出：√(4x² + x − 1) = −2x·√(1 + 1/(4x) − 1/(4x²)) = −2x − 1/4 + o(1)。分子 = −2x − 1/4 + x + 1 + o(1) = −x + 3/4 + o(1)。分母 = |x|·√(1 + sin x/x²) = −x·(1 + o(1))。故原式 → (−x)/(−x) = 1。",
    difficulty=4, minutes=6, sub=SUB_C))

Q.append(exprfill("equivalent-infinitesimal", "CH1C-K05",
    "求 lim_{x→0⁺} (1 − √(cos x))/(x(1 − cos √x))。",
    "1/2", [], "1/2",
    "1 − √(cos x) = (1 − cos x)/(1 + √(cos x)) ~ (x²/2)/2 = x²/4；1 − cos √x ~ (√x)²/2 = x/2。分母 = x·(x/2) = x²/2。故原式 ~ (x²/4)/(x²/2) = 1/2。",
    difficulty=4, minutes=5, sub=SUB_C))

Q.append(numfill("left-right-limit", "CH1C-K06",
    "求 lim_{x→0} ((2 + e^(1/x))/(1 + e^(4/x)) + (sin x)/|x|)。",
    1,
    "必须分侧。x → 0⁺：分子分母同除以 e^(4/x)，第一项 = (2e^(−4/x) + e^(−3/x))/(e^(−4/x) + 1) → 0，sin x/|x| → 1，和为 1。x → 0⁻：两个指数项都 → 0，第一项 → 2/1 = 2，sin x/|x| = sin x/(−x) → −1，和为 1。左右极限相等，故极限为 1。",
    difficulty=4, minutes=5, sub=SUB_C))

Q.append(choice("discontinuity-classification", "CH1C-K07",
    "求函数 f(x) = (1 + x)^(x/tan(x − π/4)) 在区间 (0, 2π) 内的间断点并判断类型，下列结论正确的是（  ）。",
    ["x = π/4, 5π/4 为第二类间断点；x = 3π/4, 7π/4 为可去间断点",
     "x = 3π/4, 7π/4 为第二类间断点；x = π/4, 5π/4 为可去间断点",
     "x = π/4, 3π/4, 5π/4, 7π/4 均为第二类间断点",
     "x = π/4, 3π/4, 5π/4, 7π/4 均为可去间断点"],
    "A",
    "间断点来自 tan(x − π/4) 取零或不存在处：x − π/4 = kπ 即 x = π/4, 5π/4（tan → 0，指数 x/tan → ∞，底 (1 + x) > 1，f → ∞，第二类间断点）；x − π/4 = π/2 + kπ 即 x = 3π/4, 7π/4（tan → ∞，指数 → 0，f → (1 + x)⁰ = 1，但函数在该点无定义，为可去间断点）。",
    difficulty=4, minutes=6, sub=SUB_C))

Q.append(choice("sequence-limit", "CH1C-K08",
    "求 lim_{n→∞} (1 + x)(1 + x²)⋯(1 + x^(2ⁿ))（x 为参数），下列结论正确的是（  ）。",
    ["|x| < 1 时为 1/(1 − x)；|x| > 1 或 x = 1 时为 ∞；x = −1 时为 0",
     "|x| < 1 时为 1/(1 + x)；|x| > 1 时为 ∞；x = ±1 时为 0",
     "对任意 x 极限均为 1/(1 − x)",
     "对任意 x 极限均为 ∞"],
    "A",
    "经典技巧：乘以 (1 − x)，反复用平方差，(1 − x)(1 + x)(1 + x²)⋯(1 + x^(2ⁿ)) = 1 − x^(2^(n+1))。故当 |x| < 1 时乘积 = (1 − x^(2^(n+1)))/(1 − x) → 1/(1 − x)；|x| > 1 时 x^(2^(n+1)) → ∞，乘积 → ∞；x = 1 时乘积 = 2^(n+1) → ∞；x = −1 时乘积中含因子 (1 + (−1)) = 0，恒为 0。",
    difficulty=4, minutes=6, sub=SUB_C))

Q.append(judge("squeeze-theorem", "CH1C-P01",
    "判断：命题「证明 lim_{n→∞} n^(1/n) = 1」及证明思路「数列 n^(1/n) 单调递减且有下界 1，由单调有界准则知极限存在，且极限只能为 1，命题得证」是否正确。",
    False,
    "不正确。「单调递减 + 下界 1」只能证明极限存在且 ≥ 1，并不能直接得到极限等于 1。正确证明（原卷解答）：令 n^(1/n) = 1 + aₙ（aₙ > 0），则 n = (1 + aₙ)ⁿ = 1 + naₙ + n(n − 1)aₙ²/2 + ⋯ ≥ n(n − 1)aₙ²/2，于是 0 < aₙ ≤ √(2/(n − 1)) → 0，由夹逼定理 aₙ → 0，即 lim_{n→∞} n^(1/n) = 1。（原卷为证明题，此判断题考查「单调有界只能证存在、不能定值」这一易错点。）",
    difficulty=4, minutes=6, sub=SUB_C))

Q.append(judge("sequence-limit", "CH1C-P02",
    "判断：命题「若数列 {xₙ} 收敛，即 lim_{n→∞} xₙ = a，则 lim_{n→∞} (x₁ + x₂ + ⋯ + xₙ)/n = a」及证明思路「对任意 ε > 0，先取 N₁ 使 n > N₁ 时 |xₙ − a| < ε/2，再把前 N₁ 项的偏差 |x₁ − a| + ⋯ + |x_{N₁} − a| 作为定数放缩为 (N₁/n)·定数，最后取 N = max{N₁, N₂} 得 |平均值 − a| < ε」是否正确。",
    True,
    "正确。这是典型的「先截后放」证法：前 N₁ 项是有限个定数，其偏差之和为常数 C，则 |(Σxₖ − na)/n| ≤ C/n + (n − N₁)·(ε/2)/n < C/n + ε/2；取 N₂ 使 n > N₂ 时 C/n < ε/2，则 n > N 时 |平均值 − a| < ε。结论即算术平均值法则。（原卷为证明题。）",
    difficulty=4, minutes=6, sub=SUB_C))

Q.append(judge("intermediate-value-theorem", "CH1C-P03",
    "判断：命题「设 f(x) 在 [0, 1] 上连续，f(0) = f(1)，求证：对任意正整数 n，必存在 xₙ ∈ [0, 1]，使 f(xₙ) = f(xₙ + 1/n)」及证明思路「令 φ(x) = f(x) − f(x + 1/n)，则 φ 在 [0, 1 − 1/n] 上连续，且 Σₖ₌₀^(n−1) φ(k/n) = f(0) − f(1) = 0；若各项不全为零则必有正有负，由零点定理即得」是否正确。",
    True,
    "正确。φ(x) = f(x) − f(x + 1/n) 在 [0, 1 − 1/n] 上连续；求和时中间项 f(k/n) 交错相消，得 Σₖ₌₀^(n−1) φ(k/n) = f(0) − f(1) = 0。若某个 φ(k/n) = 0，取 xₙ = k/n 即可；否则各项中必有正有负，由零点定理存在 xₙ ∈ (0, 1 − 1/n) ⊂ [0, 1] 使 φ(xₙ) = 0，即 f(xₙ) = f(xₙ + 1/n)。（原卷为证明题。）",
    difficulty=4, minutes=6, sub=SUB_C))

Q.append(judge("monotone-convergence", "CH1C-P04",
    "判断：命题「设 a > 0，x₁ > 0，x_{n+1} = (1/2)(xₙ + a/xₙ)，证明 {xₙ} 的极限（n → ∞）存在，并求出极限值」及证明思路「由均值不等式 x_{n+1} ≥ √a 知 {xₙ} 单调递增且有上界 √a，故极限存在；设极限为 l，对递推式取极限得 l = (1/2)(l + a/l)，解得 l = ±√a，舍负得 l = √a」是否正确。",
    False,
    "不正确。x_{n+1} ≥ √a（均值不等式）说明从第 2 项起数列有下界 √a，但单调方向是递减而非递增：当 xₙ ≥ √a 时 a/xₙ ≤ xₙ，故 x_{n+1} = (xₙ + a/xₙ)/2 ≤ xₙ。正确论证：x₂ = (1/2)(x₁ + a/x₁) ≥ √a；n ≥ 2 后 {xₙ} 单调递减且有下界 √a，由单调有界准则知极限存在；设极限为 l，对递推式取极限得 l = (1/2)(l + a/l)，即 l² = a，l = √a（负值舍去）。（原卷为证明题，此判断题考查递推数列「先估界、再定单调方向」的易错点。）",
    difficulty=4, minutes=6, sub=SUB_C))


# ── 发布前自检 ──

def preflight():
    errors = []
    ids = [q["id"] for q in Q]
    if len(ids) != len(set(ids)):
        errors.append("存在重复题目 id")
    if len(Q) != 80:
        errors.append(f"题目总数 {len(Q)} ≠ 80")
    for q in Q:
        spec = q["answer_spec"]
        kind = spec["kind"]
        if kind == "choice":
            opt_ids = [o["id"] for o in q["options"]]
            if len(q["options"]) < 2 or spec["correct"] not in opt_ids:
                errors.append(f"{q['id']}: 选项或答案 id 无效")
            if q["answer"] != spec["correct"]:
                errors.append(f"{q['id']}: answer 与 answer_spec 不一致")
        elif kind == "judge":
            if not isinstance(spec["correct"], bool):
                errors.append(f"{q['id']}: judge spec 无效")
        elif kind == "numeric_fill":
            if not isinstance(spec["value"], (int, float)):
                errors.append(f"{q['id']}: numeric spec 无效")
        elif kind == "expression_fill":
            try:
                from app.services.safe_math import parse_safe_expression
                parse_safe_expression(spec["canonical"], spec["variables"])
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{q['id']}: canonical 无法解析: {exc}")
        if not q["knowledge_point_codes"]:
            errors.append(f"{q['id']}: 未挂载知识点")
        if not q["analysis"].strip():
            errors.append(f"{q['id']}: 缺少解析")
    return errors


async def main():
    pre_errors = preflight()
    if pre_errors:
        for e in pre_errors:
            print("PREFLIGHT_ERR", e)
        return False

    from app.data.database import close_db, init_db
    from app.services.question_importer import QuestionImporter
    from app.services.content_review import ContentReviewService
    from app.services.paper_generator import _grade_one

    await init_db()

    importer = QuestionImporter()
    import_result = await importer.import_from_dict_list(Q)
    print(f"[import] total={import_result.total} success={import_result.success} "
          f"failed={import_result.failed} errors={import_result.errors[:5]}")

    review = ContentReviewService()
    reviewed_ids, review_errors = [], []
    for q in Q:
        qid = q["id"]
        try:
            question = await review.get_question(qid)
            if question is None:
                raise RuntimeError("题目不存在")
            if question.review_status == "draft":
                question = await review.mark_reviewed(qid, operator_id="ch1-pdf-import")
            elif question.review_status not in {"reviewed", "published"}:
                raise RuntimeError(f"不支持从 {question.review_status} 状态继续")
            reviewed_ids.append(question.id)
        except Exception as error:
            review_errors.append({"question_id": qid, "error": str(error)[:200]})
    print(f"[review] reviewed={len(reviewed_ids)} errors={len(review_errors)}")
    for e in review_errors[:10]:
        print("  REVIEW_ERR", e)

    pub = await review.batch_publish(reviewed_ids, operator_id="ch1-pdf-import")
    print(f"[publish] published={len(pub['published'])} skipped={len(pub['skipped'])} "
          f"errors={len(pub['errors'])}")
    for e in pub["errors"][:10]:
        print("  PUBLISH_ERR", e)

    # 发布后立刻刷 outbox，把向量写入 Qdrant（不依赖调度器周期）
    try:
        from app.services.outbox import process_outbox_batch
        outbox_result = await process_outbox_batch()
        print(f"[outbox] {outbox_result}")
    except Exception as error:
        print(f"[outbox] 刷批失败（可稍后由调度器重试）: {error}")

    # ── 验证：发布数量、题型分布、判分冒烟测试 ──
    from sqlalchemy import select, func
    from app.data.database import get_db_session
    from app.data.models import Question, QuestionKnowledgePoint

    ids = [q["id"] for q in Q]
    async with get_db_session() as db:
        rows = (await db.execute(
            select(Question.question_type, func.count())
            .where(Question.id.in_(ids), Question.review_status == "published")
            .group_by(Question.question_type)
        )).all()
        missing = (await db.execute(
            select(func.count()).select_from(Question)
            .where(Question.id.in_(ids), Question.review_status != "published")
        )).scalar_one()
        kp_linked = (await db.execute(
            select(func.count(func.distinct(QuestionKnowledgePoint.question_id)))
            .where(QuestionKnowledgePoint.question_id.in_(ids))
        )).scalar_one()

    by_type = dict(rows)
    print("[verify]")
    print(f"  published(本批 80 题) = {80 - missing}, 题型分布 = {by_type}, 已挂知识点 = {kp_linked}/80")

    # 判分冒烟测试：用标准答案判应得「对」，再用一个错误答案判应得「错」
    grade_fail = []
    wrong_probe = {"choice": "Z", "judge": None, "numeric_fill": "999999", "expression_fill": "0"}
    for q in Q:
        spec = q["answer_spec"]
        kind = spec["kind"]
        if kind == "choice":
            good, bad = spec["correct"], wrong_probe["choice"]
        elif kind == "judge":
            # 判分引擎 _norm_bool 接受 bool 或「对/错/√/×/true/false」等字符串
            good, bad = bool(spec["correct"]), not spec["correct"]
        elif kind == "numeric_fill":
            good, bad = str(spec["value"]), wrong_probe["numeric_fill"]
        else:
            good, bad = spec["canonical"], wrong_probe["expression_fill"]
        snap = {"answer_spec": spec}
        if not _grade_one(snap, good)["correct"]:
            grade_fail.append(f"{q['id']} 正确答案被判错")
        if _grade_one(snap, bad)["correct"]:
            grade_fail.append(f"{q['id']} 错误答案被判对")
    print(f"  grading_smoke = {'PASS' if not grade_fail else 'FAIL'} ({grade_fail[:5]})")

    ok = missing == 0 and not grade_fail
    print(f"RESULT = {'OK' if ok else 'FAILED'}")
    await close_db()
    return ok


if __name__ == "__main__":
    passed = asyncio.run(main())
    sys.exit(0 if passed else 1)
