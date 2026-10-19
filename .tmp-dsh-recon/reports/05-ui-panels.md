# 05 · 桌面版（Web GUI）面板逐讲 + Standard / Minimal / Creator 三种运行模式

> 适用实例：DSH 桌面版 **0.2.1-rc.1**（Electron 外壳 F:\DSH，官方运行时 check out 在 app.asar\dsh\）。
> **证据路径约定**：文中用反引号标注的相对路径，一律相对 C:\Users\HUAWEI\Desktop\math AI assistant\.tmp-dsh-recon\asar\@deepseek-ai\；profile 与外部插件用绝对路径。
> **标注约定**：凡源码/文档里没有依据的点，文中写明「未在源码中找到依据」，不代替读者臆测。

---

## 0. 先建立心智模型（不然面板会看起来像一堆并列功能）

桌面版前端不是「一个页面 + 若干弹窗」，而是 **三栏 AppFrame + 若干「注册出来的席位」**：

- **左栏**：Workspace（工作区）与 Session（会话）的浏览器（侧栏）。
- **中栏**：会话本身。中栏有 **视图环（view ring）**——同一份会话数据可以用不同「视图」渲染，当前出厂有两个：**Chat** 和 **Trajectory（轨迹）**。
- **右栏**：一个「船坞式」面板，里面是**多标签页**（files / terminal / browser / documentpreview / plan 等），标签类型由插件注册。
- **会话头部（Session Header）** 与 **输入框（composer）区域** 是最密集的席位：jobs 按钮、subagent 目录、goal 条、plan 芯片、permission 选择器、agent-preset 标签都在这里。

证据：`dsh-client-ui-layout/README.md`（三栏 AppFrame、右列先让位、布局状态刷新即重置）、`dsh-client-ui-sidebar-right/README.md`（每会话一张 dock 面、两种呈现、展开按钮在会话头部、`ctx.sidebarRight` / `ctx.sidebarRightTabs` 注册表）、`dsh-client-ui-conversation/README.md`（`conversation.view` 环；具体视图如 Chat 是独立包注册的 Definition/Snapshot/View）。

> 讲解时最好的一句话：**「面板 = 某个插件往预留席位里注册的一块 UI」**。这解释了两件事：为什么插件装上/卸掉面板会变；为什么同一个功能可能同时出现在两三个地方（例如 permission 既在设置里也在输入框旁）。

---

## A. 面板逐讲

### A1. 左栏：Workspace / Session 浏览器（侧栏）

- **解决什么问题**：把「一堆会话」组织成「按项目目录分组的历史」，并让新建会话知道「要绑到哪个目录」。
- **界面区域与按钮**：
  - 分组视图 **View options → Group by**：默认 **WorkSpace**（同级平铺工作区），可切 **Workspace Tree**（按注册路径的父子关系嵌套）。子工作区排在父工作区自己的会话之前。
  - 每个工作区可折叠（折叠会隐藏当前会话；祖先文件夹图标仍高亮）。
  - 会话行：标题、未命名占位（「未命名 / Untitled」）、待处理警示点、运行中/子代理活动、时钟标记（有活动中的定时任务）。
  - 行内悬浮按钮与行菜单是**可被插件扩展的 slot 列表**（所以第三方插件能往会话行里加动作）。
  - **Add workspace**（需要组合进来的目录选择器：browse 或 native；没有选择器时该操作不可用）。
  - 排序：**Last updated**（按最近用户提问 / steer 时间倒序，pinned 分区在前）/ **Manual**（拖拽，冻结当时时序）。默认 Last updated，选择记在浏览器本地。
  - **Show more / Show less**：每个工作区初始只显示前 5 个非空会话，水位线可涨不跌，点一次 +5。
- **数据从哪来**：Host 侧 `ctx.workspaceRegistry` 的持久有序工作区清单 + 每目录下的会话列表；显示顺序等 UI 偏好是浏览器本地；工作区分组拖拽顺序是 Host 持久的。
- **常见用法**：加目录 → 新会话自动属于该工作区；把常用会话 **Pin**；用搜索跳到一个很深的会话（会自动抬高水位线并展开祖先）。
- **容易误解**：
  - 「删除工作区会删文件」——**不会**：只删注册记录，不删目录、文件、会话；重新添加同一目录会被当成一个**新**工作区（`dsh-workspace/README.md`）。
  - 路径不同（哪怕指向同一真实目录的不同写法）就是**不同**工作区；它不扫描项目、不解析符号链接别名（`dsh-client-ui-workspace/README.md`）。
  - 子代理会话**不会**出现在这个列表里（同上，以及 `dsh-client-ui-subagent/README.md`）。

### A2. Chat（聊天视图）——「工作细节」四档

- **解决什么问题**：把「推理过程 / 工具过程」与「最终答案」分层展示，既不丢答案也不让过程淹没答案。
- **界面**：Turn 卡片（用户消息 / 助手消息 / 工具调用卡片 / 上下文变更 / 附件）。用户消息下方有一排小动作（时间戳、Copy，以及第三方插件加的动作，例如 Turn Rewind）。
- **「工作细节」模式**（`ui-chat` 设置的 `transcriptView` 字段）真实取值：`compact` / `standard` / `detailed` / `verbose`；旧值 `normal` / `expanded` 只读取不再写入。**桌面端默认 `standard`**。折叠时机另有 `collapseTiming`：`completion`（本轮完成即折叠，默认）或 `next-input`。
  证据：`dsh-client-ui-chat/lib/client.js:12614-12641`、`:13146`；文案键 `settings.transcript.verbose` = 「完全展开 / Verbose」（`:5823`、`:6017`）。
  本机 profile 把它显式设成了 `verbose`：`E:\dsh-data\profiles\desktop\cordis.patch.yml`（`id: ui-chat` → `transcriptView: verbose`、`performanceUsage: detailed`）。
- **数据从哪来**：会话事件投影（Session projection）+ 本会话的对话绑定；历史图片走「每会话一份授权 URL 缓存」。
- **容易误解**：Chat 里工具过程被折叠**不是**丢信息，切 Trajectory 或调高工作细节档位即可看到；Chat 也**不负责组装模型请求**（`dsh-client-ui-chat/README.md`）。

### A3. Trajectory（轨迹面板）★ 用户点名

- **解决什么问题**：把「这一步模型到底发了什么请求、拿了什么结果、花了多少 token、耗时多少」逐条摊开。它是**排查问题**的面板，不是聊天面板。
- **它在哪**：会话中栏的**视图环**里，和 Chat 并列为标签（`conversation.view` ring）。
- **重要前提（很容易踩）**：当 **设置 → 通用 →「显示代码工作视图」（Show coding view / developerTools）关闭**时，视图环会**直接过滤掉 id 为 `trajectory` 的视图**——轨迹标签根本不出现。
  证据：`dsh-client-ui-conversation/lib/client.js:19560`（`if (!developerTools.enabled.getSnapshot() && entry.options.id === "trajectory") continue;`），订阅在 `:19598`；开关文案在 `dsh-client-ui-settings-general/lib/client.js:994-996`（「开启后，显示轨迹、本轮代码差异，可选择完整的 Agent 预设切换」）与 `:1038-1040`（英文 "Shows trajectory, code diffs, and all Agent presets"）；命名空间 `ui-settings` 见 `dsh-client-ui-settings/lib/client.js:1067`。
