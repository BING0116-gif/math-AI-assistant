# 知微前端视觉重构方案（Design System V4 · 翡翠青 × 活力橙）

> **版本**：v1.0 · 2026-09-29
> **视觉基准**：`design-preview/` 下 `home.html / dashboard.html / chat.html / error-book.html / profile.html`（含 `screenshots/` 定稿截图）+ `mock.css`（令牌源）+ `anim.js`（动效源）+ `nav.js`（交互源）
> **状态**：已定稿，待执行。配色经五轮评审定案：翡翠青品牌色 + 活力橙行动色（白字，用户拍板）。
> **执行方式**：后续任一会话输入「按 `design-preview/REFACTOR_PLAN.md` 执行 P0」（P1…P6 同理），按本文档逐阶段实施。

---

## 1. 目标与非目标

### 1.1 目标
1. 将现有三代并存的样式体系（`tokens.css` V3.0 / `themes.scss` / `variables.scss`）收敛为**单一 V4 令牌源**，全站无硬编码颜色残留。
2. 以 `design-preview/` 原型为唯一视觉基准，重构 AppShell 与全部 27 个视图的视觉层。
3. 图表（ECharts）与知识图谱（Cytoscape/Three.js）全面主题化：读令牌取色、跟随暗色模式、带入场动画。
4. 建立**开屏入场动效系统**（数字滚动 / 曲线描绘 / 柱条生长 / 热力波浪 / 环形扫描 / 雷达绽放），切换页面即重放，遵循 `prefers-reduced-motion`。
5. 统一图标语言为 lucide-vue-next（依赖已存在，当前未使用），清除字符图标与手写 SVG 混用。
6. 清理孤儿组件与未使用依赖，使 `npm run test`（42 个测试）与 `npm run build` 全程保持绿色。

### 1.2 非目标（硬性边界）
- **不改任何 API 契约**：`src/api/` 下 11 个模块的请求/响应结构、路径、鉴权注入方式零改动。
- **不改路由路径与守卫语义**：`router/index.js` 的路径、`requiresAuth/requiresAdmin`、重定向规则不动（仅允许换组件内部实现）。
- **不改业务逻辑与状态语义**：8 个 store 的状态与动作签名不动；视图仅替换模板结构与样式。
- **不引入新 UI 框架/CSS 框架**：Element Plus 按需注册模式保留，无 Tailwind/unplugin 引入。
- 不做信息架构调整（导航 6 项与路由一一对应不变）。

---

## 2. 现状诊断（重构依据）

| # | 问题 | 证据 | 方案对应 |
|---|---|---|---|
| A | 三代样式体系并存，互相打架 | `tokens.css`(V3.0, 279行) + `themes.scss`(legacy `--color-*`, 104行) + `variables.scss`(SCSS, 27行)；`$sidebar-width:248px` vs token `--sidebar-width:250px` | P0 收敛为 V4 单源（§4.2） |
| B | 主色漂移残留 | `ProfileView.vue` 图表 fallback `#416B56`（旧墨绿）vs 现靛紫 `#5B52C9` | P0 令牌化后消除 |
| C | 图表硬编码色，不随主题 | Dashboard heatmap visualMap `['#F3F2FA'…'#5B52C9']`；两视图 `getCSSVar()` 仅 init 时快照、无主题重绘 | P3（§7） |
| D | 知识图谱完全脱离令牌 | `KnowledgeGraph2D.vue` JS 段 53-70 行 graphStyle() 约 20 个硬编码色 + scoped 段固定深色 UI；`KnowledgeGalaxy.vue` three.js `typeColors/0x0B1924` 等 | P3（§7.3） |
| E | 间距/圆角/字号不守网格 | `ErrorBookView.vue` 26 处裸值圆角（2px/3px）、内容宽 1280 vs token 820；各页滚动条颜色不一 | P2 逐视图重写（§6） |
| F | 图标语言混杂 | 文本字符（→/✓/·）、手写 inline SVG、lucide 依赖闲置 | P1/P2 统一 lucide（§6.4） |
| G | 孤儿组件与死依赖 | 孤儿 12 个：`home/`整组、`chat/InputArea`、`common/{MathRenderer,ThemeToggle,ToastMessage}`、`errorBook/{ErrorFilter,ErrorStats}`、`ui/{BaseButton,EmptyState,StatusBadge}`；未使用依赖 `vue-echarts/marked/reka-ui` | P5 清理（§13） |
| H | 字体声明未加载 | `index.html` 无任何 web font，Inter/Space Grotesk 仅是字体名 | P0 字体接入（§3.2） |

---

## 3. V4 设计令牌规范（唯一视觉事实源）

> 来源：`design-preview/mock.css` 定稿值。命名沿用原型，降低映射成本。P0 起新代码一律用 V4 名；V3 旧名以别名层兼容（§4.2），P5 删除。

### 3.1 色彩令牌（亮 / 暗）

