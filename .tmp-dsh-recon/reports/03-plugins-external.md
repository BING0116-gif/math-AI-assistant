# 03 · 第三方插件清点：bundle 层与 profile patch 层

> 取证对象：本机当前运行的 DeepSeek Harness 桌面版 0.2.1-rc.1（Electron 外壳 F:\DSH，运行时在 app.asar 内）。
> 路径简写：
> - `asar/<包名>/…` = `.tmp-dsh-recon\asar\@deepseek-ai\<包名>\…`（从 app.asar 抽出的官方源码）
> - `nm/<包名>/…` = `E:\dsh-data\profiles\desktop\node_modules\<包名>\…`（外部插件真实安装位置）
> - `prof/…` = `E:\dsh-data\profiles\desktop\…`
> - `f.js:123` 指该文件内实际行号。

---

## 0. 三句话结论

1. 本机装了 **7 个第三方 npm 插件 + 1 个聚合壳（内含 20 个子面板行）+ 2 个随安装附带的实验包**。它们靠「profile 的 `dsh.profile.bundles` 清单 + 每包自带的 `dsh.bundle.patch`」挂进运行时，用户自己的 `cordis.patch.yml` 是最后一道覆盖层。
2. **两个插件实测不可用**：`@liustack/modlens`（从 git 装的源码包缺 `dist/` 构建产物，工具一调用就抛 `Cannot find module …\dist\main.js`）；`@wxg-prc-cpg/dsh-weknora`（工具注册成功，但没有任何后端地址，默认 `http://localhost:8080` 无服务，实测 `fetch failed`）。
3. **两个实验包（Agent Teams、Auto review）虽然写在 `prof/package.json` 的 bundles 里，运行面并未生效**：本会话工具面仍是 `subagent` / `subagent_fork` / `list_agents`，而不是团队包的 `spawn_teammate` / `team_task_*`。原因未能定位（见 §3.8）。

---

## 1. 机制：这四层怎么叠起来（讲给新手）

一次启动的补丁顺序是源码写死的（`asar/dsh-app-boot/lib/index.js:1118-1136`）：

```text
package.json 的 dsh.profile.bundles（有序）
  -> 每个包的 dsh.bundle.patch 指向的 cordis.patch.yml
  -> profile 自己的 cordis.patch.yml      <- 用户层（§5 逐行解释的就是它）
  -> $DSH_HOME/cordis.patch.yml           <- 本机不存在
  -> 启动时 --patch overlay
  -> （最后）遥测硬关补丁
```

三件事必须记住：

- **插件的入场券只有一行**：`- insert: - id: <行id> / name: <npm 包名>`。`id` 是后续所有覆盖与开关的唯一把手。
- **用户层的 `config` 是整块替换，不是深合并**：想保留的字段要一起写全。原文："patch 是整块替换该行的 config，所以要保留的字段需要一并写出"（`nm/@wxg-prc-cpg/dsh-weknora/README_CN.md:60`）。
- **全有或全无**：DSH loader 把全部 patch 行当一个事务组挂载，任何一个插件 import 或启动失败都会回滚整组并中止启动（`nm/@linxin666/dsh-web-all/README.zh.md:21`）。另一条更温和的路径是"读不出来就跳过并记入 `skippedBundles`"（`asar/dsh-app-boot/lib/index.js:1054-1055`）。

**开关位置统一是两处**：

- UI：设置 -> 插件 -> 插件管理，逐行开关。市场/插件管理器把 `- id: … disabled: true|false` 写进 `prof/cordis.patch.yml`，DSH 的 HMR 约 1 秒重组，不用重启（`nm/dshmarket/README.zh.md:46`）。
- 手工：`prof/cordis.patch.yml` 里加 `- id: <行id>` + `disabled: true`。

---

## 2. 本机实测总表

| # | 包名 | 版本 | 行 id | 运行时状态 | 关键依据 |
|---|---|---|---|---|---|
| 1 | `dshmarket` | 1.66.22 | `dsh-market` | 在跑 | `prof/package.json`、`nm/dshmarket/package.json` |
| 2 | `@liustack/modlens` | 3.27.1 | `modlens` | 挂载了但**坏了** | 调用报 `Cannot find module …\dist\main.js` |
| 3 | `@linxin666/dsh-web-all` | 0.4.6 | `web-ui-*`（20 行） | 12 子面板活跃，degraded 为空 | `GET /api/dsh-web-all/rows` 实测 |
| 4 | `@anionex/dsh-turn-rewind` | 0.3.9 | `turn-rewind` | 在跑（存档目录已生成） | `E:\dsh-data\change-ledger` 存在 |
| 5 | `@wxg-prc-cpg/dsh-weknora` | 0.1.0 | `weknora` | 工具在，**后端不通** | 实测 `fetch failed`；`localhost:8080` 拒绝连接 |
| 6 | `dsh-context` | 0.71.0 | `dsh-context` | 在跑 | 侧栏「上下文洞察」入口，`nm/dsh-context/README.md:13-18` |
| 7 | `dsh-find-plugins` | 0.2.10 | `dsh-find-plugins` | 在跑（工具可用） | 本会话工具面含 `find_dsh_plugins` |
| 8 | `@deepseek-ai/dsh-experimental-agent-team-profile` | 0.2.1-rc.1 | `agent-team` / `tool-agent-team` / `ui-agent-team` | **清单里有，未生效** | 工具面仍是 `subagent`/`subagent_fork`/`list_agents` |
| 9 | `@deepseek-ai/dsh-experimental-auto-review` | 0.2.1-rc.1 | `auto-review` | 未见 Auto 权限模式被选中 | 当前会话策略是 `workspace-write` |