- **一步一条展示什么字段**（「怎么读它」的核心）：
  - 记录类型分组：**User / Assistant / Tool / 嵌套 Subtool / compaction（压缩）**，并标出 **turn 边界** 与 **step 边界**。
  - 每条记录打开**检查器（inspector）**：token 用量、耗时（duration）、**Input**、**Output**、**Timing**、图片与附件摘要。
  - 工具行以**记录下来的工具名**标识；`run_code` 这类额外显示「程序描述」，检查器里给出**带行号高亮的源码**（Code 标签：自动换行开关、`{}` 切原始 JSON 参数、精确复制源码含尾随换行）。输出若是完整 JSON 对象/数组用树形展示；高亮只在工具 schema 里有**明确的 TypeScript 或 Python 提示**时才启用，缺失或冲突按纯文本渲染。
  - 顶部有 **交互式时间总览（timing overview）**；Summary / Preview / Raw 三种呈现：Raw 保留内容块原始顺序与未渲染文本，图片/文件放在默认折叠的披露块里。
  - 用户记录同时显示图片数与普通文件数（包括「只有附件没有文字」的记录）。
  - 独立的 compaction 请求按时间出现在 **「Between turns」** 分区；带编号的 compaction 留在它所属的 turn 内。
  - 请求在「等待输出 / 流式 / 重试」期间保持 **pending**；**正在进行的行不编造耗时**（显示起始标记而不是假装有一个正在增长的时长）。
- **长历史怎么处理**：**打开时定位在当前末尾（tail）**；点首行控件一次加载更早的**一页**；只渲染可见行（虚拟化，初始 50 个目标节点）。流式输出时**自动跟随末尾**，一旦向上滚就停止跟随。搜索/折叠/选择只覆盖 React 可见窗口，而「请求序号与累计用量」覆盖整个常驻快照。
- **排查问题的读法（实操）**：
  1. 先看 **Timing / 耗时**：某一步特别长 → 是模型慢还是工具慢。
  2. 看 **tool 行的 Input**：参数是不是就错了（路径、正则、模式）。
  3. 看 **Output**：失败原因、是否被截断、是否返回了巨大结果（配合工具结果裁剪阈值）。
  4. 看 **token 用量 + 累计**：上下文是不是被撑爆、compaction 是否触发。
  5. 看 **system prompt 变更行**：工具集被增删（tool-change 呈现）时，是哪个请求开始变的。
- **容易误解**：
  - Trajectory **不是**日志文件查看器，也不导出；它是**会话事件投影**的一个视图。
  - 「Chat 里准备中（preparing）」这种瞬态**不会**在 Trajectory 里生成工具行，也不改历史工具的耗时口径（`dsh-client-ui-trajectory/README.md`）。
  - 选择与时间轴定位是 **Trajectory 本地状态**，没有可分享的深链接锚点。

### A4. 右栏（Right Sidebar）与 files / terminal / browser / documentpreview

- **解决什么问题**：不离开会话就能看文件、开终端、看网页、看文档/计划。
- **结构**：每个会话一张 dock 面，两种呈现（边缘锚定面板 / 全屏），展开按钮在会话头部；标签类型由 `ctx.sidebarRightTabs` 注册，标签「从哪来、活多久」由 Tab 域管理（`dsh-client-ui-sidebar-right/README.md`）。
- **files 标签**：列会话所属**工作区根目录**，**一次只列一层**，展开目录靠直系 entry 的 watch **自动刷新**，另有手动 Reload；点文件按资源地址打开到侧栏预览（`dsh-client-ui-sidebar-files/README.md`）。
- **terminal 标签**：从右栏 **Start** 页选一个已安装 shell，在**会话当前工作目录**里跑命令；可重命名标签、刷新页面后**恢复保留的进程**；折叠侧栏命令继续跑；关标签 = 请求终止进程；补全跟随 shell 配置（`dsh-client-ui-sidebar-terminal/README.md`）。
  - ⚠️ **关键区分**：终端里跑的命令用的是**执行环境的系统用户权限**，与 Agent 的沙箱/权限预设**互相独立**（同上："independently of Agent permissions"）。别把它当成「被沙箱管的工具」。
- **browser 标签**：独立标签里浏览 HTTP(S) 页面（含 loopback 服务）。**Web 端用 iframe + 应用自己管历史；桌面端用 Electron webview，有原生导航历史与页面保留**；两者都不把 Electron/Node 能力注入被访问内容（`dsh-client-ui-sidebar-browser/README.md`）。
- **documentpreview 标签**：Office 文档 / 表格 / Markdown / 代码 / 图片的可扩展预览，跟随 `file` 提供者读取「它的那一页」（`dsh-api-workspace-files/README.md:123`、`dsh-agent-preset/skills/cordis-composition-reference/references/packages.md:110`）。
  - 取证说明：本机抽取树里**没有** `dsh-client-ui-sidebar-documentpreview` 这个目录（Test-Path 为 False），它是 `dsh-client-ui-chat` 的依赖（`dsh-client-ui-chat/package.json:71`）。因此该标签行为以这些**交叉引用**为准，未读到它自己的 README。
- **容易误解**：右栏**不是全局的**，是**每会话一份**；布局状态刷新即重置（`dsh-client-ui-layout/README.md`）。

### A5. Workspace（工作区）：会话目录、文件侧栏、changes、权限的关系

四件事常被混成一个「工作区」，实际是**四个不同的东西**：

| 概念 | 是什么 | 谁定义 | 你在哪看到 |
|---|---|---|---|
| **Workspace 注册项** | 一个**持久、有序的目录记录**，会话按目录分组 | `ctx.workspaceRegistry`（`dsh-workspace/README.md`） | 左栏分组 |
| **会话工作目录** | 会话实际跑在哪个目录（终端 cwd、文件树根） | 会话/工作区绑定 | 右栏 files 根、terminal 启动目录 |
| **沙箱 workspace 根** | 允许写入/删除的边界（`workspace-write` 的「工作区」） | `dsh-sandbox-policy` 的 `workspaceRoot`（`dsh-base/cordis.patch.yml:243-247`） | 权限预设效果、被拒时的提示 |
| **workspace changes** | 每个**顶层 turn** 改了哪些文件 + 每文件行数 | `dsh-workspace-changes` | 会话里的「改动文件卡片」 |

- **改动怎么算出来的**：turn 开始时对 git 工作树快照、turn 结束时再快照并 diff；**文件工具**编辑的文件在首次编辑前整文件备份、turn 结束再备份一次，用来覆盖 git 看不到的文件。没有仓库/git 时只列文件工具的编辑。会话日志落一条 `workspace/changes` 事件；汇总与逐文件对比**只留在 Host 上，会话释放即丢**（`dsh-workspace-changes/README.md`）。
- **和权限的关系**：`workspace-write` 这一档就是「只允许写**会话工作区**或平台临时目录」；换目录不是换个 UI 面板，而是换**沙箱边界**。
- **容易误解**：
  - 左栏工作区与「文件树根」通常一致，但工作区记录**本身不保证目录还在**（目录被删，会话仍归组）。
  - 改动卡片**不是 git 面板**：它不改索引、不提交，也不等于「未提交变更列表」（没列出的只是没被这个 turn 触碰）。
  - 没有 git 也能有改动卡片，但覆盖面更窄（只有文件工具碰过的文件）。