| V4 令牌 | Light | Dark | 用途 |
|---|---|---|---|
| `--bg` | `#F4F5F8` | `#0B0D12` | 应用画布 |
| `--bg-soft` | `#FAFAFC` | `#0E1117` | 次级画布 |
| `--side` | `#FAFAFC` | `#0E1117` | 侧边栏底色 |
| `--surface` | `#FFFFFF` | `#14171F` | 卡片/面板 |
| `--surface-2` | `#F7F8FA` | `#1A1E29` | 卡片内嵌面/输入底 |
| `--ink-1` | `#171923` | `#E8EAF2` | 主文字 |
| `--ink-2` | `#565D6D` | `#9CA3B2` | 次文字 |
| `--ink-3` | `#8A91A0` | `#6B7280` | 辅助文字/说明 |
| `--ink-4` | `#B8BDC9` | `#4A505D` | 占位/禁用文字 |
| `--border` | `rgba(23,25,35,.08)` | `rgba(255,255,255,.08)` | 发丝线边框 |
| `--border-strong` | `rgba(23,25,35,.15)` | `rgba(255,255,255,.17)` | 强边框/输入框 |
| `--brand` | `#0B7A5E` | `#45C8A0` | **品牌翡翠青**：导航激活、链接、进度条默认、图表主系列、雷达、热力、XP、Logo、brand 标签 |
| `--brand-strong` | `#08604A` | `#6FD9BB` | brand hover / 渐变深端 |
| `--brand-text` | `#08604A` | `#7DDFC0` | 白底上的品牌色文字（≥4.5:1） |
| `--brand-soft` | `rgba(11,122,94,.10)` | `rgba(69,200,160,.14)` | brand 浅底（标签、chip hover） |
| `--brand-soft-2` | `rgba(11,122,94,.16)` | `rgba(69,200,160,.22)` | brand 选中底 / 雷达填充 / 热力 l1 |
| `--accent` | `#F4570A` | `#F4570A` | **行动活力橙**：主按钮底、发送键、用户气泡、打卡、紧急提示底 |
| `--accent-bright` | `#F4570A` | `#F4570A` | 无文字图形用（“今天”复习条等），与 accent 同值保留 |
| `--accent-strong` | `#E04E08` | `#E04E08` | accent hover |
| `--accent-text` | `#C2410C` | `#FFB37E` | **白底上的橙色小字**（“今日待复盘 9”、pill 文字，≥4.5:1）——橙底上的文字不用它 |
| `--accent-soft` | `rgba(244,87,10,.10)` | `rgba(255,154,87,.15)` | 橙浅底（pill、图标 chip） |
| `--accent-soft-2` | `rgba(244,87,10,.16)` | `rgba(255,154,87,.22)` | 橙选中底 |
| `--green` / `--green-soft` | `#1E9E6A` / `rgba(30,158,106,.11)` | `#3FCE93` / `rgba(63,206,147,.13)` | 语义·已掌握 / 正向 delta |
| `--amber` / `--amber-soft` | `#D08700` / `rgba(224,158,52,.13)` | `#E5B567` / `rgba(229,181,103,.13)` | 语义·复习中 / 薄弱项标签 |
| `--rose` / `--rose-soft` | `#DE5A63` / `rgba(222,90,99,.11)` | `#F08088` / `rgba(240,128,136,.13)` | 语义·薄弱 / 负向 delta / 待复盘计数 |
| `--sky` / `--sky-soft` | `#3E8DDD` / `rgba(62,141,221,.12)` | `#6BB2F2` / `rgba(107,178,242,.13)` | 图表分类色（线性代数） |
| `--teal` / `--teal-soft` | `#2FA79B` / `rgba(47,167,155,.12)` | `#4FC3B4` / `rgba(79,195,180,.13)` | 图表分类色（概率论/错因条） |
| `--violet` | `#2BB08C` | `#5ED4AE` | 渐变辅端（XP 条 brand→violet） |
| `--glow` | `0 1px 2px rgba(244,87,10,.32), inset 0 1px 0 rgba(255,255,255,.18)` | `0 1px 2px rgba(255,154,87,.4), inset 0 1px 0 rgba(255,255,255,.14)` | 主按钮光效 |

**既定决策（用户拍板，记录在案）**：橙底白字对比度 3.4:1（低于 WCAG AA 4.5:1）。补偿措施为落地约束：① 橙底文字一律 ≥14px / font-weight 600；② hover 加深至 `--accent-strong`；③ 纯白底上的橙色**小字**必须用 `--accent-text`（#C2410C）而非 #F4570A；④ 图形元素（非文字）在白底使用需 ≥3:1（#F4570A 为 3.4:1，达标）。

**色彩语义使用规则**（评审时逐条对照）：

| 场景 | 用色 |
|---|---|
| 侧栏/分段控件激活态、链接与“查看更多”、默认进度条、图表主数据系列、雷达/热力/学习节奏、XP 条、Logo、`tag-soft-accent` 类标签（知识点/科目/艾宾浩斯）、AI 卡片描边与图标、步骤序号 | `--brand` 系 |
| 主 CTA 按钮（新对话/开始专注/继续学习/开始复习/添加错题）、发送键、**用户消息气泡**、连续打卡火焰、“今日待复习”pill+边框+复习条+统计数字、正确率对比线 | `--accent` 系（橙底一律白字） |
| 已掌握=green、复习中/薄弱项标签=amber、薄弱/待复盘计数=rose、科目分类 tag=sky(线代)/teal(概率论)/brand(微积分) | 语义色 |
| 卡片 hover 边框、链接 hover | `--brand`（不用橙，避免“处处是按钮”） |

### 3.2 字体

