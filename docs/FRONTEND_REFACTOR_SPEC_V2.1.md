# 知微 Math AI 前端重构产品与设计规格 V2.1

> 文档用途：直接交付 Trae Work 或其他开发 Agent 执行。  
> 文档类型：前端重构 PRD + UX/UI 设计规范 + 学习证据/教学策略 + 技术实施约束。  
> 日期：2026-08-10。  
> 当前技术基线：Vue 3、Vite、Pinia、Vue Router、Element Plus、KaTeX、Three.js、FastAPI。  
> 核心原则：所有页面和画像结论必须符合真实数学教学流程，并能由系统实际采集的数据支持。  
> 开源参考：OpenHuman（记忆可视化与可追溯记忆交互）和 Chatbox（聊天工作台、会话管理与响应式侧栏）。只借鉴交互原则与信息架构，不直接复制其品牌、代码、CSS 或资产。

---

## 0. 给开发 Agent 的执行摘要

本次任务不是在现有页面上继续换颜色、加渐变或调整圆角，而是重新建立产品信息架构和核心界面。开发时必须遵循以下冻结决策：

1. 首页对话框下方现有六个功能卡全部删除，不得以另一种卡片形式恢复。
2. 首页与空白对话页合并。首页的唯一主任务是让用户开始或继续一次数学学习对话。
3. AI 回答采用无大气泡的内容流排版，用户消息使用克制的小气泡。
4. 一级导航固定为：新对话、对话历史、记忆画像、知识地图、错题复盘。
5. “课程目录”合并进知识地图，不继续占据独立一级入口。
6. 新增“记忆画像”页面，但只展示能够由数字交互证据支撑的学习画像。
7. 不展示或推断“解题风格”“认知风格”“专注程度”“学习态度”“纸上书写过程”等系统无法可靠观察的属性。
8. 画像中的每项结论必须显示证据数量、数据来源、更新时间和置信状态。
9. 默认知识/画像图谱使用 2D 交互图，不把现有 Three.js 星系作为默认操作界面。
10. 保留 Vue 3，渐进迁移 TypeScript；不进行 React 全量重写。
11. 优先复用现有后端能力，不在前端伪造画像数据。
12. 第一阶段必须先完成 App Shell、首页和对话页，画像页随后接入真实接口。
13. OpenHuman 与 Chatbox 只作为“参考实现来源”，Trae Work 必须先阅读其当前开源实现，再用 Vue 3 原生重建对应交互，不允许把 React 组件硬迁移到本项目。
14. Chatbox 主要参考稳定聊天工作台模式：会话搜索、历史列表、桌面持久侧栏、移动端临时抽屉、轻量会话管理；不引入其模型供应商、图片生成等与数学学习无关的产品结构。
15. OpenHuman 主要参考记忆工作区模式：搜索/筛选导航、活动热力图、图谱/树、结果列表、证据详情与可纠正性；必须改写为“数学学习证据”的教育语义。
16. V2.1 默认继续使用 Cytoscape.js 构建 2D 知识/画像图，不移植 OpenHuman 的 Pixi.js + d3-force 技术栈；只有真实性能基准证明 Cytoscape.js 不满足目标规模时，才单独评估 WebGL 方案。
17. Phase 3 开始前必须冻结 Learning Evidence Model、Mastery Model V1、Tutoring Policy 和 Learning Event Schema，不允许边做画像页面边临时发明业务语义。
18. XSS、上传安全、消息幂等、全局错误边界、历史数据迁移属于本轮重构的 P0 工程要求。
19. OpenHuman 与 Chatbox 当前仓库均采用 GPL-3.0；在未完成许可证兼容性评估前，禁止直接复制其源码、样式文件、图标、图片和品牌资源。本文要求的是独立实现交互思想，不是代码复用。

任何与上述决策冲突的旧设计稿、旧 PRD 或旧组件实现，以本文档为准。

---

## 1. 产品概述

### 1.1 产品定位

知微不是一个展示六种 AI 工具的通用聊天网站，而是一个围绕数学学习闭环工作的 AI 学习助手：

```text
提出问题 / 上传题目
        ↓
AI 讲解与追问
        ↓
关联知识点与课程位置
        ↓
练习、作答或记录错题
        ↓
更新可验证的知识掌握状态
        ↓
推荐下一步学习或复习任务
```

产品的视觉目标是“专业、克制、耐读、可信”，交互目标是“用户随时知道下一步可以做什么”，差异化能力是“可追溯的个人数学学习画像”。

### 1.2 目标用户

- 以大学基础数学为主要学习范围的学生。
- 使用电脑或手机上传题目、阅读讲解、复习错题的自主学习者。
- 需要通过知识点掌握状态规划学习，而不是只进行一次性问答的用户。

### 1.3 当前问题

1. 首页由欢迎区、输入框、六个功能卡拼接而成，视觉重心分散。
2. 六个功能卡中的多数能力实际都通向对话页，属于重复入口。
3. 对话页具有传统管理后台和聊天气泡感，长数学推导的阅读体验差。
4. 多套颜色、圆角、阴影、渐变和组件风格同时存在，缺少统一产品气质。
5. 现有知识图谱偏展示，没有成为“定位薄弱点—开始学习—完成练习”的操作工具。
6. 后端已有画像、技能、记忆和错题能力，但前端没有形成清晰、可信的解释界面。
7. 现有 `/api/profile/{user_id}/skills` 返回 `cognitive_style`，但当前交互无法可靠判断纸上解题思路，因此该字段不应进入产品 UI。

---

## 2. 目标与非目标

### 2.1 目标

1. 首屏只保留最重要的数学提问入口，用户无需理解工具分类即可开始。
2. 让数学公式、步骤推导、图片题目和长回答具有专业阅读体验。
3. 打通提问、知识点、练习、错题、掌握度更新和下一步推荐。
4. 提供可验证、可解释、可追溯的个人学习画像。
5. 桌面端呈现接近专业 AI 工作台的稳定结构，移动端保持核心学习闭环。
6. 通过组件和设计 Token 建立长期可维护的统一视觉系统。
7. 在不重写后端和全部业务逻辑的前提下渐进交付。

### 2.2 非目标

- 不分析用户在纸上的完整解题过程，除非未来提供明确的分步作答或手写过程上传功能。
- 不根据聊天语气推断学习态度、性格、专注力或智力水平。
- 不使用“视觉型/听觉型学习者”等缺乏可靠证据的学习风格标签。
- 不把问过某个知识点直接等同于掌握该知识点。
- 不把阅读了 AI 回答直接等同于完成学习。
- 不制作仅用于展示的 3D 动画首页。
- 不建设教师后台、班级管理、排行榜、社区或游戏化勋章。
- 不在本轮更换后端框架或数据库。
- 不为了“高级感”加入大面积玻璃拟态、霓虹渐变、自动旋转或无意义微动效。

---

## 3. 学习画像的数据边界

### 3.1 系统可以直接观察的数据

| 数据 | 来源 | 可支持的结论 |
|---|---|---|
| 用户提出的题目文本/图片识别结果 | 对话、多模态接口 | 用户近期接触过的知识点；不能证明已经掌握 |
| 系统内练习的提交结果 | 练习/事件接口 | 对应知识点的正确与错误记录 |
| 系统内练习用时 | 明确开始、提交时间 | 单题耗时趋势；仅在计时完整时使用 |
| 用户主动加入的错题 | 错题本 | 用户确认该题需要复盘 |
| 用户选择或确认的错误原因 | 错题本表单 | 错误类别统计，如概念不清、公式误用、条件遗漏、计算错误 |
| 知识点学习页完成状态 | 课程/学习事件 | 学习进度；不能单独证明掌握 |
| 再测结果 | 复习练习 | 错题是否得到纠正、掌握度是否恢复 |
| 对话、错题、练习与知识点的关联 | 分类器 + 用户确认 | 建立证据链和推荐依据 |

### 3.2 系统可以经过规则计算的数据

- 知识点掌握度：必须由练习正确率、题目难度、时间衰减、近期表现等组合计算。
- 学习状态：未开始、接触过、学习中、待巩固、已掌握。
- 薄弱知识点：需要达到最小证据量，且近期错误/再测结果支持。
- 高频错误类别：只使用用户确认或系统能明确判定的错误记录。
- 推荐下一步：结合前置关系、当前目标、薄弱点、复习到期时间计算。
- 学习进度：由课程节点完成、练习和再测记录计算。
- 近期变化：比较两个时间窗口内的真实掌握度或练习结果。

### 3.3 系统不得自动宣称的数据

以下内容不进入画像 UI，也不得包装成确定性结论：

- 解题风格，例如“擅长逆向思考”“倾向几何法”。
- 学习习惯，例如“喜欢夜间学习”，除非有长期、明确且充分的使用时间数据，并且文案仅描述行为事实。
- 认知风格、思维类型、智力水平、专注力、粗心程度。
- 用户在纸上的中间步骤、擦改过程和真实思考路径。
- 仅根据一道上传题目判断用户“不会”某知识点。

### 3.4 证据等级

所有画像结论都必须带证据等级：

| 等级 | 规则 | UI 表达 |
|---|---|---|
| 数据不足 | 0–2 条有效作答证据 | “数据不足”，不显示精确百分比 |
| 初步判断 | 3–5 条有效证据 | 显示范围或“初步”标签 |
| 较可靠 | 6–14 条且包含不同题目 | 显示掌握度和证据数量 |
| 稳定判断 | 15 条以上且跨多个日期 | 显示趋势和稳定状态 |

阈值应由后端配置，前端不得自行硬编码业务结论。上述数值作为第一版默认建议。

### 3.5 用户纠错权

- 用户可以查看一项画像结论的证据来源。
- 用户可以移除错误关联的对话、练习或错题证据。
- 用户可以手动修改错题的知识点分类和错误原因。
- 系统推荐使用“根据最近 X 次练习判断”而不是“你就是……”的绝对化文案。

---

## 4. 用户故事

