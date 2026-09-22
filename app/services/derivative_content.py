"""Curated Phase 3 derivative taxonomy and original Chinese golden lessons.

The prose is project-authored. OpenStax is recorded as a reference, not copied
or AI-ingested; its attribution and current licence are retained in SQL.
"""

DERIVATIVE_POINTS = [
    ("derivative-definition", "导数定义", 1, 3, ["function-limit", "continuity-definition"]),
    ("derivative-existence", "可导性与连续性的关系", 2, 3, ["derivative-definition"]),
    ("one-sided-derivative", "单侧导数", 3, 3, ["left-right-limit", "derivative-definition"]),
    ("derivative-geometric-meaning", "导数的几何意义", 4, 2, ["derivative-definition"]),
    ("derivative-physical-meaning", "导数的物理意义", 5, 2, ["derivative-definition"]),
    ("derivative-function", "导函数与导数记号", 6, 2, ["derivative-definition"]),
    ("constant-power-rules", "常数与幂函数求导", 7, 2, ["derivative-function"]),
    ("trigonometric-derivatives", "三角函数求导", 8, 3, ["important-limits", "derivative-function"]),
    ("exponential-log-derivatives", "指数与对数函数求导", 9, 3, ["derivative-function"]),
    ("sum-difference-rule", "和差求导法则", 10, 2, ["constant-power-rules"]),
    ("product-rule", "乘积求导法则", 11, 3, ["sum-difference-rule"]),
    ("quotient-rule", "商求导法则", 12, 3, ["product-rule"]),
    ("chain-rule", "复合函数与链式法则", 13, 4, ["composite-function", "constant-power-rules"]),
    ("inverse-function-derivative", "反函数求导", 14, 4, ["inverse-function", "chain-rule"]),
    ("implicit-differentiation", "隐函数求导", 15, 4, ["chain-rule", "product-rule"]),
    ("logarithmic-differentiation", "对数求导法", 16, 4, ["exponential-log-derivatives", "implicit-differentiation"]),
    ("parametric-derivative", "参数方程求导", 17, 4, ["chain-rule"]),
    ("higher-order-derivatives", "高阶导数", 18, 3, ["sum-difference-rule", "product-rule"]),
    ("differential-definition", "微分定义", 19, 3, ["derivative-definition"]),
    ("linear-approximation", "线性近似", 20, 3, ["differential-definition", "derivative-geometric-meaning"]),
    ("differential-rules", "微分运算法则", 21, 3, ["differential-definition", "chain-rule"]),
    ("derivative-section-review", "导数与微分综合", 22, 4, ["implicit-differentiation", "higher-order-derivatives", "differential-rules"]),
]

