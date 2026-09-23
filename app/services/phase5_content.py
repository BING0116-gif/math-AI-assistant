"""Curated Phase 5 (version 3.0) golden lessons for chapters 3-6.

The prose is project-authored original Chinese teaching content. OpenStax is
recorded as a scope reference only, never copied; attribution stays in SQL via
the Phase 5 source document.
"""

GOLDEN_IMPORTANCE = 0.92

# OpenStax Calculus Volume 1 reference chapter per knowledge point code.
CHAPTER_REF = {
    "rolle-theorem": "第 4 章 Applications of Derivatives",
    "lagrange-mvt": "第 4 章 Applications of Derivatives",
    "lhopital-rule": "第 4 章 Applications of Derivatives",
    "function-graph-analysis": "第 4 章 Applications of Derivatives",
    "antiderivative": "第 5 章 Integration",
    "substitution-first-kind": "第 5 章 Integration",
    "integration-by-parts": "第 5 章 Integration",
    "definite-integral-definition": "第 5 章 Integration",
    "variable-upper-integral": "第 5 章 Integration",
    "fundamental-calculus-theorem": "第 5 章 Integration",
    "area-cartesian": "第 6 章 Applications of Integration",
    "volume-revolution": "第 6 章 Applications of Integration",
    "arc-length": "第 6 章 Applications of Integration",
}