| 角色 | 字体 | 接入方式 |
|---|---|---|
| UI 正文/中文 | `"Noto Sans SC", "PingFang SC", "Microsoft YaHei UI", system-ui` | 系统栈（不自托管中文包，体积不可控） |
| 拉丁 UI | `"Inter", ...` | **新增依赖** `@fontsource/inter`（400/500/600/700，OFL 许可，仅 latin 子集） |
| 展示数字/Logo | `"Space Grotesk", ...` | **新增依赖** `@fontsource/space-grotesk`（500/600/700） |
| 等宽/代码 | `"JetBrains Mono", ui-monospace, Consolas` | **新增依赖** `@fontsource/jetbrains-mono`（400/500） |
| 数学公式容器 | `"STIX Two Math","Cambria Math","Times New Roman",serif` | 系统栈（KaTeX 自带字体负责公式本体） |

- 引入位置：`main.js` 在 `tokens.css` 之前 `import '@fontsource/inter/400.css'` 等；执行 `npm run budget` 确认不击穿 bundle 预算（fonts 计入资产，必要时上调 `scripts/check-bundle-budget.mjs` 阈值并在 PR 说明）。
- 数字排版：所有统计数值类元素加 `.num` 工具类（`font-family: var(--font-disp); font-variant-numeric: tabular-nums; letter-spacing:-.02em`）。
- 字号阶梯：`12 / 13 / 13.5 / 14 / 15 / 17 / 20 / 24 / 28 / 30 / 34px`，行高正文 1.6、标题 1.35。

### 3.3 几何与层级

| 令牌 | 值 | 用途 |
|---|---|---|
| `--r-s / --r-m / --r-l / --r-xl` | `8 / 12 / 16 / 20px` | 小件 / 输入与内嵌 / 卡片 / 大容器与 Composer |
| `--r-pill` | `999px` | 胶囊 |
| `--shadow-1` | `0 1px 2px rgba(18,22,33,.05)` | 轻件 |
| `--shadow-2` | `0 1px 2px rgba(18,22,33,.04), 0 6px 20px -8px rgba(18,22,33,.08)` | 卡片默认 |
| `--shadow-3` | `0 16px 40px -14px rgba(18,22,33,.2)` | hover / 浮层（暗色 `0 16px 44px -12px rgba(0,0,0,.6)`） |
| `--space-*` | 4px 网格 `4/8/12/16/20/24/32/40/48` | 全站间距（卡内边距 16-20，区块间 16-24，页头下 22） |
| `--sidebar-width` | `264px`（收起 `68px`） | AppShell（统一旧 248/250/56 三值冲突） |
| `--topbar-height` | `60px`（移动端 `52px`） | AppShell |
| `--inspector-width` | `360px` | 右侧检查器 |
| `--content-max` | `1200px` | 数据页内容宽（首页 hero 居中列 860px） |
| z-index 阶梯 | `0 内容 / 10 sticky / 20 topbar / 30 drawer-mask / 40 drawer / 50 modal / 60 toast` | 全站统一 |

### 3.4 动效令牌（源自 `anim.js` 定稿参数）

| 令牌 | 值 | 用途 |
|---|---|---|
| `--ease-standard` | `cubic-bezier(.22,.61,.25,1)` | 位移/尺寸/描线 |
| `--ease-pop` | `cubic-bezier(.34,1.5,.64,1)` | 圆点/格子弹出（微过冲） |
| `--dur-enter` | `520ms` | 卡片浮入 |
| `--dur-grow` | `820ms` | 柱条宽度生长 |
| `--dur-draw` | `1150ms` | 折线描绘 |
| `--stagger` | `45ms`（卡片）/ `55ms`（条）/ `70ms`（周柱）/ `26ms`（热力列） | 交错延迟 |

---

## 4. 目标架构与文件变更地图

### 4.1 总览

```
src/styles/
  tokens.css        重写  → V4 单一令牌源（含 V3 兼容别名层，P5 删别名）
  global.scss       重写  → 仅保留 reset/滚动条/focus/sr-only/排版工具类
  element-plus.scss 新增  → 从 global.scss 拆出全部 EP 覆盖（--el-* 映射 §9）
  math.scss         新增  → KaTeX 容器/.formula 公式卡/mathlive 主题（§7.4）
  transitions.scss  保留  → 时长改读令牌，删除 glass-effect/glow-pulse 等花哨项
  themes.scss       删除(P5) → legacy --color-* 别名并入 tokens.css 兼容层
  variables.scss    删除(P5) → $sidebar-width 等改由 tokens.css 的 CSS 变量承担
src/composables/
  useEntranceAnimation.ts 新增 → 开屏动效引擎（§8.1）
  useCountUp.ts           新增 → 数字滚动（§8.2）
  useChartTheme.ts        新增 → ECharts 主题注册/切换重绘（§7.1）
src/utils/charts.ts      修改 → 注册 'zhiwei-light'/'zhiwei-dark' 主题（§7.2）
src/components/shell/AppShell.vue 重写（§6.1）
src/components/ui/*      增强（§6.3）
```

### 4.2 V3 → V4 兼容别名层（P0 建立，P5 删除）

`tokens.css` 底部保留一段「LEGACY ALIASES」，把现网仍在消费的 V3 名映射到 V4 值（组件迁移时逐个换成 V4 名，P5 删本段）：