GOLDEN = {
    "derivative-definition": {
        "intuition": "导数研究的是函数在一个点附近的瞬时变化。先取两个很近的点，割线斜率表示平均变化率；让第二个点不断靠近第一个点，若割线斜率趋于唯一有限值，这个极限就是该点的导数。关键不是把增量直接取成零，而是考察非零增量趋近于零时比值的极限。",
        "definition": "设函数 $f$ 在点 $x_0$ 的某邻域内有定义。若极限 $$\\lim_{h\\to0}\\frac{f(x_0+h)-f(x_0)}{h}$$ 存在且有限，则称 $f$ 在 $x_0$ 可导，极限记作 $f'(x_0)$。等价地，也可写成 $\\lim_{x\\to x_0}\\frac{f(x)-f(x_0)}{x-x_0}$。可导必连续，但连续不一定可导。",
        "formula": "$$f'(x_0)=\\lim_{h\\to0}\\frac{f(x_0+h)-f(x_0)}{h}$$\n$$f'(x)=\\lim_{h\\to0}\\frac{f(x+h)-f(x)}{h}$$",
        "examples": [
            "例 1：由定义求 $f(x)=x^2$ 在 $x_0=3$ 的导数。差商为 $[(3+h)^2-9]/h=6+h$，令 $h\\to0$ 得 $f'(3)=6$。注意约去 $h$ 的步骤只在 $h\\ne0$ 时进行。",
            "例 2：判断 $f(x)=|x|$ 在 0 处是否可导。$h>0$ 时差商为 1，$h<0$ 时差商为 -1；左右极限不同，所以导数不存在，尽管函数在 0 处连续。",
        ],
        "errors": "常见错误：①把 $h=0$ 直接代入差商，得到无意义的 $0/0$；②只算右极限便断言可导；③把连续当作可导。修正方法是明确写出 $h\\ne0$ 的化简过程，并分别检查可能不同的左右差商极限。",
        "checkpoint": "1. 用定义求 $f(x)=3x-2$ 在任一点的导数。\n2. 若左右导数分别为 2 和 2，函数值却与极限不同，能否可导？为什么？\n3. 写出以 $x\\to x_0$ 表示的等价定义。",
    },
    "derivative-geometric-meaning": {
        "intuition": "把曲线上一点 $P$ 与邻近点 $Q$ 连成割线。当 $Q$ 沿曲线趋近 $P$ 时，割线若趋向一条确定直线，这条直线就是切线；其斜率就是导数。导数的正负描述曲线局部上升或下降，绝对值描述倾斜程度。",
        "definition": "若 $f'(x_0)$ 存在，则曲线 $y=f(x)$ 在 $P(x_0,f(x_0))$ 处的非竖直切线斜率为 $f'(x_0)$，切线方程为 $y-f(x_0)=f'(x_0)(x-x_0)$。法线在 $f'(x_0)\\ne0$ 时斜率为 $-1/f'(x_0)$。",
        "formula": "$$y-f(x_0)=f'(x_0)(x-x_0)$$\n$$m_{normal}=-\\frac{1}{f'(x_0)}\\quad(f'(x_0)\\ne0)$$",
        "examples": [
            "例 1：$y=x^2$ 在 $x=1$ 处，$f'(1)=2$，点为 $(1,1)$，故切线为 $y-1=2(x-1)$，即 $y=2x-1$。",
            "例 2：$y=\\sqrt{x}$ 在 $x=4$ 处导数为 $1/4$，切线为 $y-2=(x-4)/4$。用 $x=4.1$ 得线性估计 $\\sqrt{4.1}\\approx2.025$。",
        ],
        "errors": "常见错误：①把点的纵坐标误写成 $x_0$；②把 $f'(x_0)$ 当作切线本身；③忽略切线公式需要同时使用点和斜率。图像看似有切线并不能替代极限存在性的判断。",
        "checkpoint": "1. 求 $y=x^3$ 在 $(1,1)$ 处切线。\n2. $f'(2)=0$ 表示切线有什么特征？\n3. 导数不存在时是否一定没有任何几何切线？说明竖直切线这一例外。",
    },
    "constant-power-rules": {
        "intuition": "基本求导公式是后续运算法则的字母表。常数没有变化，所以导数为零；幂函数的指数会移到系数位置并减一。公式必须连同定义域一起记忆，尤其是分数幂与负幂。",
        "definition": "对常数 $C$，有 $(C)'=0$。在表达式有定义且导数存在的区间内，幂函数满足 $(x^\\alpha)'=\\alpha x^{\\alpha-1}$。指数、对数和三角函数的公式应按其定义域使用。",
        "formula": "$$(C)'=0,\\quad(x^\\alpha)'=\\alpha x^{\\alpha-1}$$\n$$(e^x)'=e^x,\\quad(a^x)'=a^x\\ln a$$\n$$(\\ln x)'=1/x,\\quad(\\sin x)'=\\cos x,\\quad(\\cos x)'=-\\sin x$$",
        "examples": [
            "例 1：$f(x)=4x^5-3x^{-2}+7$，逐项求导得 $f'(x)=20x^4+6x^{-3}$，定义域仍要求 $x\\ne0$。",
            "例 2：$g(x)=\\sqrt{x}+\\ln x$，在 $x>0$ 上有 $g'(x)=1/(2\\sqrt{x})+1/x$；不能把该式延伸到 $x=0$。",
        ],
        "errors": "常见错误：①常数项求成 1；②指数减一却忘记乘原指数；③漏掉 $(\\cos x)'$ 的负号；④只写公式不检查定义域。建议每次求导后用量纲、符号或简单点值做快速核验。",
        "checkpoint": "1. 求 $x^{3/2}$ 的导数并写明实数定义域。\n2. 求 $2^x+\\cos x$ 的导数。\n3. 为什么 $x^{-1}$ 的导数不能在 $x=0$ 使用？",
    },
    "chain-rule": {
        "intuition": "复合函数经历多层变化：外层对中间变量变化，中间变量再随 $x$ 变化。总变化率等于各层局部变化率相乘。识别‘外层—内层’比死记展开更可靠。",
        "definition": "若 $u=g(x)$ 在 $x$ 可导，$y=f(u)$ 在 $u=g(x)$ 可导，则复合函数 $f(g(x))$ 可导，且 $[f(g(x))]'=f'(g(x))g'(x)$。和差逐项求导；乘积用 $(uv)'=u'v+uv'$；商在 $v\\ne0$ 时用 $(u/v)'=(u'v-uv')/v^2$。",
        "formula": "$$[f(g(x))]'=f'(g(x))g'(x)$$\n$$(uv)'=u'v+uv',\\quad\\left(\\frac uv\\right)'=\\frac{u'v-uv'}{v^2}$$",
        "examples": [
            "例 1：$y=(3x^2+1)^5$。外层为 $u^5$，内层为 $u=3x^2+1$，所以 $y'=5(3x^2+1)^4\\cdot6x=30x(3x^2+1)^4$。",
            "例 2：$y=x^2\\sin(1/x)$（$x\\ne0$）。乘积法则与链式法则共同给出 $y'=2x\\sin(1/x)-\\cos(1/x)$。",
        ],
        "errors": "常见错误：①只求外层导数，漏乘内层导数；②把乘积导数错写为 $u'v'$；③商法则分子次序颠倒；④多层复合只处理一层。可在草稿中逐层设元，并从最外层向内连乘。",
        "checkpoint": "1. 求 $\\sin(x^2)$ 的导数。\n2. 求 $(x+1)e^x$ 的导数。\n3. 求 $\\ln(1+x^2)$ 的导数，并指出用了几层规则。",
    },
    "implicit-differentiation": {
        "intuition": "隐式方程没有把 $y$ 单独写成 $x$ 的函数，但沿曲线运动时 $y$ 仍随 $x$ 改变。对等式两边关于 $x$ 求导，并把 $y$ 看成 $y(x)$；凡是含 $y$ 的项都要带出 $y'$。",
        "definition": "若方程 $F(x,y)=0$ 在点附近确定可导函数 $y(x)$，且 $F_y\\ne0$，则对等式求导有 $F_x+F_y y'=0$，因此 $y'=-F_x/F_y$。实际计算可直接逐项求导后收集 $y'$。",
        "formula": "$$F(x,y)=0\\Rightarrow F_x+F_y y'=0$$\n$$y'=-\\frac{F_x}{F_y}\\quad(F_y\\ne0)$$",
        "examples": [
            "例 1：圆 $x^2+y^2=25$。求导得 $2x+2yy'=0$，故 $y'=-x/y$。在点 $(3,4)$ 处斜率为 $-3/4$。",
            "例 2：$x^2y+y^3=2$。求导得 $2xy+x^2y'+3y^2y'=0$，收集后 $y'=-2xy/(x^2+3y^2)$。",
        ],
        "errors": "常见错误：①把 $(y^2)'$ 写成 $2y$ 而漏掉 $y'$；②乘积 $x^2y$ 只求一项；③得到 $y'$ 后忽略分母为零的点；④未确认所求点满足原方程。",
        "checkpoint": "1. 对 $xy=1$ 求 $y'$。\n2. 对 $\\sin y=x$ 求 $y'$。\n3. 在什么条件下公式 $-F_x/F_y$ 不能直接使用？",
    },
}


def resources_for(code: str) -> list[tuple[str, str, str]]:
    item = GOLDEN[code]
    rows = [
        ("intuition", "一句话直觉", item["intuition"]),
        ("definition", "定义与适用条件", item["definition"]),
        ("formula", "核心公式", item["formula"]),
        ("worked_example", "基础例题", item["examples"][0]),
        ("worked_example", "迁移例题", item["examples"][1]),
        ("common_error", "常见错误与反例", item["errors"]),
        ("checkpoint", "理解检查", item["checkpoint"]),
        ("exercise_set", "正式分层练习", "进入正式题库完成基础、常规与进阶练习；题目按当前知识点稳定 code 关联，作答证据由正式练习管道记录。"),
        ("summary", "小结与下一步", "先说明所用定义或法则，再完成代数化简并检查定义域。完成检查题后进入正式练习；若错误集中在前置步骤，返回图谱复习直接前置知识点。"),
        ("source_reference", "来源与署名", "项目原创中文教学内容；概念范围参考 OpenStax Calculus Volume 1 第 3 章。未复制原文，使用时保留来源与许可证记录。"),
    ]
    return rows