附带一个容易误判的点：本机还有第二个 profile `E:\dsh-data\profiles\web`（dsh-context 0.72.0、dshmarket 1.66.27、**没有**实验包、patch 只有 `dsh-market.allowRestart: false`）。判断桌面端实际跑的是 `desktop`：`E:\dsh-data\pet.json` 写入时间 2026/10/17 17:40:21 紧跟主进程启动 17:40:19，而宠物行只存在于 desktop 的聚合层里。

---

## 3. 逐个插件

### 3.1 dshmarket 1.66.22 —— 插件市场（"应用商店"）

- **是什么**：装在设置页里的插件市场。浏览/搜索 4200+ 社区插件、截图轮播、评论、收藏、分组、备注、一键装卸、逐插件更新、主题一键切换、备份恢复（WebDAV / GitHub Gist）、诊断面板、加载顺序拖拽、AI 修复提示词、脱敏日志导出（`nm/dshmarket/README.zh.md:31-55`）。
- **在系统里干什么**：host 半区真执行安装/卸载/更新（内部走 pnpm），并把"停用某插件"写成 `cordis.patch.yml` 的 `disabled` 行；浏览器半区是设置页的「插件市场」分区与卡片。
- **注册了什么**：一行 loader 条目 `dsh-market`（`nm/dshmarket/cordis.patch.yml`）；浏览器半区注入 `dsh-client-locale` / `dsh-client-ui-settings` / `dsh-client-ui-theme`（`nm/dshmarket/package.json` 的 `dsh.client.inject`）。**不注册模型工具**（`nm/dshmarket/lib` 里 grep 不到 `tools.register`）。
- **触发**：设置 -> 插件市场。
- **配置项**：更新通道（稳定 / Beta / 开发）、GitHub 加速前缀（也可用运维环境变量 `DSHM_GITHUB_PROXY`，后者始终优先，`README.zh.md:43`）。
- **开关位置**：设置 -> 插件 -> 插件管理里关 `dsh-market` 行；或手工 `- id: dsh-market` + `disabled: true`。
- **坑**：要求宿主 dsh web >= 0.1.0-rc.6，宿主太旧它**自我禁用且不报错**（设置里干脆看不到「插件市场」，`README.zh.md:26-28`）；桌面端可能内置比 npm 更旧的 dsh（同上，issue #139）。peerDependencies 锁 `@deepseek-ai/cordis ^4.0.1`、`dsh-settings`、`schemastery ^3.18.1`。

### 3.2 @liustack/modlens 3.27.1 —— 给纯文本模型补视觉（**本机坏**）

- **是什么**：外挂视觉引擎。DeepSeek 主力模型读不了图，modlens 把图交给另一个多模态引擎，返回**结构化证据**（全文转录、按阅读顺序的版面区块、实体与关系、不确定项），而不是一句"我看到一张图"（`nm/@liustack/modlens/README.zh-CN.md:28,51`）。
- **注册了什么**：一个模型工具 `modlens_read_image`（`nm/@liustack/modlens/dsh/index.js:387`，`ctx.tools.register(readImageTool(preferred))`）。另两件事属浏览器半区：粘贴图片时把图转成文件路径塞进输入框；给每条纯文本模型路由生成带 `(modlens vision)` 后缀的模型变体（后者能直接看缩略图，`README.zh-CN.md:40-42`）。
- **触发**：① 直接往输入框粘图；② 切到 `(modlens vision)` 变体再粘；③ 模型自己调用 `modlens_read_image`。
- **配置项**：唯一共享配置文件 `~/.modlens/config.json`（`nm/@liustack/modlens/dsh/index.js:1785-1787`，注释原文 "the one file every harness shares"）。**本机 `C:\Users\HUAWEI\.modlens` 不存在**。
- **开关位置**：`- id: modlens` + `disabled: true`。
- **坑（本机正是踩了这个）**：`prof/package.json` 写的是 `"@liustack/modlens": "git+https://github.com/liustack/modlens.git"`。git 装的是源码，`dist/` 要自己 `pnpm build`，而 `package.json` 的 `bin` 指向 `dist/main.js`。实测调用：

  ```
  modlens failed (exit 1): Error: Cannot find module
  'E:\dsh-data\profiles\desktop\node_modules\@liustack\modlens\dist\main.js'
  ```

  也就是说：**工具在、面板在、模型一调用就崩**。两条修法：在该目录跑 `pnpm install && pnpm build`（需 devDeps），或改装 npm 正式包 `@liustack/modlens@3.27.1`（`package.json` 的 `files` 声明发布物含 `dist`）。