1. 作为学生，我希望打开产品后立即输入问题，不需要先选择工具。
2. 作为学生，我希望上传一道图片题后能补充文字说明，再一起发送。
3. 作为学生，我希望 AI 的长推导像教材一样清晰，而不是塞在巨大聊天气泡里。
4. 作为学生，我希望能随时看到回答关联了哪些知识点。
5. 作为学生，我希望能把没掌握的题加入错题本，并明确填写错误原因。
6. 作为学生，我希望从 AI 回答直接生成一道相似练习来验证是否理解。
7. 作为学生，我希望查看某知识点的掌握度时，能知道这个判断依据是什么。
8. 作为学生，我希望系统明确区分“我问过”“我学过”和“我已经掌握”。
9. 作为学生，我希望点击薄弱知识点后看到关联错题、最近练习和建议行动。
10. 作为学生，我希望查看画像随时间的真实变化，而不是看到静态装饰图表。
11. 作为学生，我希望推荐的下一步能说明推荐原因和前置关系。
12. 作为学生，我希望错误分类不准确时可以修改，而不是被系统永久贴标签。
13. 作为学生，我希望网络或生成失败时可以保留输入并一键重试。
14. 作为键盘用户，我希望不用鼠标也能开始对话、切换历史和操作图谱。
15. 作为移动端用户，我希望能提问、查看回答、记录错题和查看局部画像，而不是缩小版桌面页面。

---

## 5. 信息架构与路由

### 5.1 一级导航

| 导航项 | 路由 | 作用 |
|---|---|---|
| 新对话 | `/` | 空白对话状态，发送后进入具体会话 |
| 对话历史 | 侧栏内列表/搜索 | 恢复最近会话，不单独占一个主页面 |
| 记忆画像 | `/profile` | 展示知识掌握、学习进度、错题证据和近期变化 |
| 知识地图 | `/knowledge` | 课程结构、前置关系、知识点状态和学习入口 |
| 错题复盘 | `/error-book` | 按知识点、错误原因和复习状态组织错题 |

保留：

- `/chat/:chatId`
- `/knowledge/points/:pointId/learn`
- `/error-book/:errorId`

移除或合并：

- `/chat` 不再创建一个带欢迎消息的伪会话；它可以重定向至 `/`。
- “课程目录”不再单独命名为一级产品模块，统一称为“知识地图”。

### 5.2 全局布局

桌面端：

```text
左侧栏 260px │ 主工作区 minmax(0, 1fr) │ 可选检查器 360px
```

- 左侧栏长期稳定存在。
- 顶部不再叠加全局顶栏 + 页面顶栏 + 面包屑三层结构。
- 普通对话页只保留 48–56px 的轻量会话标题栏。
- 右侧检查器只在用户主动打开上下文、知识点或画像证据时出现。

平板端：

- 72px 图标侧栏。
- 右侧检查器以覆盖抽屉形式出现。

手机端：

- 顶部轻量标题栏。
- 左侧栏变为抽屉。
- 底部固定导航最多四项：对话、画像、知识、错题。
- 图谱详情使用 bottom sheet。

---

## 6. 页面详细规格

## 6.1 App Shell 与侧栏

### 结构顺序

1. 品牌标识“知微”。
2. 高对比主按钮“新对话”。
3. 对话搜索入口。
4. 最近对话列表，按“今天 / 最近 7 天 / 更早”分组。
5. 主导航：记忆画像、知识地图、错题复盘。
6. 底部：主题、设置、用户。

### 行为

- 侧栏桌面展开宽度 260px，收起宽度 68px。
- 新对话按钮只创建空白界面；用户第一次发送后才持久化会话。
- 当前会话显示选中背景，但不使用高饱和整块颜色。
- 对话项 hover 后显示“更多”，支持重命名和删除。
- 删除必须使用自定义确认弹层，不使用原生 `confirm`。
- 对话超过 30 条后启用虚拟列表或分页加载。
- 收起状态、主题和检查器状态保存到本地。

### Chatbox 参考实现原则

Chatbox 只用于校准“聊天工作台”的交互成熟度，不复制其 React/Mantine/MUI 组件。V2.1 采用以下可行原则：

- 桌面端侧栏保持持久存在，移动端切换为临时抽屉；用户进入具体会话后不丢失当前上下文。
- 会话列表承担“恢复历史”的主职责，搜索入口始终靠近历史列表。
- 新对话是高频动作，视觉优先级高于设置、帮助等低频入口。
- 侧栏内容滚动与主会话内容滚动相互独立，但页面主工作区只保留一个正文滚动容器。
- Chatbox 当前实现支持桌面拖拽改变侧栏宽度；知微 V2.1 **不把可拖拽宽度列为 P0**，先保持 260px / 68px 的可预测布局。若 1024–1440px 可用性测试证明有价值，可在 P1 加入 220–360px 范围内的可调宽度。
- 移动端抽屉需保持打开速度和状态连续性，但必须遵循本项目统一焦点管理规则，不能直接照搬其他项目对 focus trap 的处理。

### 不允许出现

- “今日”这类与实际数据无对应页面的模糊导航。
- 课程、提问、首页三个含义重叠的入口。
- Emoji 作为结构图标。
- 页脚堆叠多个大按钮。

## 6.2 首页 / 空白对话

### 页面目标

用户在 3 秒内理解：这里可以直接输入或上传数学问题。

### 桌面布局

- 内容区最大宽度 820px。
- 输入区垂直位置约在视口 42%–48%，不是严格居中。
- 标题最多两行，避免营销式长文。
- 输入框下方最多展示三条与真实状态相关的继续入口。

### 文案

- 新用户：`今天想解决什么数学问题？`
- 有历史用户：`继续学习，或提出一个新问题。`
- 输入提示：`输入问题，或拖入一道题目……`

### 可展示的继续入口

只在真实数据存在时显示：

- 最近未完成的知识点。
- 到期需要复习的错题。
- 上一次未完成的对话。

无数据时不放占位卡片；可以显示两条纯文本示例问题，但不能做成六宫格。

### 输入组件

`AgentComposer` 支持：

- 多行文本输入，默认 1 行，最多扩展到 8 行。
- 粘贴或拖拽图片。
- 文件选择入口，未实现的文件类型不显示按钮。
- 图片缩略图、移除、上传失败重试。
- `Enter` 发送，`Shift + Enter` 换行。
- 发送时按钮变为停止生成。
- IME 中文输入期间不得误发送。

## 6.3 对话页

### 内容结构

- 会话正文最大宽度 820px。
- 页面滚动容器只有一个。
- 用户消息右对齐，小范围中性背景，最大宽度 80%。
- AI 消息左对齐、无大气泡、占正文宽度。
- AI 头像只在需要表达身份时出现，不在每段重复。
- 时间戳和操作按钮默认弱化。

### AI 回答视觉层级

回答内容按语义呈现：

1. 结论或解题目标。
2. 条件整理。
3. 分步推导。
4. 结果检查。
5. 相关知识点。
6. 可执行的下一步。

前端应正确呈现 Markdown，但不得假定模型一定返回以上所有章节；缺少章节时正常降级。

### 数学内容

- 行内公式与文字基线对齐。
- 块级公式上下至少 16px 留白。
- 超宽公式允许横向滚动，不挤压页面。
- 每个块级公式 hover 后显示复制 LaTeX。
- 不在公式容器内使用低对比度灰字。
- 代码块、表格、引用和列表拥有统一样式。

### 消息操作

AI 消息底部按权限与数据状态显示：

- 复制。
- 重新生成。
- 标记没懂。
- 生成相似题。
- 定位到知识地图。
- 加入错题本。

“加入错题本”不能默认认定 AI 回答错误，也不能自动生成用户的错误原因。弹层要求用户至少选择一个原因：

- 概念不清。
- 公式记错或误用。
- 条件遗漏。
- 计算错误。
- 不会选择方法。
- 其他。

如用户只上传题目但没有提供自己的答案或错误过程，UI 文案使用“这道题需要复盘”，不能声称知道用户错在具体哪一步。

### 教学交互状态

对话不能把所有数学问题都处理成“直接给完整答案”，也不能反过来强迫所有用户先接受提示。前端需配合后端/Agent 保留三种教学上下文：

- `direct_answer`：用户明确要求完整讲解时，直接提供完整、可读的解法。
- `guided`：用户表示“做到这里不会”“给我一点提示”时，优先给最小必要提示，再逐步升级。
- `practice`：系统生成的练习默认隐藏最终答案，按提示 1 → 提示 2 → 关键步骤 → 完整解答逐层释放。

“标记没懂”不是普通负反馈。点击后允许用户快速选择：`概念没懂 / 这一步没懂 / 公式来源不清楚 / 不知道为什么用这个方法 / 其他`，下一轮解释应改变粒度或策略。该选择可作为教学交互事件，但**不能直接成为“未掌握”证据**。

### 流式生成

- 不直接通过 `document.getElementById` 和 `innerHTML` 操作消息 DOM。
- SSE 内容写入响应式 stream buffer，由 Vue 正常渲染。
- 不能仅依靠“30–50ms 批处理后重新渲染整条回答”。长回答必须按语义块拆分：段落、列表、代码块、表格、块级公式等已完成 block 冻结，仅重新解析当前未完成 block。
- token/delta 进入 buffer 后使用 `requestAnimationFrame` 或约 30–50ms 合并刷新；块完成后再执行最终 Markdown/KaTeX 渲染。
- 生成期间显示克制的状态文本，如“正在组织推导”。
- 用户主动向上滚动后停止强制自动滚底；底部出现“回到最新”按钮。
- 终止生成后保留已经生成的内容。
- 前端必须区分 `idle / sending / streaming / completed / cancelled / interrupted / failed` 状态。
- “SSE 中断可恢复”在 V2.1 中定义为：至少保留部分内容并可重新生成；只有后端提供 generation checkpoint / event id 时，才能实现真正的断点续传，前端不得伪装成已续传。

### 失败状态

- 网络失败：保留用户消息和输入附件，AI 消息位置显示“生成失败，重试”。
- SSE 中断：保留部分内容，并明确“回答未完成”。
- 图片识别失败：保留图片，允许重新识别或仅发送文字。
- 401：引导重新登录，不清空本地未发送输入。
- 429：展示可读的稍后重试提示。

## 6.4 右侧上下文检查器

检查器默认关闭，由消息操作或顶部按钮打开。

标签页最多三个：

1. `知识点`：本轮识别的知识点和课程位置。
2. `依据`：AI 使用的资料、历史记忆或错题；没有数据时不显示该标签。
3. `画像变化`：本轮产生的有效学习证据。