| V3 名（现网在用） | → V4 映射 |
|---|---|
| `--canvas` | `var(--bg)` |
| `--surface`（V3 米白 #FCFBF8） | `var(--surface)` |
| `--accent`（V3 靛紫 #5B52C9） | `var(--brand)` ⚠️ 语义变化：V3 accent 是“品牌主色”，V4 accent 是“行动橙”。迁移时**逐个判断**该处语义（品牌→brand / 行动→accent），禁止盲替换 |
| `--knowledge`（#417E7A） | `var(--brand)` |
| `--learning` | `var(--amber)` |
| `--weak` | `var(--rose)` |
| `--mastered` | `var(--green)` |
| `--text-primary/-secondary/-tertiary` | `var(--ink-1/2/3)` |
| `--el-color-primary` 等 EP 变量 | 见 §9 映射表 |
| `--content-max-width` | `var(--content-max)` |

### 4.3 依赖变更表

| 包 | 动作 | 理由 |
|---|---|---|
| `@fontsource/inter` `@fontsource/space-grotesk` `@fontsource/jetbrains-mono` | **新增**（devDependencies 亦可，因构建期打包） | 原型字体落地，OFL 许可，锁文件更新；`npm run budget` 复核 |
| `marked` | **移除**（P5） | 全项目 0 处 import（markdown 渲染实际用 markdown-it + @mdit/plugin-katex） |
| `reka-ui` | **移除**（P5，需决策点 D3 确认） | 0 处 import；BaseDialog 为自研（Teleport+焦点陷阱） |
| `vue-echarts` | **移除**（P5） | 0 处使用；本方案沿用原生 `init/setOption` 模式 + `useChartTheme` 封装，不引入组件化层 |
| `lucide-vue-next` | **启用**（已存在） | 全站图标统一源（§6.4） |
| `konva` / `three` / `cytoscape*` / `mathlive` / `katex` | 保留 | 手写实验台 / 3D 星系 / 图谱 / 公式输入 / 渲染在用 |

### 4.4 孤儿组件处置表（P5 执行，逐项决策点见 D5）

| 组件 | 处置 | 说明 |
|---|---|---|
| `home/`（ChatInput/FeatureCards/QuickTools/WelcomeHero，共 616 行） | **删除** | HomeView 原型已重写为新结构（hero+composer+recent+continue），旧组件族无人引用；AgentComposer 承担提问入口 |
| `chat/InputArea.vue` | **删除** | 被 AgentComposer 取代（现状 0 引用） |
| `common/ThemeToggle.vue` | **删除** | AppShell 内置主题按钮；新 AppShell 沿用 |
| `common/ToastMessage.vue` | **删除** | 全局提示实际用 ElMessage |
| `common/MathRenderer.vue` | **保留并接线** | LaTeX 渲染基件（有测试），MessageItem/LearningResourceCard 迁移时统一走它 |
| `errorBook/{ErrorFilter,ErrorStats}.vue` | **删除** | 新 ErrorBookView 将筛选/统计内联（对照原型），旧件 0 引用 |
| `ui/BaseButton.vue` | **启用** | variant 映射 §6.3，P1 起 shell/核心页按钮统一走它 |
| `ui/EmptyState.vue` | **启用** | 增加 `icon` 插槽后用于各空态 |
| `ui/StatusBadge.vue` | **启用** | 状态色改绑 V4（`--amber/--rose/--green`），掌握度语义全站统一 |

---

## 5. 分阶段执行计划

> 每阶段 = 1 个独立 PR（分支 `feat/design-v4` 自 `wip-2026-09-07` 拉出），独立可合可回滚。完成定义统一见 §12.4。估时为单人净工时。

### P0 设计令牌与基础设施（约 1 天）
**做**：重写 `src/styles/tokens.css` 为 V4（§3.1/3.3/3.4 全量变量 + §4.2 兼容别名 + EP 映射暂留原位）；新增 `styles/element-plus.scss`、`styles/math.scss`、`styles/motion.css`；新增三个 composables；`utils/charts.ts` 注册双主题；接入 @fontsource 三包（`package.json` + `main.js`）；`global.scss` 瘦身。
**不做**：不动任何视图模板。
**验收**：`npm run test` 42/42 绿；`npm run build && npm run budget` 通过；亮暗两态下**全站无视觉回归**（兼容层生效——所有页面应与改造前一致或仅色彩微调）；DevTools 中 `--brand/--accent` 在 `:root` 可见且暗色切换生效。
**回滚**：PR revert 即可（无模板变更）。

### P1 AppShell 重写（约 1–1.5 天）
**做**：按 `dashboard.html` 原型重写 `AppShell.vue`（结构对照 §6.1）；顶部具名插槽 `topbar-title/topbar-actions/page-header/inspector` **全部保持不变**；导航 `navItems` 数据结构不变（6 项）；图标换 lucide；新对话/搜索/历史/收起/主题按钮对齐原型；l1 断点(≤1279px) rail、l2 断点(≤768px) 抽屉行为保留；skip-link 保留。
**验收**：23 个使用方视图零模板改动即可正常渲染；`routerGuard` 等测试不涉及 shell 仍绿；手工走查 1440/1280/768/375 四宽度 + 亮暗。
**回滚**：仅 revert AppShell.vue。