- 其他：`engines.node >= 22.19`。

### 3.3 @linxin666/dsh-web-all 0.4.6 —— 全家桶聚合壳（拆解见 §4）

- **是什么**：一个"载具"。它本身只做两件事：把家族子插件汇总成自己的 `cordis.patch.yml`；提供**永不失败的壳模块**，让每个子插件挂在它后面，从而把"一个插件炸全组回滚"降级成"只降级自己"（`nm/@linxin666/dsh-web-all/README.zh.md:21`）。
- **注册了什么**：20 条 loader 行，id 统一带 `web-ui-` 前缀（目的：能与同名独立插件共存，`cordis.patch.yml:1-7`）；一行自己的 `web-ui-compat` 壳；两条健康路由 `GET /api/dsh-web-all/rows`（哪些行活跃）与 `GET /api/dsh-web-all/degraded`（哪个子插件降级了）。
- **触发**：装上即用，功能按子面板各自触发（§4 表）。
- **开关位置**：设置 -> 插件 -> 插件管理里本包展开为子插件列表，逐行开关。**注意**：聚合包的配置行必须写 `web-ui-` 前缀的 id（如 `web-ui-remote-web-ui`），独立安装的插件仍用原 id（`README.zh.md:78`）；手写覆盖必须保留 `plugin` 键，否则这行什么都不挂载（同上）。
- **坑**：家族包 peer 要求 `@deepseek-ai/dsh >= 0.2.0-rc.2`（`nm/@linxin666/dsh-web-all/package.json` 的 `dsh.engines`）；升级时 `node_modules/@linxin666/*` 常是旧 store 的目录链接、不会自动刷新，Windows 上要 `rmdir` + `mklink /J` 重建（`README.zh.md`「手工升级」）；README 还留了历史坑：0.1.17 及更早把 `settings.plugin.item` 的必填 `key` 传成 `id`，导致 Web GUI 直接 "Failed to load plugins"（issue #513）。

### 3.4 @anionex/dsh-turn-rewind 0.3.9 —— 单轮回退（Turn Rewind / Change Ledger）

- **是什么**：给会话加"每轮一个恢复点"：看改动文件 -> 预演 -> 选"恢复文件并从这里继续 / 只恢复文件 / 只回溯消息"，按最终按钮才执行；执行前先建救援点、执行后哈希校验（`nm/@anionex/dsh-turn-rewind/README.zh.md:13-25`）。**不**自动 commit / stash / reset / 切分支（同文件 27 行）。
- **注册了什么**：一个公共 Cordis 服务 `ctx.provide('changeLedger', this)`（`nm/@anionex/dsh-turn-rewind/lib/index.js:49`）——别的插件可以依赖它；**不注册模型工具**；UI 是每条用户消息下方的第三个纯图标按钮 + 审阅弹窗 + 一行可展开的设置卡片（`README.zh.md:43-47`）。
- **触发**：点消息下方「回退」图标；或别的插件/脚本调 `ctx.changeLedger` API。
- **配置项**：`nm/@anionex/dsh-turn-rewind/lib/settings.js` 定义；「自动（推荐）」模式 = Git 工作区用 Git 原生检查点、普通目录用插件自己的存储（`README.zh.md:34`）；普通目录可写 `.dsh-rewindignore` 追加排除（33 行）。存档落在 `$DSH_HOME/change-ledger`（本机 `E:\dsh-data\change-ledger` 已存在）。
- **开关位置**：`- id: turn-rewind` + `disabled: true`。
- **坑**：子模块、sparse checkout、超限文件、总量超限、特殊文件类型会让"创建恢复点"**直接失败**而不是悄悄跳过（`README.zh.md:73`）；大仓库首次检查点慢（0.3.5 才靠路径身份缓存把 20000 文件从 237s 降到 7s，35 行）。

### 3.5 @wxg-prc-cpg/dsh-weknora 0.1.0 —— 给 Agent 接知识库（**本机后端不通**）

