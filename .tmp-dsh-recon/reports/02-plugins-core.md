# 02 · 官方 bundle 装载的核心插件清点

> 视角：DeepSeek Harness 桌面版 0.2.1-rc.1，本机 profile = `E:\dsh-data\profiles\desktop`。
> 只清点**由官方 bundle 装载**的条目；profile 里的第三方插件（dshmarket、@linxin666/dsh-web-all、@liustack/modlens、dsh-context 等）不在本文范围。
> 证据路径若无特别说明，均相对 `.tmp-dsh-recon\asar\@deepseek-ai\`（即 asar 内 `dsh/node_modules/@deepseek-ai/` 的同构拷贝）。

---

## 0. 一句话结论

本 profile 的插件树由 **5 层官方 patch** 叠出来，约 **200 个不同 id**：

| 层 | 文件 | 内容 |
|---|---|---|
| 1 | `dsh-base/cordis.patch.yml` | 95 行 insert：所有模式共享的内核、LLM、会话、存储、沙箱、工具、subagent、Web 能力、压缩策略 |
| 2 | `dsh-web-app/cordis.patch.yml` | 87 行 insert（浏览器面：Web 服务、Remote 控制器、约 45 个 dsh-client-ui-* 面板）+ 26 行**按 id 覆盖 base**（其中 23 行是 disable） |
| 3 | `dsh-web-app/presets/{standard,cordis,ptc,minimal}.patch.yml` | 4 个 **agent preset**：把"模型可见的东西"（工具 / 提示 / 委派后端）从宿主面挪到每会话作用域。standard 33 行、cordis 34 行、ptc 34 行、minimal 12 行 |
| 4 | `dsh-experimental-agent-team-profile/cordis.patch.yml` | 4 行 disable（宿主面旧 subagent 工具）+ 3 行 insert（Agent Teams） |
| 5 | `dsh-experimental-auto-review/cordis.patch.yml` | 1 行 insert（Auto 权限模式的逐次 LLM 审批） |
| 末尾 | 用户层 `E:\dsh-data\profiles\desktop\cordis.patch.yml` | 覆盖 UI 偏好与默认模型；bundle 顺序见 ...\desktop\package.json 的 dsh.profile.bundles |

**读懂这张表的关键一句话**：base 里那些 tool-* 行在 web 层被**整体 disable**，改由每个会话挂载的 preset 重新声明。所以"用户到底有没有 bash 工具"不由 base 决定，而由**当前会话选中的 preset** 决定（本 profile 的 agent-preset-registry.selectedDefault 是 cordis，见 `E:\dsh-data\profiles\desktop\cordis.patch.yml`）。

---

## 1. 判定规则（后文"开关"列都按这套语义读）

### 1.1 三种 disabled 写法，含义完全不同

| 写法 | 含义 | 例子 |
|---|---|---|
| disabled: true | **静态关闭**，永远不装 | base tool-plugin-manager（`dsh-base/cordis.patch.yml:16-18`） |
| disabled: !!js process.platform === 'win32' | **平台/环境判定**，装载时求值 | bash-sandbox 在 Windows 关、pwsh-sandbox 在非 Windows 关（:249-258） |
| disabled: !!js "!ctx.get('profileContext')" | **依赖 profile 上下文**：有 profile 就装 | plugin-manager、hmr、config-editor、settings（:20-22、:27-32、:105-111） |

> 桌面版跑的是 profile（profileContext.name === 'desktop'，见 `dsh-base/cordis.patch.yml:120-124`），所以第三类在本机**都是启用**的；第二类里 Windows 分支生效（pwsh-* 装、bash-* 不装）。

### 1.2 preset 作用域的一个注意点

profileContext 由 profile 启动器在宿主 ctx 上 provide（`dsh/lib/profile-boot-C14i-8IN.js:290-304`）。preset 内是否能解析到同一服务取决于 Loader 作用域；源码里的 preset 用同一表达式（`dsh-web-app/presets/cordis.patch.yml:131-136`），但**未在 lib 中找到对 preset 作用域可见性的显式说明**，故本文不推断其运行期结果，只照抄表达式。

### 1.3 UI 配置为什么能持久化

config-editor 把表单写回 **profile patch 文件**（`dsh-config-editor/lib/index.js:18-78`：inject = ['loader','profileContext']，写 profileContext.patchPath）；dsh-settings 建立在它之上（`dsh-settings/lib/index.js:324-347`）。base 注释直说：**"Live Config forms persist through the active profile patch"**（`dsh-base/cordis.patch.yml:102-107`）。
→ "在设置页改一项" = 往 `E:\dsh-data\profiles\desktop\cordis.patch.yml` 里同 id 的 config 补一行；这正是该文件里出现 ui-theme/preference: dark、ui-chat/transcriptView: verbose 的原因。

---

## 2. 总表：按功能域分组（含状态与配置键）

列说明：**层** = base / web / preset / exp；**配置键** = 该行 config schema 的键（括号里是默认值；"—" 表示该包无 Config schema）。

### 2.1 内核与运行时

| id | 包 | 层 | 状态 | 配置键 |
|---|---|---|---|---|
| `timer` | cordis-plugin-timer | base | 开 | — |
| `hmr` | dsh-hmr | base | 开（有 profile 才开） | root: []、base、ignored、debounce(100) |
| `llm` | dsh-llm | base | 开 | — |
| `deepseek-llm-api-extensions` | 同名 | base | 开 | — |
| `session` | dsh-session | base | 开 | — |
| `typert` | dsh-typert-registry | base | 开 | — |
| `typert-loader` | dsh-typert-loader | base | 开（cfg yes） | — |
| `typert-gateway` | dsh-api-gateway | base | 开（cfg yes） | — |
| `remote-access` | dsh-api-remote-access | base | 开 | — |
| `user-questions` | dsh-user-questions | base | 开 | — |
| `agent` | dsh-agent | base | 开 | — |
| `agent-loop` | dsh-agent-loop | base | 开 | maxParallelToolCalls(10)、agents: [] |
| `agent-default-model` | 同名 | base + 用户层 | 开 | provider、model、reasoningEffort |
| `jobs` | dsh-jobs-local | base | 开 | maxConcurrentJobsPerOwner(10)、retainBytes(256KiB)、settledRetainBytes(16KiB)、pumpPollMs |
| `llm-retry` | 同名 | base | 开 | {} （重试策略挂在各 provider 配置下，有校验强制） |
| `config-editor` | 同名 | base | 开 | — |
| `settings` | 同名 | base | 开 | — |
| `working-directory` | 同名 | base | 开 | 目录未抽出（catalog: cfg yes） |
| `tool-working-directory` | 同名 | base | 开 | — |
| `subprocess` | dsh-subprocess-local | base | 开 | — |
| `shell-env` | 同名 | base | 开 | cfg yes |
| `tools` | dsh-tools | base/web | 开（web 覆盖） | mode: !!js process.env.DSH_TOOLS_MODE（native / ptc） |
| `system-prompt` | 同名 | base/web | 开（web 覆盖） | personaPrefix（web：You are a coding agent powered by the {{model}} model.） |
| `fs-sandbox` | 同名 | base | 开 | cfg yes |
| `plugin-package-inventory-deepseek` | 同名 | base | 开 | cfg yes |
| `harness-dev-context` | 同名 | web | 开 | — |

> task_board_* 一类工具**不属于官方 bundle**：来自第三方 @linxin666/dsh-client-ui-task-board（见 §8.6）。

### 2.2 LLM 与账号

| id | 包 | 层 | 状态 | 配置键 / 关键事实 |
|---|---|---|---|---|
| `llm-deepseek` | dsh-llm-deepseek-api-key | base | 开 | apiKeyEnv(DEEPSEEK_API_KEY) + 通用 DeepSeek 字段；key 每请求从凭据库解析，不内联 |
| `llm-deepseek-account` | dsh-llm-deepseek-account | base | 开 | 账号型 provider 的认证与发现（cfg yes） |
| `llm-pi-ai` | dsh-llm-pi-ai | base | 开但**休眠** | providers: {}（默认空 → 0 条路由、模型选择器里不出现额外模型） |
| `authorization` | dsh-authorization | base | 开 | — |
| `deepseek-account` | dsh-deepseek-account-platform | base | 开 | desktopPlatform（desktop + win32/darwin 时注入平台名） |
| `credentials` | dsh-credentials-local | base | 开 | cfg yes（$DSH_HOME/.env 形态） |
| `agent-default-model` | 同名 | base + 用户层 | 开 | profile 覆盖为 provider=deepseek-account、model=deepseek-flash、reasoningEffort=high |
| `plugin-package-inventory-deepseek` | 同名 | base | 开 | 把已装载插件包清单附加到官方 API 请求 |

### 2.3 会话与持久化

| id | 包 | 层 | 状态 | 配置键 / 关键事实 |
|---|---|---|---|---|
| `session-log-deepseek` | 同名 | base | 开 | settings 命名空间 session-log-deepseek；是否随请求上传由 UI 开关控制 |
| `session-title` | 同名 | base | 开 | fallbackMaxWords(5)、fallbackMaxBytes(40)、maxTitleBytes(80) |
| `session-title-llm` | dsh-session-title-first-prompt-llm | base | 开 | targetWords(5)、targetCjkCharacters(10)、maxInputBytes(4096)、maxOutputTokens(4096)、timeoutMs(60000) |
| `session-persistence-jsonl` | 同名 | base | 开 | root: $DSH_HOME/sessions |
| `attachment-local` | 同名 | base | 开 | maxImageBytes(20MiB)、maxImagesPerMessage(20)、maxMessageImageBytes、maxImagePixels、maxImageDimension、normalized*、imageCompressionConcurrency(2) |
| `session-query-sqlite` | 同名 | base/web | 开但**搜索关闭** | path: ':memory:'、openAt: never → 搜索调用返回 SESSION_QUERY_SEARCH_DISABLED，SQLite 不被打开 |
| `session-projection` | 同名 | base | 开 | — |
| `session-projection-cache` | 同名 | base | 开 | writeEveryEvents(200)、writeIntervalMs(5000) |
| storage / storage-json / storage-domain | 各自包 | base | 开 | storage-json.root = $DSH_HOME/storages；storage-domain.backend: json |
| `session-stats` | 同名 | web | 开 | — |
| `session-turn-outline` | 同名 | web | 开 | — |
| `session-reference` | 同名 | web | 开 | maxReferences(3)、candidateLimit(50)、maxReferenceBytes、referenceContextFraction |
| `file-reference-local` | 同名 | web | 开 | maxResults(20)、maxEntries、excludedDirectories |
| `session-log-download` | dsh-session-log-export | web | 开 | cfg yes（/export） |
| `session-checkpoint-policy` | 同名 | base | 开 | — |
| `workspace` | dsh-workspace | web | 开 | — |
| `workspace-changes` | 同名 | web | 开 | cfg yes |
| `workspace-controller` | dsh-api-workspace-controller | web | 开 | cfg yes |
| `workspace-files` | dsh-api-workspace-files | web | 开 | cfg yes |

### 2.4 工具类（模型可见的 dsh-tool-*）

> 这一组在 **base 里全部声明、在 web 层全部被 disable**（`dsh-web-app/cordis.patch.yml:474-577`），真正的挂载点是 preset。"层"列写作 base+preset。

| id | 包 | 工具名 | 配置键 |
|---|---|---|---|
| `tool-fs` | dsh-tool-fs | read、write、edit、read_image | read/readImage/write/edit: true、readLimit(2000 行)、readMaxLineLength(2000)、readMaxBytes(50KiB)、readStreamMinSize |
| `tool-fs-search` | dsh-tool-fs-search | glob、grep | sampleOverCapGlobResults（必填，本机 false）、globMaxResults(100)、grepMaxMatches(250)、timeoutMs(30s)、graceMs、rawOutputMaxBytes(20MB)、stderrMaxBytes(64KiB)、searchMetaMaxBytes、grepMaxLineBytes |
| `tool-bash` | dsh-tool-bash | bash | enableRunInBackground(true)、promoteOnTimeout(true) |
| `tool-pwsh` | dsh-tool-pwsh | pwsh | 同上 |
| `tool-jobs` | dsh-tool-jobs | job_list、job_output、job_kill | waitTimeoutMs(30s)、maxWaitTimeoutMs(600s)、completionDelivery(wakeup)、maxConsecutiveWakes |
| `tool-todo` | dsh-tool-todo | todo_write | allowParallelInProgress（必填，本机 true） |
| `tool-skill` | dsh-tool-skill | skill | catalogDescriptionMaxLength |
| `tool-goal` | dsh-tool-goal | get_goal、update_goal | blockedAfterConsecutiveRounds(3) |
| `tool-ask-user` | dsh-tool-ask-user | ask_user_question | mode(legacy｜timed，默认 legacy)、timeout(120s) |
| tool-subagent / tool-subagent-fork | dsh-tool-subagent | subagent / subagent_fork | provider、toolName、modelSelectionSettings(false)、agentOptions、agentPreset、allowedAgentPresets、maxDepth |
| `tool-subagent-control` | 同名 | send_message、interrupt_agent | — |
| `tool-subagent-list-agents` | .../list-agents | list_agents | — |
| `tool-schedule` | 同名 | schedule_create、schedule_list、schedule_update、schedule_delete | — |
| `tool-web` | 同名 | web_search、web_fetch | search(true)、fetch(true)、searchMaxResults(8)、searchMaxQueries(4)、searchTimeoutMs(本 profile 60s)、fetchTimeoutMs(30s)、fetchMaxOutputChars |
| `tool-workflow` | 同名 | workflow | toolName(workflow)、maxResultChars(50000)、enableRunInBackground(true) |
| `present` | dsh-tool-present | present | maxFiles(8) |
| `tool-cordis` | 同名 | cordis_inspect_list、cordis_inspect_query | —（仅 cordis preset） |
| `tool-working-directory` | 同名 | working_directory | — |
| `mcp-resources` | 同名 | list_mcp_resources、list_mcp_resource_templates | —（无 MCP server 时不出现） |
| `tool-plugin-manager` | dsh-plugin-manager/tools | 装/启/停插件的模型工具 | **base 与 web 均 disable**，见 §5 |
| `tool-plugin-market` | dsh-plugin-market/tools | plugin_market | preset 内 !!js "!ctx.get('profileContext')" |

### 2.5 沙箱与权限

| id | 包 | 层 | 状态 | 配置键 |
|---|---|---|---|---|
| `sandbox` | dsh-sandbox-local | base | 开 | cfg yes：bwrap / landlock-run / Seatbelt / Windows ACL 受限令牌，逐能力探测、fail-closed |
| `sandbox-policy` | 同名 | base | 开 | mode(workspace-write，DSH_PERMISSION_MODE 可覆)、workspaceRoot(process.cwd()) |
| `bash-sandbox` | 同名 | base | **Windows 关** | timeoutMs(60000) |
| `pwsh-sandbox` | 同名 | base | **Windows 开** | cfg yes |
| `approval` | dsh-user-approval | base | 开 | policy(ask｜never，默认 ask；DSH_PERMISSION_MODE=danger-full-access 时 never) |
| `permission` | dsh-permission-presets | base | 开 | presets{read-only, workspace-write, danger-full-access}、defaultPreset |
| `fs-sandbox` | 同名 | base | 开 | cfg yes |
| `fs-observation-policy` | 同名 | base | 开 | —（读后写、版本守卫） |

### 2.6 文件系统

| id | 包 | 层 | 关键事实 |
|---|---|---|---|
| `fs-sandbox` | dsh-fs-sandbox | base | 实现 ctx.fs：读直通，写/改按 per-call 沙箱模式围栏 |
| `fs-observation-policy` | 同名 | base | 观察态 / 读后写 / 版本守卫（fs/* 事件门，无服务 API） |
| `spill-local` | 同名 | base | 溢出内容落本地、按会话私有 |
| `attachment-local` | 同名 | base | $DSH_HOME 内内容寻址的图片存储 |
| `office-to-pdf` | 同名 | web | Office→PDF 转换（供右侧栏文档预览），有界队列 + 缓存 |
| `directory-picker` | dsh-host-directory-picker-auto | web | 开机探测环境后挂 native 或 browse 目录选择器 |
| open-in-app / ui-open-in-app | dsh-host-open-in-app / dsh-client-ui-open-in-app | web | probeTimeoutMs(10000)、iconTimeoutMs(10000)、launchWatchMs(1000) |

### 2.7 Web / API 网关

| id | 包 | 层 | 作用 / 配置 |
|---|---|---|---|
| `webserver` | dsh-host-webserver | web | host(127.0.0.1)、port(3080 回退)、tls、compression(gzip)、compressionLevel(1)、compressionThresholdBytes(1024)；拒绝通配绑定。**本机实际监听 29310**（由 webStartup 注入，3080 只是回退值） |
| `web-runtime` | dsh-web-app | web | openBrowser、printUrl(true)、publicUrl、surfaceContext(true) |
| `web-startup` | dsh-web-app/startup | web | 解析 Web 启动参数，provide webStartup 服务 |
| `connection` | dsh-client-connection | web | trustedHosts；回环 / 绑定地址 / 信任主机三重策略 |
| `modules` | dsh-client-modules | web | 组装 window.__DSH_BOOT__，服务 /plugins/<id>/client.js |
| `file-upload` | dsh-client-file-upload | web | 浏览器上传与暂存回执 |
| `api-remotes` | 同名（目录未抽出） | web | Remote BFF 装配 |
| `session-controller` | dsh-api-session-controller | web | 会话命令 / 冷读 / 实时控制 |
| `job-controller` | dsh-api-job-controller | web | 后台作业观察流 |
| `terminal-controller` | dsh-api-terminal-controller | web | 会话内交互终端（shell 探测、屏幕恢复） |
| account-controller / settings-controller | 各自包 | web | 账号与配置面的 Remote 读写 |
| `plugin-inventory` | dsh-host-plugin-inventory | web | 只读的 Loader 插件状态投影 |
| cordis-host-runner / cordis-client-runner | 各自包 | web | 动态双半插件的宿主/浏览器执行器（cordis_define 卡片背后的运行时） |
| `client-hmr` | 同名 | web | 客户端 bundle 重建后的热重载（平时空转） |
| `ui-theme` | dsh-client-ui-theme | web | preference（本机 dark） |

### 2.8 客户端 UI（dsh-client-ui-*，约 45 行）

中文名取自各包 `locale/zh.js`on 的 meta.title——这是判断"用户看到哪块界面"最直接的证据。

| id | 中文名 | 用户在哪看到 |
|---|---|---|
| `ui-layout` | 应用布局 | 三栏 AppFrame、拖拽分隔条 |
| `ui-renderer` | 界面渲染 | React 插槽与 App 根 |
| `ui-session` | 会话界面连接 | Session Controller 的 React 适配 |
| `ui-sidebar` | 会话侧栏 | 左侧会话树、搜索、分组、状态点 |
| `ui-sidebar-right` | 右侧面板 | 右侧停靠面板 |
| `ui-sidebar-files` | 文件浏览面板 | 右侧"文件"页签 |
| `ui-sidebar-terminal` | 终端面板 | 右侧"终端"页签 |
| `ui-sidebar-browser` | 浏览器面板 | 右侧"浏览器"页签（**仅 desktop 启用**） |
| `ui-sidebar-documentpreview` | （目录未抽出；catalog：预览 Office/表格/Markdown/代码/图片/PDF/HTML/纯文本） | 右侧"文档"页签 |
| `ui-conversation` | 会话界面框架 | 会话外壳、composer、队列 |
| `ui-chat` | 聊天内容展示 | 消息气泡、状态条；transcriptView、performanceUsage（本机 verbose/detailed） |
| `ui-tool` | 工具调用展示 | 工具调用树与按工具的专用视图 |
| `ui-approval` | 操作审批界面 | 需要审批时接管 composer |
| `ui-attachment` | 附件展示 | 输入区/消息内的图片与文件 |
| `ui-brand-official` | DeepSeek 品牌展示 | 侧栏与会话的品牌位 |
| `ui-deliverables` | 文件变更与交付展示 | 每轮结束后的改动文件卡与交付卡 |
| `ui-workspace` | 工作区选择界面 | 侧栏与空态的工作区选择 |
| `ui-workflow-run` | 工作流运行展示 | 会话内 workflow 节点 |
| `ui-input-trigger` | 输入联想服务 | / 与 @ 触发的候选菜单 |
| `ui-commands` | 命令选择界面 | / 命令面板 |
| `ui-skill` | 技能引用与展示 | 技能引用与技能工具行 |
| `ui-subagent` | 子智能体会话界面 | 子智能体会话目录、@ 引用、续聊入口 |
| `ui-reference` | 文件与会话引用界面 | @ 文件/会话引用 |
| `ui-secret-mask` | 凭据遮挡 | 已发送文本里的凭据打码（删该行即关闭） |
| `ui-jobs` | 后台任务界面 | 会话头部的后台作业列表与记录面板 |
| `ui-schedule` | 任务界面 | 任务管理页 + 会话提醒目录 |
| `ui-goal` | 会话目标栏 | 输入框上方 GoalBar |
| `ui-plan` | 计划审阅界面 | 计划模式的 composer 座位、计划卡片、侧栏预览 |
| `ui-user-questions` | 用户问答界面 | ask_user_question 的接管界面与计划审阅 |
| `ui-model-selection` | 模型选择界面 | /model 弹出选择与 composer 座位 |
| `ui-permission` | 权限模式界面 | 通用设置里的新会话默认 + 会话内 /permission |
| `ui-agent-preset` | Agent 预设界面 | 通用设置里的默认预设行、会话内座位、组合编辑器 |
| `ui-message-feedback` | 消息反馈界面 | 消息动作条 Like/Dislike、/feedback 弹窗 |
| `ui-trajectory` | 运行轨迹 | 轨迹事件账本 + 计时总览 |
| `ui-cordis` | 动态插件运行卡片 | cordis_define 卡片与其运行/停止开关 |
| `ui-open-in-app` | 外部应用打开界面 | 会话头 "Open In…" 按钮与文档预览的默认应用 |
| `ui-shortcuts` | 快捷键设置界面 | 快捷键参考/录制 |
| `ui-theme` | 界面主题 | 明暗 / 跟随系统 |
| `ui-settings` | 设置界面框架 | 设置窗口外壳与槽位契约 |
| `ui-settings-general` | 通用设置与欢迎提示 | 设置·通用 |
| `ui-settings-models` | 模型设置界面 | 设置·模型 |
| `ui-settings-account` | （目录未抽出；catalog：DeepSeek 登录 + Platform 账单入口） | 设置·账号 |
| `ui-plugin-manager` | 插件管理界面 | **侧栏 Plugins 页**：安装/启用/停用/重试/组合插件包 |
| `ui-settings-plugins` | 内置插件设置入口 | 设置里的"内置插件"分区与标签页容器 |
| `ui-settings-plugin-inventory` | 内置插件列表界面 | 只读清单（内置 bundle + 各 preset 用的插件） |
| `ui-settings-shell` | 命令执行设置 | 内置插件页·命令执行 |
| `ui-settings-agent-loop` | 智能体运行设置 | 内置插件页·智能体运行 |
| `ui-settings-subagent` | 子智能体设置 | 内置插件页·子智能体 |
| `ui-settings-web-search` | 网页搜索设置 | 内置插件页·网页搜索 |
| `ui-settings-session-log` | 会话日志上传设置 | 内置插件页·会话日志上传（写 session-log-deepseek 命名空间） |
| locale / shortcuts / resources | 语言 / 快捷键路由 / 资源模型 | 基础设施 |

### 2.9 Skill

| id | 包 | 层 | 状态 | 配置键 |
|---|---|---|---|---|
| `skill` | dsh-skill | base | 开 | cfg yes（技能提供者注册表） |
| `skill-filesystem` | 同名 | base | **web 层 disable**（:511-512），改由 preset 挂 | providerName(filesystem)、includeDefaultRoots(true)、dshHome、agentsHome、customSkillDirs[]、watch(true)、watchUsePolling(false)、watchStabilityThresholdMs、watchPollIntervalMs、watchMaxProjects、watchFollowSymlinks(true)、bundledSkillDir |
| `tool-skill` | 同名 | base | **web 层 disable**，由 preset 挂 | catalogDescriptionMaxLength |

cordis preset 额外给 skill-filesystem 追加 customSkillDirs = dsh-agent-preset 自带 skills/ 目录（`presets/cordis.patch.yml:122-126`），即"插件开发与编排参考"那套内置技能。

### 2.10 Subagent / Agent Teams

| id | 包 | 层 | 状态 | 配置键 |
|---|---|---|---|---|
| `subagent` | dsh-subagent | base | 开（宿主面） | maxDepth(1)、maxActiveSubagents(8) |
| `subagent-spawn-in-process` | 同名 | base | 开 | providerName(spawn) |
| `subagent-fork-in-process` | 同名 | base | 开 | providerName(fork) |
| `tool-subagent-control` | 同名 | base | web disable → preset 挂 | — |
| `tool-subagent-list-agents` | .../list-agents | base | web disable → preset 挂 | — |
| tool-subagent / tool-subagent-fork | dsh-tool-subagent | base | web disable → preset 挂 | 见 §2.4 |
| `subagent-model-selection-settings` | dsh-tool-subagent/model-selection-settings | web | 开 | enabled(false)、allowedModels[]（volatile） |
| `agent-team` | dsh-experimental-agent-team | exp | 开 | maxMembers(8)、maxTasks(256)、maxMessageBytes(65536)、disposalTimeoutMs(5000) |
| `tool-agent-team` | dsh-experimental-tool-agent-team | exp | 开 | freshProvider(spawn)、forkProvider(fork) |
| `ui-agent-team` | dsh-experimental-client-ui-agent-team | exp | 开 | — |

tool-agent-team 注册的 9 个工具（`dsh-experimental-tool-agent-team/lib/index.js`）：spawn_teammate、send_message、list_agents、wait_agent、interrupt_agent、team_task_create、team_task_list、team_task_get、team_task_update。

### 2.11 任务 / 作业 / 计划

| id | 包 | 层 | 配置键 / 作用 |
|---|---|---|---|
| `jobs` | dsh-jobs-local | base | 作业注册表（**故意留宿主面**，注释见 `dsh-web-app/cordis.patch.yml:483-493`） |
| `tool-jobs` | 同名 | base（web disable） | job_* 三件套 |
| `schedule` | dsh-schedule | web | deliveryHistoryDays、deliveryHistoryRecords；到期提醒**投递回原会话** |
| `tool-schedule` | 同名 | preset | schedule_* 四件套 |
| `goal` | dsh-goal | base | defaultMaxGoalRounds(256) |
| `goal-round-driver` | 同名 | base | 目标续跑（竞态围栏） |
| command-goal / tool-goal | 各自包 | base（web disable → preset） | /goal 与 get_goal / update_goal |
| `plan-mode` | 同名 | base（web disable → preset） | section（计划模式提示词，yml 内联全文） |
| commands / command-feedback / command-compact | 各自包 | base | 人类命令注册表与 /feedback、/compact |
| ui-jobs / ui-schedule / ui-goal / ui-plan | 各自包 | web | 对应界面（见 §2.8） |

### 2.12 市场与插件管理

| id | 包 | 层 | 状态 | 配置键 / 事实 |
|---|---|---|---|---|
| `plugin-manager` | dsh-plugin-manager | base | 开（有 profile 才开） | pnpmCommand(pnpm)、outputBytes(16384)、lockWaitMs(120000)、inspectTimeoutMs(20000)、githubConnectionTimeoutMs(5000)、idleTimeoutMs(600000)、registry、fallbackRegistries([NPMMIRROR_REGISTRY]) |
| `tool-plugin-manager` | dsh-plugin-manager/tools | base+web+preset | **三处均 disable** | — |
| `plugin-market` | dsh-plugin-market | 目录未抽出 | 未见于本 profile 的 insert 行 | cfg yes；catalog 描述"配置化插件市场索引，服务 Web Discover 页与 plugin_market 工具" |
| `tool-plugin-market` | dsh-plugin-market/tools | preset | !!js "!ctx.get('profileContext')" | — |
| `ui-plugin-manager` | 同名 | web | 开 | cfg yes（侧栏 Plugins 页） |
| `ui-settings-plugin-inventory` | 同名 | web | 开 | 只读清单 |
| `plugin-inventory` | dsh-host-plugin-inventory | web | 开 | 清单的 Remote 投影 |
| `plugin-package-inventory-deepseek` | 同名 | base | 开 | 请求侧的插件包清单扩展 |

> 注意区分：本机 profile 另装了第三方市场类插件（dshmarket、dsh-find-plugins、@liustack/modlens 等，见 `E:\dsh-data\profiles\desktop\package.json:4-11`），**不是**官方 bundle 的一部分。

### 2.13 遥测与日志

| id | 包 | 层 | 状态 | 配置键 / 事实 |
|---|---|---|---|---|
| `otel` | dsh-otel | base | 开 | —（普通事件与 Session-log 两条 OTLP 通道的服务层） |
| `session-telemetry-otel` | 同名 | base | 开 | mode(FEEDBACK_ONLY)、shutdownTimeoutMillis(3000)、maxRequestBytes(4000000)、exporter.url(https://dsh-otel-collector.deepseeksvc.com/v1/logs)、exporter.compression(gzip)、exporter.timeoutMillis(1000)、processor.scheduledDelayMillis(10000)、processor.maxQueueSize(2048)、processor.maxExportBatchSize(2048)、processor.exportTimeoutMillis(1500) |
| `desktop-product-telemetry` | dsh-host-product-telemetry-otel | web | 开（仅 desktop） | serviceName(deepseek-harness-desktop)、serviceVersion($DSH_CLIENT_VERSION)、endpoint($DSH_PRODUCT_ANALYTICS_OTLP_URL)、scheduledDelayMillis(30000)、timeoutMillis(15000)、exportTimeoutMillis(20000)、shutdownTimeoutMillis(2000) |
| `product-analytics` | dsh-client-product-analytics | web | 开（仅 desktop） | enabled(true)、appVersion、environmentQueryTimeoutMillis(5000)、environmentQueryMaxOutputBytes(16384) |
| `session-log-deepseek` | 同名 | base | 开 | 会话日志随官方 API 请求的增量扩展；UI 开关在"内置插件·会话日志上传" |
| `message-feedback` | 同名 | web | 开 | maxNoteBytes(8192) |

session-telemetry-otel 的语义由 base 注释写死（`dsh-base/cordis.patch.yml:205-217`）：**只在用户显式反馈后释放一段会话日志前缀**，普通活动不触发采集；DSH_TELEMETRY_OTLP_URL 改端点；**非空 DSH_TELEMETRY_DISABLED（任何值，含 0/false）整进程退出**——注释同时说明"config 不能关这一行，是启动器把该行 patch 成 disabled"。

### 2.14 压缩与上下文管理（补充分组）

| id | 包 | 层 | 状态 | 配置键 |
|---|---|---|---|---|
| `token-meter` | 同名 | base | 开（宿主面） | {}；拥有 context-meter 投影单元 |
| `compaction-basic` | 同名 | base（web disable → preset） | thresholdRatio、headroomTokens、retainRatio、retainTokens、summarizationProvider、summarizationModel、maxTokens、compactionRetries、maxOverflowRetries、modelPolicies[]、auto |
| `command-compact` | 同名 | base（web disable → preset） | —（/compact） |
| `tool-result-pruner` | dsh-compaction-tool-result-pruner | base（web disable → preset） | thresholdChars(8192)、headChars(4096)、tailChars(1024) |
| `image-offload` | dsh-compaction-image-offload | base | —（超图像预算时把最老图片换占位并重试） |
| spill-policy / spill-local | 各自包 | base | maxInlineTokens(12500) |
| `repeat-tool-reminder` | 同名 | base | thresholds([3,5,8])、include[]、exclude[]、argumentsPreviewChars(500) |
| `timeout-policy` | dsh-tool-call-timeout-policy | base | —（给每次工具调用挂 deadline，超时返回 TOOL_TIMEOUT） |

### 2.15 Web 能力（search / fetch）

| id | 包 | 层 | 配置键 |
|---|---|---|---|
| `web` | dsh-web | base | searchProvider(deepseek-official)、fetchProvider(http) |
| `web-search-deepseek` | 同名 | base | apiKey（secret, volatile）、apiKeyEnv(DEEPSEEK_API_KEY)、baseURL、model、apiVersion、maxTokens、maxUses(5) |
| `web-fetch-http` | 同名 | base | maxResponseBytes(5e6)、maxBodyChars(1e5)、timeoutMs(30000)、maxRedirects(5)、userAgent(deepseek-harness/0.0.1 …) |
| `tool-web` | 同名 | base（web disable → preset） | 见 §2.4 |

---

## 3. 重点插件详解（作用 / 触发 / 配置 / 开关）

### 3.1 工具 · 文件系统 tool-fs

- **作用**：给模型 read / write / edit / read_image 四个文件工具，走 ctx.fs 缝，因此受沙箱与观察策略约束。
- **触发**：模型调用这四个工具时；read 遇图片走 read_image 分支，结果受 readMaxBytes(50KiB)、readLimit(2000 行) 裁剪（`dsh-tool-fs/lib/index.js:1194-1203`）。
- **配置**：read/readImage/write/edit（可单独关）、readLimit、readMaxLineLength、readMaxBytes、readStreamMinSize。
- **开关**：无 UI 页。改 preset（id tool-fs）或在 profile patch 对该 id 写 disabled: true；彻底不给文件能力要同时考虑 fs-sandbox。

### 3.2 工具 · 检索 tool-fs-search

- **作用**：glob（找文件）与 grep（搜内容），底层用打包的 ripgrep。
- **触发**：模型调用 glob/grep；超上限时由 sampleOverCapGlobResults 决定是否采样（本 profile 为 false → 不采样，直接截断），grep 最多 250 条、30s 超时。
- **配置**：见 §2.4。
- **开关**：同 3.1（preset 行 id tool-fs-search）。

### 3.3 工具 · Shell tool-pwsh / tool-bash

- **作用**：Windows 上给 pwsh 工具，其他平台给 bash。
- **触发**：模型调用 pwsh（本机）/ bash；run_in_background 转后台作业，promoteOnTimeout 在超时后把前台命令提升为后台作业并返回 job id。
- **配置**：enableRunInBackground(true)、promoteOnTimeout(true)；执行侧还有 bash-sandbox.timeoutMs(60000) 与对应的沙箱行。
- **开关**：无 UI 页；base 已按平台写好两个条件 disable（`dsh-base/cordis.patch.yml:281-287`），要彻底关 shell 就在 preset 把对应 id 置 disabled: true。

### 3.4 工具 · 后台作业 tool-jobs + jobs-local

- **作用**：job_list / job_output / job_kill 三个工具 + 宿主面的作业注册表。
- **触发**：run_in_background: true 的命令、超时被提升的命令；作业完成时按 completionDelivery(wakeup) 唤醒会话（maxConsecutiveWakes 限制连续唤醒）。
- **配置**：waitTimeoutMs(30s)、maxWaitTimeoutMs(600s)、completionDelivery、maxConsecutiveWakes；注册表侧 maxConcurrentJobsPerOwner(10)、retainBytes(256KiB)、settledRetainBytes(16KiB)。
- **开关**：工具随 preset（id tool-jobs）；注册表（jobs）故意留宿主面，因为"preset 外的作用域看不见它"（`dsh-web-app/cordis.patch.yml:483-491`）。界面开关是会话头部后台任务图标（ui-jobs）。

### 3.5 工具 · 待办 tool-todo

- **作用**：todo_write，把任务清单写进事件溯源会话日志，从而在 UI 显示进度。
- **触发**：多步任务时模型主动调用；allowParallelInProgress: true 允许同时多条 in_progress。
- **配置**：allowParallelInProgress（必填）。
- **开关**：preset 行 id tool-todo。计划模式明确要求**不要**用它做规划（plan-mode.section，`dsh-base/cordis.patch.yml:340`）。

### 3.6 工具 · 问人 tool-ask-user

- **作用**：ask_user_question，在会话里向用户提结构化问题。
- **触发**：模型调用该工具 → UI 由 ui-user-questions 接管 composer；mode: legacy 时无倒计时，timed 时按 timeout(120s) 超时。
- **配置**：mode、timeout。
- **开关**：preset 行 id tool-ask-user；UI 侧可关 ui-user-questions（那时工具仍在，但呈现退化）。

### 3.7 工具 · 网页 tool-web + web + 两个 provider

- **作用**：web_search（DeepSeek 服务端检索）与 web_fetch（匿名公共 HTTP(S) 抓取），正文一律加"外部内容不可信"前缀。
- **触发**：模型调用这两个工具；搜索是一次完整的辅助模型请求（所以本 profile 给 60s），抓取 30s。
- **配置**：工具侧 search/fetch、searchMaxResults(8)、searchMaxQueries(4)、searchTimeoutMs、fetchTimeoutMs、fetchMaxOutputChars；provider 侧见 §2.15。
- **开关**：搜索的 key/端点/请求预算**有 UI 页**——设置 → 内置插件 → 网页搜索（dsh-client-ui-settings-web-search，写 apiKey、baseURL、maxUses，见其 `lib/client.js` 里的 apiKeyHint/baseUrlHint/maxUsesHint）。整体关闭抓取：preset 里 tool-web.config.fetch: false，或把 web 行的 provider 换成更严实现。

### 3.8 工具 · 技能 tool-skill + skill-filesystem

- **作用**：skill 按名称加载一份技能说明；skill-filesystem 从磁盘发现技能（customSkillDirs、$DSH_HOME 与 agents 目录、内置 bundle 自带技能），并 watch 变更。
- **触发**：模型调用 skill({name})；UI 里 @ 与技能引用由 ui-skill 呈现；技能目录变化由 watch 失效重建（watch(true)）。
- **配置**：见 §2.9。
- **开关**：宿主层 skill-filesystem 在 web 被 disable（注释：presets own local discovery，`dsh-web-app/cordis.patch.yml:502-512`）；实际由各 preset 的 skill-filesystem 决定搜索哪些目录，改 preset 的 customSkillDirs 即可增减技能根。

### 3.9 沙箱与权限 sandbox / sandbox-policy / approval / permission

- **作用**：sandbox-local 提供真正的进程级围栏后端（bwrap / landlock-run / Seatbelt / Windows ACL 受限令牌，探测后 fail-closed）；sandbox-policy 决定**每次调用**用哪种模式与工作区根；user-approval 提供一次性审批决策；permission-presets 把"沙箱模式 + 审批策略"打包成一个用户可选项。
- **触发**：任何写文件、跑命令的工具调用都会向 sandbox-policy 要策略；需要更宽权限时向 approval 发请求，UI 由 ui-approval 接管。
- **配置**：mode（默认 workspace-write，DSH_PERMISSION_MODE 可覆写）、workspaceRoot（默认 process.cwd()）、approval.policy（ask / never）、permission.presets（只读 / 工作区写 / 完全访问三档）。
- **开关**：**有 UI**——设置 → 通用里的新会话默认权限，以及会话内 /permission 弹窗（dsh-client-ui-permission-presets）。改默认档位最终落到 profile patch。
- **本机事实**：本次会话文件策略为 workspace-write，且审批不可交互（自动拒绝），与 presets 里 workspace-write + approval: ask 的组合一致。

### 3.10 Subagent：subagent + tool-subagent + 背板

- **作用**：subagent 是提供者注册表（spawn 新建子代理、fork 继承父上下文）；tool-subagent 把某个 provider 暴露成模型工具（本 profile：subagent → spawn、subagent_fork → fork）。
- **触发**：模型调用 subagent / subagent_fork；list_agents / send_message / interrupt_agent 用于查看与续聊；UI 由 ui-subagent 呈现目录与续聊入口。
- **配置**：注册表 maxDepth(1)、maxActiveSubagents(8)；工具侧 provider、toolName、modelSelectionSettings、agentOptions、agentPreset、allowedAgentPresets、maxDepth。模型自选能力在 model-selection-settings：enabled(false)、allowedModels[]。
- **开关**：委派深度 / 并发 / 允许模型**有 UI**——设置 → 内置插件 → 子智能体（dsh-client-ui-settings-subagent，字段 maxDepth、maxActiveSubagents、允许模型清单）。list_subagent_models 工具只在 modelSelectionSettings: true 时出现。

### 3.11 计划任务 schedule + tool-schedule + ui-schedule

- **作用**：宿主级持久提醒：任务存在 Host，到期时**投递回它原本的会话**（不是新会话）。
- **触发**：模型调用 schedule_create/list/update/delete；用户也可在**任务页**管理（ui-schedule：任务管理页 + 会话提醒目录）。投递历史受 deliveryHistoryDays、deliveryHistoryRecords 约束。
- **配置**：仅两条历史保留参数（`dsh-schedule/lib/index.js` 的 Config）；tool-schedule 本身无 schema。
- **开关**：UI 任务可见可管；schedule 行本身无 UI 开关，要停就 profile patch 里 disable（会连带 tool-schedule 失效）。

### 3.12 目标 goal / tool-goal / ui-goal

- **作用**：同一会话内的持久目标（可跨自动续跑轮次），get_goal / update_goal 让模型读写，goal-round-driver 负责一轮轮推动。
- **触发**：用户用 /goal 或模型在有目标时调用 update_goal；界面是输入框上方的 GoalBar。update_goal(action: blocked) 需连续 blockedAfterConsecutiveRounds(3) 才允许。
- **配置**：defaultMaxGoalRounds(256)、blockedAfterConsecutiveRounds(3)。
- **开关**：UI 上可暂停/恢复目标；整体移除就 disable goal / tool-goal / ui-goal。

### 3.13 压缩与上下文 compaction-basic / tool-result-pruner / spill-policy / image-offload

- **作用**：compaction-basic 按 token 计量做阈值压缩（可 LLM 摘要）；tool-result-pruner 先把超大工具结果按 head/middle/tail 裁剪；spill-policy 把超 maxInlineTokens(12500) 的内容落盘并给可恢复路径；image-offload 在图像超预算时把最老图片换占位并重试。
- **触发**：上下文接近阈值（自动）或用户 /compact（一次显式压缩，dsh-command-compact）；工具结果超 thresholdChars(8192) 时裁剪。
- **配置**：见 §2.14。
- **开关**：无设置页；compaction-basic.auto 与阈值只能在 preset 或 profile patch 改。token-meter 与 jobs 一样**必须留宿主面**（`dsh-web-app/cordis.patch.yml:529-537`）。

### 3.14 插件管理 plugin-manager + ui-plugin-manager + 清单

- **作用**：dsh-plugin-manager 是当前 profile 的插件包管理器（装/启/停/重试/组合 bundle，底层调 pnpm）；ui-plugin-manager 是**侧栏 Plugins 页**；ui-settings-plugin-inventory 是设置里的只读清单；plugin-inventory 提供 Loader 状态投影。
- **触发**：用户在 Plugins 页操作时；ui-plugin-manager 通过 pluginManager Remote 调宿主，宿主没有 profile 时自报不可用（`dsh-web-app/cordis.patch.yml:315-319`）。
- **配置**：pnpmCommand、outputBytes、lockWaitMs、inspectTimeoutMs、githubConnectionTimeoutMs、idleTimeoutMs、registry、fallbackRegistries（默认含 npmmirror）。
- **开关**：模型侧 tool-plugin-manager **是关的**（见 §5）；用户侧入口就是侧栏 Plugins 页，装/停 bundle 的等价物是改 dsh.profile.bundles。

### 3.15 遥测：三个必须区分的通道

| 通道 | 何时发出 | 用户可关吗 |
|---|---|---|
| session-telemetry-otel（会话日志） | **只有用户对某条消息显式反馈后**，释放该段日志前缀（FEEDBACK_ONLY） | 只能改 profile patch / 启动器；注释明确"config 不能 disable 该行，是启动器 patch 成 disabled"；进程级开关 DSH_TELEMETRY_DISABLED（非空即退） |
| desktop-product-telemetry + product-analytics（产品事件） | 桌面版产品使用事件，30s 批量导出 | 无设置页；product-analytics.enabled: true 写死在 web patch，需改 profile patch |
| session-log-deepseek + plugin-package-inventory-deepseek（随模型请求） | 作为官方 API 请求的增量扩展随请求上传 | **有 UI**：设置 → 内置插件 → 会话日志上传（dsh-client-ui-settings-session-log，写 session-log-deepseek 命名空间） |

---

## 4. 用户可见的一级开关清单

表里没有的能力，只能改 profile patch。

| 用户想关的东西 | 去哪 | 落到哪一行 |
|---|---|---|
| 某个已装 bundle / 插件包 | 侧栏 **Plugins** 页 | dsh.profile.bundles + 该 bundle 的 patch |
| 新会话默认权限档位 | 设置 → 通用 | permission / ui-permission |
| 本会话权限 | 会话内 /permission | permission.defaultPreset |
| 新会话默认模型 / 供应商 | 设置 → 模型（+ 账号页登录） | agent-default-model、llm-deepseek* |
| 会话内换模型 | /model | 会话状态 |
| 委派深度 / 并发 / 子代理可用模型 | 设置 → 内置插件 → 子智能体 | subagent、subagent-model-selection-settings |
| 并行工具调用数 | 设置 → 内置插件 → 智能体运行 | agent-loop.maxParallelToolCalls |
| 命令执行超时 / 输出上限 | 设置 → 内置插件 → 命令执行 | shell 命名空间（timeoutMs / maxOutputBytes） |
| 网页搜索 key / 端点 / 预算 | 设置 → 内置插件 → 网页搜索 | web-search-deepseek |
| 会话日志随请求上传 | 设置 → 内置插件 → 会话日志上传 | session-log-deepseek |
| 主题 / 快捷键 | 设置 → 外观 / 快捷键 | ui-theme.preference、locale、ui-shortcuts |
| 默认 agent preset | 设置 → 通用 | agent-preset-registry.selectedDefault |
| 后台作业观察 | 会话头部作业徽标（ui-jobs） | 只影响观察，不影响执行 |
| 提醒 / 计划任务 | 任务页（ui-schedule） | schedule |
| 消息反馈 / /feedback | 消息动作条 | message-feedback |
| 会话导出 | /export | session-log-download |

---

## 5. disabled 行全清单与原因

### 5.1 base 层的 disable

| id | 写法 | 原因（源码给的） |
|---|---|---|
| `tool-plugin-manager` | true | 静态关闭：不把"装插件"能力暴露给模型（`dsh-base/cordis.patch.yml:16-18`） |
| `plugin-manager` | !profileContext | 只在 profile 环境装（桌面版**是装的**） |
| `hmr` | !profileContext | 注释：配置默认热重载，模块根需 opt-in，故 root: []（:27-32） |
| config-editor / settings | !profileContext | 表单需写回 profile patch，没有 profile 就没有可写目标（:105-111） |
| bash-sandbox / pwsh-sandbox / tool-bash / tool-pwsh | 平台判定 | Windows 装 pwsh 系、非 Windows 装 bash 系（:249-258、:281-287） |

### 5.2 web 层的 23 个 disable —— **核心架构决策，不是省事**

`dsh-web-app/cordis.patch.yml:457-577` 有完整注释，归纳三句：

1. **agent 面搬到 preset**：一个会话该有哪些工具、提示段、委派后端，由它的 preset 声明；宿主层再留一份会让"每个会话的工具集"取决于进程里恰好装了谁。
2. **服务留宿主面**：jobs（作业注册表）、skill（技能注册表）、goal + goal-round-driver、token-meter、subagents（进程单例，浏览器经 api-proxy 读它）**不能**进 preset，否则 preset 外的作用域看不见它们（:483-491、:517-519、:529-534、:545-550）。
3. **禁用而非删除**：base 被多模式共享，删掉的行会在某次重排后"悄悄复活"（:464-466）。

被 disable 的 23 行：tool-plugin-manager、tool-bash、tool-pwsh、tool-jobs、tool-fs、tool-fs-search、skill-filesystem、tool-skill、command-goal、tool-goal、plan-mode、compaction-basic、command-compact、tool-result-pruner、tool-subagent-control、tool-subagent-list-agents、tool-subagent、tool-subagent-fork、workflow-ptc、tool-workflow、agent-instructions、tool-todo、tool-web。

> 特别注意 agent-instructions（`AGENTS.md` / `CLAUDE.md` 加载器）：**web 层也是 disable 的**，所以桌面版会话读到的工作区指令来自 preset 那一行（standard/cordis/ptc 都有，maxBytes: 65536），而不是 base 的宿主行。

### 5.3 其余条件 disable

| id | 条件 | 在本机结果 |
|---|---|---|
| `ui-sidebar-browser` | profileContext.name !== 'desktop' | desktop → **启用**（注释：Web profile 选择性开启，桌面保留沙箱 HTTP(S) 浏览器页签） |
| desktop-product-telemetry / product-analytics | 同上 | desktop → **启用** |
| tool-plugin-manager（preset 内） | !profileContext | 见 §1.2 |
| tool-plugin-market（preset 内） | 同上 | 见 §1.2 |
| preset minimal 的 pty 行 | 平台判定 | terminal-bash / persistent-bash 在 Windows 关；terminal-pwsh 行也指向 dsh-terminal-bash 且带 platform 判定——**该行在 Windows 同样关**，属源码原样，未做修正 |
| preset ptc 的 workflow-ptc / tool-workflow | 静态 true | PTC 模式不带 workflow 工具 |
| exp-team 的 4 行 | 静态 true | 关掉宿主面旧 subagent 工具，让位给 Agent Teams |

### 5.4 Agent preset 一览（决定"会话里能看见什么工具"）

| preset | 行数 | 与 standard 的差异 |
|---|---|---|
| standard（registry 的 default） | 33 | 基准：persona + agent-instructions + time-context + fs/fs-search/shell/jobs/schedule + skill + goal + plan + compaction + delegation + ask-user + todo + web + present |
| cordis（本 profile 的 selectedDefault） | 34 | 在 standard 基础上 **加** tool-cordis（cordis_inspect_list/query）与 customSkillDirs（dsh-agent-preset/skills）；**没有** host 版 skill-filesystem 默认根那些行（preset 自己带 skill-filesystem 行） |
| `ptc` | 34 | 加 tool-presentation（PTC 呈现），workflow-ptc / tool-workflow 关闭 |
| `minimal` | 12 | 只有 persona + tool-fs + compaction 组 + 持久终端组（pty 面） |

---

## 6. dsh-client-ui-settings-* → 桌面设置页映射

设置窗口骨架由 ui-settings 提供（槽位契约 + 共享表单），各页面注册进去。**注意分两类**：顶层分区 vs 注册进"内置插件"页的分页。

| 包 | 中文名（`locale/zh.js`on 的 meta.title） | 位置 | 页内改的是什么 |
|---|---|---|---|
| `ui-settings` | 设置界面框架 | 窗口外壳 | 不含具体项 |
| `ui-settings-general` | 通用设置与欢迎提示 | **顶层分区·通用** | 欢迎提示版本（welcomeNoticeVersion）、通用项、设置文案 |
| `ui-settings-models` | 模型设置界面 | **顶层分区·模型** | 模型目录与凭据联接（写 llm-deepseek* / 凭据文档） |
| `ui-settings-account` | （目录未抽出；catalog：DeepSeek 登录 + Platform 账单入口） | **顶层分区·账号** | 登录状态、引导进度（本机 profile 有 version/step/purpose/process/completion/usage/developerTools 这些引导字段） |
| `ui-theme` | 界面主题 | 顶层分区·外观 | preference（本机 dark） |
| `ui-shortcuts` | 快捷键设置界面 | 顶层分区·快捷键 | 按键绑定偏好 |
| `ui-settings-plugins` | 内置插件设置入口 | **顶层分区·内置插件**（外壳 + 标签页容器） | 只负责导航与标签栏 |
| `ui-settings-plugin-inventory` | 内置插件列表界面 | 内置插件 → **清单页签** | 只读：全局插件清单 + 各 preset 用了哪些插件 |
| `ui-settings-shell` | 命令执行设置 | 内置插件 → **命令执行** | timeoutMs、maxOutputBytes（shell 命名空间） |
| `ui-settings-agent-loop` | 智能体运行设置 | 内置插件 → **智能体运行** | maxParallelToolCalls |
| `ui-settings-subagent` | 子智能体设置 | 内置插件 → **子智能体** | maxDepth、maxActiveSubagents、允许模型清单 |
| `ui-settings-web-search` | 网页搜索设置 | 内置插件 → **网页搜索** | apiKey、baseURL、maxUses |
| `ui-settings-session-log` | 会话日志上传设置 | 内置插件 → **会话日志上传** | session-log-deepseek 命名空间的开关 |
| `ui-plugin-manager` | 插件管理界面 | **不在设置里**：侧栏 Plugins 页 | 安装/启用/停用/重试/组合插件包 |

证据：各包 `locale/zh.js`on:meta.title；注册关系见 `dsh-web-app/cordis.patch.yml:415-455`（尤其 :426-434：内置插件分区的导航入口 + 各官方配置页"one companion package per host-plane namespace, each registering its page into the Plugins page"）。

---

## 7. 内部管道（无用户开关，合并说明）

以下条目没有用户可见配置，也没有 UI 页，出问题只能看日志：
timer、llm、session、typert、typert-loader、typert-gateway、remote-access、agent、user-questions、deepseek-llm-api-extensions、plugin-package-inventory-deepseek、llm-retry、subprocess、shell-env、session-projection、session-projection-cache、storage / storage-json / storage-domain、otel、session-checkpoint-policy、timeout-policy、repeat-tool-reminder、spill-local、client-hmr、modules、file-upload、api-remotes、connection、resources、locale、shortcuts、session-stats、session-turn-outline、harness-dev-context、mcp-resources（无 MCP server 时不下发工具）。

> 其中 repeat-tool-reminder、timeout-policy、spill-policy、session-checkpoint-policy 虽属"策略类"，但**策略值写在 patch 里**（见 §2.14），没有 UI。

---

## 8. 未取证 / 需注意（诚实标注）

1. **7 个包的目录没有出现在抽取树里**，只能引用官方生成目录 `dsh-agent-preset/skills/cordis-composition-reference/references/packages.md` 的描述，未读其 lib：dsh-api-remotes、dsh-api-session-controller、dsh-client-ui-settings-account、dsh-client-ui-sidebar-documentpreview、dsh-plugin-market、dsh-ptc-runtime-node、dsh-working-directory。
2. **preset 作用域内 ctx.get('profileContext') 的解析结果**未在源码中找到明确说明；本文只照抄表达式，不推断 tool-plugin-manager / tool-plugin-market 在各 preset 里的最终状态。
3. **plugin-market 的宿主行**：base/web 的 insert 里没有 plugin-market，只在 preset 里出现 tool-plugin-market；catalog 说该包有 Config。若要"Discover"市场页，本机实际由第三方 dshmarket 提供。
4. **compaction-basic 各阈值的具体默认数字**由包内 schema 常量给出（thresholdRatioSchema 等），本次只取到键名，未逐个反解常量值。
5. **minimal preset 的 terminal-pwsh 行**指向 dsh-terminal-bash 且带 process.platform !== 'win32' 判定，在 Windows 上两行 pty 后端都关——源码原样，未判断是否为有意设计。
6. **非官方来源的工具**（讲课时不要混进"官方核心插件"）：task_board_*、ralph、fact_register、weknora_*、find_dsh_plugins、modlens_read_image 均来自第三方包（@linxin666/dsh-client-ui-task-board、dshmarket、@wxg-prc-cpg/dsh-weknora、dsh-find-plugins、@liustack/modlens 等）。已用 grep 在 `E:\dsh-data\profiles\desktop\node_modules` 里确认 task_board_create 只出现在 @linxin666/dsh-client-ui-task-board。
7. **dsh-experimental-auto-review / agent-team 的实际生效状态**：两者的 patch 都在本 profile 的 bundle 列表里、行上也无 disable；但 auto-review 的 README 写"dsh 安装随附此层但默认关闭，在 Web 侧栏插件页开启或显式安装之前默认保持三种权限模式"。二者是否存在额外的"bundle 启停状态"存储未在 .plugin-manager 目录中找到（该目录只有 logs/）。因此本文只按 patch 陈述装载关系，不宣布其运行期可见效果。