“画像变化”只有在发生真实事件时显示。例如：

- 完成一道系统练习并判分。
- 用户确认一道错题及其原因。
- 完成知识点 exit ticket。

普通提问只能记录“近期接触”，不得提升掌握度。

## 6.5 记忆画像页

### 页面名称

用户侧统一称为“记忆画像”。页面内主标题可以使用“你的数学学习画像”。不要使用“认知诊断”这类医疗化或过度承诺文案。

### 首屏结构

```text
标题与更新时间
一句基于证据的概述

总体进度摘要 │ 待复习 │ 当前薄弱点 │ 推荐下一步

视图切换：[知识图谱] [知识树] [变化记录]

主视图区域 + 右侧证据检查器
```

### OpenHuman 参考：学习记忆工作区

OpenHuman 的价值不在于“做一个会动的关系图”，而在于把记忆做成可搜索、可浏览、可追溯、可纠正的工作区。知微采用同类交互结构，但数据对象必须全部替换为数学学习证据。

桌面端推荐结构：

```text
学习导航 240px │ 画像主视图 minmax(0, 1fr) │ 证据检查器 340–380px
```

左侧 `LearningNavigator`：

- 搜索知识点、章节和可搜索的证据摘要。
- 顶部放置紧凑的学习活动热力图；热力只统计有教学意义的事件，不统计单纯打开页面、停留时长或闲聊数量。
- 可折叠筛选组：最近活动、课程/章节、学习状态、错误原因。
- 多个筛选条件可以组合，默认使用交集语义，并在界面显示当前筛选条件，避免用户不知道结果为何变少。
- 不照搬 OpenHuman 的 people/sources/topics 分类；教育产品中的对应维度必须来自课程结构与学习证据。

中间 `ProfileWorkspace`：

- `[知识图谱] [知识树] [变化记录]` 三视图共享同一 profile DTO。
- 图谱用于关系探索，知识树用于快速扫描与无障碍替代，变化记录用于解释状态如何形成。
- 图谱必须支持 pan、zoom、fit/reset、节点选择、聚焦前置/后继路径。
- 节点拖拽只作为临时探索；默认课程布局由系统计算，刷新后不依赖用户拖拽位置作为业务数据。
- 不使用持续 force simulation、自动旋转、粒子、漂浮等展示效果。

右侧 `EvidenceInspector`：

- 显示状态、有效证据数、证据等级、更新时间和最近计算时间。
- 显示最近练习、错题、复习、exit ticket 等证据，并标注每条证据的来源。
- 允许修正错误的知识点关联、错误原因或排除无效证据；修改必须进入审计记录。
- 提供“为什么是这个状态？”入口，把 mastery 的关键输入转为自然语言说明。

OpenHuman 强调记忆内容可阅读、可修改、不是黑箱；知微对应的产品原则是：**学习画像必须可检查、可解释、可纠正，而不是只展示一个分数。**

实现约束：

- V2.1 继续使用 Cytoscape.js，不移植 OpenHuman 当前的 React/Pixi.js/d3-force 图谱组件。
- 原因不是 OpenHuman 技术不可用，而是两者数据结构不同：OpenHuman 更偏自由记忆网络，知微是有课程层级和前置关系的技能图，更适合稳定的层级/依赖布局。
- 首版优先使用 Cytoscape.js 内建/成熟扩展可支持的层级或 breadth-first 布局；若需要更强的 DAG 分层，可评估 `dagre`/`elk` 类布局扩展，但必须在现有 Vue 构建中单独验证 bundle 和性能后再引入。

首屏摘要只保留四项，不做八张统计卡：

1. 有证据的知识点数量。
2. 已掌握/待巩固分布。
3. 到期复习数量。
4. 当前推荐下一步。

### A. 知识图谱视图

用途：探索知识点之间的前置关系和个人掌握状态。

节点数据：

- 知识点节点来自 `math_skill_graph.yml` 或课程知识图谱。
- 节点状态来自技能画像。
- 错题和对话默认不作为全部展开的图节点，避免形成毛线团。
- 选中知识点后，相关错题和证据在右侧检查器中展示。

布局规则：

- 默认按课程章节或前置依赖分层布局，优先稳定、可重复的布局，不采用每次进入位置都变化的自由力导向图作为默认教学视图。
- 默认只显示当前课程或当前学习范围。
- 选中节点时高亮前置、后继和当前推荐路径。
- 其他节点降至 25%–35% 透明度。
- 禁止默认自动旋转、持续漂浮和随机粒子背景。

状态规则：

| 状态 | 条件 | 样式 |
|---|---|---|
| 未开始 | 无有效学习证据 | 中性灰，空心 |
| 接触过 | 只出现于对话/浏览，无作答证据 | 灰蓝细环 |
| 学习中 | 有练习但证据不足或未稳定 | 金色描边 |
| 待巩固 | 有掌握基础但近期错误或到期复习 | 珊瑚色标记 |
| 已掌握 | 达到后端掌握阈值且证据充足 | 低饱和绿色实心 |
| 推荐下一步 | 推荐算法选中 | 紫色外环 + “下一步”标签 |

颜色不能是唯一状态表达，还需图标、边框和文字标签。

### B. 知识树视图

用途：稳定、快速地浏览课程层级，承担类似 OpenHuman Memory Tree 的可读性，但内容是数学教学结构。

每行显示：

- 知识点名称。
- 学习状态。
- 掌握度或“数据不足”。
- 有效证据数。
- 到期复习状态。

支持折叠章节、搜索、只看薄弱点、只看待复习。

### C. 变化记录视图

按时间展示可解释事件：

- 完成练习。
- 添加或复习错题。
- 掌握度变化。
- 知识点状态改变。
- 推荐路径改变。

不得把普通打开页面、发送闲聊等无教学意义事件放入时间线。

### 知识点证据检查器

点击节点后显示：

- 名称、课程路径、状态。
- 掌握度；证据不足时不显示虚假精度。
- 有效练习数、正确数、最近练习日期。
- 关联错题数量和错误原因分布。
- 最近三条证据。
- 前置知识点。
- 推荐动作：开始学习、针对性练习、复习错题。
- “为什么是这个状态？”解释入口。

### 画像文案规范

正确：

- `根据最近 8 次练习，定积分目前处于待巩固状态。`
- `最近 3 道相关错题中，有 2 道由条件遗漏导致。`
- `你已经接触过分部积分，但还没有足够作答数据判断掌握程度。`

禁止：

- `你是视觉型学习者。`
- `你的逻辑思维很强。`
- `你习惯跳步，所以容易粗心。`
- `你不擅长抽象思考。`

## 6.6 知识地图页

知识地图是标准课程知识结构，不等于个人画像。

区别：

- 知识地图回答“这门课包含什么、知识之间如何依赖”。
- 记忆画像回答“用户在哪些节点有何证据、当前处于什么状态”。

页面包括：

- 课程切换。
- 章节树 / 依赖图切换。
- 搜索知识点。
- 掌握状态覆盖层开关。
- 节点详情检查器。
- “开始学习”主动作。

不得在同一页面同时默认展示 3D 星系、课程卡片、章节列表和大量统计卡。

## 6.7 知识点学习页

页面遵循数学教学顺序：

1. 学习目标。
2. 必要前置知识。
3. 核心概念与直觉。
4. 公式或定理推导。
5. 完整例题。
6. 引导练习。
7. 独立验证题（exit ticket）。
8. 结果回写画像。

只阅读内容不更新为“已掌握”。至少完成可判分的验证题后才能产生掌握证据。

## 6.8 错题复盘页

默认组织维度按优先级排列：

1. 到期复习。
2. 知识点。
3. 用户确认的错误原因。
4. 添加时间。

顶部只保留：搜索、筛选、待复习数量和“开始复习”。

错题列表项显示：

- 题目摘要或图片。
- 关联知识点。
- 错误原因。
- 上次复习和下次复习时间。
- 当前状态。

复习流程：

```text
显示题目 → 用户自行作答/查看提示 → 展示答案 → 用户提交结果
→ 更新错题状态和对应知识点证据 → 安排下次复习
```

“已掌握”不能只是用户点击一次按钮就永久成立；点击可作为自评，但应与再测结果分开记录。

---

## 7. 视觉设计系统

### 7.1 视觉关键词

专业、理性、克制、耐读、安静、可信、有适度温度。

参考产品只提取原则：

- ChatGPT / Codex：输入和内容优先、低干扰界面。
- Chatbox：稳定聊天工作台、会话搜索与列表、桌面持久侧栏、移动端临时抽屉、清晰的新对话动作。
- OpenHuman：记忆结构可搜索、可视化、可查看来源、可纠正；重点参考 Navigator + activity heatmap + graph/tree + detail/inspector 的组合方式。

参考优先级：

1. **先匹配知微的真实学习任务**，再考虑视觉相似度。
2. 可以借鉴布局关系、信息密度、交互流程和状态反馈；不能照搬品牌、文案、图标、动画、CSS 数值和组件实现。
3. OpenHuman/Chatbox 均不是 Vue 3 项目，Trae Work 必须在现有组件系统中重新实现，不为“像参考项目”而引入 React 运行时。
4. 开发开始时记录所参考仓库的 commit SHA 和查看日期；开源项目持续变化，不能把 `main` 分支的瞬时实现当作永久规范。
5. 当前两个仓库均标注 GPL-3.0。若未来决定复用任何实际源码而非仅借鉴思想，必须先做许可证兼容性评估；本规范默认**零源码复制**。

不得一比一复制任何产品的品牌、布局细节或图标。

### 7.2 浅色主题 Token

| Token | 值 | 用途 |
|---|---:|---|
| `--canvas` | `#F7F7F4` | 全局背景 |
| `--surface` | `#FFFFFF` | 主表面 |
| `--surface-muted` | `#F1F1ED` | 次级区域 |
| `--surface-hover` | `#ECECE7` | hover |
| `--text-primary` | `#1D1D1B` | 主文字 |
| `--text-secondary` | `#666660` | 次文字 |
| `--text-tertiary` | `#92928B` | 弱信息 |
| `--border-subtle` | `#E6E6E0` | 分隔线 |
| `--border-strong` | `#D5D5CE` | 输入和交互边界 |
| `--accent` | `#456F65` | 主动作 |
| `--accent-hover` | `#365B53` | 主动作 hover |
| `--knowledge` | `#6E67A3` | 知识关系/推荐 |
| `--mastered` | `#5F947C` | 已掌握 |
| `--learning` | `#B08A47` | 学习中 |
| `--weak` | `#C46F5D` | 待巩固/薄弱 |
| `--danger` | `#B84E4E` | 删除和错误 |