- **是什么**：dsh 自己没有检索/向量/知识库能力（`grep`/`glob` 只看工作区，`web_search` 只看互联网），这个插件把腾讯 WeKnora 知识库接进来：混合检索、按文档通读、以及 WeKnora 自己带引用的成稿答案（`nm/@wxg-prc-cpg/dsh-weknora/README_CN.md:7-8`）。
- **注册了什么**：4 个模型工具，本机工具面都可见——`weknora_list_knowledge_bases`、`weknora_search`、`weknora_read_document`、`weknora_ask`（对应接口表见 `README_CN.md:66-71`）。无 UI 面板。
- **触发**：模型判断需要查文档时调用；Code Mode 下还能写 `await tools.weknora_search({ query })` 一次扇出十个子问题（`README_CN.md:92-93`）。
- **配置项**：默认值由 bundle patch 直接从环境变量取（`nm/@wxg-prc-cpg/dsh-weknora/cordis.patch.yml:8-13`）：`WEKNORA_BASE_URL`（默认 `http://localhost:8080/api/v1`，缺 `/api/v1` 自动补）、`WEKNORA_API_KEY`（走 `X-API-Key`）、`WEKNORA_KNOWLEDGE_BASE_IDS`（逗号分隔）、`WEKNORA_AGENT_ID`。其余字段完整默认值表见 `README_CN.md:108-121`：`tenantId`(未设) / `maxResults`(8) / `maxChunkChars`(1200) / `requestTimeoutMs`(30000) / `chatTimeoutMs`(300000) / `resourceUrls`(handle) / `toolPrefix`(weknora) / `tools.*`(全部 true)。
- **开关位置**：`- id: weknora` + `disabled: true`。
- **本机实测**：环境变量里没有任何 `WEKNORA_*`；`E:\dsh-data` 下的设置文档也没有 weknora 配置（只有两个 profile 的 `package.json` 提到包名）；`http://localhost:8080/api/v1/knowledge-bases` 拒绝连接；实调 `weknora_list_knowledge_bases` 返回 `GET /knowledge-bases failed: fetch failed`。**结论：工具齐备、后端缺位，现在调用只会失败。**
- **坑**：只读（不入库/不改分块/不删）；三个工具只需 `retrieve` 能力的 Key，`weknora_ask` 额外要 `chat`；平台级 Key 必须配 `tenantId`（`README_CN.md:97-101`）；片段按 `maxChunkChars` 截断并显式告知模型 `truncated: true`；配置不合法会在**插件加载阶段**就失败并逐条列出问题，而不是等模型第一次调工具（`README_CN.md:62-64`）；自身零运行时依赖、只要 Node >= 20.11（`README_CN.md:149-151`）。

### 3.6 dsh-context 0.71.0 —— 上下文洞察与管理

- **是什么**：把"这次对话到底把上下文花在哪了"做成可看的仪表盘，并给出跨会话总览（`nm/dsh-context/README.md:13-18`）。
- **注册了什么 / 用户看到什么**（五个面）：① 侧栏一级面板「上下文洞察」：KPI 带、7 天 token/成本柱、8 周活动热力图、构成环、可筛选会话卡片，点卡片直接进会话；② 每会话的 Context 标签页：统计/构成/逐请求趋势/事件/文件活动；③ Fleet 标签页：当前 agent、它的父级、所有子代理各一张实时卡；④ 右侧栏 Context 面板（与聊天并排）；⑤ `/context` 斜杠命令：居中构成弹窗。**不注册模型工具**（本会话工具面无任何 context 工具，与 README 的 UI-only 描述一致）。
- **触发**：点侧栏入口、切标签页、敲 `/context`。
- **配置项**：一张「偏好」卡（`README.md:54`）：视图位置、趋势粒度与模式、File Activity 排序、以及注入每个会话的**系统提示前缀/后缀**。
- **开关位置**：`- id: dsh-context` + `disabled: true`。
- **坑**：本机两个 profile 版本漂移（desktop 0.71.0 / web 0.72.0），跨 profile 对照截图会对不上；README 未声明 `engines.dsh` 下限（未找到依据）。

### 3.7 dsh-find-plugins 0.2.10 —— 给模型一个"找插件"的工具

- **是什么**：把 `find_dsh_plugins` 交给模型，聚合 dsh.so、dsh.works、plugin-radar、awesome-dsh-plugin、npm、GitHub topic 六个来源，按「相关度 x 可信度 x 新鲜度」排序，而不是按 star 或字面名匹配（`nm/dsh-find-plugins/README.md:7-30`）。
- **注册了什么**：一个模型工具 `find_dsh_plugins`（本会话工具面可见）；无 UI 面板。
- **触发**：你问"有没有能 X 的插件"，或模型判断需要扩展能力时。
- **配置项**：未见 schema（无配置项）。
- **开关位置**：`- id: dsh-find-plugins` + `disabled: true`。
- **坑**：必须和宿主**共享同一个 `@deepseek-ai/dsh-tools` 实例**，所以只能走 `peerDependencies`——写成 `dependencies` 会在 profile 里塞第二份副本、覆盖运行时版本、导致服务激活失败（`README.md:43-45`）；要求 Node >= 22。

### 3.8 @deepseek-ai/dsh-experimental-agent-team-profile 0.2.1-rc.1 —— Agent Teams（**本机未生效**）