### P2 核心六视图（约 3–4 天，顺序固定）
1. `HomeView.vue`（对照 `home.html`：hero-glow、渐变字、居中 Composer（**复用 AgentComposer**，重皮不重写逻辑）、最近对话 3 卡、继续学习 2 卡；删除旧 home/ 孤儿引用如存在）
2. `ChatView.vue` + `conversation/AgentComposer.vue` + `chat/MessageItem.vue` + `FollowUpRecommendation.vue` + `chat/AskStudentCard.vue`（对照 `chat.html`：气泡/定理卡/.formula/引用 chip/消息底栏/Composer 工具行；暗色为默认展示态之一，两种主题都要走查）
3. `DashboardView.vue`（对照 `dashboard.html`：4 KPI 卡+计数动画+迷你 sparkline、趋势卡、章节掌握度、今日任务、AI 洞察卡、打卡热力；图表接入 §7 主题）
4. `ErrorBookView.vue` + `ErrorCard.vue` + `ErrorDetailModal.vue`（对照 `error-book.html`：统计条、segmented 筛选、错题卡、AI 错因画像、复习计划、掌握分布环图）
5. `ProfileView.vue`（对照 `profile.html`：画像头、雷达、留存曲线、学习节奏、AI 解读、掌握分布堆叠条；清除 `#416B56` fallback）
6. `KnowledgeCatalogView.vue` + `KnowledgeLearningView.vue` + `LearningResourceCard.vue`（对照知识星球原型语言：目录卡片、资源卡；图谱本体在 P3）
**验收**：每页与 `screenshots/` 对应定稿图并排比对（布局/间距/色彩/字号）；`useDashboardMetrics/useErrorBookMetrics/useProfileMetrics` 测试不破；数学渲染（KaTeX/mathlive）回归通过；移动端 375px 无横向滚动。
**回滚**：按单视图 revert。

### P3 图表与知识图谱（约 1.5 天）
**做**：§7 全部内容（ECharts 双主题 + 主题切换重绘 + 图表入场动画；KnowledgeGraph2D/KnowledgeGalaxy 令牌化 + 主题跟随）。
**验收**：亮暗切换后 1s 内图表/图谱完成重绘且配色正确；无任何 hex 残留（grep 校验见 §12.3）。
**回滚**：revert P3 涉及文件。

### P4 练习考试 / 笔记 / 登录（约 1–1.5 天）
**做**：`ApplyHubView`（学以致用入口卡）、`ExerciseShell/QuestionAnswer/QuestionNavigator/SubmitOverview`（三套 Session 共用件，一处改三处生效）、`ExamReportView`（119 行，含报告图表走 §7）、`StudentPaper*` 四壳、`NotesLibraryView/NoteWorkspaceView`（Konva 手写层不动，只动周边 UI）、`LoginDialog.vue`（BaseDialog 重皮）。
**验收**：练习→作答→交卷→结果全流程 + 考试 + 组卷手工回归；`errorBookVariant/practiceVariant/assessment` 等 store/api 测试全绿。
**回滚**：按组件 revert。

### P5 Admin 视图 + 大清理（约 1 天）
**做**：`AdminReviewView/AdminPapersView/AdminReadinessView` 重皮（可保守：仅换令牌引用与基础件，保持布局）；删除 §4.4 孤儿组件与 `themes.scss/variables.scss`、删除兼容别名层、移除 `marked/reka-ui/vue-echarts`、tokens.css 删除注释掉的死变量。
**验收**：`grep -rn "themes.scss\|variables.scss\|marked\|reka-ui\|vue-echarts" frontend/src` 零命中；全量测试绿；budget 通过（体积应下降）。
**回滚**：清理 PR 独立，revert 恢复。

### P6 全量 QA 与收尾（约 1 天）
**做**：§12 全量验证矩阵跑一遍；`math-ai-frontend-qa` 流程执行并留档；更新 `frontend/README`（若有）与根 `README.md` 前端截图/说明；本文档标记各阶段完成。
**验收**：§12.4 DoD 全勾。

**总计约 9–11.5 人日**。P0–P2 完成即可对外展示新形象（核心七页占学生流量主体），P3–P6 为完整收口。

---

## 6. 组件迁移细则

### 6.1 AppShell.vue 重写要点（对照 `dashboard.html`）
- 结构：`grid-template-columns: var(--sidebar-width) 1fr`；侧栏 flex 列（brand → 新对话主按钮 → 搜索框(含 `Ctrl K` kbd) → 「学习空间」nav 6 项 → 「最近对话」→ 底部主题行 + 用户卡）；主列 topbar + `#main-content` 内滚。
- 激活态：`.nav-item.active` = `--brand-soft-2` 底 + `--brand-text` 字 + 600 字重；错题项右侧 `--rose` 计数胶囊。
- 品牌标：圆角 9px 渐变方块（`linear-gradient(135deg,#17A98A,#0B7A5E 55%,#08604A)`）内白色 `∑`（Space Grotesk）+ 「知微 / MATH AI ASSISTANT」双行。
- 主题切换按钮沿用 `ui.toggleTheme()`；用户卡静态展示（昵称/等级后续接 profileStore，本方案不改逻辑）。
- `topbar-*` 插槽样式对齐原型 crumb + global-search + bell(dot) + avatar；`.page-header` 插槽保留。
- 保留：skip-link、`prefers-reduced-motion` 降级、`100dvh` + 内滚（聊天页依赖）。

### 6.2 卡片 / 统计 / 标签 / 分段控件（全站原子类，进 `global.scss`）
`.card`（surface+border+radius 16+shadow-2）、`.card-head`、`.stat`（含 hover 上浮 2px+shadow-3）、`.tag`/`.tag-soft-*` 六色系、`.segmented`、`.chip`、`.progress`、`.pill-alert`、`.num`、`.delta`（up 绿/down 玫红）、`.ai-card::before`（brand 渐变描边 + mask 镂空）。这些类在 P0 定义、P2 起消费。