### 7.3 深色主题 Token

| Token | 值 |
|---|---:|
| `--canvas` | `#181817` |
| `--surface` | `#20201E` |
| `--surface-muted` | `#282826` |
| `--surface-hover` | `#30302D` |
| `--text-primary` | `#F0F0EC` |
| `--text-secondary` | `#B2B2AA` |
| `--text-tertiary` | `#85857E` |
| `--border-subtle` | `#32322F` |
| `--border-strong` | `#42423E` |
| `--accent` | `#78A99B` |

### 7.4 排版

- UI 和正文：`Inter, "Noto Sans SC", "Microsoft YaHei", sans-serif`。
- 数字、快捷键、代码：`JetBrains Mono, ui-monospace, monospace`。
- 数学公式：KaTeX 默认数学字体。
- 正文：16px / 1.7。
- AI 长回答：桌面 16px，移动端 15px。
- 页面标题：24–28px，禁止 48px 以上营销标题。
- 次级标题：18–20px。
- 辅助文字不得低于 12px。

### 7.5 空间与形态

- 4px 基础网格。
- 常用间距：8、12、16、20、24、32、48。
- 圆角：8px 控件、12px 卡片/输入、16px 弹层；胶囊只用于标签。
- 普通卡片以边框和背景层级区分，不加大阴影。
- 只有弹层、浮动输入框和选中检查器可以使用柔和阴影。

### 7.6 动效

- hover/focus：120–160ms。
- 抽屉/弹层：180–220ms。
- 图谱聚焦：280–360ms。
- 不使用循环呼吸、漂浮、闪烁。
- 流式内容不使用逐字跳动光标动画。
- 支持 `prefers-reduced-motion`。

---

## 8. 组件系统

### 8.1 基础组件

- `BaseButton`
- `IconButton`
- `BaseInput`
- `BaseTextarea`
- `BaseDialog`
- `BaseDrawer`
- `BaseDropdown`
- `BaseTooltip`
- `StatusBadge`
- `SkeletonBlock`
- `EmptyState`
- `ErrorState`
- `Toast`

每个组件必须提供 default、hover、focus-visible、pressed、disabled、loading 状态。

### 8.2 业务组件

- `AppShell`
- `ConversationSidebar`
- `ConversationListItem`
- `AgentComposer`
- `AttachmentPreview`
- `UserMessage`
- `AssistantMessage`
- `MessageActions`
- `MathBlock`
- `KnowledgePointChip`
- `ContextInspector`
- `ProfileSummary`
- `MasteryStatus`
- `ProfileGraph`
- `ProfileTree`
- `ProfileTimeline`
- `EvidenceList`
- `KnowledgeInspector`
- `ReviewQueue`
- `ErrorReasonSelector`

### 8.3 图标

- 使用 `lucide-vue-next`。
- 统一 1.75–2px 描边。
- 普通图标 18–20px，导航图标 20px。
- 禁止混用手写 SVG、Emoji、Element Plus 图标和多套线宽。

---

## 9. 技术架构

### 9.1 推荐技术栈

- Vue 3 Composition API。
- TypeScript，新组件必须使用 `<script setup lang="ts">`。
- Vite。
- Pinia。
- Vue Router。
- CSS Variables + SCSS Modules 或 Tailwind CSS 4 二选一。
- 推荐优先 CSS Variables + 轻量 utility，避免一次性引入过多框架。
- Reka UI 用于无样式可访问组件。
- Lucide Vue 图标。
- Cytoscape.js 用于 2D 图谱。
- KaTeX + Markdown-it 统一渲染链，不再同时维护 `marked` 和 `markdown-it` 两套路径。
- Vitest + Vue Test Utils。
- Playwright 用于核心流程和视觉回归。

### 9.1.1 开源参考的技术落地边界

- Chatbox 当前前端核心实现使用 React 生态；知微不引入 React，仅复刻会话工作台的行为。
- OpenHuman 当前记忆图组件采用 React，并在 WebGL 可用时使用 Pixi.js + d3-force，另有 SVG 回退；知微 V2.1 不复制这套渲染链。
- Cytoscape.js 已支持节点/边模型、pan、zoom 与多种布局，能够满足当前“课程技能图 + 局部画像覆盖”的第一版需求，因此继续作为默认方案。
- 不设置武断的“超过 200 节点必卡”规则。性能验收采用真实数据集和设备基准，以首绘时间、交互帧率、pan/zoom 响应和内存为准。
- 当默认课程局部图在真实基准下无法满足目标时，再创建独立技术决策记录（ADR）比较 Cytoscape.js 优化、Canvas/WebGL 或 Pixi.js 方案，禁止提前过度工程化。

### 9.2 Element Plus 策略

- 不要求一次删除整个依赖。
- 新页面不得直接使用 Element Plus 默认视觉样式。
- 第一阶段可保留消息提示、复杂弹层等功能，但必须通过封装组件输出统一样式。
- 完成基础组件后逐步移除 `ElMessageBox` 等视觉不一致实现。

### 9.3 状态管理

建议拆分：

- `conversationStore`：会话列表、当前会话、消息元数据。
- `streamStore` 或 composable：SSE 生命周期、停止、重试、部分结果。
- `composerStore`：草稿、附件、发送状态；按会话保存草稿。
- `profileStore`：画像摘要、图谱、筛选、证据详情。
- `knowledgeStore`：课程树、节点、学习内容。
- `reviewStore`：错题和复习队列。
- `uiStore`：主题、侧栏、检查器、移动端抽屉。

缓存与持久化规则：

- 后端是 mastery、画像、错题和课程状态的 source of truth；前端不得通过本地缓存计算最终业务结论。
- 会话列表、课程树、画像 overview 可以做会话级内存缓存，并在写操作成功后显式失效相关 query/store。
- 草稿按 conversation id 持久化到本地；正式发送成功后清除对应草稿。
- profile graph / evidence 使用短期缓存时必须带 `generated_at` 或版本信息；用户完成练习、复习或证据纠错后触发失效。
- 不在 localStorage 持久化 access token 之外的敏感画像明细；具体认证存储方式以现有后端安全方案为准。

不得继续将所有消息长期以 Base64 图片形式写入 localStorage。图片应上传并存储引用；短期兼容旧数据时需要迁移和容量保护。

### 9.4 建议目录

```text
frontend/src/
├─ api/
│  ├─ client.ts
│  ├─ conversation.ts
│  ├─ profile.ts
│  ├─ knowledge.ts
│  └─ review.ts
├─ components/
│  ├─ ui/
│  ├─ shell/
│  ├─ conversation/
│  ├─ profile/
│  ├─ knowledge/
│  └─ review/
├─ composables/
│  ├─ useChatStream.ts
│  ├─ useAutoScroll.ts
│  ├─ useKeyboardShortcuts.ts
│  └─ useResponsiveInspector.ts
├─ stores/
├─ styles/
│  ├─ tokens.css
│  ├─ reset.css
│  ├─ typography.css
│  └─ themes.css
├─ types/
└─ views/
```

---

## 10. API 契约与后端需求

### 10.1 现有可复用接口

- `POST /api/chat`
- `POST /api/chat/multimodal`
- `GET /api/profile/{user_id}`
- `GET /api/profile/{user_id}/skills`
- `GET /api/profile/{user_id}/report`
- `GET /api/profile/{user_id}/recommendations`
- `GET /api/memory/retrieve`
- `GET /api/memory/skill-impact`
- `GET /api/knowledge/courses`
- `GET /api/knowledge/courses/{course_id}/tree`
- `GET /api/knowledge/points/{point_id}`
- `GET /api/knowledge/points/{point_id}/learning`
- `/api/error-book` CRUD。

注意：当前记忆 Dashboard 的 `/api/dashboard/memory/timeline` 受管理员权限保护，不能直接作为普通用户画像时间线。需要新增用户自有时间线接口。

### 10.2 新增聚合接口

#### `GET /api/profile/me/overview`

返回首屏摘要：

```json
{
  "generated_at": "2026-08-09T10:00:00Z",
  "evidenced_skill_count": 18,
  "status_counts": {
    "mastered": 5,
    "learning": 7,
    "needs_review": 4,
    "insufficient_data": 2
  },
  "due_review_count": 6,
  "recommended_next": {
    "skill_code": "integ_by_parts",
    "name": "分部积分法",
    "reason": "前置知识已达到要求，且当前课程路径指向该知识点"
  }
}
```

#### `GET /api/profile/me/graph?course_id=&scope=current`

```json
{
  "nodes": [
    {
      "id": "integ_indefinite",
      "type": "skill",
      "label": "不定积分",
      "category": "积分",
      "status": "learning",
      "mastery": 0.68,
      "evidence_level": "reliable",
      "evidence_count": 9,
      "last_activity_at": "2026-08-08T12:00:00Z"
    }
  ],
  "edges": [
    {
      "source": "derivative_rules",
      "target": "integ_indefinite",
      "type": "prerequisite"
    }
  ],
  "recommended_path": ["integ_indefinite", "integ_by_parts"]
}
```

#### `GET /api/profile/me/skills/{skill_code}/evidence`

返回：

- 练习统计。
- 最近有效练习。
- 关联错题。
- 错误原因分布。
- 状态变化历史。
- 前置知识点。
- 推荐动作。

#### `GET /api/profile/me/timeline?cursor=&limit=30`

只返回当前用户、具有教学意义的画像事件。使用 cursor 分页。

#### `PATCH /api/profile/me/evidence/{evidence_id}`

用于用户修正知识点关联或排除错误证据。操作必须审计。

### 10.3 数据语义修正