- **是什么**：纯 patch 组合包（运行时内容就是它的 `cordis.patch.yml`），把"团队协作 + 团队工具 + 团队 Web UI"一次性打开（`asar/dsh-experimental-agent-team-profile/README.zh.md:9-10`）。
- **注册了什么**（`asar/dsh-experimental-agent-team-profile/cordis.patch.yml` 全文 32 行）：关掉 4 行 `tool-subagent-control` / `tool-subagent-list-agents` / `tool-subagent` / `tool-subagent-fork`；插入 `agent-team`（`maxMembers: 8`、`maxTasks: 256`、`maxMessageBytes: 65536`、`disposalTimeoutMs: 5000`）、`tool-agent-team`（`freshProvider: spawn`、`forkProvider: fork`）、`ui-agent-team`。对应工具面是 `spawn_teammate` / `wait_agent` / `team_task_*`（工具标题映射见 `asar/dsh-client-ui-tool/lib/client.js:157`）。
- **触发**：装好后让 Lead 把任务拆给 teammate；Web 侧栏插件页「智能体团队」开关同时控制工具与 UI（README.zh.md:35-40）。
- **开关位置**：设置 -> 插件 -> 插件管理里本包一行（`package.json.icon` 声明的图标禁用时也显示）。
- **本机状态**：`prof/package.json` 的 bundles 里确实有它（倒数第二项），但本会话工具面是 `subagent` / `subagent_fork` / `list_agents` / `send_message`，**没有** `spawn_teammate` / `wait_agent` / `team_task_*`。而 `tool-subagent-list-agents` 若被真禁用，`list_agents` 就不该出现——所以这层没被应用。
- **未定位的原因**：loader 有"读不出/不兼容的 bundle 跳过并记入 `skippedBundles`"的路径（`asar/dsh-app-boot/lib/index.js:1054-1055`），但本机 profile 层、`$DSH_HOME/cordis.patch.yml`（不存在）、Electron 侧状态文件里都没有它的痕迹，也没有可读的启动日志。**"为什么被跳过"在可读源码/日志中找不到依据**，需一次带诊断的启动日志确认。

### 3.9 @deepseek-ai/dsh-experimental-auto-review 0.2.1-rc.1 —— 逐调用自动审查（EXP）

- **是什么**：给权限选择器加一个带 `EXP` 标记的「自动审查」模式：**每次**原生或 PTC inner 工具调用执行前，用当前 agent 自己的模型审一遍——低风险（项目内普通改动、精确清理本 Session 创建的对象）直接放行；中风险（不可逆删除既有对象、生产操作、外部写入、安全控制变更）要人明确授权动作/目标/范围；高风险（跨信任边界泄露敏感信息）**一律拒绝**；效果不明确也拒（`asar/dsh-experimental-auto-review/README.zh.md:20-27`）。
- **注册了什么**：一行 `auto-review`（其 `cordis.patch.yml` 只有 3 行）；运行时向权限机制贡献一个 preset，并挂一个**置前**的 pre-execute listener；依赖 approval / LLM / permission / Session / tools 五个服务（`README.zh.md`「理解实现」）。
- **触发**：在 composer 菜单或 `/permission` 选择器里选「自动审查」并确认当前会话风险对话框，或用 `/permission auto`。**通用设置与"未来会话默认值"都不提供 Auto**（`README.zh.md:14`）。
- **开关位置**：插件页一行开关；或 `- id: auto-review` + `disabled: true`。
- **本机状态**：本会话文件策略是 `workspace-write`（不是 Auto 的"Full access 沙箱 + `ask` 审批"），且本会话审批提示被禁用——**没有观测到 Auto 模式被选中**。该行是否已挂载无法从工具面判断（它不注册工具）。
- **坑（README 明说）**：实验功能，可能**误放行不安全动作**、也可能误拒有用操作，并**消耗额外 token**（`README.zh.md:9`）；卸载时会把存活的 Auto 会话迁到 Full access + `never` 策略（`README.zh.md`「理解实现」末段）——即权限被**放大过**，别在敏感机器上随手开。

---

## 4. @linxin666/dsh-web-all 到底注入了什么（逐行拆解）

来源：`nm/@linxin666/dsh-web-all/cordis.patch.yml`（149 行，注释说明由 `scripts/aggregate.mjs` 从 `aggregate.yml` 生成，别手改）。活跃名单来自实测 `GET http://127.0.0.1:29310/api/dsh-web-all/rows`。