### 6.3 `ui/` 基件增强
- `BaseButton`：variant 重定义 `primary→橙底白字 / secondary→白底 border / ghost→无底 / soft→brand-soft 底 brand-text 字`；尺寸 `sm 30px / md 36px / lg 42px`；radius 10；font 13.5/600；`loading` 复用现有 spinner；focus-visible 2px brand 描边。**启用范围**：P1–P4 迁移到的按钮全部替换；长尾按钮可保留原生写法但必须走令牌。
- `BaseDialog`：radius 20、`--shadow-3`、header/footer 内边距 20/16/20、遮罩 `rgba(9,11,15,.5)`；暗色走 surface 令牌。焦点陷阱逻辑不动。
- `EmptyState`：加 `<slot name="icon">`（默认文档图标 → 各页可传 lucide 图标）。
- `StatusBadge`：色映射改 `mastered→--green / learning→--amber / needs_review→--accent-text / insufficient_data→--ink-3`；形状对齐原型 tag（radius 7 / 11.5px / 600）。

### 6.4 图标规范
- 统一 `lucide-vue-next`，`:size=17 :stroke-width=1.75`（顶栏/导航 17，行内 14–15），`fill:none`。
- 导航映射：学习看板 `LayoutDashboard`、记忆画像 `UserRound`、知识星球 `Network`（或 `Orbit`）、智能笔记 `FileText`、学以致用 `Target`、错题复盘 `BookX`。
- 禁止：emoji 图标、文本符号图标（→/✓）；数学符号 `∑` 仅用于 Logo 与公式工具位。

---

## 7. 图表与可视化规范

### 7.1 ECharts 主题注册（`utils/charts.ts` 扩展）
新增 `registerTheme('zhiwei-light'| 'zhiwei-dark', theme)`，主题 JSON 要点：

```ts
// 共同结构（两套取值来自 §3.1 对应主题）
{
  color: ['--brand值', '--accent值', '--sky值', '--amber值', '--rose值', '--teal值'], // 系列顺序
  backgroundColor: 'transparent',
  textStyle: { fontFamily: 'Inter, "Noto Sans SC", sans-serif' },
  axis: { line: '--border-strong', split: '--border' (dashed) },
  categoryAxis/axisLabel: '--ink-3', valueAxis splitLine dashed,
  tooltip: { bg '--surface', border '--border-strong', text '--ink-1', extraCssText: 'border-radius:10px; box-shadow:var(--shadow-3)' },
  legend: { textStyle '--ink-2', icon 'circle', itemWidth 8 },
}
```
- 调色板语义固定：**系列 1（主数据）恒为 brand 青**，系列 2（对比/正确率）恒为 accent 橙——与原型 trend 图一致。
- heatmap `visualMap` 五档色带改为从令牌计算的青色阶梯：`['--surface-2','--brand-soft-2','rgba(11,122,94,.35)','rgba(11,122,94,.62)','--brand']`（dark 取 dark 值），**废除 `#F3F2FA…#5B52C9` 旧紫阶**。
- `donutChart`：green/amber/rose 三段 + 中心 `--ink-1` 大数字；`barChart`（错因/薄弱）：rose/sky/amber/teal 语义横条。

### 7.2 主题切换重绘（`useChartTheme.ts`）
- API：`const { bindChart, disposeAll } = useChartTheme()`；内部 `watch(() => ui.theme, …)` 触发已注册实例 `setOption(rebuildOptions(), true)`（不 dispose 重建，避免闪烁）。
- 替换两视图中 `getCSSVar()` 一次性快照模式 → `chartVar(name)` 实时取值 + 主题 watch。**顺带清除 Profile 的 `#416B56` fallback**。
- 每图启用 `animationDuration: 900, animationEasing: 'cubicOut'`；折线 `animationDurationFrom: 0` 实现从左向右生长。

### 7.3 知识图谱令牌化
- `KnowledgeGraph2D.vue`：`graphStyle()` 全部改读 `chartVar()`；节点语义映射：mastered→`--green` 系、learning→`--brand` 系、weak→`--rose` 系、locked→`--ink-4` 虚线、selected→`--accent`、predecessor/successor→`--brand-strong/--teal`、边→`--border-strong`、related 虚线→`--amber`。scoped 段的“固定深色面板”改为读令牌（亮色下浅面板、暗色下深面板）。新增 `watch(ui.theme)` 重建样式并 `cy.style().update()`。
- `KnowledgeGalaxy.vue`（three.js）：`typeColors` 改由 `getComputedStyle` 读取令牌转 `0x` 数值（工具函数 `cssVarToHex()`）；背景/Fog `--bg`、灯光 `--brand` 系；`watch(ui.theme)` 重建场景材质。保持 `manualChunks: three` 不变。

### 7.4 数学公式样式（`styles/math.scss`）
- `.formula` 公式卡（surface-2 底 + border + radius 12 + STIX 栈）用于 MessageItem/LearningResourceCard 的展示块。
- KaTeX 容器统一 `.katex-wrap { overflow-x:auto }`（移动端长公式）；mathlive `math-field` 的 `--caret-color/--selection-color` 走 accent/brand。

---

## 8. 动效规范