- `cognitive_style` 不进入新前端响应模型；后端可以暂时保留兼容，但标记 deprecated。
- `correct_rate` 没有足够题量时必须返回证据状态，前端不显示 0% 造成误导。
- “接触过”与“掌握”分开存储或计算。
- 普通聊天分类事件不直接改变 mastery。
- 错题的 `error_reason` 优先使用用户选择；系统自动建议必须明确标记为“建议分类”，等待确认。
- `skill_code` 必须是长期稳定 ID，不得因知识点展示名称改动而变化。
- 知识关系至少区分 `prerequisite`、`part_of`、`related_to`；只有真正的先修关系才能参与推荐路径阻塞或解锁。
- `evidence_count` 与 `effective_evidence_count` 分开：前者是原始有效记录数，后者是考虑重复题、提示、重试、跨日期和题目多样性后的有效证据量。

---

## 11. 响应式与可访问性

### 11.1 断点

- `>= 1280px`：完整侧栏 + 主区 + 可选检查器。
- `768–1279px`：图标侧栏 + 抽屉检查器。
- `< 768px`：顶部栏 + 导航抽屉/底部导航。
- `< 480px`：输入工具折叠到 `+` 菜单，保留发送和图片入口。

### 11.2 可访问性要求

- 达到 WCAG 2.2 AA 基本要求。
- 所有交互可通过键盘完成。
- focus-visible 清晰可见。
- 点击区域至少 44×44px。
- 图谱必须提供等价的树/列表视图。
- `< 768px` 的记忆画像默认优先打开知识树/列表；关系图可由用户主动切换，避免在小屏上把复杂拖拽图当作唯一入口。
- 状态不只依赖颜色。
- 弹层打开时正确管理焦点，关闭后回到触发按钮。
- 流式回答状态使用 `aria-live="polite"`，避免逐 token 播报。
- 图片题提供识别文本和替代说明。

---

## 12. 性能要求

- 首屏不加载 Three.js、Cytoscape.js 或画像数据。
- 画像和知识地图按路由懒加载。
- 桌面中端设备上首屏 LCP 目标 `< 2.5s`。
- 常规交互 INP 目标 `< 200ms`。
- 初始前端 JS gzip 目标 `< 250KB`，图谱独立 chunk。
- 100 条消息会话保持平滑滚动；超过阈值启用虚拟化或分段渲染。
- Markdown 与 KaTeX 流式渲染采用批处理。
- 图谱默认只加载当前课程/局部范围，避免一次绘制全部证据节点。
- 图谱不以固定节点阈值猜测性能；建立三组真实基准数据（小/中/大），记录首绘耗时、pan/zoom 响应和内存。只有真实瓶颈出现后才更换渲染技术。
- 图片上传前进行客户端预览与可选压缩，显示压缩后大小；服务端再次验证 MIME、尺寸和格式。
- 多图必须保持用户选择顺序；单图失败可独立重试，不能让已成功图片重复上传。
- Skeleton 只模拟真实布局，不使用整页闪烁占位。

---

## 13. 隐私、安全与可信度

- 画像页明确说明数据来源：系统内练习、用户确认的错题、课程进度。
- 用户能够查看画像更新时间。
- 用户能够查看并纠正证据关联。
- 敏感错误记录不出现在公开分享内容中。
- 不在前端日志中输出完整题目、Token、用户画像或图片 Base64。
- 所有画像接口验证当前用户数据所有权。
- 删除错题或证据后，相关画像应异步重算并在 UI 中显示更新状态。
- Markdown-it 默认 `html: false`；任何未来需要渲染 HTML 的路径必须先经过成熟 sanitizer，禁止未经净化的 AI/用户内容直接 `v-html`。
- 链接只允许安全 scheme；外部链接采用安全的 `rel` 策略。
- KaTeX 使用安全配置，不开启不受控的 trust 能力；代码块只展示，绝不执行。
- 上传格式默认限制为 JPEG/PNG/WebP；SVG 默认禁止，除非未来建立独立的 SVG 净化流程。服务端不能信任浏览器声明的 MIME。
- 图片保存为对象存储/文件存储引用，数据库保存 object key/URL 与所有权；明确会话删除、用户删除与临时上传失败后的清理策略。
- 前端异常上报需脱敏，不发送完整题目、图片内容、Authorization 头或画像详情。

---

## 14. 空状态、加载状态和降级

### 画像无数据

显示：

`完成几道系统内练习后，这里会逐步形成你的知识掌握图。普通提问只会记录为“接触过”，不会被当作掌握证据。`

主动作：`去做一次基础检测`。  
次动作：`浏览知识地图`。

不得生成随机示例画像冒充真实数据。

### 画像部分数据

- 有知识点但证据不足：显示节点和“数据不足”。
- 有错题但无错误原因：显示“待补充原因”。
- 推荐接口失败：隐藏推荐区，其他画像正常使用。
- 图谱加载失败：自动降级到知识树。

### 对话空状态

- 不自动创建欢迎 AI 消息。
- 不在历史列表产生大量“新对话”。
- 用户第一次发送后才创建正式会话。

---

## 15. 实施阶段

### Phase 0：基线与设计系统（2–4 天）

- 为现有关键页面保存 1440、1024、768、390px 截图。
- 建立 `tokens.css`、排版、按钮、输入、弹层、图标规范。
- 安装并接入 TypeScript、Lucide Vue；选择并封装 Reka UI。
- 建立 Playwright 视觉回归基线。
- 对 OpenHuman、Chatbox 做一次“参考实现审计”：记录仓库 commit SHA、参考组件路径、只借鉴的交互原则和明确不复制的代码/资产。
- 定义 XSS/Markdown/上传安全基线和全局错误处理骨架。
- 盘点旧会话、旧错题、旧画像字段和 localStorage Base64 数据，输出迁移清单。
- 起草 Learning Event、Evidence、Message/Streaming DTO，避免 Phase 2/3 再临时发明字段。

验收：基础组件状态完整，浅/深主题一致，无业务页面大改；参考项目的使用边界和旧数据迁移清单已落文档。

### Phase 1：App Shell 与首页（3–5 天）

- 重写侧栏和移动导航。
- 删除 `FeatureCards` 和首页六卡区域。
- 首页改为空白对话。
- 新建统一 `AgentComposer`。
- 解决空会话自动持久化问题。

验收：打开产品后首屏只有真实主任务；可以发送文字和图片进入会话。

### Phase 2：对话体验（5–8 天）

- 拆分用户消息、AI 消息、操作栏和公式块。
- 重构流式 store，移除直接 DOM/`innerHTML` 更新。
- 完成自动滚动、停止、重试、部分失败和移动端。
- 增加错题原因确认流程。
- 增加知识点/依据检查器框架。
- 落地 message/generation/client_message_id 和流状态机；发送接口具备幂等保护。
- 流式 Markdown/KaTeX 改为 block-level 增量渲染，完成块不重复解析。
- 落地 `direct_answer / guided / practice` 教学上下文和“没懂”细分反馈。

验收：长公式回答阅读稳定；SSE 中断保留部分回答并能明确重试/重新生成；只有后端支持 checkpoint 时才标记为断点续传；加入错题不产生伪错误原因。

### Phase 3：画像 API 与画像页（7–12 天，Learner Model V1）

进入条件：Learning Evidence Model、Mastery Model V1、Learning Event Schema 已冻结并通过语义测试。若条件未满足，不开始大规模画像 UI。

- 新增 overview、graph、evidence、timeline 接口。
- 落地画像摘要、知识树和证据检查器。
- 接入 Cytoscape.js 图谱，并按 OpenHuman 的“Navigator + Graph/Tree + Inspector”工作区思想实现学习画像探索。
- 增加紧凑学习活动热力图，只统计有教学意义的 LearningEvent。
- 加入证据等级、解释和用户纠错。
- 移除 UI 中的 `cognitive_style`。

验收：每个画像状态均可追溯到真实证据；无数据时不显示假百分比。

### Phase 4：知识地图与错题闭环（5–8 天）

- 统一知识地图视觉和节点状态。
- 对接知识点学习、exit ticket 与画像更新；exit ticket 只新增高质量证据，不允许一次做对直接改为“已掌握”。
- 相似题生成至少接收 `skill + difficulty + 当前错误原因/训练目标`，优先做针对性练习，而不是仅替换数字。
- 重做错题筛选、复习队列和再测结果。
- 若现有题库与判分能力允许，可加入小规模“基础检测”入口作为画像冷启动；若数据和题库条件不足，明确延后，不用 LLM 随机生成一套检测冒充标准测评。
- 从对话、画像、知识地图和错题之间双向跳转。

验收：用户能完成“提问 → 知识点 → 练习 → 错题/结果 → 画像更新”的闭环。

### Phase 5：质量与发布（3–5 天）

- 完成响应式、键盘、屏幕阅读器基本检查。
- 优化 bundle、消息长列表和图谱性能。
- 修复视觉回归。
- 删除废弃组件和未使用样式。
- 更新启动、开发和界面说明文档。

---

## 16. 文件级改造建议

优先替换或拆分：

- `frontend/src/views/HomeView.vue`
- `frontend/src/views/ChatView.vue`
- `frontend/src/components/layout/AppShell.vue`
- `frontend/src/components/home/FeatureCards.vue`：删除引用后移除。
- `frontend/src/components/home/WelcomeHero.vue`：删除或仅保留极少文案能力，不作为独立大区块。
- `frontend/src/components/home/ChatInput.vue` 与 `frontend/src/components/chat/InputArea.vue`：合并为 `AgentComposer.vue`。
- `frontend/src/components/chat/MessageItem.vue`：拆为 User/Assistant/Actions/MathBlock。
- `frontend/src/stores/chatStore.js`：迁移为 TypeScript 并拆分流状态和输入草稿。
- `frontend/src/styles/variables.scss`、`themes.scss`、`global.scss`：收敛到语义 Token。
- `frontend/src/components/knowledge/KnowledgeGalaxy.vue`：保留为实验性 3D 视图，不作为默认视图。

新增：

- `frontend/src/views/ProfileView.vue`
- `frontend/src/api/profile.ts`
- `frontend/src/stores/profileStore.ts`
- `frontend/src/components/profile/*`：至少包含 `LearningNavigator`、`LearningActivityHeatmap`、`ProfileGraph`、`ProfileTree`、`ProfileTimeline`、`EvidenceInspector`。
- `frontend/src/components/conversation/*`
- `frontend/src/components/ui/*`
- `frontend/src/styles/tokens.css`

后端建议修改：