### A6. Jobs（后台任务）面板

- **解决什么问题**：让「跑很久的命令」不阻塞对话，还能回看输出。
- **界面**：会话头部一个控件，里面分 **运行中** 与 **已完成** 两段；运行中行以**跳动的时长**打头，然后是 kind 与状态；有保留输出的已结束任务可展开输出面板，**折叠即停止流**；没有保留输出的（例如答案直接给了模型的子代理）是静态行（`dsh-client-ui-jobs/README.md`）。
- **数据从哪来**：Host 的 job 服务（`dsh-jobs` 等）+ 工具侧 `dsh-tool-jobs`；本会话里对应的模型工具是 job_list / job_output / job_kill。
- **容易误解**：Jobs 里的东西**不是**会话历史的一部分；折叠/刷新后按保留策略可能只剩静态行。

### A7. Goal（目标）面板

- **解决什么问题**：长任务需要一个**跨轮次仍存在的问题定义**（「要达成什么」），并驱动自动续轮。
- **界面**：输入框上方的 **composer-context 条**，显示「持久目标状态 + 当前进程内激活状态」，可就地 **编辑 / 暂停 / 恢复 / 清除**，被拒绝的修改在行内报错；`/goal` 这类**持久命令输入**以 "Command input" 气泡显示，刷新后仍在（`dsh-client-ui-goal/README.md`）。
- **数据从哪来**：`dsh-goal`（持久目标）+ `dsh-goal-round-driver`（续轮驱动）+ `dsh-command-goal` / `dsh-tool-goal`（人和模型两个入口），都装在 `dsh-base/cordis.patch.yml:323-331`。
- **容易误解**：目标条显示的是**两个状态**（持久目标 vs 本次激活），「暂停」不等于「清除」；出厂 Web 预设里**除 `minimal` 外**才给 agent 提供 `/goal`（`dsh-client-ui-goal/README.md`）。

### A8. Plan（计划模式）面板

- **解决什么问题**：先出方案再动手。
- **界面**：`/plan` 进入；输入框里的**芯片**表示「计划模式开着」，点它退出；提交的计划会**自动在右栏打开**供审阅，批准/拒绝/忽略后仍能从该 turn「最终产物区」的卡片再次打开；重开计划会聚焦已有那个标签；刷新页面从会话历史恢复文档（`dsh-client-ui-plan/README.md`）。
- **数据从哪来**：`dsh-plan-mode`（提示词段落 + `exit_plan_mode` 工具）+ 会话历史里的计划文档。
- **容易误解**：计划模式的约束是**提示词层面**的，工具目录刻意保持不变（为了请求缓存稳定）——所以「计划模式下模型也看得见写文件工具」是设计，不是漏洞（`dsh-base/cordis.patch.yml:332-346` 的 `section` 原文）。

### A9. Subagent（子代理）面板

- **解决什么问题**：父会话要能看到/继续它派出去的子代理。
- **界面**：**父会话头部**的子代理目录；本地子会话显示活动、token 用量、耗时；**可继续的子代理接受追问并支持 Stop**；外部任务显示为**不可导航的叶子**（没有执行状态）；历史一次性会话以**只读记录**打开（`dsh-client-ui-subagent/README.md`）。
- **@ 引用源**：可以把「正在运行的子代理标签」插入为引用，但**不授予继续对话的权限**（同上）。
- **容易误解**：普通左栏**不列**子代理会话；「能 @ 到它」≠「能给它发指令」。

### A10. Skill（技能）与 `/` 触发

- **解决什么问题**：把「一套可复用的操作说明」按需装进上下文，而不是常驻。
- **界面**：输入 `/` 时技能出现在建议里，也可直接打 `/技能名`；技能调用在会话里渲染成可展开的 **Instructions 卡片**，卡片内容在技能目录变化后**保持稳定**（已结算内容不随后变化）。同名时**宿主命令优先**（`dsh-client-ui-skill/README.md`）。
- **数据从哪来**：`dsh-skill` + `dsh-skill-filesystem`（文件系统里的技能目录）+ `dsh-tool-skill`（模型侧加载）。
- **容易误解**：`/名字` 与「技能名」共用一个命名空间，撞名会解析成命令；minimal 预设里**没有** `tool-skill` 行（见 B2），所以极简模式下技能不可用。

### A11. 命令面板与斜杠命令（真实存在的命令）

- **面板是什么**：`dsh-client-ui-commands` 提供 `/` 命令源与四种派发形态：
  - `leadingInput`：宿主命令声明了 `input` → 变成「命令 + 输入」；
  - `popupSelect`：客户端注册的选择弹层（如 `/model`、`/permission` 的裸调用）；
  - `action`：客户端动作；
  - 其余走 `execute` 直接执行。
  **原则：命令行永远不会被悄悄降级成普通提示词**（`dsh-client-ui-commands/README.md`）。
- **宿主命令（本机代码里核到的真实注册）**：

| 命令 | 作用 | 证据 |
|---|---|---|
| `/compact` | 压缩较早的对话历史 | `dsh-command-compact/lib/index.js` |
| `/feedback` | 记录对本会话的反馈（`<text>`，`recordInput: false`） | `dsh-command-feedback/lib/index.js` |
| `/goal` | 设置/查看长任务目标（`[<objective>|clear|edit <objective>|pause|resume]`） | `dsh-command-goal/lib/index.js` |
| `/permission` | 切换当前会话权限预设（裸调用出选择器） | `dsh-permission-presets/lib/index.js`；装饰见 `dsh-client-ui-permission-presets/README.md` |
| `/plan` | 进入计划模式 | `dsh-plan-mode/lib/index.js` |
| `/export` | 导出会话日志 ZIP（会话 + 子会话 + 附件） | `dsh-session-log-export/lib/index.js` |
| `/file` | 由会话包注册的文件引用命令 | `dsh-client-ui-conversation/lib/client.js`（commands.register 扫描命中） |

  - 另有 `/model`（模型选择弹层）由 `dsh-client-ui-model-selection` 通过 `commandUi` 注册（`dsh-client-ui-commands/README.md` 明确点名 `/model`、`/permission` 为 popupSelect 规格）。
  - 技能名同样以 `/` 形式出现（见 A10）。
- **命令与提示词的区别（重要）**：命令**直接对 agent 执行**，不产生模型消息；每次被接纳的运行会记进**接收 agent 的会话日志**，UI 在模型历史之外渲染结果（`dsh-commands/README.md`）。
- **容易误解**：`/compact` 在 minimal 里也有（它带了 `command-compact`），但 `/goal` 只在 standard/ptc/cordis 有；**命令是否可用取决于当前预设**，不是全局恒定。

### A12. 插件设置：**两个不同的地方**（最容易误解的一处）

| | **侧栏 → Plugins** | **设置 → Built-in plugins（内置插件）** |
|---|---|---|
| 性质 | **可写**：装/卸/启用/禁用/改配置 | **只读**：清单 + 运行时状态 |
| 谁实现 | `dsh-client-ui-plugin-manager`（+ 市场页 `dsh-client-ui-plugin-market`） | `dsh-client-ui-settings-plugins`（外壳）+ `dsh-client-ui-settings-plugin-inventory`（列表页） |
| 能做什么 | 开关 bundle 与其中插件行；**Add plugin** 安装（包名 / Git 仓库 / 本地目录）；看 pnpm 输出、**停止**安装；**卸载需二次确认**；带配置页的插件在自己的页里编辑 | 按 **agent preset 组合**分组（默认展开）+ 折叠的**全局清单**；搜索可跨两组；卡片显示本地化标题/描述、稳定 entry id、启用状态、来源、运行时状态、**disabled 条件**、发现失败；预设提供的全局条目会**标出它来自哪个预设** |

