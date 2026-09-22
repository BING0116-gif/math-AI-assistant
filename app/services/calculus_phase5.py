"""Curated upper-calculus taxonomy added by Phase 5.

The entries are project-authored catalog metadata.  They deliberately keep the
graph small enough to review while bringing the published course to 98 points.
"""

CHAPTERS = [
    ("mean-value-and-applications", "中值定理与导数应用", "中值定理、单调性、极值、曲线研究与近似。", 3),
    ("indefinite-integrals", "不定积分", "原函数、基本积分法与常见积分技巧。", 4),
    ("definite-integrals", "定积分", "定积分概念、性质、计算与反常积分。", 5),
    ("integral-applications", "定积分的应用", "面积、体积、弧长与物理应用。", 6),
]

# code, name, chapter code, order, difficulty, prerequisites
POINTS = [
    ("fermat-theorem", "费马引理", "mean-value-and-applications", 1, 3, ["derivative-definition"]),
    ("rolle-theorem", "罗尔定理", "mean-value-and-applications", 2, 3, ["fermat-theorem", "closed-interval-properties"]),
    ("lagrange-mvt", "拉格朗日中值定理", "mean-value-and-applications", 3, 4, ["rolle-theorem"]),
    ("cauchy-mvt", "柯西中值定理", "mean-value-and-applications", 4, 4, ["lagrange-mvt", "quotient-rule"]),
    ("lhopital-rule", "洛必达法则", "mean-value-and-applications", 5, 4, ["cauchy-mvt", "higher-order-derivatives"]),
    ("monotonicity-derivative", "函数单调性的判定", "mean-value-and-applications", 6, 3, ["lagrange-mvt"]),
    ("local-extrema", "函数的极值", "mean-value-and-applications", 7, 3, ["monotonicity-derivative"]),
    ("global-extrema", "最大值与最小值", "mean-value-and-applications", 8, 3, ["local-extrema", "closed-interval-properties"]),
    ("optimization-modeling", "最优化问题建模", "mean-value-and-applications", 9, 4, ["global-extrema"]),
    ("concavity", "曲线的凹凸性", "mean-value-and-applications", 10, 3, ["higher-order-derivatives"]),
    ("inflection-points", "拐点", "mean-value-and-applications", 11, 3, ["concavity"]),
    ("curve-asymptotes", "曲线的渐近线", "mean-value-and-applications", 12, 3, ["function-limit"]),
    ("function-graph-analysis", "函数图形的综合描绘", "mean-value-and-applications", 13, 4, ["local-extrema", "inflection-points", "curve-asymptotes"]),
    ("curvature", "曲率", "mean-value-and-applications", 14, 4, ["parametric-derivative", "higher-order-derivatives"]),
    ("taylor-formula", "泰勒公式", "mean-value-and-applications", 15, 5, ["lagrange-mvt", "higher-order-derivatives"]),
    ("maclaurin-expansions", "常用麦克劳林展开", "mean-value-and-applications", 16, 4, ["taylor-formula"]),
    ("differential-approximation", "微分近似与误差估计", "mean-value-and-applications", 17, 3, ["linear-approximation", "lagrange-mvt"]),
    ("root-approximation", "方程根的近似求法", "mean-value-and-applications", 18, 4, ["monotonicity-derivative", "linear-approximation"]),

    ("antiderivative", "原函数与不定积分", "indefinite-integrals", 1, 2, ["derivative-function"]),
    ("indefinite-properties", "不定积分的性质", "indefinite-integrals", 2, 2, ["antiderivative"]),
    ("basic-integral-table", "基本积分公式", "indefinite-integrals", 3, 2, ["antiderivative", "constant-power-rules"]),
    ("direct-integration", "直接积分法", "indefinite-integrals", 4, 3, ["basic-integral-table", "indefinite-properties"]),
    ("substitution-first-kind", "第一类换元积分法", "indefinite-integrals", 5, 3, ["direct-integration", "chain-rule"]),
    ("substitution-second-kind", "第二类换元积分法", "indefinite-integrals", 6, 4, ["substitution-first-kind"]),
    ("integration-by-parts", "分部积分法", "indefinite-integrals", 7, 4, ["product-rule", "direct-integration"]),
    ("rational-integration", "有理函数积分", "indefinite-integrals", 8, 4, ["integration-by-parts"]),
    ("trigonometric-integration", "三角函数有理式积分", "indefinite-integrals", 9, 4, ["substitution-second-kind", "trigonometric-derivatives"]),
    ("radical-integration", "简单无理函数积分", "indefinite-integrals", 10, 4, ["substitution-second-kind"]),
    ("integration-strategy", "积分方法的选择", "indefinite-integrals", 11, 5, ["integration-by-parts", "rational-integration", "trigonometric-integration"]),
    ("indefinite-integral-review", "不定积分综合", "indefinite-integrals", 12, 4, ["integration-strategy"]),

    ("riemann-sum", "黎曼和", "definite-integrals", 1, 3, ["sequence-limit", "function-limit"]),
    ("definite-integral-definition", "定积分的定义", "definite-integrals", 2, 3, ["riemann-sum", "continuity-definition"]),
    ("definite-integral-properties", "定积分的性质", "definite-integrals", 3, 3, ["definite-integral-definition"]),
    ("integral-mean-value", "积分中值定理", "definite-integrals", 4, 3, ["definite-integral-properties", "closed-interval-properties"]),
    ("variable-upper-integral", "变上限定积分", "definite-integrals", 5, 4, ["definite-integral-definition", "continuity-properties"]),
    ("fundamental-calculus-theorem", "微积分基本定理", "definite-integrals", 6, 4, ["variable-upper-integral", "antiderivative"]),
    ("definite-substitution", "定积分换元法", "definite-integrals", 7, 4, ["fundamental-calculus-theorem", "substitution-first-kind"]),
    ("definite-parts", "定积分分部积分法", "definite-integrals", 8, 4, ["fundamental-calculus-theorem", "integration-by-parts"]),
    ("symmetry-periodicity-integrals", "对称性与周期性积分", "definite-integrals", 9, 4, ["definite-integral-properties", "function-properties"]),
    ("improper-infinite-interval", "无穷区间反常积分", "definite-integrals", 10, 4, ["definite-integral-definition", "function-limit"]),
    ("improper-unbounded-function", "无界函数反常积分", "definite-integrals", 11, 4, ["improper-infinite-interval", "discontinuity-classification"]),
    ("improper-convergence", "反常积分敛散性", "definite-integrals", 12, 5, ["improper-infinite-interval", "improper-unbounded-function"]),

    ("area-cartesian", "平面图形面积", "integral-applications", 1, 3, ["fundamental-calculus-theorem"]),
    ("area-parametric-polar", "参数方程与极坐标面积", "integral-applications", 2, 4, ["area-cartesian", "parametric-derivative"]),
    ("volume-slicing", "平行截面面积求体积", "integral-applications", 3, 3, ["area-cartesian"]),
    ("volume-revolution", "旋转体体积", "integral-applications", 4, 4, ["volume-slicing"]),
    ("arc-length", "平面曲线弧长", "integral-applications", 5, 4, ["fundamental-calculus-theorem", "parametric-derivative"]),
    ("surface-area-revolution", "旋转曲面面积", "integral-applications", 6, 5, ["arc-length", "volume-revolution"]),
    ("work-by-variable-force", "变力做功", "integral-applications", 7, 3, ["fundamental-calculus-theorem"]),
    ("fluid-force", "液体静压力", "integral-applications", 8, 4, ["work-by-variable-force", "area-cartesian"]),
    ("average-value-function", "函数平均值", "integral-applications", 9, 3, ["integral-mean-value"]),
    ("integral-application-modeling", "积分应用综合建模", "integral-applications", 10, 5, ["volume-revolution", "work-by-variable-force", "average-value-function"]),
]