- `app/api/profile_api.py`：新增当前用户 overview、graph、evidence、timeline 接口。
- `app/services/profile_service.py` 或新增聚合 service：统一计算证据等级和图谱 DTO。
- `app/services/skill_aggregator.py`：明确“接触”与“作答证据”的权重边界。
- `app/services/profile_analyzer.py`：不再向产品 UI 输出无法验证的认知风格结论。

---

## 17. 验收标准

### 17.1 产品与教学逻辑

- [ ] 首页不存在六功能卡或等价的功能宫格。
- [ ] 普通提问不会直接增加知识掌握度。
- [ ] 仅上传题目不会被记录成“用户答错”。
- [ ] 错误原因由用户选择/确认，系统建议不得伪装成事实。
- [ ] 只阅读知识内容不会直接标记已掌握。
- [ ] 画像不展示解题风格、认知风格、专注力或纸上过程推断。
- [ ] 每个掌握状态都能查看证据和更新时间。
- [ ] 数据不足时不显示误导性的 0% 或精确小数。
- [ ] 看过完整解答后的作答与完全独立作答不会被当成同等强度的掌握证据。
- [ ] 使用提示后做对会记录提示使用情况，而不是伪装成独立正确。
- [ ] 同一模板题的重复作答不会单靠数量把证据等级推到“稳定判断”。
- [ ] exit ticket 做对只产生证据，不直接永久标记为“已掌握”。
- [ ] 用户可以查看“为什么是这个状态”，并纠正影响画像的错误证据。

### 17.2 视觉与交互

- [ ] 首页、对话、画像、知识地图和错题属于同一视觉系统。
- [ ] AI 回答无大面积卡片/气泡包裹。
- [ ] 页面没有结构性 Emoji、彩色渐变卡堆叠或自动旋转背景。
- [ ] 桌面 1440px、1024px，移动 390px 下布局完整。
- [ ] 所有按钮具备 hover、focus、disabled、loading 状态。
- [ ] 所有弹层使用统一组件并管理焦点。
- [ ] 深色模式不是简单颜色反转，公式和图谱对比度合格。
- [ ] 画像工作区具备可搜索/可筛选导航、图谱/树/时间线和证据检查器，但视觉与代码均不是 OpenHuman 的一比一复制。
- [ ] 手机端画像默认有稳定树/列表入口，不强迫用户操作复杂关系图。

### 17.3 功能

- [ ] 文本、图片题目发送和停止生成可用。
- [ ] 网络失败、SSE 中断、图片识别失败都有恢复路径。
- [ ] 对话草稿按会话保存。
- [ ] 用户可以从回答定位到知识点。
- [ ] 用户可以从知识点开始练习。
- [ ] 用户可以将题目加入错题本并补充原因。
- [ ] 练习/复习结果可以回写画像。
- [ ] 图谱、树和时间线共享同一真实数据源。
- [ ] 重复点击发送、网络重试不会生成重复用户消息。
- [ ] OCR 结果允许用户查看；识别错误时可修正或仅发送原图+文字。
- [ ] 旧错题无错误原因时显示“待补充”，不得由前端自动补一个原因。

### 17.4 性能与质量

- [ ] 首页不加载图谱或 Three.js chunk。
- [ ] 100 条消息滚动与输入保持流畅。
- [ ] 流式 Markdown/KaTeX 不逐 token 全量重渲染。
- [ ] 核心流程具备自动化测试。
- [ ] 四个目标宽度具备视觉回归截图。
- [ ] `npm run build` 和测试通过。
- [ ] Markdown/XSS 恶意输入测试通过；AI 输出与用户输入均不能注入可执行脚本。
- [ ] 中长回答 streaming 时，仅当前未完成 block 重新解析，已完成 block 不反复做 KaTeX/Markdown 全量渲染。
- [ ] 图谱使用小/中/大真实数据基准完成性能记录，而不是用固定节点数拍脑袋判断。

---

## 18. 测试场景

1. 首次进入、无历史、无画像数据。
2. 有历史会话但无正式练习证据。
3. 上传图片题，不填写自己的答案。
4. 上传图片题并说明自己的错误步骤。
5. AI 回答包含多段 LaTeX、表格和代码。
6. 流式生成中途断网。
7. 用户向上滚动后 AI 继续生成。
8. 同一道题加入错题本并选择错误原因。
9. 知识点只有 1 条证据。
10. 知识点拥有跨日期的 15 条有效证据。
11. 删除一条关键错题证据后画像重算。
12. 图谱库加载失败并降级到知识树。
13. 手机端打开知识点详情 bottom sheet。
14. 纯键盘完成新对话、发送、打开画像和查看证据。
15. 浅色/深色主题下查看复杂公式。
16. 学生只问过一道导数题，没有作答证据：状态仍为“接触过”。
17. 学生先查看完整答案再提交正确：该记录不得等价于独立正确。
18. 学生使用两次提示后答对：记录 `hint_count`，证据强度低于独立完成。
19. 学生连续完成大量高度相似模板题：`raw evidence count` 增长，但稳定性不能仅由数量触发。
20. 同一条发送请求因网络重试重复到达：后端按 `client_message_id` 幂等处理。
21. AI 输出包含 `<script>`、危险链接或恶意 HTML：页面不执行。
22. 上传伪装扩展名图片、SVG 或异常大图：服务端拒绝并给出可恢复错误。
23. 旧错题没有 error reason：正常展示且标记“待补充原因”。
24. OpenHuman/Chatbox 参考实现更新后：本项目仍以记录的 commit SHA 和本规范为准，不随上游 UI 自动漂移。
25. 手机端打开画像：默认可用树/列表浏览全部关键信息，图谱不是唯一交互。

---

## 19. 风险与处理

### 风险 1：现有数据不能支持完整画像

处理：先显示“接触过”和“数据不足”，不要为了页面丰满伪造掌握度。通过系统内练习和复习逐步积累证据。

### 风险 2：画像图谱节点过多

处理：默认只加载当前课程或当前局部；证据不作为全部节点展开；提供树视图和搜索。

### 风险 3：一次重构范围过大

处理：严格按 Phase 1–4 纵向交付，每阶段保持可运行；不要同时重写所有页面和后端。

### 风险 4：旧组件样式污染新界面

处理：新 App Shell 下使用新的语义 Token 和组件命名空间，逐页迁移后删除旧全局变量。

### 风险 5：AI 自动分类产生错误画像

处理：自动分类只作为建议；影响画像的重要错误原因和知识点关联允许用户确认或纠正。

### 风险 6：为了“像 OpenHuman/Chatbox”导致技术栈污染或许可证风险

处理：只记录可借鉴的交互原则和截图/组件路径；Vue 3 独立实现。默认不复制源码、CSS、图标和品牌资产；如未来确需复用源码，先做许可证兼容性评估。

### 风险 7：掌握度出现虚假精确

处理：证据不足时显示状态而非小数；可靠性不足时不展示 `68%` 这类容易被理解为测量精度的数字。内部可保留连续分数用于排序，但 UI 文案服从证据等级。

### 风险 8：AI 辅导变成“自动给答案”

处理：区分 direct_answer、guided、practice；系统练习默认逐层提示，用户明确要求完整讲解时允许直接解释，避免僵硬的苏格拉底式反问。

---

## 20. 成功指标

产品指标：

- 首页首次提问完成率提高。
- 从回答进入知识点或练习的比例提高。
- 错题补充错误原因的完成率提高。
- 推荐下一步的接受率和完成率提高。
- 画像证据查看率和纠错率可追踪。
- 用户完成“提问—练习—画像更新”闭环的比例提高。

体验指标：

- 用户能在可用性测试中准确解释“接触过”和“已掌握”的区别。
- 用户能在 10 秒内找到当前最需要复习的知识点。
- 用户能理解画像状态的依据，而不是将其视为黑箱评分。
- 核心界面在 390、768、1024、1440px 下无关键内容截断。

上述产品指标必须有对应事件埋点定义；没有事件数据时不得在复盘中主观宣称“提升”。

技术指标：

- LCP `< 2.5s`。
- INP `< 200ms`。
- 核心流程无高优先级可访问性错误。
- 视觉回归和核心 E2E 测试纳入提交检查。

---

## 21. Trae Work 开发约束

将本文档交给 Trae Work 时，同时附上以下指令：

1. 开发前先阅读现有 Vue 路由、ChatView、HomeView、AppShell、chatStore、profile API、memory API、knowledge API 和 error-book API。
2. 不修改与当前阶段无关的后端业务。
3. 不覆盖工作区中用户已有的未提交修改。
4. 每个 Phase 独立提交可运行结果，并提供改动文件清单、截图、测试结果和剩余问题。
5. 不擅自增加新功能、营销模块、统计卡、游戏化模块或动画。
6. 不使用 mock 画像作为正式页面数据；后端未完成时显示真实空状态。
7. 任何 mastery、错误原因和推荐结果都必须说明来源，禁止仅在前端计算伪业务值。
8. 所有新增组件使用 TypeScript；旧 JavaScript 按触及范围渐进迁移。
9. 先交付 Phase 1 的高保真静态界面供确认，再接入全部业务逻辑。
10. Phase 1 未通过视觉确认前，不开始大规模建设画像图谱。
11. 开工前阅读并记录以下参考实现（以当时 `main` 的具体 commit SHA 为准）：`tinyhumansai/openhuman` 的 MemoryNavigator、MemoryHeatmap、MemoryGraph 与 Memory Tree/Obsidian memory 文档；`chatboxai/chatbox` 的 Sidebar、SessionList 和消息列表相关组件。
12. 参考项目的目的是提取交互原则。禁止把 React 组件、Mantine/MUI、Pixi.js 技术栈直接塞入现有 Vue 项目；禁止为了模仿参考项目进行框架重写。
13. 不复制 OpenHuman/Chatbox 的源码、CSS、品牌资源、图标和图片；若确需源码级复用，先停止开发并完成许可证兼容性评估。
14. 每次依据参考项目做 UI 决策时，在 PR/提交说明中写清“参考了什么交互原则、知微为什么这样改、与原实现有哪些不同”。
15. Phase 2 前确认 Message/Streaming Protocol；Phase 3 前确认 Learning Evidence Model、Mastery Model、Learning Event Schema；未确认不得由 Agent 自行发明临时字段。
16. 不将 mastery、confidence、difficulty、error reason 等核心业务逻辑放入 Vue 组件内部。组件只消费后端 DTO 或明确的前端展示映射。
17. 任何为了“视觉丰满”新增的热力图、趋势、数字卡都必须能从真实 LearningEvent 计算；无数据时显示空状态。
18. 如果参考项目的最新实现与本文档冲突，以本文档冻结的教育逻辑、Vue 技术基线和数据可信度规则优先。