按钮级细节（`dsh-client-ui-plugin-manager/README.md`）：
- 信息按钮解释：「本页配置官方插件并安装/管理其它插件；**Settings → Built-in plugins** 显示内置清单与运行时状态」。
- **Built-in plugin settings** 按配置顺序列出官方配置页：**Subagent、web search、agent loop、shell**（对应 `dsh-client-ui-settings-subagent` / `-web-search` / `-agent-loop` / `-shell`，注册在 `dsh-web-app/cordis.patch.yml:436-445`）。
- **Experimental plugins**：主列表放主要可选 bundle，标题旁 **More** 打开同名独立页，列出全部官方 bundle（含主列表已有的），Codex / Claude Code subagent 放最后；安装/移除后目录条目**保持原位**。
- **Add plugin** 主按钮 + 单独箭头菜单：「**Install a third-party plugin**」（同一个对话框）、「**Let the agent create a plugin**」（仅在 `ui-agent-preset` 贡献该项且 Creator 可用时可点）。
- 开关一个「被 More 页暂存」的 bundle 会把它并入主列表；关掉则只留在 More 页。
- 首次使用会在官方 npm registry 与 npmmirror 之间**并行探测**，先成功的作为初始源。
- **Refresh**：500ms 后才出 tooltip；手动刷新时按钮转圈且禁用直到所有待读完成且至少 400ms；失败保留缓存内容 + toast。
- 卡片图标：包根 `icon` 或导出的 `./icon`；子路径插件用 `<subpath>/icon`。
- **Discover（市场）页**是 Plugins 页的**第二个标签**（在 Installed 之后）：管理索引源、切市场、搜索、按分类/标签过滤、排序、打开条目页、确认后安装。Host 侧 `pluginMarket` 负责抓取与校验索引，本包只做呈现（`dsh-client-ui-plugin-market/README.md`）。
- **「查看源码」入口**：这两类包里我能核到的是**「查看配置」**（`agentPresets/read` 返回该预设声明子树的 YAML，只读，含 `!!js` 条件）与包根 / 子路径的 icon、locale meta、package.json 展示回退链；**没有**核到「打开包源码目录 / 在编辑器中打开」的按钮实现 → **未在源码中找到「查看源码」按钮的依据**。讲解请说「查看配置（YAML）」，不要说「查看源码」。
- **Host API 对应**：清单类读取走 `dsh-host-plugin-inventory`（组合清单）+ `api-remotes`（`dsh-client-ui-plugin-manager/README.md`："page reads the inventory and the bundles through api-remotes"）；预设 YAML 读取走 `agentPresets/read`（`dsh-agent-preset-registry/README.md`）；变更走 `plugin_manager` 工具 / 配置编辑（`dsh-plugin-manager`、`dsh-config-editor`）。

### A13. 沙箱权限：三档语义、在哪选、审批流程、Windows 差异 ★ 用户点名

**三档「预设」= 沙箱模式 + 审批策略 的捆绑**（先讲清这点：用户选的是**组合**，不是两个独立开关）：

| 预设（UI 文案） | `sandbox` | `approval` | 确切语义 |
|---|---|---|---|
| **仅可查看 / Read Only** | `read-only` | `ask` | 子进程**不允许写**；`ctx.fs` 的**每一个**变更被拒 |
| **工作区内修改 / Workspace Write** | `workspace-write` | `ask` | 只允许写**会话工作区**或**平台临时根**；`ctx.fs` 仅允许这些目标 |
| **完全权限 / Full access** | `danger-full-access` | `never` | 不做限制；审批策略为「从不询问」 |
| （当前会话专属）**自动审查 / Auto review**（EXP 徽章） | 需显式加载 experimental Auto 集成 | — | 独立 per-call 审查器；**不是**预设表里的项 |

证据：`dsh-base/cordis.patch.yml:240-277`（`sandbox-policy.mode` 读 `DSH_PERMISSION_MODE`，缺省 `workspace-write`；`approval.policy` 在 `danger-full-access` 时为 `never`，否则 `ask`；`permission.presets` 三行表）；UI 文案 `dsh-client-ui-permission-presets/README.md`（Read Only / Workspace Write / Full access / Auto review ↔ 仅可查看 / 工作区内修改 / 完全权限 / 自动审查）。

**语义来自执行层，不是 UI 层**：
- `dsh-sandbox`：`read-only`（无写）/ `workspace-write`（只在工作区内写）/ `danger-full-access`（不限制）；无法实施所请求模式时**失败关闭**，报 `SANDBOX_UNAVAILABLE`，**绝不**退化成无约束运行；这是**同一世界**（共享内核与文件系统）的隔离，**不是**容器。
- `dsh-fs-sandbox`：`read-only` 拒绝一切变更；`workspace-write` 只放行会话工作区或平台临时根；`danger-full-access` 不限制；拒绝返回 `FS_SANDBOX_DENIED`，工具会带**当前模式**和**同轮升级提示**。

**在哪选（两个入口，作用范围不同）**：
1. **设置 → 通用（Settings → General）的默认行**：改的是**未来会话的默认值**，选项来自 Host 的动态 `defaultPreset` 枚举；**改它不会切换或改写当前会话**。
2. **输入框旁的 permission 控件 / 裸 `/permission`**：切**当前会话**；需要「会话投影 + 完整目录快照」两者都在。
   - `/permission <preset>` 带参形式**直接执行**；裸调用出选择器；选择器里选 **Full access / Auto review** 各自需要**风险确认**（Auto 还带 EXP 徽章；选中后输入框控件上不显示徽章）。
   - `custom` 是**展示态**：出现说明当前旋钮组合不匹配任何预设，**能离开但不能选它**。
   - 目录里撤回某个预设时，输入框会关掉待确认并回显会话当前值，而不是留下一个不可用的乐观选择。
   证据：`dsh-client-ui-permission-presets/README.md`、`dsh-permission-presets/README.md`。

**每次改写要审批的流程**：
1. 工具调用进入沙箱；不满足策略 → **拒绝**，并把「当前模式 + 可升级提示」返回给模型。
2. 模型可以请求**恰好更宽一档**的模式 → 变成一次**人工审批请求**（`dsh-sandbox/README.md` 原文："After a denied call, the model can request one strictly wider mode for human approval"）。
3. 审批请求走 `dsh-user-approval`：`ask` 策略把请求交给部署配置的应答者；`never` 不询问直接拒；**应答者缺失或失败返回 `unavailable` → 失败关闭**；**一次批准只对那一次请求有效**；请求与结果**逐条写进请求会话的审计日志**。
4. 浏览器侧由 `dsh-client-ui-approval` 呈现：**接管 composer**，可附上关联的工具详情；**在详情区按 Enter 批准 / Esc 拒绝**（插件会占住这两个键，避免被可编辑快捷键抢走）；键盘与指针共用**同一个待决锁**，被撤回/替换的请求不能再被作答。
5. 模型只看到工具结果与当前策略，**看不到**人工审批界面与审计事件（`dsh-user-approval/README.md`）。