### 8.1 `useEntranceAnimation.ts`（移植 `anim.js`）
- 签名：`useEntranceAnimation(scope?: Ref<HTMLElement|undefined>, opts?: { disabled?: boolean })`；`onMounted` 后对 scope 内元素按选择器策略执行 WAAPI：
  - `.card/.stat/.err-card/.cont-card/.recent-card` → 浮入（`--dur-enter`，delay `60+i*45`）
  - `.progress>i, .hbar>i` → 宽度 0→目标（`--dur-grow`，delay `180+i*55`，onfinish 清除并取消）
  - `.week-bars .wbar i` → `scaleY(0→1)` origin bottom
  - `.heat i` → 按列 `scale+opacity`（`--ease-pop`，列距 26ms）
  - `[data-count]` → 数字滚动（§8.2）
  - `.donut-wrap circle[stroke-dasharray]` → 扇区扫描；`.radar-poly` → 中心绽放；图表内 circle/tooltip → 延迟弹出
- 硬性规则：`matchMedia('(prefers-reduced-motion: reduce)')` 命中 → 全部跳过；动画 `fill` 结束后必须回写内联终值并 `cancel()`，避免 WAAPI 残留。
- 集成点：6 个核心视图 + ApplyHub 在 `onMounted` 调用；路由切换即重放（vue-router 每次挂载触发）。

### 8.2 `useCountUp.ts`
- 签名：`useCountUp(el, target, { duration=950, decimals=0 })`；rAF + easeOutCubic；reduced-motion 时直接置终值。消费方式：模板 `<span v-countup="{ value: kpi.hours, decimals: 1 }">` 自定义指令或组件内手动调用（P2 实施时二选一，指令式更省模板改动）。

### 8.3 保留与删除
- `transitions.scss` 保留路由过渡 `slide-fade`（时长改读 `--dur-enter`）、`fade/scale/slide-up/list`；删除 `glass-effect/glow-pulse/float-animation/shimmer` 等装饰项。
- 全局 `prefers-reduced-motion` 降级规则保留并覆盖新动效。

---

## 9. Element Plus 对接（`styles/element-plus.scss`）

| EP 变量 | → V4 | 备注 |
|---|---|---|
| `--el-color-primary` 及 `light-3/5/7/9`、`dark-2` | `--brand` 系（light-9=`--brand-soft`） | EP 的 Link/Tabs/Progress/Checkbox 等多为“状态与导航”语义 → 用品牌青 |
| `--el-color-success/warning/danger/error` | `--green / --amber / --rose` | |
| `--el-bg-color / -overlay` | `--surface` | |
| `--el-text-color-primary/regular/secondary/placeholder` | `--ink-1 / --ink-2 / --el 用 --ink-3 / --ink-4` | |
| `--el-border-color / -light / -lighter` | `--border-strong / --border / --border` | |
| `--el-fill-color-light/blank` | `--surface-2 / --surface` | |
| `--el-border-radius-base` | `10px` | |
| `--el-font-family` | `var(--font-ui)` | |

- 组件级覆盖保留现 global.scss 中已有的选择器集（button/input/select/dialog/drawer/tabs/tag/table/timeline/message…），值全部改令牌；`dark/css-vars.css` 继续引入且顺序在本文件之后以便覆写。
- EP 弹层（el-message/dialog）圆角 12–16、边框 1px `--border`、去大阴影改 `--shadow-3`。

---

## 10. 暗色模式规范

- `uiStore.theme` 扩展为 `'light' | 'dark' | 'system'`（`init()` 读取 `matchMedia('(prefers-color-scheme: dark)')` 并监听变更；`math_ai_theme` 旧值 'light'/'dark' 兼容直迁）；`applyTheme()` 保持挂 `<html data-theme>`。
- 消费侧统一走令牌（本方案完成后天然支持）；三个“逃逸点”必须处理：ECharts（§7.2 watch 重绘）、Cytoscape（§7.3）、Three.js（§7.3）。
- 暗色专属校验点：shadow 层级（§3.3 dark 值）、EP dark css-vars 叠加顺序、热力图阶梯、图谱深底面板、图片/插画无白底穿帮。
- 验收：切主题后所有页面无“闪白/闪黑”突变（EP css-vars + 令牌同帧生效），图表 1s 内重绘完成。

---

## 11. 响应式与移动端

- 断点沿用现状：`≤1279px` 侧栏 rail（68px）、`≤768px` 侧栏隐藏 + 汉堡抽屉 + topbar 52px + Inspector 隐藏；新增校验：375px 下看板/错题页统计条改 2×2 网格、KPI 网格 2 列、聊天气泡 max-width 92%。
- 触控：所有可点元素 ≥44×44（导航项/按钮含 padding 达标；`icon-btn` 28px 视觉 + 扩展热区至 44）。
- 移动端 composer 吸底需加 `env(safe-area-inset-bottom)`；viewport meta 追加 `viewport-fit=cover`（P1 一并改 index.html）。
- 长公式/表格横向可滚（`overflow-x:auto`），禁止页面级横向滚动。

---

## 12. 质量保障与验证流程

### 12.1 命令（每阶段 PR 必跑）
```bash
cd frontend
npm run test        # vitest，42 个测试必须全绿
npm run build       # 产出 dist + manifest
npm run budget      # bundle 预算校验（P0 加字体后必须复跑）
npm run dev         # 手工走查（配合后端 docker compose 或既有本地环境）
```