---

## 22. 最终产品判断标准

重构成功并不是“页面更丰富”，而是：

- 用户打开后马上想输入问题。
- 数学推导长时间阅读不疲劳。
- 每个按钮都与下一步学习行为有关。
- 页面不存在为了填空而出现的卡片和数据。
- 系统诚实区分知道的、推断的和暂时不知道的。
- 画像不是性格测试，而是一张由练习、错题和进度逐渐形成的数学知识证据图。
- 记忆可视化不是装饰图；用户能从任一状态追溯到“哪些证据导致了这个判断”，并有纠错路径。
- 产品可以有 OpenHuman 的“透明记忆感”和 Chatbox 的“稳定工作台感”，但最终仍一眼看得出它是知微的数学学习系统。

---

## 23. 开源前端参考实现与复用边界

### 23.1 参考仓库

本项目允许 Trae Work 在开发过程中阅读以下公开仓库，以获得当前真实实现的交互参考：

- `tinyhumansai/openhuman`
  - 重点：Memory Tree / Obsidian Memory 文档。
  - 重点组件：`MemoryNavigator`、`MemoryHeatmap`、`MemoryGraph` 及其 Memory Workspace 相关组合。
  - 借鉴目的：将“记忆不是黑箱，而是可浏览、可搜索、可追溯、可纠正的数据结构”迁移为数学学习画像原则。
- `chatboxai/chatbox`
  - 重点组件：`Sidebar`、`SessionList`、消息列表及小屏侧栏处理。
  - 借鉴目的：成熟聊天工作台的侧栏、会话恢复、搜索、响应式和低干扰内容布局。

开发 Agent 必须在项目文档/PR 中记录实际查看的 commit SHA。不能只写“参考最新版”，因为上游实现会变化。

### 23.2 可以借鉴的内容

允许：

- 信息架构。
- 三栏/双栏布局关系。
- 导航层级。
- 搜索与筛选交互。
- 图谱/树/列表之间的视图切换方式。
- 节点选择、pan、zoom、fit/reset、检查器展开等交互模式。
- 桌面持久侧栏与移动端临时抽屉的响应式原则。
- 空状态、错误态、loading 的产品处理原则。

### 23.3 默认禁止直接复用的内容

除非另行完成许可证与工程评估，否则禁止：

- 复制 React/TSX 组件到本项目。
- 复制 CSS、design tokens 或布局数值并进行近似换皮。
- 复制品牌名、Logo、专有图标、插画、截图资产。
- 为复用参考代码而引入 React runtime、Mantine、MUI、Pixi.js 等与现有 Vue 体系重复的 UI/runtime 依赖。
- 以“OpenHuman 就这样做”为理由覆盖知微已经冻结的教育数据边界。

### 23.4 OpenHuman → 知微的语义映射

| OpenHuman 记忆概念 | 知微对应概念 | 是否直接照搬 |
|---|---|---|
| memory source | 学习证据来源：练习/错题/复习/exit ticket | 只借鉴信息组织 |
| topic/entity | 数学知识点/章节/课程 | 使用知微稳定 skill_code |
| memory heatmap | 有教学意义的学习活动热力图 | 借鉴形式，重写统计口径 |
| memory graph | 个人知识掌握关系图 | 借鉴交互，不照搬 force layout |
| memory navigator | 学习导航与多条件筛选 | 借鉴结构 |
| memory detail | Evidence Inspector | 借鉴“可追溯”原则 |
| editable memory | 用户纠正证据关联/错误原因 | 借鉴“可纠正”原则 |

### 23.5 为什么 V2.1 不直接采用 OpenHuman 的图谱渲染技术

OpenHuman 当前记忆图面向较自由的记忆网络，采用力导向布局，并存在 WebGL/Canvas 类渲染优化需求；知微首版核心图是课程技能 DAG/层级图，节点范围默认受课程或章节限制。两者的问题结构不同。

因此 V2.1 的现实方案是：

1. 继续使用已选定的 Cytoscape.js。
2. 默认层级/前置关系布局。
3. 证据放在 Inspector/List，不把每条错题、每条消息都画成节点。
4. 按路由懒加载 Cytoscape.js。
5. 用真实数据做性能基准。
6. 只有基准失败才评估 Pixi.js/WebGL 等替代技术。

这比为了“像 OpenHuman”提前引入第二套渲染体系风险更低。

---

## 24. Learning Evidence Model V1

### 24.1 目标

画像系统的最小单位不是“聊天次数”，而是 `LearningEvidence`。任何 mastery 变化必须能够追溯到一组明确的 LearningEvidence。

普通提问、打开页面、阅读回答默认只形成 exposure/activity 记录，不直接形成 mastery evidence。

### 24.2 建议数据结构

```ts
interface LearningEvidence {
  id: string
  user_id: string
  skill_code: string
  item_id?: string
  event_id: string
  evidence_type:
    | 'independent_attempt'
    | 'hinted_attempt'
    | 'retry_attempt'
    | 'review_attempt'
    | 'exit_ticket'
    | 'diagnostic_attempt'
  result: 'correct' | 'partial' | 'incorrect'
  difficulty?: 'basic' | 'standard' | 'advanced' | number
  attempt_index: number
  hint_count: number
  solution_viewed: boolean
  response_time_ms?: number
  source: 'practice' | 'review' | 'knowledge_learning' | 'diagnostic'
  occurred_at: string
  excluded: boolean
  user_confirmed?: boolean
}
```

字段最终以 FastAPI/Pydantic DTO 为准，前端 TypeScript 类型与后端保持同步。

### 24.3 证据强度原则

以下是排序原则，不要求 V1 在前端硬编码具体权重：

```text
独立完成的不同题目
    > 使用少量提示后完成
    > 多次提示/重试后完成
    > 已查看完整解答后的再次作答
```

- `solution_viewed = true` 的当次/紧邻重做不能被包装成完全独立掌握。
- 同一道题或高度同模板题重复多次需要去重/衰减。
- 跨日期、跨题型、不同难度的独立正确比同一会话中批量重复更能提高稳定性。
- 作答时间只在开始/提交计时完整时使用；异常后台停留不得直接解释为“做题慢”。
- 普通聊天分类可形成 `exposure`/接触记录，但不进入 mastery 强证据集合。

### 24.4 raw evidence 与 effective evidence

API 至少允许区分：

- `evidence_count`：原始有效证据记录数。
- `effective_evidence_count`：经过重复题、提示、重试、答案暴露、多样性等规则折算后的有效证据量。

证据等级优先依据 effective evidence 与时间/多样性条件，而不是简单按数据库行数计数。

### 24.5 错误原因结构

V2.1 不强制一次性建立复杂二级错误树，避免增加学生记录负担。推荐：

```ts
interface ErrorAttribution {
  primary_reason:
    | 'concept'
    | 'formula'
    | 'condition'
    | 'calculation'
    | 'method_selection'
    | 'reading'
    | 'other'
  secondary_reasons?: string[]
  note?: string
  user_confirmed: boolean
  suggested_by_ai?: boolean
}
```

- 初版 UI 主原因保持 6–7 个高频入口。
- 次要原因可多选但非必填。
- 二级 taxonomy 等真实数据积累后再扩充。

---

## 25. Mastery Model V1

### 25.1 目标

Mastery 是后端根据证据计算的学习状态，不是前端“正确率换算百分比”。V1 优先追求可解释和稳定，而不是伪精确。

### 25.2 输入信号

至少允许使用：

- independent/hinted/retry 等证据类型。
- correct / partial / incorrect。
- 题目难度。
- 是否查看答案。
- 提示数量。
- 近期表现。
- 时间衰减/复习到期。
- 跨日期稳定性。
- 题目多样性。

不允许使用：

- 聊天语气。
- 页面停留时长推断专注力。
- AI 主观判断“这个学生聪明/粗心”。
- 仅阅读解释。

### 25.3 UI 状态优先于伪精确分数

主 UI 使用：

- 数据不足。
- 接触过。
- 学习中。
- 待巩固。
- 已掌握/稳定掌握。

后端可以内部返回连续 `mastery_score` 用于排序和推荐，但：

- 数据不足时 UI 不显示 `0%`。
- 低置信时不展示 `0.68` 这类精确小数。
- 需要展示数值时优先使用合理范围或离散状态，并同时显示证据数量和等级。

### 25.4 Exit Ticket

Exit ticket 是高价值独立证据之一：

```text
完成 exit ticket
        ↓
新增 evidence
        ↓
重新聚合 mastery
        ↓
状态可能变化
```

禁止：

```text
exit ticket 正确一次
        ↓
直接永久 mastered
```

### 25.5 状态解释

后端应返回解释所需的结构化 reason，例如：

```json
{
  "status": "needs_review",
  "evidence_level": "reliable",
  "effective_evidence_count": 8,
  "reason_codes": ["recent_errors", "review_due"],
  "last_calculated_at": "..."
}
```

前端再转成学生可理解的文案，不在组件里重新计算业务结论。

---

## 26. Tutoring Policy V1

### 26.1 三种上下文

#### A. direct_answer

适用：

- “完整讲一下这道题。”
- “给我标准解法。”
- 用户明确要求核对答案。

行为：可以直接完整讲解，但仍应标明关键知识点和检查步骤。

#### B. guided

适用：

- “我做到这里不会了。”
- “给我一点提示。”
- 用户已经提供部分过程。

行为：

1. 识别当前卡点。
2. 给最小必要提示。
3. 等待尝试。
4. 仍失败再升级提示。
5. 用户要求时给完整答案。

#### C. practice

适用：系统主动生成的相似题、知识点练习、错题再测、exit ticket。

行为：

- 默认不展示最终答案。
- 提示分层：方向提示 → 关键公式/关系 → 关键步骤 → 完整答案。
- 每次提示使用写入 LearningEvent/Evidence metadata。
- 看过答案后的正确不能伪装成 independent attempt。