**Windows 上的实现差异**：
- 本地后端 `dsh-sandbox-local` 按平台自动选 runner，选不出就 `SANDBOX_UNAVAILABLE`；每次执行回报 `full` 或 **`partial`** 实施程度 + 拒绝/runner 失败签名（`dsh-sandbox-local/README.md`）。
- **Windows = ACL 受限令牌**：`workspace-write` 授予工作区 + 私有临时目录，`read-only` 两者都不授予；每份授权 = **capability-SID allow ACE + 拒绝环境父目录的 delete 权限 + 必须匹配的 Low 完整性标签**；任何 Win32 操作失败都**阻止**无约束 spawn。**保证是「部分」的**：硬链接可以别名同一个文件对象；被其它 AppContainer 工具 ACL 过的文件仍不可读（`dsh-sandbox-windows-acl/README.md`）。
- **Linux/macOS = bwrap / Landlock / Seatbelt**（`dsh-pwsh-sandbox/README.md` 摘要有对照）。
- 具体到 PowerShell：每次命令都是**全新的 `pwsh -Command` 进程**，经 `ctx.sandbox` 受限，settled 结果上盖着 mode / enforcement / denial 事实；Windows 上沙箱缝解析到 **ACL 受限令牌链**（同上）。Windows 上 `dsh-bash-sandbox` 与 `tool-bash` 是 `disabled: !!js process.platform === 'win32'`，反之 pwsh 系在非 Windows 上 disabled（`dsh-base/cordis.patch.yml:249-257, 281-287`）。
- **现场事实（可作为讲解的活例子）**：本会话的工具结果里出现过 `File sandbox enforcement is partial on this host`——正是上面 `partial` 回报；且本会话「审批提示被禁用，需要批准的操作会被自动拒绝」，与「无应答者 → 失败关闭」一致。

**容易误解**：
- 「我在 Full access，所以模型能随便来」——仍然是**同一世界**的进程；Auto review 是**另一种**独立审查，不是沙箱。
- 「改设置里的权限就改了当前会话」——**不会**，只影响未来会话（`dsh-client-ui-permission-presets/README.md`）。
- 「终端标签也归沙箱管」——**不归**，见 A4。
- 「把 `DSH_PERMISSION_MODE` 设成 danger-full-access 只是关弹窗」——它**同时**把 approval 策略变成 `never`（`dsh-base/cordis.patch.yml:262`）。

### A14. 会话管理：新建 / 切换 / 归档 / 导出 / 搜索 / checkpoint / rewind / 标题

- **新建**：左栏顶部的 **New Session** 是「选中的空白行」，有第一格**临时位置且不能拖**；拿到第一条 prompt 后变成普通可拖行。**绑定工作区后才落到某个目录**；hero 里的 picker 用来选工作区。
- **切换**：点左栏会话行；子代理会话不在左栏（要从父会话头部进）。
- **归档（archive）**：会话行菜单里的动作，确认对话框 id `workspace.session-archive`（`dsh-client-ui-workspace/lib/client.js:5314`、`dsh-cordis-client-runner/lib/client.js:5485`）。归档**只是从列表里过滤**，不改保存顺序、不改账号成员关系，历史仍在；被归档的原会话在 Schedule 详情里提示 "The original session is archived."（`dsh-client-ui-schedule/lib/client.js:7107`）。磁盘上归档数据在 `E:\dsh-data\dsh-session-archive`（本机实测存在该目录）。
- **导出**：会话头部「更多动作」里的 **Download session log**，或 `/export`，把**会话 + 子会话 + 附件**打成 ZIP；下载路由是带认证的 Fetch 路由，**下载位置由浏览器决定**（`dsh-session-log-export/README.md`）。
- **搜索**：左栏的搜索是**会话/工作区**搜索（`dsh-client-ui-workspace`）；另有一个**实验性** bundle 给 **Agent** 五个只读全局工具去检索「更早的会话」，出厂是**关的**，要在 Plugins 里开（`dsh-experimental-session-search/README.md`）。**两者不是一回事**。
- **checkpoint**：`dsh-session-checkpoint-policy` 是**耐久性检查点**——在模型请求前、顶层工具可能产生外部副作用前、下一 agent step 前把工作落盘；检查点失败**失败关闭**；崩溃后可恢复，但**未完成的助手流仍是瞬态**，被打断的工具调用以「结果未知」恢复而**不会自动重试**。这是**崩溃恢复**语义，**不是**用户可见的「回滚」按钮。
- **rewind（turn-rewind）**：由外部插件 `@anionex/dsh-turn-rewind`（本机 `^0.3.9`，见 `E:\dsh-data\profiles\desktop\package.json`）提供，底层是 **Change Ledger** 引擎。UI 上它是**用户消息下方第三个图标动作**（在时间戳与 Copy 之后），打开后列出受影响文件并给三个选择：**恢复文件并从该消息之前重启** / **只恢复文件** / **只回退消息、文件不动**。安全契约要点：**显式触发**（没有自动回滚）、**先预览后写**（生成会过期的、会话绑定的计划）、**先救生再改**（恢复前把当前树拍成 rescue point）、**不碰 git 控制面**（索引/分支/HEAD/stash/commit 一律不动）、恢复后哈希校验、失败回滚、对「审查后又被改动」做 stale-plan 检测。证据：`E:\dsh-data\profiles\desktop\node_modules\@anionex\dsh-turn-rewind\README.md`；磁盘上的 ledger 目录 `E:\dsh-data\change-ledger`（本机实测存在）。
- **标题生成**：`dsh-session-title` + `dsh-session-title-first-prompt-llm`（基于**第一条 prompt** 用 LLM 生成标题）在 `dsh-base/cordis.patch.yml:60-68`；另有 `dsh-session-title-all-prompts-llm` 由实验 bundle 提供（`dsh-experimental-session-titles-bundle/cordis.patch.yml:5-6`）。**没有标题的行**显示本地化的「未命名 / Untitled」，不会退化成目录名；未命名行不提供「复制标题」（`dsh-client-ui-workspace/README.md`）。
- **容易误解**：
  - 「归档 = 删除」→ 不是。
  - 「checkpoint 就是 rewind 的存档」→ 不是，两套机制、两套代码、两套语义。
  - 「导出会包含凭证」→ 文档口径是**会话树（会话 + 子会话 + 附件）**；会话内容之外的东西代码里没有依据，别承诺。

---

## B. 运行模式（Agent preset）★ 重点

### B1. 先对齐概念：preset 是什么，定义在哪，怎么加载

- **Agent preset = 一份「这个 Agent 由哪些插件行组成」的声明**：工具、提示词段落、技能都来自这些行的 `plugins` 列表。注册表本身**不扫描目录、不接受 preset 路径**；定义就是**普通的插件行**（`dsh-agent-preset-registry/README.md`）。
- **谁提供定义**：`dsh-web-app` bundle 的 `package.json` 里 `dsh.bundle.patch` 按顺序挂 5 个 patch：`./cordis.patch.yml` 然后 `presets/standard`、`presets/ptc`、`presets/minimal`、`presets/cordis`（`dsh-web-app/package.json`）。每个 preset 文件是**一条 `insert`**：`id: preset-<name>` + `name: '@deepseek-ai/dsh-agent-preset'` + `config.id/order/plugins`。
- **注册表配置**（本机 profile 覆盖）：`E:\dsh-data\profiles\desktop\cordis.patch.yml` 的 `id: agent-preset-registry` → `default: standard`、`selectedDefault: cordis`。
- **一个进程可以同时跑多套组合**；定义加载失败的 preset **仍留在名单里**（带诊断），而已存在的 Agent **继续用它启动时的那份组合**（`dsh-agent-preset-registry/README.md`）。
- **权威性提醒**：preset **不是安全沙箱**——YAML 与插件可以执行 Host 代码；用户覆盖会**整体替换**子列表，不自动合并未来内置列表的变化（同上，Known Limitations）。