| 行 id | 挂载的包 | 干什么（`package.json` description 摘要） | 状态 |
|---|---|---|---|
| `web-ui-compat` | `@linxin666/dsh-web-all` 自身 | 永不失败的壳模块：失败隔离 + 健康路由 | 活跃（壳，不在 rows 列表里） |
| `web-ui-settings` | `dsh-client-ui-web-ui-settings` | 设置页里的**一个一级分区**，托管家族各插件的开关与配置表单 | 活跃 |
| `web-ui-plugin-manager` | `dsh-client-ui-plugin-manager` | 官方插件页的**更新检查**：比对注册源版本、按声明的 DSH 最低版本设闸、走官方安装通道更新 | 活跃 |
| `web-ui-market` | `dsh-client-ui-market` | 工坊浏览卡：从 dsh-market.com 逛皮肤/宠物/社区插件并安装（资产进 DSH home，插件走插件管理器） | 活跃 |
| `web-ui-task-board` | `dsh-client-ui-task-board` | **Host 权威任务看板**：真会话执行、Host 侧 cron 调度、可选跨平台防休眠 | 活跃（工具面有整套 `task_board_*`） |
| `web-ui-task-board-github` | `dsh-client-ui-task-board-github` | 看板的 GitHub Issues 同步 provider | 活跃（工具面有 `task_board_github_*`） |
| `web-ui-git-graph` | `dsh-client-ui-git-graph` | 空会话时的分支选择器 + Git 图谱，host 侧真 git 操作带守卫 | 活跃 |
| `web-ui-remote-web-ui` | `@linxin666/dsh-remote-web-ui` | 手机远程控制 Web UI（依赖 `cloudflared` / `qrcode.react`） | 活跃 |
| `web-ui-update` | `@linxin666/dsh-update` | 自更新入口 | 活跃 |
| `web-ui-ssh` | `@linxin666/dsh-ssh` | SSH 终端运维（带 `ssh2` / `@xterm/*` / `cpu-features` 原生依赖） | 出厂 `disabled: true` |
| `web-ui-liangshen` | `@linxin666/dsh-liangshen` | 「梁神」agent preset + composer 拨杆；宿主半区激活时把内置 preset 声明给 registry | 活跃 |
| `web-ui-skill-explorer` | `dsh-client-ui-skill-explorer` | 技能中心：按来源浏览/开关/新建/删除 skill | 出厂 `disabled: true` |
| `web-ui-usage` | `@linxin666/dsh-usage` | 用量统计 | 活跃 |
| `web-ui-session-archive` | `@linxin666/dsh-session-archive` | 会话归档（`$DSH_HOME/dsh-session-archive` 已存在） | 活跃 |
| `web-ui-model-capabilities` | `dsh-client-ui-model-capabilities` | 给自定义 pi-ai provider 逐模型声明「能否吃图 / 支持哪些推理力度」，写官方 `llm-pi-ai` 命名空间 | 活跃 |
| `web-ui-i18n` | `@linxin666/dsh-i18n` | 向 locale catalog 注册俄语并集中携带家族插件的俄语词典（**直挂**，宿主半区为空） | 活跃但不在 rows 列表内 |
| `web-ui-community-plugins` | `dsh-client-ui-community-plugins` | `community.json` 社区插件索引数据源（工坊商店与 dsh-market.com 清单的唯一来源） | 活跃（外部行，直挂） |
| `web-ui-pet` | `@linxin666/dsh-pet` | 桌面宠物：多宠物注册表、随模型活动反应、命名/抚摸/投喂/好感度 | **被用户 patch 关掉**（§5 第 8 条） |
| `web-ui-preset-center` | `dsh-client-ui-preset-center` | 社区 agent preset 管理器：安装/声明/禁用/卸载 dsh-market.com 下载的 preset | 活跃（外部行，直挂） |
| `web-ui-skin-center` | `dsh-client-ui-skin-center` | 皮肤中心：皮肤是纯资产目录（内置 + `$DSH_HOME/skins`），页面内即时试穿/一键应用（不刷新、不改 patch、不重启） | 活跃，但**未应用任何皮肤**（§5 第 9 条） |

**12 项活跃子面板**（rows 实测）：settings、plugin-manager、market、task-board、task-board-github、git-graph、remote-web-ui、update、liangshen、usage、session-archive、model-capabilities；`degraded` 为空数组（没有子插件降级）。

两点需要纠正任务书里的猜测：**本机没有 doctor 与 describe-image 行**（149 行 patch 内无此 id，rows 也不返回）；并存的"市场"有两套——独立包 `dshmarket`（行 `dsh-market`）与聚合层的 `web-ui-market`（不同包、不同功能，前者是安装器，后者是工坊浏览卡）。

---

## 5. 你的 cordis.patch.yml：9 行逐行是什么、UI 上看到啥

文件：`prof/cordis.patch.yml`（1505 字节，最后修改 2026/10/17 21:20:16）。每一条都是"按 id 命中某一行、整块替换它的 config"。