### 12.2 视觉走查矩阵（P2/P4/P6 各跑一轮）
页面集合 = 6 核心视图 + ApplyHub + 1 个 Session 流 + LoginDialog；条件 = {亮, 暗} × {1440, 1280, 768, 375}；比对基准 = `design-preview/screenshots/` 定稿图。Admin 三页在 P5 后补走一轮即可。

### 12.3 硬性静态检查（P3/P5 grep 门禁）
```bash
# P3 后：核心图表/图谱文件零 hex（白名单：字体名、transparent）
grep -rn "#5B52C9\|#416B56\|#5d83aa\|#0B1924" frontend/src && exit 1
# P5 后：legacy 引用清零
grep -rn "themes.scss\|variables.scss" frontend/src && exit 1
grep -rn "from 'marked'\|from 'reka-ui'\|from 'vue-echarts'" frontend/src && exit 1
```

### 12.4 每阶段 DoD
- [ ] `npm run test` 全绿；`npm run build`、`npm run budget` 通过
- [ ] 视觉走查矩阵（该阶段涉及页面）通过，截图与原型并排比对无 8px 级以上偏差
- [ ] 无新增硬编码颜色/裸值圆角/字号（对照 §3 阶梯）
- [ ] 亮暗两态 + 375px 宽度过检
- [ ] 涉及动效的页面开启系统“减弱动态效果”后表现正常
- [ ] PR 描述含：改动范围、截图（前/后）、回滚方式

### 12.5 `math-ai-frontend-qa` 流程（P6 执行）
按该 skill 清单跑：聊天数学渲染、错题本流程、知识学习页、画像页、Dashboard、移动端布局六大块，输出 QA 记录归档到本目录。

---

## 13. 风险与回滚

| 风险 | 概率 | 缓解 | 回滚 |
|---|---|---|---|
| V3 兼容别名遗漏导致某组件崩样式 | 中 | P0 全量 grep 现网消费的 V3 变量名入别名层；每阶段视觉走查兜底 | 该组件临时补别名，PR 内修复 |
| 语义变化点误替换（V3 `--accent`=品牌 → V4 `--accent`=行动） | 中 | §4.2 明确“禁止盲替换”；P2 逐视图评审对照原型 | 单视图 revert |
| 图表重绘闪烁/内存泄漏 | 中 | `setOption(notMerge:true)` 不重建实例；`disposeAll` 在 onUnmounted 调用 | 关闭 watch 重绘，保留手动刷新 |
| 字体击穿 bundle budget | 低 | 仅 latin 子集、按需字重；预算上调需 PR 说明 | 移除 @fontsource，回退系统栈 |
| 孤儿删除误伤（隐式引用） | 低 | 删除前 `grep` 引用确认；42 测试 + build 兜底 | revert 清理 PR |
| EP 大版本行为差异 | 低 | 锁定 ^2.8 不升级 | — |

**分支策略**：自 `wip-2026-09-07` 拉出 `feat/design-v4`，P0–P6 每阶段一个 PR 依序合并；任一阶段可独立 revert，不影响已合并阶段。

---

## 14. 待确认决策点（默认值已给出，可推翻）

| # | 决策 | 默认 |
|---|---|---|
| D1 | 站点 title/favicon 是否随重构改为「知微 · 数学AI助手」+ ∑ 图标（现为“数学AI助手”+📐 emoji） | **改**（P1 顺手，涉及 `index.html` + 路由 title 后缀） |
| D2 | 是否引入 ESLint/StyleLint | **本方案不引入**（避免范围膨胀），作为后续独立任务 |
| D3 | `reka-ui`/`vue-echarts`/`marked` 移除确认 | **移除**（均 0 引用，P5） |
| D4 | 字体自托管 vs CDN | **自托管 @fontsource**（原型用 CDN，产品不可依赖外网） |
| D5 | `home/` 孤儿组件族删除确认 | **删除**（新 HomeView 不消费） |
| D6 | 入场动效是否每次路由切换重放 | **是**（对齐原型体验；如嫌频繁可加 sessionStorage 仅首访播放，P6 微调） |

---

## 15. 附录：原型文件 ↔ 项目落点对照

| 原型 | 对应视图/组件 | 关键迁移件 |
|---|---|---|
| `home.html` | `HomeView.vue` + `AgentComposer.vue` | hero-glow、home-composer、home-cards、cont-grid |
| `dashboard.html` | `DashboardView.vue` | stat-grid、chart-wrap 趋势、bar-row 章节、task、ai-card、heat |
| `chat.html`（暗） | `ChatView.vue` + `MessageItem.vue` + `AgentComposer.vue` | msg-user/msg-ai、formula、cite-chips、step、composer |
| `error-book.html` | `ErrorBookView.vue` + `ErrorCard.vue` + `ErrorDetailModal.vue` | stats-strip、err-card、hbar-row、donut-wrap、pill-alert |
| `profile.html` | `ProfileView.vue` | profile-head、radar、retention、week-bars、kw/堆叠条 |
| `mock.css` | `src/styles/tokens.css` + `global.scss` | 全部令牌与原子类 |
| `anim.js` | `src/composables/useEntranceAnimation.ts` | 动效引擎（参数见 §3.4） |
| `nav.js` | AppShell 内导航逻辑（原型专用的页面跳转映射**不迁移**，真实项目由 vue-router 承担） |

> 执行提醒：动效引擎移植时以本文 §8 的令牌/选择器为准，`anim.js` 仅作参数基准；原型中 `nav.js` 的跨页跳转、`noanim` URL 参数属于 mock 专用，不进入生产代码。