### 26.2 “没懂”交互

`没懂` 展开轻量选择：

- 概念没懂。
- 这一步推导没懂。
- 公式/定理来源不清楚。
- 不知道为什么选择这个方法。
- 其他。

目的：改变下一轮解释策略，而不是给用户贴负面标签。

### 26.3 针对性相似题

生成练习的输入至少包含：

```text
skill_code
+ target difficulty
+ 当前训练目标
+ 可选 error_reason
+ 已用题目去重信息
```

不要把“相似题”简化为原题换数字。题目应保持核心技能一致，同时有适当表征变化。

### 26.4 数学答案验证

对可以确定性验证的代数、方程、微积分等内容，后续优先建立：

```text
LLM 生成题目/候选答案
        ↓
确定性数学工具验证（如 SymPy）
        ↓
通过 → 发布给学生
失败 → 重新生成/转人工规则
```

V2.1 不要求所有数学题都能自动验证；几何证明、开放题等无法可靠符号验证的内容必须明确采用不同路径。禁止为了覆盖率伪造“已验证”。

---

## 27. Learning Event Schema

### 27.1 原则

对话、练习、错题、知识点学习不要各自发明互不兼容的“学习记录”。建立统一、可审计的 LearningEvent，画像聚合器消费这些事件。

### 27.2 建议事件类型

```text
QUESTION_ASKED
SKILL_VIEWED
PRACTICE_STARTED
PRACTICE_ATTEMPTED
HINT_USED
SOLUTION_VIEWED
PRACTICE_SUBMITTED
ERROR_CONFIRMED
ERROR_REASON_UPDATED
REVIEW_STARTED
REVIEW_COMPLETED
EXIT_TICKET_COMPLETED
DIAGNOSTIC_COMPLETED
EVIDENCE_CORRECTED
```

普通 `PAGE_OPENED`、闲聊、页面停留不进入 mastery 证据流。

### 27.3 建议公共字段

```ts
interface LearningEvent {
  id: string
  user_id: string
  session_id?: string
  conversation_id?: string
  course_id?: string
  skill_code?: string
  item_id?: string
  event_type: string
  source: string
  occurred_at: string
  metadata: Record<string, unknown>
}
```

- `metadata` 只能存事件特有、非核心查询字段；不能把所有业务字段都塞进 JSON。
- LearningEvent 不等于前端分析埋点。教学证据事件和产品行为埋点可以关联，但职责分开。

### 27.4 学习活动热力图口径

OpenHuman 风格的 heatmap 在知微中只统计以下一种或多种可解释指标：

- 有效练习提交数。
- 完成复习数。
- 已确认错题/纠错数。
- exit ticket 完成数。

默认不统计：

- 打开 App 次数。
- 在线分钟数。
- 发送闲聊数量。

热力图只表达“学习活动发生”，不表达“学习质量高低”。

---

## 28. Message & Streaming Protocol

### 28.1 消息标识

每次用户发送至少需要：

```text
conversation_id
message_id
client_message_id
```

每次 AI 生成至少需要：

```text
generation_id
assistant_message_id
```

`client_message_id` 由客户端生成，用于网络重试幂等。后端必须避免同一 client id 重复创建消息。

### 28.2 SSE 事件建议

```text
message_start
content_delta
metadata
message_end
error
```

`metadata` 可包含本轮知识点关联、工具状态等结构化信息，但不要混在 Markdown 字符串里让前端正则解析。

### 28.3 前端状态机

```text
idle
→ sending
→ streaming
→ completed

streaming → cancelled
streaming → interrupted
sending/streaming → failed
```

### 28.4 中断与重试

- 用户取消：保留已经生成内容，标记 cancelled。
- 网络/SSE 异常：保留部分内容，标记 interrupted。
- 重新生成：创建新的 generation id，不覆盖旧 generation 的审计信息。
- 真正断点续传只有在服务端保存 generation 状态并支持 event id/checkpoint 时才能实现。

### 28.5 Block-level Streaming Renderer

推荐内部结构：

```text
SSE deltas
   ↓
stream buffer
   ↓
block parser
   ├─ completed blocks → immutable render nodes
   └─ active block      → throttled re-render
```

目标是避免 5000 字回答每收到一小段内容就从头运行 Markdown + KaTeX。

---

## 29. Content Security、上传与数学内容可信度

### 29.1 Markdown/XSS

- `markdown-it` 默认关闭原始 HTML。
- 禁止未经 sanitizer 的 `v-html`。
- URL scheme 白名单至少排除 `javascript:` 等危险协议。
- 任何插件都必须评估是否生成不受控 HTML。
- KaTeX 不开启不必要的 trust 能力。
- 代码块仅渲染文本，不提供自动执行能力。

### 29.2 图片上传

客户端：

- 选择/拖拽后立即本地预览。
- 校验明显不支持的扩展名和大小。
- 大图可压缩预览/上传版本，但不得因压缩使数学符号不可辨认。
- 多图保留顺序；每张图有独立状态。

服务端：

- 二次校验 MIME 和真实文件类型。
- 默认只允许 JPEG/PNG/WebP。
- SVG 默认禁用。
- 限制尺寸、像素量和文件大小。
- 使用不可预测 object key。
- 访问接口验证文件归属。

### 29.3 OCR

- OCR 文本对用户可见时允许修正。
- OCR 失败保留原图，允许重试或仅发送图片 + 用户文字。
- OCR 结果是“识别结果”，不能自动等于用户答案。

### 29.4 数学答案可信度

- AI 自生成的“相似题 + 答案”不得默认视为已验证。
- 能用确定性工具检查的题型优先做自动验证。
- 工具无法验证时记录 `verification_status = unverified | heuristic | verified` 一类状态，是否向用户展示由产品策略决定。
- 高风险错误不应该通过伪造置信度隐藏。

---

## 30. Migration、错误边界、缓存与 TypeScript 治理

### 30.1 历史数据迁移

上线前盘点：

- 历史对话格式。
- Base64 图片。
- 旧错题缺失的 `error_reason`。
- 旧画像 `cognitive_style`。
- 旧 mastery/correct_rate 的语义。

迁移原则：

- 旧错题 `error_reason = null`，UI 显示“待补充原因”。
- 不用 AI 批量伪造用户过去的错误原因。
- `cognitive_style` 可暂留数据库兼容，但新 DTO 不再输出。
- 新写入停止 Base64；旧数据采用兼容读取 + 后台/懒迁移，避免一次阻塞上线。
- 所有 migration 可重复运行或具备版本记录，失败可恢复。

### 30.2 全局错误边界

至少覆盖：

- Vue 组件运行时错误：局部 Error Boundary，不让整个 App 白屏。
- route/chunk 动态加载失败：提供刷新/重试入口。
- API timeout / network / 5xx：统一错误类型和用户可读文案。
- 图谱失败：降级到树/列表。
- 图片/OCR 失败：保持草稿和附件。

错误日志必须脱敏。

### 30.3 缓存

- mastery/profile 以后端为真值。
- `overview/tree/graph` 可短期缓存。
- 学习写事件成功后，使相关 profile cache 失效。
- 不使用 localStorage 长期缓存整套画像来规避后端接口。
- 草稿是例外，可按会话持久化。

### 30.4 TypeScript 治理

- 所有新增 `.vue/.ts` 逻辑使用 TypeScript。
- 修改旧 JS 文件时，在成本合理且覆盖范围明确时同步迁移；不为了“100% TS”阻塞业务阶段。
- 新增代码禁止无理由 `any`；确有边界不明确时用 `unknown` + 类型收窄。
- FastAPI OpenAPI 稳定后，可评估通过 OpenAPI 生成前端 API types；未建立稳定契约前不强制引入自动生成工具。
- ESLint/TypeScript 检查进入 CI 或至少进入提交前检查。

---

## 31. Analytics、Observability 与迭代优先级

### 31.1 产品埋点

至少定义：

```text
conversation_started
question_submitted
answer_completed
answer_cancelled
answer_interrupted
mark_not_understood
knowledge_point_opened
practice_started
practice_submitted
hint_used
solution_viewed
error_added
review_completed
profile_opened
evidence_opened
evidence_corrected
recommendation_clicked
recommendation_completed
```

埋点公共维度可包括：

```text
anonymous/user id（按隐私方案）
session id
course id
skill code
source surface
timestamp
```

禁止把完整题目、AI 完整回答、图片内容作为默认分析事件 payload。

### 31.2 技术可观测性

至少能定位：

- API 错误率与主要错误码。
- SSE interrupted rate。
- 图片/OCR 失败率。
- 前端未捕获异常。
- route chunk 加载失败。
- Web Vitals（LCP、INP 等）。
- 图谱真实数据基准的首绘与交互性能。

### 31.3 P0 / P1 / P2

#### P0：当前重构必须完成

工程：

- XSS/Markdown 安全。
- block-level streaming。
- 全局错误边界。
- 历史数据迁移方案。
- 上传安全。
- message idempotency。

教学/数据：

- Learning Evidence Model。
- Mastery Model V1 契约。
- Learning Event Schema。
- Tutoring Policy。
- independent / hinted / solution-viewed 证据区分。
- exit ticket 不直接等于 mastered。

#### P1：第一轮核心闭环后补充

- 画像/课程数据缓存失效策略完善。
- 图谱真实性能预算与优化。
- OCR 手动修正体验。
- 多图上传完整状态机。
- 推荐难度梯度。
- 错误原因多标签。
- 产品埋点与错误监控完善。
- 可选：桌面侧栏宽度调整（需可用性验证后再做）。

#### P2：验证核心闭环后再做

- 更细错误二级 taxonomy。
- 综合应用/跨知识点练习。
- 元认知反思问题。
- 错题/学习资料导出打印。
- 更多题型与更成熟的自动判分。
- 更广的数学答案确定性验证覆盖。

#### Backlog：当前不因“工程完整”而提前建设

- 完整 i18n 产品化。
- PWA/大规模离线模式。
- 固定学习时长/专注提醒。
- 为了视觉效果升级 WebGL 图谱。
- 教师后台、排行榜、社区、勋章。

这些功能不是永远不做，而是当前没有足够证据证明其价值高于核心学习闭环。