### B2. 本机实际存在的 preset 清单（4 个，全部来自 `dsh-web-app/presets/`）

| preset id | 显示名（中 / 英） | `order` | 定义文件 |
|---|---|---|---|
| `standard` | **标准模式** / Standard mode | 1 | `dsh-web-app/presets/standard.patch.yml` |
| `ptc` | **PTC 模式** / PTC mode | 2 | `dsh-web-app/presets/ptc.patch.yml` |
| `minimal` | **极简模式** / Minimal mode | 3 | `dsh-web-app/presets/minimal.patch.yml` |
| `cordis` | **创造模式** / **Creator mode** | 4 | `dsh-web-app/presets/cordis.patch.yml` |

> **关键对齐**：用户口中的 **「Creator（创造）模式」= preset id `cordis`**，不是另一个叫 creator 的 preset。显示名映射在 `dsh-agent-preset-registry/lib/types/display.js`（standard/ptc/minimal/cordis → `preset*Name/Description` 文案键），文案在 `dsh-client-ui-agent-preset/lib/client.js:917-924`（英）与 `:949-956`（中）。
> **本机没有**额外的自定义 preset：profile patch 里没有任何 `preset-*` 覆盖行，外部 bundle 也没插 `dsh-agent-preset` 行（对 `*.yml` 全树 grep `dsh-agent-preset` 只命中 web-app 的 4 个文件）。

**各 preset 的插件行（逐条，来自对应 patch 文件的 `config.plugins`）**

- **standard**（`dsh-web-app/presets/standard.patch.yml`）
  - `persona`（前缀 "You are a coding agent powered by the {{model}} model."）、`agent-instructions`（maxBytes 65536）、`time-context`
  - `tool-bash`（Windows disabled）/ `tool-pwsh`（非 Windows disabled）、`tool-fs`、`tool-fs-search`（`sampleOverCapGlobResults: false`）、`tool-jobs`、`tool-schedule`
  - `skill-filesystem`、`tool-skill`、`command-goal`、`tool-goal`
  - `planning` 组（`isolate: planMode`）→ `plan-mode`
  - `compaction` 组（`isolate: compaction, toolResultPruner`）→ `compaction-basic`、`command-compact`、`tool-result-pruner`（thresholdChars 8192）
  - **没有**：子代理/工作流、`tool-todo`、`tool-web`、`tool-ask-user`、`present`、`tool-cordis`、插件管理/市场工具。
- **ptc**（`ptc.patch.yml`）= standard 的全部 + 以下差异
  - `delegation` 组（`isolate: workflowEngine`）：`tool-subagent-control`、`list-agents`、`tool-subagent`（provider spawn）、`tool-subagent-fork`（provider fork）、`workflow-ptc`（**disabled: true**）、`tool-workflow`（**disabled: true**）
  - `tool-ask-user`、`tool-todo`（`allowParallelInProgress: true`）、`tool-web`（fetch, 60s）、`tool-presentation`（`@deepseek-ai/dsh-agent-tool-presentation`，`mode: ptc`）、`present`
  - `tool-plugin-manager`、`tool-plugin-market` 都是 **disabled: true**
- **minimal**（`minimal.patch.yml`）
  - `persona`：前缀 "You are a helpful software engineer assistant."，且 **`complete: true`、`includeRuntimeContext: false`**（不注入运行时上下文）
  - `tool-fs`：**`read: false`、`write: false`、`edit: false`，只有 `readImage: true`**
  - `compaction` 组：`compaction-basic` + `command-compact`（**无** tool-result-pruner）
  - `persistent-shell` 组（`isolate: terminals`）：`dsh-terminal`（pty）、`terminal-bash`（posix）/ `terminal-pwsh`（win，`shellDialect: pwsh`）、`persistent-bash` / `persistent-pwsh`（300000ms 超时，带工具描述）
  - **只有这些**：没有检索、没有子代理、没有 todo/web/present/skill/plan-mode/goal。
- **cordis（创造模式）**（`cordis.patch.yml`）= standard 的全部 +
  - `delegation` 组：`tool-subagent-control`、`list-agents`、`tool-subagent`（spawn，**`modelSelectionSettings: true`**）、`tool-subagent-fork`、`workflow-ptc`（**启用**）、`tool-workflow`
  - `tool-ask-user`、`tool-todo`、`tool-web`、`tool-cordis`、`present`
  - `skill-filesystem` 额外带 `customSkillDirs` → 指向 `@deepseek-ai/dsh-agent-preset/skills`（**预设创作技能**）
  - `tool-plugin-manager` / `tool-plugin-market`：`disabled: !!js "!ctx.get('profileContext')"`（有 profile 上下文才开）

### B3. 三种模式逐讲（Standard / Minimal / Creator）

**Standard（标准模式）**
- 开了什么：文件读写 + 检索（glob/grep）、终端（bash/pwsh）、后台任务、定时任务、技能、目标、计划模式、上下文压缩（含工具结果裁剪）。
- 关了什么：子代理/工作流、todo、联网工具、提问工具、present、插件创作工具。→ 「**单线程、专一、不派活也不改 DSH 自己**」的日常主力。
- 适合：绝大多数编码 / 文件 / 资料任务。
- 切换影响：只影响**新任务**；已有会话保留它启动时的组合。
- 文案自述：「处理代码、文件和资料，适合大多数任务。Agent 会按需使用检索、编辑和终端等工具。」（`dsh-client-ui-agent-preset/lib/client.js:950`）

**Minimal（极简模式）**
- 开了什么：**一个持久 shell（bash 或 pwsh）+ 图片读取 + 上下文压缩 + `/compact`**。
- 关了什么：文件读/写/编辑工具、检索、技能、目标、计划模式、子代理、todo、web、present；**并关掉了运行时上下文注入**（`includeRuntimeContext: false`）、persona 用 `complete: true`。
- 适合：**测试/对比 agent 的基础表现**（官方文案 "Useful for testing and comparing its basic performance"），或故意用最窄工具面做受控实验。
- **实操坑**：minimal 下模型**不能用 read/write 工具**读文件——只能靠 shell 命令；也不要期望 `/goal`、技能、plan 模式存在（对应插件行确实不在）。
- 文案自述：「Agent 使用终端和图片读取工具，并支持上下文压缩，适合测试和对比其基础表现。」（`:953-954`）