| # | 行 id | 你写的值 | 这一行改了什么 | UI 上的表现 |
|---|---|---|---|---|
| 1 | `ui-settings-general` | `welcomeNoticeVersion: 2026-08-13.1` | 记录"欢迎提示已阅到哪个版本"。该插件的 Config 只有这一个字段：`z.object({ welcomeNoticeVersion: z.string().volatile() })`（`asar/dsh-client-ui-settings-general/lib/index.js:4`） | 版本 2026-08-13.1 的欢迎/更新提示不再弹。`volatile` 表示这类字段改了即时生效、不需要重挂载插件（`asar/dsh-settings/lib/schema.js:39-48`：select fields whose nearest volatile ancestor makes them editable without remounting） |
| 2 | `agent-default-model` | `provider: deepseek-account`、`model: deepseek-flash`、`reasoningEffort: high` | 新会话的默认模型三元组。schema 是 `provider: z.string().required().volatile()`、`model: …required().volatile()`、`reasoningEffort: z.string().volatile()`（`asar/dsh-agent-default-model/lib/index.js:22-24`），装配时原样喂给模型选择（同文件 8-10 行） | 开新对话时顶部就是 DeepSeek Flash（账号通道）、推理力度 High，不用每次手选 |
| 3 | `ui-theme` | `preference: dark` | 内置主题偏好。合法值只有 `light` / `dark` / `system`，默认 `system`（`asar/dsh-client-ui-theme/lib/index.js:5-9,17`）；同插件还管 `fontSize`（默认 14，范围 10-22） | 界面固定深色、不跟随系统——这条把你从"跟随系统"改成了"锁深色" |
| 4 | `ui-settings-account` | `version: 1`、`step: done`、`purpose: development`、`process: detailed`、`completion: completed`、`usage: detailed`、`developerTools: true` | 这是**首次启动引导问卷的进度存档**：`step` 取 `welcome/credit/purpose/process/done`，`purpose` 取 `office/development/both`，`process` 取 `compact/standard/detailed`，`completion` 取 `completed/skipped/api-key`，`usage` 取 `compact/detailed`，`developerTools` 默认 `false`（`asar/dsh-client-ui-settings-account/lib/index.js:18-47`） | 引导流程被标记为**已完成**（用途=开发、流程=详细、账号步骤=已完成、用量展示=详细），不会再次弹新手引导；`developerTools: true` 会放出开发者向选项，例如会话视图里的 `trajectory` 轨迹视图（`asar/dsh-client-ui-conversation/lib/client.js:19560`）、preset 选择器里"需要编码工具"的内置 preset（`asar/dsh-client-ui-agent-preset/lib/client.js:1301`） |
| 5 | `ui-chat` | `transcriptView: verbose`、`performanceUsage: detailed` | 聊天区两个展示偏好。`transcriptView` 合法值 `compact/standard/detailed/verbose`（默认 `detailed`；旧值 `normal`/`expanded` 只读兼容）；`performanceUsage` 只有 `compact/detailed`（默认 `detailed`）（`asar/dsh-client-ui-chat/lib/index.js:15-19,35-46`） | 聊天记录展开成**最详细**形态（工作细节全展开、不折叠），性能/用量也按详细显示；代价是每屏信息量大 |
| 6 | `ui-settings` | `enabled: true` | 把设置界面这一行显式置为启用 | 设置入口在。这条基本是冗余的安全声明（默认即启用） |
| 7 | `agent-preset-registry` | `default: standard`、`selectedDefault: cordis` | preset 注册表两个字段：`default` 是**发布默认**（`z.string().required()`），`selectedDefault` 是**用户选择**（`volatile()`）；实际生效值 = `selectedDefault ?? default`（`asar/dsh-agent-preset-registry/lib/index.js:442-443,464`） | 新会话默认套用 **cordis** preset，而不是发布默认的 standard。也就是说这行是"用户覆盖"，`default: standard` 只是把发布默认一并写出，防止整块替换把原值弄丢 |
| 8 | `web-ui-pet` | `visible: false`、`size: 160`、`right: 24`、`bottom: 120`、`petId: whale-girl`、`enabled: false`、`decorationEnabled: false` | 宠物插件自己的表单字段：`visible`/`enabled`/`decorationEnabled` 默认都是 `true`，`size` 是 32 到上限的整数（`nm/@linxin666/dsh-pet/lib/index.js:6391-6425`） | **宠物被关掉并隐藏**；`size/right/bottom/petId` 只是把位置和"鲸鱼女孩"的设定留着，将来把 `enabled`/`visible` 改回 `true` 就原地复原。注意插件**仍在加载**（启动时照样写了 `E:\dsh-data\pet.json`，时间 17:40:21），只是自己不上屏——真要省资源应改用 `disabled: true` |
| 9 | `web-ui-skin-center` | `skin-custom-theme: { applied: false }` | 皮肤中心里"自定义主题"命名空间的开关：`SKIN_CUSTOM_THEME_NS = "skin-custom-theme"`，`applied` 为 `z.boolean().default(false).volatile()`（`nm/@linxin666/dsh-client-ui-skin-center/lib/index.js:3902-3944,3983`） | 表示**没有应用自定义皮肤**，界面用内置默认主题。等于把默认值又写了一遍，是一条无害的显式声明；当前生效的皮肤记录另存在 `E:\dsh-data\skin-center-active.json` |

> 提醒：`config` 是整块替换。第 8、9 条这种"把默认值也抄一遍"的写法是**对的习惯**——否则插件后续新增字段会被整块顶掉。