GOLDEN = {
    "rolle-theorem": {
        "description": "通过端点等高与可导性条件，证明函数内部存在水平切线，并用于根的存在性论证。",
        "intuition": "一条光滑曲线若两端高度相同，中途要么全程平坦，要么先升后降（或先降后升），升降转折处必有一点的切线是水平的。罗尔定理把这一几何事实转化为可检验的条件与结论。",
        "definition": "设 $f$ 在闭区间 $[a,b]$ 上连续，在开区间 $(a,b)$ 内可导，且 $f(a)=f(b)$，则存在 $\\xi\\in(a,b)$ 使得 $f'(\\xi)=0$。三个条件缺一不可：端点不连续、内部不可导或端点值不相等时，结论都可能失效。",
        "formula": "$$f'(\\xi)=0,\\quad \\xi\\in(a,b)$$",
        "examples": [
            "例 1：验证 $f(x)=x^2-4x+3$ 在 $[1,3]$ 上满足罗尔定理。$f(1)=0=f(3)$，多项式处处连续可导；由 $f'(x)=2x-4=0$ 得 $\\xi=2\\in(1,3)$，与定理结论一致。",
            "例 2：$f(x)=|x|$ 在 $[-1,1]$ 上两端等高 $f(-1)=f(1)=1$，但它在 $x=0$ 不可导，不满足定理条件；事实上该函数在开区间内不存在水平切线，说明条件被破坏时结论未必成立。",
        ],
        "errors": "常见错误：①不验证 $f(a)=f(b)$ 就套用结论；②在分段点不可导的函数上使用；③把结论误解为导数处处为零。规范做法是先逐条核对连续、可导、端点等高三个条件，再解方程 $f'(x)=0$ 并确认根落在开区间内。",
        "checkpoint": "1. 写出罗尔定理的三个前提条件。\n2. $f(x)=x^3-3x$ 在 $[-\\sqrt3,\\sqrt3]$ 上是否满足罗尔定理？求出 $\\xi$。\n3. 举一个缺少可导性时结论失败的例子。",
    },
    "lagrange-mvt": {
        "description": "用割线斜率与切线斜率的关系给出函数增量与导数的精确等式，是导数应用与不等式证明的核心工具。",
        "intuition": "连接曲线上两点的割线总有一条平行于区间内某处的切线。把“平行”翻译成斜率相等，就得到函数在整个区间上的平均变化率等于某一点的瞬时变化率。",
        "definition": "设 $f$ 在 $[a,b]$ 上连续，在 $(a,b)$ 内可导，则存在 $\\xi\\in(a,b)$ 使得 $$f'(\\xi)=\\frac{f(b)-f(a)}{b-a}$$ 罗尔定理是它端点等高时的特例；该式也写作 $f(b)-f(a)=f'(\\xi)(b-a)$。",
        "formula": "$$f(b)-f(a)=f'(\\xi)(b-a),\\quad \\xi\\in(a,b)$$",
        "examples": [
            "例 1：$f(x)=x^3$ 在 $[0,1]$ 上，$\\frac{f(1)-f(0)}{1-0}=1=3\\xi^2$，解得 $\\xi=1/\\sqrt3\\approx0.577$，落在开区间内。",
            "例 2：证明 $|\\sin a-\\sin b|\\le|a-b|$。对 $\\sin x$ 在以 $a,b$ 为端点的区间用中值定理：$\\sin a-\\sin b=\\cos\\xi\\cdot(a-b)$，而 $|\\cos\\xi|\\le1$，不等式立得。",
        ],
        "errors": "常见错误：①把条件写成开区间连续、闭区间可导，方向颠倒；②认为 $\\xi$ 唯一——定理只保证存在，可能多个；③用中点值代替 $\\xi$ 检验。证明题中应设辅助函数（如 $F(x)=f(x)-\\frac{f(b)-f(a)}{b-a}x$）化归为罗尔定理。",
        "checkpoint": "1. 写出拉格朗日中值定理并说明它与罗尔定理的关系。\n2. 求 $f(x)=\\ln x$ 在 $[1,e]$ 上满足结论的 $\\xi$。\n3. 用中值定理证明当 $x>0$ 时 $\\frac{x}{1+x}<\\ln(1+x)<x$。",
    },
    "lhopital-rule": {
        "description": "在 $\\frac{0}{0}$ 或 $\\frac{\\infty}{\\infty}$ 型极限中对分子分母分别求导，把未定式化为可计算的极限。",
        "intuition": "当分子分母同时趋于零时，两者变化的“速度之比”决定比值极限。对分子分母分别求导正是提取各自变化率，因此导数之比常能揭示原比值的极限。",
        "definition": "设当 $x\\to a$ 时 $f(x)$ 与 $g(x)$ 同时趋于零或同时趋于无穷，且在 $a$ 附近 $g'(x)\\ne0$。若 $\\lim\\frac{f'(x)}{g'(x)}$ 存在（或为无穷），则 $$\\lim_{x\\to a}\\frac{f(x)}{g(x)}=\\lim_{x\\to a}\\frac{f'(x)}{g'(x)}$$ 每次使用后必须重新确认仍是未定式才能继续。",
        "formula": "$$\\lim\\frac{f(x)}{g(x)}=\\lim\\frac{f'(x)}{g'(x)}\\quad\\left(\\frac{0}{0}\\text{ 或 }\\frac{\\infty}{\\infty}\\right)$$",
        "examples": [
            "例 1：$\\lim_{x\\to0}\\frac{e^x-1}{x}$ 是 $\\frac{0}{0}$ 型，分子分母求导得 $\\lim_{x\\to0}\\frac{e^x}{1}=1$。",
            "例 2：$\\lim_{x\\to+\\infty}\\frac{\\ln x}{x}$ 是 $\\frac{\\infty}{\\infty}$ 型，求导得 $\\lim_{x\\to+\\infty}\\frac{1/x}{1}=0$，说明对数增长慢于幂函数增长。",
        ],
        "errors": "常见错误：①不是未定式也求导，例如 $\\lim_{x\\to0}\\frac{\\sin x+1}{x}$；②连续使用时不逐步检查类型；③$0\\cdot\\infty$、$\\infty-\\infty$ 等其他未定式未先恒等变形就套用；④导数比极限不存在时误以为原极限不存在（定理条件不满足只能说方法失效）。",
        "checkpoint": "1. 洛必达法则适用于哪两类未定式？\n2. 计算 $\\lim_{x\\to0}\\frac{x-\\sin x}{x^3}$。\n3. $\\lim_{x\\to\\infty}\\frac{x+\\sin x}{x}$ 能否用洛必达法则？应如何计算？",
    },
    "function-graph-analysis": {
        "description": "综合单调性、极值、凹凸性、拐点与渐近线，完整描绘函数图形，是导数工具的系统化应用。",
        "intuition": "函数图形由三类局部信息拼装而成：一阶导数告诉你在哪里升降、在哪里到达峰谷；二阶导数告诉你弯曲方向在哪里改变；趋于无穷远的行为则由渐近线概括。先列分析表，再画草图，不易遗漏。",
        "definition": "规范流程：①求定义域与奇偶性、周期性；②解 $f'(x)=0$ 与 $f''(x)=0$，标出不存在点；③用符号表确定单调区间、极值、凹凸区间与拐点；④求水平、铅直与斜渐近线；⑤补关键点连线成图。斜渐近线 $y=kx+b$ 中 $k=\\lim_{x\\to\\infty}f(x)/x$，$b=\\lim_{x\\to\\infty}[f(x)-kx]$。",
        "formula": "$$y=b\\text{（水平）},\\quad x=a\\text{（铅直）},\\quad y=kx+b\\text{（斜）}$$",
        "examples": [
            "例 1：$y=x^3-3x^2$。$y'=3x(x-2)$：在 $(-\\infty,0)$ 增、$(0,2)$ 减、$(2,+\\infty)$ 增，$x=0$ 极大值点、$x=2$ 极小值点；$y''=6x-6$：$x<1$ 凸、$x>1$ 凹，拐点 $(1,-2)$；无渐近线。",
            "例 2：$y=\\frac{1}{x^2-1}$。定义域 $x\\ne\\pm1$；令分母为零得铅直渐近线 $x=\\pm1$；$x\\to\\infty$ 时 $y\\to0$，水平渐近线 $y=0$；函数为偶函数，只需先分析 $x>1$ 一侧。",
        ],
        "errors": "常见错误：①漏查铅直渐近线（分母零点、无界点）；②把拐点当极值点，拐点是凹凸分界而非峰谷；③斜渐近线计算 $b$ 时忘记减去 $kx$；④草图不经过计算出的关键点，凭感觉画形。",
        "checkpoint": "1. 极值点与拐点的判据分别用什么导数？\n2. 求 $y=\\frac{x}{x^2-1}$ 的全部渐近线。\n3. 描绘 $y=e^{-x^2}$ 的图形需计算哪几类信息？",
    },
    "antiderivative": {
        "description": "把求导运算反过来看，用原函数族表达全部可能的原函数，是不定积分与定积分计算的基础。",
        "intuition": "已知一个函数的导数，反推这个函数本身：速度回到位置、斜率回到曲线。由于常数的导数为零，答案永远差一个任意常数 $C$，因此不定积分表示一族函数而不是单个函数。",
        "definition": "若在区间 $I$ 上恒有 $F'(x)=f(x)$，则称 $F$ 为 $f$ 在 $I$ 上的一个原函数，全体原函数写作不定积分 $\\int f(x)dx=F(x)+C$。连续函数必有原函数；同一函数的任意两个原函数只差一个常数。",
        "formula": "$$\\int x^\\alpha dx=\\frac{x^{\\alpha+1}}{\\alpha+1}+C\\;(\\alpha\\ne-1),\\quad\\int\\frac{dx}{x}=\\ln|x|+C$$\n$$\\int e^xdx=e^x+C,\\quad\\int\\cos xdx=\\sin x+C$$",
        "examples": [
            "例 1：$\\int x^2dx=\\frac{x^3}{3}+C$。验证方法是对结果求导：$(\\frac{x^3}{3}+C)'=x^2$，还原为被积函数。",
            "例 2：已知曲线在任一点处切线斜率为 $2x$，且过点 $(1,3)$，求曲线方程。设 $y=x^2+C$，代入 $3=1+C$ 得 $C=2$，故 $y=x^2+2$。初始条件从函数族中挑出一条确定曲线。",
        ],
        "errors": "常见错误：①结果漏写 $+C$；②把 $\\int\\frac{dx}{x}$ 写成 $\\ln x+C$ 而丢掉绝对值与负半轴；③验证意识缺失——求完后不回头求导检查；④误以为原函数一定有初等表达式（如 $e^{-x^2}$ 的原函数没有初等表示）。",
        "checkpoint": "1. 为什么原函数要加任意常数 $C$？\n2. 求 $\\int(3x^2-\\cos x)dx$。\n3. 已知 $f'(x)=\\cos x$ 且 $f(0)=1$，求 $f(x)$。",
    },
    "substitution-first-kind": {
        "description": "识别 $\\int f(g(x))g'(x)dx$ 结构并令 $u=g(x)$ 化简积分，即“凑微分法”，是使用频率最高的积分技巧。",
        "intuition": "复合函数的外层先积分，内层的导数恰好提供所需的微分因子。把 $g'(x)dx$ 凑成 $du$，积分就化归为关于 $u$ 的基本积分，最后把 $u$ 换回 $g(x)$。",
        "definition": "设 $f$ 连续，$g$ 可导且复合有意义，则 $$\\int f(g(x))g'(x)dx=\\int f(u)du\\Big|_{u=g(x)}=F(g(x))+C$$ 操作要点：凑出 $g'(x)dx=du$、对 $u$ 积分、结果回代为 $x$ 的表达式。",
        "formula": "$$\\int f(g(x))g'(x)dx=\\left[\\int f(u)du\\right]_{u=g(x)}$$",
        "examples": [
            "例 1：$\\int 2x\\cos(x^2)dx$。令 $u=x^2$，则 $du=2x\\,dx$，积分化为 $\\int\\cos u\\,du=\\sin u+C=\\sin(x^2)+C$。",
            "例 2：$\\int\\tan x\\,dx=\\int\\frac{\\sin x}{\\cos x}dx$。令 $u=\\cos x$，$du=-\\sin x\\,dx$，得 $-\\int\\frac{du}{u}=-\\ln|u|+C=-\\ln|\\cos x|+C$。",
        ],
        "errors": "常见错误：①凑微分时系数补错，如把 $dx$ 凑成 $d(2x)$ 却不除以 2；②积分完成后忘记回代 $u$；③内层导数与被积因子只差常数倍时误判不可用——常倍数可以调节，含 $x$ 的因子不行。",
        "checkpoint": "1. $\\int x e^{x^2}dx$ 应令 $u$ 等于什么？\n2. 计算 $\\int\\frac{\\ln x}{x}dx$（$x>0$）。\n3. 说明为什么 $\\int x e^{x^2}dx$ 可用凑微分而 $\\int x^2 e^{x^2}dx$ 不能直接用。",
    },
    "integration-by-parts": {
        "description": "由乘积求导法则反转得到的积分法，处理“两类不同函数乘积”的积分，关键是按‘反对幂三指’选 $u$。",
        "intuition": "乘积求导法则 $(uv)'=u'v+uv'$ 移项积分就得到分部积分。它把难处理的 $\\int u\\,dv$ 换成较易的 $\\int v\\,du$，本质是转移求导负担：让 $u$ 求导变简单，让 $dv$ 积分可行。",
        "definition": "设 $u=u(x)$、$v=v(x)$ 有连续导数，则 $$\\int u\\,dv=uv-\\int v\\,du$$ 选 $u$ 的经验顺序是‘反三角、对数、幂、三角、指数’：排在前的作 $u$ 留下来求导，排在后的进入 $dv$ 先积分。",
        "formula": "$$\\int u\\,dv=uv-\\int v\\,du$$",
        "examples": [
            "例 1：$\\int xe^xdx$。取 $u=x$、$dv=e^xdx$，则 $du=dx$、$v=e^x$，得 $xe^x-\\int e^xdx=xe^x-e^x+C$。",
            "例 2：$\\int\\ln x\\,dx$。取 $u=\\ln x$、$dv=dx$，则 $du=\\frac{dx}{x}$、$v=x$，得 $x\\ln x-\\int x\\cdot\\frac{dx}{x}=x\\ln x-x+C$。",
        ],
        "errors": "常见错误：①$u$ 与 $dv$ 选反导致越积越复杂甚至循环回原积分；②连续两次分部时第二次换了 $u$ 的类型，绕回原式；③丢掉负号或积分常数。规范做法是同一题中保持 $u$ 的类型选择前后一致。",
        "checkpoint": "1. 分部积分公式由哪条求导法则推出？\n2. $\\int x\\cos xdx$ 应如何选 $u$ 与 $dv$？\n3. 计算 $\\int x\\ln x\\,dx$。",
    },
    "definite-integral-definition": {
        "description": "用分割、近似、求和、取极限四步定义定积分，刻画曲边梯形面积与连续累积量。",
        "intuition": "求曲边下的面积时，先把区间切成许多小段，每小段用细矩形近似；分割越细，矩形面积之和越贴近真实面积。当最长小区间长度趋于零时，和式的极限就是定积分。",
        "definition": "设 $f$ 在 $[a,b]$ 上有界。任取分割 $a=x_0<x_1<\\cdots<x_n=b$ 与样本点 $\\xi_i\\in[x_{i-1},x_i]$，记 $\\lambda=\\max\\Delta x_i$。若极限 $$\\lim_{\\lambda\\to0}\\sum_{i=1}^n f(\\xi_i)\\Delta x_i$$ 存在且与分割、样本点取法无关，则称 $f$ 在 $[a,b]$ 上可积，极限值记作 $\\int_a^bf(x)dx$。闭区间上的连续函数必可积；单调有界函数也可积。",
        "formula": "$$\\int_a^bf(x)dx=\\lim_{\\lambda\\to0}\\sum_{i=1}^n f(\\xi_i)\\Delta x_i$$",
        "examples": [
            "例 1：用定义求 $\\int_0^1x^2dx$。取等分分割并取 $\\xi_i=\\frac{i}{n}$，和式为 $\\sum\\frac{i^2}{n^2}\\cdot\\frac{1}{n}=\\frac{n(n+1)(2n+1)}{6n^3}\\to\\frac13$。",
            "例 2：由几何意义求 $\\int_0^R\\sqrt{R^2-x^2}dx$。被积函数是上半圆，积分区间恰为四分之一圆，故积分值为 $\\frac{\\pi R^2}{4}$。",
        ],
        "errors": "常见错误：①把定积分结果再加 $C$——定积分是数，不是函数族；②交换积分限时忘记变号：$\\int_b^a=-\\int_a^b$；③以为有界必可积——在闭区间上有无穷多个间断点的有界函数可能不可积；④把 $\\lambda\\to0$ 误写成 $n\\to\\infty$ 而不保证等分。",
        "checkpoint": "1. 写出定积分定义的四步。\n2. $\\int_a^af(x)dx$ 等于多少？为什么？\n3. 用几何意义求 $\\int_{-1}^1\\sqrt{1-x^2}dx$。",
    },
    "variable-upper-integral": {
        "description": "把积分上限看成变量得到的新函数必定可导，揭示了积分与求导的互逆关系，是微积分基本定理的引理。",
        "intuition": "固定下限、让上限移动，面积就成为一个关于上限的函数。上限推进一小段时新增面积约为“高乘宽”，高度正是被积函数在该处的值，因此这个面积函数的变化率就是被积函数本身。",
        "definition": "设 $f$ 在 $[a,b]$ 上连续，定义变上限积分 $\\Phi(x)=\\int_a^xf(t)dt$。则 $\\Phi$ 在 $[a,b]$ 上可导，且 $$\\Phi'(x)=\\frac{d}{dx}\\int_a^xf(t)dt=f(x)$$ 这说明连续函数必有原函数，$\\Phi$ 就是其中一个。",
        "formula": "$$\\frac{d}{dx}\\int_a^xf(t)dt=f(x),\\quad \\frac{d}{dx}\\int_a^{\\varphi(x)}f(t)dt=f(\\varphi(x))\\varphi'(x)$$",
        "examples": [
            "例 1：$\\frac{d}{dx}\\int_0^x\\sin(t^2)dt=\\sin(x^2)$，尽管 $\\sin(t^2)$ 的原函数没有初等表达式，求导公式依然适用。",
            "例 2：求 $\\lim_{x\\to0}\\frac{\\int_0^xe^{t^2}dt}{x}$。这是 $\\frac{0}{0}$ 型，分子导数为 $e^{x^2}$，由洛必达法则极限为 $\\lim_{x\\to0}e^{x^2}=1$。",
        ],
        "errors": "常见错误：①被积函数的哑变量 $t$ 与上限变量 $x$ 混用，写成 $\\int_a^xf(x)dx$；②上限是复合函数 $\\varphi(x)$ 时忘记乘 $\\varphi'(x)$；③公式要求被积函数连续却被用于含瑕点的积分；④上下限都是变量时不会拆成两个变上限积分之差。",
        "checkpoint": "1. 求 $\\frac{d}{dx}\\int_1^{x^2}\\frac{dt}{1+t}$。\n2. 变上限积分为何能证明‘连续函数必有原函数’？\n3. 求 $\\lim_{x\\to0}\\frac{\\int_0^x\\cos t\\,dt}{x}$。",
    },
    "fundamental-calculus-theorem": {
        "description": "牛顿-莱布尼茨公式把定积分计算化为先求原函数再代上下限，是连接微分学与积分学的桥梁。",
        "intuition": "一段区间上变化率的累积正好等于净变化量：速度对时间积分得到位移，而位移就是位置函数在两端点值之差。于是求定积分不再需要极限和式，只需求一个原函数并相减。",
        "definition": "设 $f$ 在 $[a,b]$ 上连续，$F$ 是 $f$ 在 $[a,b]$ 上的任意一个原函数，则 $$\\int_a^bf(x)dx=F(b)-F(a)$$ 计算时 $+C$ 会被相减抵消，故可省略；结果是一个确定的数。",
        "formula": "$$\\int_a^bf(x)dx=F(b)-F(a)=\\Big[F(x)\\Big]_a^b$$",
        "examples": [
            "例 1：$\\int_0^1x^2dx=\\Big[\\frac{x^3}{3}\\Big]_0^1=\\frac13$，与用定义求和取极限的结果一致，但计算量大幅减少。",
            "例 2：$\\int_0^{\\pi/2}\\cos x\\,dx=\\Big[\\sin x\\Big]_0^{\\pi/2}=1-0=1$。",
        ],
        "errors": "常见错误：①$F$ 必须在包含 $[a,b]$ 的整个区间上是原函数——被积函数有瑕点（如 $\\int_{-1}^1\\frac{dx}{x^2}$）时直接套用会得到错误负值，应按反常积分处理；②把 $F(b)-F(a)$ 的顺序算反；③与不定积分混淆又给结果加上 $C$。",
        "checkpoint": "1. 用牛顿-莱布尼茨公式计算 $\\int_1^2\\frac{dx}{x}$。\n2. 为什么使用公式时原函数中的常数 $C$ 可以省略？\n3. 指出 $\\int_{-1}^1\\frac{dx}{x^2}=\\left[-\\frac{1}{x}\\right]_{-1}^1=-2$ 的错误原因。",
    },
    "area-cartesian": {
        "description": "用定积分表示并计算两条曲线围成区域的面积，核心是定出交点、判断上下（或左右）曲线。",
        "intuition": "把区域竖切成细条，每条细条的高约等于上方曲线值减下方曲线值；把所有细条面积累加即得区域面积。若竖切不便（右曲线减左曲线更简单），可改为对 $y$ 积分。",
        "definition": "设在 $[a,b]$ 上 $f(x)\\ge g(x)$，则两曲线与直线 $x=a$、$x=b$ 围成的面积为 $$S=\\int_a^b[f(x)-g(x)]dx$$ 若上下关系在区间内发生交换，必须以交点为界分段积分再求和；必要时改用 $S=\\int_c^d[\\text{右}(y)-\\text{左}(y)]dy$。",
        "formula": "$$S=\\int_a^b[f(x)-g(x)]dx$$",
        "examples": [
            "例 1：求 $y=2x$ 与 $y=x^2$ 围成的面积。交点满足 $2x=x^2$，得 $x=0,2$；在 $(0,2)$ 内 $2x\\ge x^2$，故 $S=\\int_0^2(2x-x^2)dx=\\Big[x^2-\\frac{x^3}{3}\\Big]_0^2=\\frac43$。",
            "例 2：求 $y^2=2x$ 与 $y=x-4$ 围成的面积。抛物线开口向右，改用对 $y$ 积分：交点由 $\\frac{y^2}{2}=y+4$ 解得 $y=-2,4$；右曲线为 $y+4$、左曲线为 $\\frac{y^2}{2}$，$S=\\int_{-2}^4\\left(y+4-\\frac{y^2}{2}\\right)dy=18$。",
        ],
        "errors": "常见错误：①不求交点就盲目积分，区间错误；②上下（左右）曲线判反得到负值后直接取绝对数掩盖错误——应先判大小关系再积分；③上下关系交换的区域不分段处理；④对开口向右的抛物线仍坚持对 $x$ 积分，把问题复杂化。",
        "checkpoint": "1. 求 $y=x^2$ 与 $y=x$ 围成的面积。\n2. 什么时候应选择对 $y$ 积分？\n3. 若在区间内两曲线交叉一次，面积应如何计算？",
    },
    "volume-revolution": {
        "description": "用圆盘法、垫圈法与柱壳法计算平面区域绕轴旋转所成旋转体的体积。",
        "intuition": "把旋转体垂直于轴切成薄片，每片近似为圆盘（实心）或垫圈（空心）：体积等于截面积乘厚度，累加即得积分。圆盘半径或垫圈内外半径由边界曲线到旋转轴的距离决定。",
        "definition": "区域由 $y=f(x)\\ge0$、$x$ 轴与 $x=a,b$ 围成。绕 $x$ 轴旋转用圆盘法 $$V=\\pi\\int_a^b f^2(x)dx$$ 若区域介于两条曲线 $y=f$（上）与 $y=g$（下）之间，绕 $x$ 轴旋转用垫圈法 $$V=\\pi\\int_a^b\\left(f^2(x)-g^2(x)\\right)dx$$ 绕 $y$ 轴旋转常用柱壳法 $V=2\\pi\\int_a^bx\\,f(x)dx$。",
        "formula": "$$V_{disk}=\\pi\\int_a^bf^2(x)dx,\\quad V_{shell}=2\\pi\\int_a^bx\\,f(x)dx$$",
        "examples": [
            "例 1：$y=\\sqrt x$、$x$ 轴与 $x=4$ 围成区域绕 $x$ 轴旋转。圆盘法：$V=\\pi\\int_0^4x\\,dx=8\\pi$。",
            "例 2：$y=x^2$ 与 $y=x$ 围成区域绕 $x$ 轴旋转。垫圈法：外半径 $R=x$、内半径 $r=x^2$，$V=\\pi\\int_0^1(x^2-x^4)dx=\\pi\\left(\\frac13-\\frac15\\right)=\\frac{2\\pi}{15}$。",
        ],
        "errors": "常见错误：①把函数值当半径——绕 $x$ 轴时半径是 $|y|$，绕 $y=1$ 等其他水平轴时半径是 $|f(x)-1|$；②垫圈法忘记平方内外半径再相减；③绕 $y$ 轴时圆盘法与柱壳法的半径来源混淆；④旋转轴穿过多区域时未分段。",
        "checkpoint": "1. 写出圆盘法与柱壳法的体积公式并说明各自适用情形。\n2. $y=x^2$、$y=0$、$x=1$ 围成区域绕 $x$ 轴旋转，体积是多少？\n3. 同一区域改绕 $y$ 轴旋转，用柱壳法列式。",
    },
    "arc-length": {
        "description": "用“以直代曲”的极限思想计算曲线弧长，掌握直角坐标与参数方程两种公式。",
        "intuition": "把曲线切成许多小段，每段用连接端点的直线段近似；由勾股定理，小段长度约为 $\\sqrt{(dx)^2+(dy)^2}$。分割无限加细时，直线段长度之和的极限就是弧长。",
        "definition": "设曲线 $y=f(x)$ 在 $[a,b]$ 上有连续导数，则弧长 $$s=\\int_a^b\\sqrt{1+f'^2(x)}\\,dx$$ 若曲线由参数方程 $x=x(t)$、$y=y(t)$（$t\\in[\\alpha,\\beta]$）给出且导数连续，则 $$s=\\int_\\alpha^\\beta\\sqrt{x'^2(t)+y'^2(t)}\\,dt$$",
        "formula": "$$s=\\int_a^b\\sqrt{1+y'^2}\\,dx,\\quad s=\\int_\\alpha^\\beta\\sqrt{x'^2+y'^2}\\,dt$$",
        "examples": [
            "例 1：求 $y=\\frac23x^{3/2}$ 在 $[0,3]$ 上的弧长。$y'=x^{1/2}$，$s=\\int_0^3\\sqrt{1+x}\\,dx=\\Big[\\frac23(1+x)^{3/2}\\Big]_0^3=\\frac23(8-1)=\\frac{14}{3}$。",
            "例 2：验证半径为 $R$ 的圆周长。取 $x=R\\cos t$、$y=R\\sin t$（$t\\in[0,2\\pi]$），$s=\\int_0^{2\\pi}\\sqrt{R^2\\sin^2t+R^2\\cos^2t}\\,dt=\\int_0^{2\\pi}R\\,dt=2\\pi R$，与已知周长一致。",
        ],
        "errors": "常见错误：①直角坐标公式忘记根号内的 $+1$；②参数方程下仍对 $x$ 积分或忘记平方和开根；③被积函数无初等原函数时（如 $y=x^2$ 的一般弧长出现 $\\sqrt{1+4x^2}$ 可积但更复杂的情形）应意识到可数值积分；④极坐标弧长直接套用直角坐标公式。",
        "checkpoint": "1. 写出直角坐标与参数方程的弧长公式。\n2. 求 $y=\\frac{x^2}{2}$ 在 $[0,1]$ 上的弧长被积表达式。\n3. 参数方程的积分变量是什么？上下限由什么决定？",
    },
}


def phase5_resources_for(code: str) -> list[tuple[str, str, str]]:
    item = GOLDEN[code]
    ref = CHAPTER_REF[code]
    rows = [
        ("intuition", "一句话直觉", item["intuition"]),
        ("definition", "定义与适用条件", item["definition"]),
        ("formula", "核心公式", item["formula"]),
        ("worked_example", "基础例题", item["examples"][0]),
        ("worked_example", "迁移例题", item["examples"][1]),
        ("common_error", "常见错误与反例", item["errors"]),
        ("checkpoint", "理解检查", item["checkpoint"]),
        ("exercise_set", "正式分层练习", "进入正式题库完成基础、常规与进阶练习；题目按当前知识点稳定 code 关联，作答证据由正式练习管道记录。"),
        ("summary", "小结与下一步", "先核对定理或方法的适用条件，再按规范步骤计算，并检查结果的方向、量纲与定义域。完成检查题后进入正式练习；错误集中在前置环节时，返回图谱复习直接前置知识点。"),
        ("source_reference", "来源与署名", f"项目原创中文教学内容；概念范围参考 OpenStax Calculus Volume 1 {ref}。未复制原文，使用时保留来源与许可证记录。"),
    ]
    return rows