**Creator / 创造模式（preset id = `cordis`）**
- 开了什么：standard 全部 + **完整委托能力**（`subagent` / `subagent_fork` / `list_agents` / `interrupt_agent` / 工作流 `workflow_ptc`）+ `ask_user_question` + `todo_write` + 联网（fetch/search）+ `tool-cordis`（Cordis 插件/运行时工具）+ `present` + **预设创作技能目录** + 插件管理/市场工具（有 profile 上下文时）。
- 关了什么：相比 standard 没关什么，它是**功能最全**的一档（`workflow-ptc` 在这里启用，与 ptc 预设相反）。
- 适合：**用对话定制 DSH 本身**——让 agent 写插件加功能/界面，或把工具与提示词组合成自己的模式（官方文案 "Customize DSH through conversation…"）。也是「让 agent 创建插件 / 创建预设」两条 UI 路径的落点。
- 额外特点：`tool-subagent` 带 `modelSelectionSettings: true`，即**子代理模型选择设置**只在这一档对 agent 暴露。
- 文案自述：「用对话定制 DSH：让 Agent 编写插件，添加新功能或界面；也能组合工具和提示词，创建自己的模式。」（`:955-956`）

**PTC 模式（第 4 个，用户没点名但会看到）**：standard + 委托 + todo + web + present，且 `dsh-agent-tool-presentation` 用 `mode: ptc`、`workflow-ptc`/`tool-workflow` **关闭**。官方文案：「包含标准模式的所有能力，更适合批量调用工具，并对结果进行筛选、整理、去重、统计或汇总的任务。」（`:951-952`）

### B4. 切换入口在 UI 哪里，以及「会影响什么」

三个入口，语义各不相同：

1. **新任务席（hero / Session Intent）**：`seatHint` = 「选择新任务使用的 Agent 预设」；菜单分组 **内置（Built-in）/ 自定义（Custom）**，可 **View configuration**（只读 YAML）、可 **设为新任务默认（Set as new task default）**。默认卡片用「新任务默认」徽章替换分组徽章，标题旁显示 preset id。
2. **会话头部标签（AgentPresetLabel）**：`headerHint` = 「本任务的 Agent 预设，在任务开始时确定」——**只读信息**，任务开始后不能改。
3. **设置 → Agent presets**：内置/自定义卡片分组、默认高亮、View configuration、Creator 入口；**这个页面本身不改任何东西**（"The page edits nothing"）。

**切换后对已有会话的影响（最常被问）**：
- **新任务默认**的修改写的是 `agentPresetRegistry` 的 settings 字段 `selectedDefault`（`ctx.remote.settings.update(AGENT_PRESET_SETTINGS_NS, { selectedDefault: id }, expectedRevision)`，`dsh-client-ui-agent-preset/lib/client.js:1095`）→ **只影响之后创建的会话**。
- **已有会话保留它已选定的模式**；`New Session` 用当前默认（`dsh-client-ui-agent-preset/README.md`："Existing sessions keep their selected mode; New Session uses the current default"）。
- 会话日志会**记录 preset id**；重启后的恢复用**该 id 的当前定义**，定义缺失则拒绝；**旧版本实现不在进程重启后保留**（`dsh-agent-preset-registry/README.md`）。
- `select` 只对**空白会话**生效：记录请求的 preset 并按当前修订运行，不产生第二条选择记录或 `tools/change`（同上）。
- **Creator 入口的特殊行为**：进入 Creator 会**只为当前接收的空白会话**选中 `cordis`，**不改新任务默认、不改 Coding Tools 设置**；没有绑定工作区或空白会话时**等待绑定**；那一次 Creator 会话之后保持自己的 preset（`dsh-client-ui-agent-preset/README.md`）。
- 一个「看起来像 bug」的联动：**把 General 里的 Coding Tools 关掉**后，所有已认证浏览器会把**保存为默认的 PTC 或 Minimal** 重置为 Standard（保存的 Standard / Creator / 自定义默认不变）；再打开 Coding Tools **不会恢复**旧默认（同上）。

### B5. 「Coding view / Coding Tools」开关：一个开关同时管两件事 ★ 必须讲

`ui-settings` 命名空间下有一个 `developerTools` 偏好，中文文案 **「显示代码工作视图」**，英文 **「Show coding view」**，副标题中文 **「开启后，显示轨迹、本轮代码差异，可选择完整的 Agent 预设切换」**（`dsh-client-ui-settings-general/lib/client.js:994-996`；英文 `:1038-1040`）。它实际管：

1. **Trajectory 视图是否存在**：`dsh-client-ui-conversation/lib/client.js:19560` 直接把 `trajectory` 从视图环过滤掉。
2. **PTC / Minimal 是否出现在预设菜单**：
   - 新任务 picker：`options.filter((option) => developerTools || !requiresCodingTools(option))`（`dsh-client-ui-agent-preset/lib/client.js:1301`）
   - 设置名单：`rows.filter((row) => isBuiltInPreset(row) === builtIn && (developerTools || !requiresCodingTools(row)))`（`:1739`）
   - 关闭时仍提供 **Standard、Creator、自定义预设**；默认选择与 Creator 入口两种状态下都在（`dsh-client-ui-agent-preset/README.md`）。
3. 副标题提到的「本轮代码差异」即 workspace changes 卡片（`dsh-workspace-changes` → "The Web changed-files card renders them"）。

> **讲解必说**：新手说「我找不到轨迹面板 / 找不到极简模式」时，第一反应是让他们去 **设置 → 通用 → 显示代码工作视图** 打开，而不是重装插件。

### B6. `default: standard` 与 `selectedDefault: cordis` 的实际差别

| 字段 | 类型/角色 | 谁写 | 语义 |
|---|---|---|---|
| `default` | **必填**，部署级 | bundle / profile patch 手写 | 「没有用户选择时用哪个」——`z.string().required()` |
| `selectedDefault` | **volatile**（`z.string().volatile()`），用户级 | UI 的「设为新任务默认」（settings mutation） | 「用户选定的新任务默认」，**优先于** `default` |

解析只有一行代码：`get defaultId() { return this.config.selectedDefault.get() ?? this.config.default; }`
证据：`dsh-agent-preset-registry/lib/index.js:441-444`（schema）、`:462-465`（`defaultId`）；`lib/types/index.js:69,88` 同构；README 原话："The selectedDefault volatile field … retains the user default, which new sessions resolve over the deployment default."

- `volatile` 是 schemastery 的包装：解析出来的值是一个**可读的稳定引用**（用 `.get()` 读），不是普通快照值（`schemastery/README.md:393`、`schemastery/lib/index.mjs:235-247`）。
- **本机结论**：`default: standard` + `selectedDefault: cordis` → `defaultId` = **`cordis`**，即**这台机器的新任务默认落在「创造模式」**。这与「出厂默认是标准模式」不同，是**用户层覆盖**的结果。
- 两个字段**不是「推荐值 vs 实际值」**，也不构成审批/回退关系：`default` 是**兜底**，`selectedDefault` 是**用户意图**；删掉 `selectedDefault` 就自动退回 `standard`。

### B7. 别混淆：Agent preset ≠ 运行形态（shape）

- **Agent preset** 决定的是**一个 Agent 内部装哪些插件行**（工具/提示词/技能）。同一进程里可并存多套。
- **运行形态**指的是「这个进程/这个前端长什么样、暴露什么入口」，完全是另一维，例如：
  - `dsh-web-app`：Web/桌面 GUI 的 bundle（本文所有面板都来自它）；
  - `dsh-sdk-minimal`：给 SDK 用的最小组合（它自己也挂了 `session-title`，见 `dsh-sdk-minimal/cordis.patch.yml:106-107`）；
  - `dsh-headless`：无头形态；
  - `dsh-acp` / `dsh-acp-app`：ACP 自动化（它也有自己的 `session-title-llm`，`dsh-acp-app/cordis.patch.yml:8`），**不提供斜杠命令面**（`dsh-commands/README.md`："UI-less demos and ACP automation do not provide this command surface"）。