---

## 6. 三项能力的可用性判定（这台机器上）

| 能力 | 判定 | 证据 |
|---|---|---|
| **modlens 视觉桥** | 不可用：工具在，执行必崩；且没有配任何视觉引擎 | 包是从 git 装的源码（`prof/package.json`：`git+…modlens.git`），`dist/` 不存在，`bin` 指向 `dist/main.js`（`nm/@liustack/modlens/package.json`）；实调报 `Cannot find module …\modlens\dist\main.js`。另外 `~/.modlens/config.json` 不存在，即**也没有配引擎**——即使补上 `dist/`，还需一个引擎（复用本机 `.claude` / `.codex` / `.config\opencode` 登录态，或自己填 OpenAI 兼容 key / 免费 Gemini key） |
| **weknora RAG 检索** | 不可用：后端缺位 | 无 `WEKNORA_*` 环境变量、无设置覆盖；`localhost:8080` 拒绝连接；实调 `weknora_list_knowledge_bases` -> `fetch failed`。补法：设 `WEKNORA_BASE_URL` / `WEKNORA_API_KEY`（必要时 `WEKNORA_KNOWLEDGE_BASE_IDS`），或在 `prof/cordis.patch.yml` 覆盖 `- id: weknora` 的 `config` |
| **dsh-context 上下文能力** | 可用：纯本地、无外部依赖 | 只读宿主已有的会话与请求统计，不调外部服务、不注册模型工具；0.71.0 已安装、侧栏入口存在（`nm/dsh-context/README.md:13-18`）。唯一"配置"是那张偏好卡（视图位置 / 趋势粒度 / 系统提示前缀后缀） |

---

## 7. 坑与风险清单（按严重度）

1. **modlens 必崩**（git 源码包缺构建产物）——§3.2、§6。
2. **weknora 必失败**（无后端）——§3.5、§6。
3. **启动是全有或全无**：一个插件炸，整组回滚、`dsh web` 起不来；聚合包用"壳模块 + degraded"把这风险隔离掉，非聚合插件没有这层保护（`nm/@linxin666/dsh-web-all/README.zh.md:21`）。
4. **Auto review 是"放大权限"的实验功能**：它用 Full access 沙箱 + `ask` 审批策略跑被放行的调用，可能误放行（`asar/dsh-experimental-auto-review/README.zh.md:9,20-27`）。
5. **两个 profile 并存且版本漂移**：desktop 的 `dsh-context 0.71.0` / `dshmarket 1.66.22` 与 web 的 `0.72.0` / `1.66.27` 不同；`@linxin666/*` 的 node_modules 条目常是旧 store 的目录链接，升级需手工重建（Windows：`rmdir` + `mklink /J`）。
6. **聚合行必须用 `web-ui-` 前缀 id**，且手写覆盖必须保留 `plugin` 键，否则该行不挂载任何东西（`README.zh.md:78`）。
7. **原生依赖**：`@linxin666/dsh-ssh` 带 `ssh2`/`cpu-features`/`nan`/`@xterm/*`，`dsh-remote-web-ui` 带 `cloudflared`，另有 `lightningcss-win32-x64-msvc`——换机器/换 Node 版本时最容易装不上（目前 ssh 行本来就关着）。
8. **实验包写了却没生效**（§3.8）：若确实想用 Agent Teams，先解决这条，别在工具面上找不存在的 `spawn_teammate`。

---

## 8. 证据索引与明确留白

- 补丁合成顺序：`asar/dsh-app-boot/lib/index.js:1118-1136`；bundle 跳过路径：同文件 `1054-1055`。
- `volatile` 语义：`asar/dsh-settings/lib/schema.js:39-48,73-79`。
- 清单与开关：`prof/package.json`、`prof/cordis.patch.yml`、`prof/cordis.yml`（内容为空数组 `[]`，说明组合在运行时算，不要手改）。
- 聚合层：`nm/@linxin666/dsh-web-all/cordis.patch.yml`（20 条 insert + 2 条出厂 `disabled: true`）、`GET /api/dsh-web-all/rows`、`GET /api/dsh-web-all/degraded`。
- 两个实验包：`asar/dsh-experimental-agent-team-profile/cordis.patch.yml`、`asar/dsh-experimental-auto-review/cordis.patch.yml` 及各自 `README.zh.md`。
- 引导问卷字段：`asar/dsh-client-ui-settings-account/lib/index.js:18-47`（从 asar 内直接读取）。
- 实调证据：`modlens_read_image` 报 `Cannot find module …\dist\main.js`；`weknora_list_knowledge_bases` 报 `fetch failed`。
- **明确留白（未在源码/日志中找到依据）**：① 实验团队包为何未生效（§3.8）；② `auto-review` 行当前是否已挂载（§3.9）；③ `dsh-context` 的 `engines.dsh` 下限（§3.6）。