- 一句话区分：**preset 换的是「agent 的手和脑子」，shape 换的是「谁来跟它说话」**。换 preset 不会给你多一个面板；换 shape 不会改工具集。

---

## C. 讲解时的「误解速查表」

| 常见误解 | 事实 | 证据 |
|---|---|---|
| 「插件有两个页面，一定是 bug」 | 侧栏 Plugins 可写（装/卸/开关/配置），设置→Built-in plugins 只读（清单+状态） | `dsh-client-ui-plugin-manager/README.md`、`dsh-client-ui-settings-plugin-inventory/README.md` |
| 「轨迹面板是日志文件」 | 它是会话事件投影的视图，虚拟化 + 只覆盖可见窗口 | `dsh-client-ui-trajectory/README.md` |
| 「找不到轨迹 = 安装坏了」 | 先看「显示代码工作视图」是否关闭 | `dsh-client-ui-conversation/lib/client.js:19560` |
| 「找不到极简/PTC = 没这个人」 | 同一开关隐藏它们；关闭时仍有 Standard/Creator/自定义 | `dsh-client-ui-agent-preset/lib/client.js:1301,1739` |
| 「改默认预设会改我的当前会话」 | 只影响新任务；已有会话保留原模式 | `dsh-client-ui-agent-preset/README.md` |
| 「Creator 是另一个包/另一个功能」 | Creator = preset id `cordis` | `dsh-client-ui-agent-preset/lib/client.js:923,955` |
| 「Workspace 删掉会删目录」 | 只删注册记录；重加算新工作区 | `dsh-workspace/README.md` |
| 「终端也受沙箱权限管」 | 终端用系统用户权限，与 Agent 权限独立 | `dsh-client-ui-sidebar-terminal/README.md` |
| 「Full access 就不审批了，等于关掉保护」 | `danger-full-access` 预设的 `approval` 确实是 `never`——**同时**改变审批策略；想保留审批需自定义组合 | `dsh-base/cordis.patch.yml:267-276` |
| 「沙箱失败会退化成不受限运行」 | 失败关闭，报 `SANDBOX_UNAVAILABLE` | `dsh-sandbox/README.md` |
| 「Windows 沙箱和 Linux 一样强」 | Windows 是 ACL 受限令牌，**保证是「部分」的** | `dsh-sandbox-windows-acl/README.md` |
| 「checkpoint = rewind」 | checkpoint 是崩溃恢复耐久性；rewind 是外部 Change Ledger 的显式恢复 | `dsh-session-checkpoint-policy/README.md`、turn-rewind README |
| 「归档 = 删除」 | 只是列表过滤，历史与文件都在 | `dsh-client-ui-workspace/README.md`；`E:\dsh-data\dsh-session-archive` |
| 「插件页能看源码」 | 能看的是**配置 YAML**（`agentPresets/read`）；「查看源码」按钮**未在源码中找到依据** | `dsh-agent-preset-registry/README.md` |

---

## D. 证据索引（按文件）

**Preset / 运行模式**
- `dsh-web-app/package.json`（`dsh.bundle.patch` 的 5 个 patch 顺序）
- `dsh-web-app/cordis.patch.yml`（`:145,310,313,319,324,424,430,436,442,445` 设置与插件行；`:579-586` 预设注册表）
- `dsh-web-app/presets/{standard,ptc,minimal,cordis}.patch.yml`
- `dsh-agent-preset-registry/README.md`、`lib/index.js:441-465`、`lib/types/display.js`
- `dsh-client-ui-agent-preset/README.md`、`lib/client.js:907-969,1095,1301,1739`
- `dsh-client-ui-settings-general/lib/client.js:994-996,1038-1040`
- `dsh-client-ui-settings/lib/client.js:1067`（`ui-settings` 命名空间）
- `E:\dsh-data\profiles\desktop\cordis.patch.yml`、`E:\dsh-data\profiles\desktop\package.json`

**面板**
- `dsh-client-ui-layout/README.md`、`dsh-client-ui-sidebar-right/README.md`、`-sidebar-files`、`-sidebar-terminal`、`-sidebar-browser`
- `dsh-client-ui-conversation/README.md` + `lib/client.js:19555-19598`
- `dsh-client-ui-chat/README.md` + `lib/client.js:12614-12641,13146`
- `dsh-client-ui-trajectory/README.md`
- `dsh-client-ui-workspace/README.md` + `lib/client.js:5314`
- `dsh-workspace/README.md`、`dsh-workspace-changes/README.md`
- `dsh-client-ui-jobs`、`-goal`、`-plan`、`-subagent`、`-skill`、`-commands` 的 `README.md`
- `dsh-commands/README.md`；`dsh-command-{compact,feedback,goal}/lib/index.js`；`dsh-plan-mode/lib/index.js`；`dsh-permission-presets/lib/index.js`；`dsh-session-log-export/lib/index.js`

**插件管理**
- `dsh-client-ui-plugin-manager/README.md`、`dsh-client-ui-settings-plugins/README.md`、`dsh-client-ui-settings-plugin-inventory/README.md`、`dsh-client-ui-plugin-market/README.md`

**权限与沙箱**
- `dsh-base/cordis.patch.yml:240-287`
- `dsh-permission-presets/README.md`、`dsh-client-ui-permission-presets/README.md`
- `dsh-sandbox/README.md`、`dsh-sandbox-local/README.md`、`dsh-sandbox-windows-acl/README.md`、`dsh-pwsh-sandbox/README.md`、`dsh-fs-sandbox/README.md`
- `dsh-user-approval/README.md`、`dsh-client-ui-approval/README.md`

**会话管理**
- `dsh-session-log-export/README.md`、`dsh-session-checkpoint-policy/README.md`、`dsh-experimental-session-search/README.md`
- `E:\dsh-data\profiles\desktop\node_modules\@anionex\dsh-turn-rewind\README.md`
- 本机实测目录：`E:\dsh-data\dsh-session-archive`、`E:\dsh-data\change-ledger`、`E:\dsh-data\storages\workspace.json`

---

## E. 明确「没写 / 没找到依据」的部分

1. **「查看源码」按钮**：插件页/预设页里能核到的是「查看配置（只读 YAML）」与 icon/locale 回退；**未找到**「打开源码目录 / 在编辑器打开」的实现。
2. **`dsh-client-ui-sidebar-documentpreview` 自身的 README**：本机抽取树中**该包目录不存在**（Test-Path = False），其行为仅据 `dsh-api-workspace-files/README.md:123`、`dsh-client-ui-chat/package.json:71` 等交叉引用描述。
3. **归档目录 `E:\dsh-data\dsh-session-archive` 的内部格式**：只确认目录存在与 UI 语义，**未读其文件格式定义**。
4. **本机当前 `developerTools` 的持久值**：未能定位 Host settings 文档的落盘文件（`E:\dsh-data\storages` 下只有 `workspace.json` 与投影缓存，根目录只有 `settings.yaml.imported`），因此**不对「本机现在是开还是关」下断言**。
