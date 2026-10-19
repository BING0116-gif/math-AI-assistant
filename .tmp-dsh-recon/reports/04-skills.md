# DSH Skill 体系详解 + 本会话 19 个可用 Skill 逐个说明

> 取证范围：把 Electron 应用内 `app.asar\dsh\node_modules\@deepseek-ai\*` 全部源码抽出到
> `C:\Users\HUAWEI\Desktop\math AI assistant\.tmp-dsh-recon\asar\@deepseek-ai\\`，
> 本机 profile 配置在 `E:\dsh-data\profiles\desktop\\`。
>
> **引用约定**
> - **【A】** = `C:\Users\HUAWEI\Desktop\math AI assistant\.tmp-dsh-recon\asar\@deepseek-ai\\`
>   （例：【A】`dsh-tool-skill/README.md` 指 `...\asar\@deepseek-ai\dsh-tool-skill\README.md`）
> - **【P】** = `E:\dsh-data\profiles\desktop\\`
> - **【W】** = 本会话工作区 `C:\Users\HUAWEI\Desktop\math AI assistant\\`
> - 其余写全路径。
>
> 结论优先用 `lib/*.js` 交叉验证；README 只用来快速定位。凡是源码里查不到依据的，文中明确标注「未在源码中找到依据」。

---

## 0. 一句话结论

**Skill 不是代码，是一份「按需下发的说明书」。** 它躺在文件系统上，由 provider 扫出来只上报
「名字 + 一句描述」进模型上下文；模型或用户真要用时，才把整篇正文注入进对话。
真正让它在会话里「活起来」的是三个 Cordis 插件：注册表（`dsh-skill`）、文件系统提供者
（`dsh-skill-filesystem`）、面向模型的消费者（`dsh-tool-skill`，它同时提供 `skill` 工具）。
【A】`dsh-skill/README.md`、【A】`dsh-skill-filesystem/README.md`、【A】`dsh-tool-skill/README.md`

**Plugin 不是说明书，是跑在 Cordis 容器里的代码模块。** 它装在 profile 的 `node_modules`，
由 `cordis.patch.yml` / bundle 层里的 plugin row 声明、在宿主进程内 in-process 执行。
【P】`cordis.yml`、【P】`package.json`、【A】`dsh-plugin-manager/README.md`

---

# A. 机制

## A.1 Skill 到底是什么

### A.1.1 磁盘形态：目录包 + SKILL.md

一个 skill 是**被扫描根的直接子项**，两种合法形态：

| 形态 | 路径 | 说明 |
|---|---|---|
| 目录包 | `<root>/<name>/SKILL.md` | 正文在 SKILL.md，可带 `references/`、`scripts/`、`assets/` 等同级资源 |
| 平铺文件 | `<root>/<name>.md` | 单文件 skill |

- 只认**一层深度**：`<root>/<name>/SKILL.md` 与 `<root>/<name>.md`；嵌套的 `**/SKILL.md` 故意不发现（避免把仓库里任意文档当 skill）。【A】`dsh-skill-filesystem/README.md`「Skill format」「Known Limitations」（"Discovery is one level deep"）
- 实测印证：本会话 19 个 skill 全部是「目录包 + SKILL.md」；`office` 还有 `references/sidecar.md`，
  `prd-writer` 有 `references/template.md`、`references/epic-sizing.md`，`security-best-practices` 有 11 个
  `references/<语言>-<框架>-<栈>-security.md`，`diagnose-windows-sandbox-acl` 有 `scripts/*.ps1`。

### A.1.2 frontmatter：DSH 到底读哪几个键

`SKILL.md` 开头是 YAML frontmatter。DSH **只解析这 6 个键**：

| 键 | 必需 | 作用 |
|---|---|---|
| `name` | 是 | 必须是 kebab-case；这是 `skill` 工具和 `/name` 的唯一标识 |
| `description` | 是 | 模型 catalog 里唯一能看到的内容（会被截断到 `catalogDescriptionMaxLength`，默认 500，最小 3） |
| `whenToUse` | 否 | 可选；**不进入模型 catalog**（catalog 模板只渲染 name + description），Skill Center 面板的行里展示 |
| `metadata` | 否 | 自由结构化数据，原样保留 |
| `disable-model-invocation` | 否 | `true` ⇒ 模型 catalog 与 `skill` 工具都看不到它，只剩用户 `/name` 一条路 |
| `user-invocable` | 否 | `false` ⇒ 用户 `/` 菜单和 `/name` 都不认它 |

两个 invocation 键接受 YAML 布尔，也接受大小写不敏感的 `true/false/yes/no/on/off/1/0`；
**写法非法或非布尔 ⇒ 整个 skill 被丢弃并告警**，不会「悄悄放行」。
证据：【A】`dsh-skill-filesystem/README.md`「Skill format」（逐个列了这些键 + 严格布尔语法）；
catalog 模板只渲染 name + description 见【A】`dsh-tool-skill/lib/index.js:966-1014`。

> **教学要点（很值得讲给新手）**：`grill-master`、`spec-writer`、`slice-the-spec`、`spec-to-plan`、`prd-writer`
> 的 frontmatter 里都有一个 `triggers:` 列表（如 `/grill`、`/spec`），但 **`triggers` 不在上面 6 个键里**
> （【W】`.agents/skills/grill-master/SKILL.md:5-9`）。DSH 的 `/name` 手势只按 **skill 名字**匹配
> （正则见 A.3.2），所以打 `/grill` 不会加载 `grill-master`，只有 `/grill-master` 才会。
> `triggers` 字段对 DSH 是**惰性数据**——它就在顶层放着，DSH 不读它。

### A.1.3 发现：5 个扫描根 + 优先级

`dsh-skill-filesystem` 按 rank 从小到大扫描，rank 小者胜（同名去重 "first-wins"）：

| rank | source | 路径 |
|---|---|---|
| 100 | `project-dsh` | `<projectRoot>/.dsh/skills` |
| 200 | `project-agents` | `<projectRoot>/.agents/skills` |
| 300 | `custom` | 配置 `customSkillDirs` |
| 400 | `user-dsh` | `<dshHome>/skills`（跳过其 `.system` 子目录） |
| 500 | `user-agents` | `<agentsHome>/skills` |
| 600 | `bundled` | 配置 `bundledSkillDir`（内置 skill 用这一档） |

- `projectRoot` = 最近的含 `.git` 的祖先目录；没有就用当前 cwd。【A】`dsh-skill-filesystem/README.md`「Roots and priority」
- 代码印证：【A】`dsh-skill-filesystem/lib/index.js:149-187`（`roots()` 里逐条 push，rank 常量 + `skipSystem: true`）。
- 默认值：`dshHome` = `$DSH_HOME` 或 `~/.dsh`（本机 `DSH_HOME=E:\dsh-data`），`agentsHome` = `$DSH_AGENTS_HOME` 或 `~/.agents`，`customSkillDirs` 默认 `[]`，`watch` 默认 `true`。

**本会话实测的落点（已核对磁盘）**：

| 落点 | 实际存在的 skill |
|---|---|
| `project-agents`（rank 200）→ 【W】`.agents/skills/` | grill-master、prd-writer、slice-the-spec、spec-to-plan、spec-writer、ui-ux-pro-max、math-ai-change-safety、math-ai-frontend-qa、math-ai-model-quality-eval（共 9 个） |
| `user-agents`（rank 500）→ `C:\Users\HUAWEI\.agents\skills\\` | developing-with-streamlit、security-best-practices（共 2 个） |
| `bundled`（rank 600）→ office 系列 assetRoot | office、office-docx、office-xlsx、office-pptx、office-render、office-export-pdf、office-recalculate（共 7 个，由 `dsh-skill-office` 作为 provider 注册） |
| `bundled`（rank 600）→ `dsh-sandbox-windows-acl` 的 assets | diagnose-windows-sandbox-acl（1 个） |

**两个容易踩的坑（都用证据排除了）**：

1. `<projectRoot>/.dsh/skills` 在本仓库**不存在**（`Test-Path` 返回 False）。
2. 【W】`.claude/skills/` 下有 6 个 SKILL.md，且与 `.agents/skills/` 下的同名文件**逐字节相同**（SHA256 前 8 位完全一致）；
   但 `.claude/skills` **不是 DSH 的扫描根**：默认 `customSkillDirs` 为空，而本机 profile / bundle 里
   唯一设置 `customSkillDirs` 的是 `cordis` preset（指向 `dsh-agent-preset/skills`），
   本会话用的 `standard` preset 没有加任何自定义目录。
   证据：【A】`dsh-web-app/presets/standard.patch.yml:37-40`（只挂 provider，无 config）、
   【A】`dsh-web-app/presets/cordis.patch.yml:122-126`（唯一带 `customSkillDirs` 的行）、
   【P】`cordis.patch.yml`（全文无 skill 行）。
   ⇒ **`.claude/skills` 是给 Claude Code 兼容用的平行副本，对 DSH 无作用。** 想改 skill 内容要改 `.agents/skills`。

### A.1.4 内置 skill 也是同一套协议

- `dsh-skill-office`：一个 provider，注册 **7 个** skill（1 个路由 `office` + 6 个实操），
  `assetRoot` 指向打包的 `assets/`；`node`/`cli` 是可配字段，操作型 skill 加载时会把
  **绝对解释器路径与 LibreOffice Kit CLI 路径**追加进正文。【A】`dsh-skill-office/README.md`「Summary」「Mount and configure」；
  代码：【A】`dsh-skill-office/lib/index.js:101` `ctx.skills.registerProvider(() => provider)`。
  桌面端挂载点：【A】`dsh-desktop-host/lib` 里 `import * as officeSkills from "dsh-skill-office"`（第 9 行）+
  `assetRoot: join(dirname(config.source), "office-skills")`（第 84 行）。
- `dsh-sandbox-windows-acl`：不只是一个沙箱后端，它还顺手注册了 `diagnose-windows-sandbox-acl` 这个 skill，
  所以 Windows 上只要挂了 local sandbox，这个诊断 skill 就在目录里。
  代码：【A】`dsh-sandbox-windows-acl/lib/types-Cl_DXjhk.js:1138` `yield ctx.skills.registerProvider(() => provider)`。
- `dsh-skill-badge`：官方 powered-by-dsh 徽章 skill（名字 `dsh-badge`），需要显式插入 plugin row，默认 composition 不声明；
  **本会话目录里没有它**，说明这一行没开。【A】`dsh-skill-badge/README.md`「Enable the plugin」

## A.2 它是怎么被"看到"的：渐进式披露（progressive disclosure）

分三层，成本逐层升高。

### 第 1 层：catalog（只有名字 + 一句描述）

在 **每个 `agent/pre-step`**，`dsh-tool-skill` 做这几件事：

1. 取当前会话的 skill catalog 快照（`ctx.skills`，各 provider 结果合并去重）；
2. 校验 `skill` 工具在这个 scope 里**确实可见**（被别人同名遮蔽就不发）；
3. 过滤出 `modelInvocable` 的条目；
4. 把条目算一个 **digest**，和会话日志里最新一条 `skill-catalog` 消息比对；
5. digest 变了才发消息——发出去是一条 **durable 的 user-role 消息**，不是往 system prompt 里拼接。

【A】`dsh-tool-skill/lib/index.js:930-965`（pre-step 决策逻辑）、`:966-1014`（两个模板函数）。

实际注入的文本（可直接引用来教学，【A】`dsh-tool-skill/lib/index.js:966-989`）：

```markdown
<system-reminder>
A skill is a reusable set of task-specific instructions. The following skills are available in this session:

<available_skills>
- `<name>`: <normalized-and-capped-description>
</available_skills>

If the user names a skill, or the task clearly matches a skill's description, call the `skill` tool with the exact skill name before taking task actions. Load all applicable skills, then follow their full instructions. This catalog contains summaries only; do not infer or follow a skill's instructions until it has been loaded.
A user may also invoke a skill directly; its <skill_content> block then appears in this conversation. Follow it, and do not call the `skill` tool again for that skill.
</system-reminder>
```

三条设计意图（都能从代码/README 读出）：

- **为什么用 `<system-reminder>` 包一层却没进 system prompt**：README 明确说 catalog 是 "durable user-role message"，
  目的是把它放在可复用前缀之后，让 KV cache 前缀保持稳定；后续变化是 append-only 的新消息。
  【A】`dsh-tool-skill/README.md`「KV Cache effect」
- **为什么 diff 用 digest 而不是比渲染文本**：按 published entries 算 digest，
  这样改一句 `<system-reminder>` 的措辞不会触发重发。【A】`dsh-tool-skill/lib/index.js:947`；README「Design concept」
- **为什么目录变更是「完整替换」而不是增量**：替换目录带一句 `This complete catalog replaces every earlier available-skills list`；
  全部删空时也发一条空目录并明说 `Do not use names from earlier skill catalogs`，防止模型用过期的名字。
  【A】`dsh-tool-skill/lib/index.js:990-1014`

**成本**：输入 token 随 skill 数量 × `catalogDescriptionMaxLength`（默认 500）线性增长；
目录为空或工具被遮蔽时，一条都不发。【A】`dsh-tool-skill/README.md`「Token effect」

### 第 2 层：`skill` 工具按需取正文

工具定义（模型看到的 schema 描述，【A】`dsh-tool-skill/lib/index.js:789-793`）：

- 工具描述：`Load the full instructions for a skill. Call it before acting on a task that names or clearly matches a skill in the session skill catalog.`
- 参数 `name`：`The exact skill name from the available skills list.`

调用后返回的是**规范化的 `<skill_content>` 块**（工具结果、以及用户 `/name` 注入，**共用同一个渲染函数**，
所以模型看到的形状完全一致）。渲染函数【A】`dsh-skill/lib/index.js:57-70`：

```markdown
<skill_content name="<escaped-name>">
<skill_resources>
<resource-guidance>
</skill_resources>

<skill_instructions>
<provider-owned-instruction-body>
</skill_instructions>
</skill_content>
```

`<skill_resources>` 那几行按 provider 给的资源基址生成四种话术之一（【A】`dsh-skill/lib/index.js:71-81`）：

- 目录基址：`Base directory for this skill: <path>` + `Resolve relative paths mentioned by this skill against the base directory before using them.`
- URL 基址：`Base URL for this skill: <url>` + 类似的相对路径提醒
- 不透明：`Resources for this skill: <description>`
- 都没有：`Resources for this skill are managed by provider "<provider>".`

> 这是给新手讲「references/ 怎么用」的关键：skill 正文里写 `references/template.md` 是**相对 skill 目录**的，
> 模型必须先看 `<skill_resources>` 拿到基址，再去 read 那个文件。本会话 `office` 的正文就是用
> `../office/references/sidecar.md` 这种相对路径指到兄弟目录（`assets/office/SKILL.md`）。

**"绝不缓存正文"**：`get()` 每次都让 provider 重新读文件；registry 只缓存「目录」，
且只在 provider 调 `invalidate()` 时失效（无 TTL）。【A】`dsh-skill/README.md`「Loading and staleness」「Invalidation」；
【A】`dsh-skill-filesystem/README.md`「The catalog and the body have separate lifecycles」

**失败语义**（模型会看到的确切错误）：【A】`dsh-tool-skill/README.md`「Observable success and failures」

| 情况 | 报错 |
|---|---|
| 名字不合 kebab-case 语法 | `Error: invalid skill name "<name>"`（【A】`dsh-tool-skill/lib/index.js:867`） |
| 名字合法但没这个 skill / 已消失 | 报 unknown / no longer available |
| 存在但 `disable-model-invocation: true` | 报 not available for model invocation |

### 第 3 层：正文里的 references/scripts 再按需读

正文自己是「步骤 + 该读哪个文件 + 该怎么验」的说明书，模型照做时再逐个子文件去 read。
典型例子：`office` 只有 15 行，作用纯粹是**路由**——要 Word 就加载 `office-docx`，
要出图就加载 `office-render`，并且明确 `Do not reload skills`。

### 变化检测（不用重启）

- 存在的根被 Chokidar 以 depth 1 监视：新增/改名/删除 skill、或改它的 frontmatter ⇒ 下一次模型 step 就能看到新目录；
  `references/`、`scripts/`、`assets/` 下的改动**不触发**目录刷新（因为正文反正每次现读）。
- 第一方 `write`/`edit` 工具改了可能影响 skill 的文件时，会走 `fs/observed` 事件**同步**让 provider 失效，
  所以模型自己的写入能立刻被自己看到；外部 IDE/Git/shell 的改动靠宿主 watcher。
- 尚未存在的根用 `fs.watchFile` 逐段探测直到出现。

证据：【A】`dsh-skill-filesystem/README.md`「Change detection」「Watching and invalidation」；
代码：【A】`dsh-skill-filesystem/lib/index.js:138-140`（`observeHostMutation`）。

## A.3 自动触发 vs 手动触发：源码里到底有没有「自动触发」

**结论：没有「按任务内容自动匹配并加载 skill」的代码。** 存在的只有两条路径，而且**都是显式的**。

### A.3.1 路径一：模型自己决定调 `skill` 工具（"语义触发"）

机制上这就是一次普通工具调用——**没有任何匹配器参与**。唯一的"触发"是一句写在 catalog 末尾的自然语言规则：
`If the user names a skill, or the task clearly matches a skill's description, call the skill tool with the exact skill name before taking task actions.`
（【A】`dsh-tool-skill/lib/index.js:978`）

也就是说：**"自动触发"= 模型读了 19 条 description 之后自己判断要不要 load**。description 写得准不准，直接决定命中率。
配套的防呆规则还有一条：catalog 明确要求 `do not infer or follow a skill's instructions until it has been loaded`
（禁止靠摘要臆测正文）。

### A.3.2 路径二：用户 `/name` 显式点名（"手势触发"，这是真正的代码路径）

`dsh-tool-skill` 注册了一个 `agent/pre-step` 监听器，扫描**本 step 认领的、来源确实是用户的消息**里的 `/name` token：

```js
// 【A】dsh-tool-skill/lib/index.js:1101
const SKILL_GESTURE = /(^|\s)\/([a-z0-9]+(?:-[a-z0-9]+)*)(?=\s|$)/g;
```

- 匹配规则：斜杠前面必须是行首或空白，名字必须是 kebab-case，后面必须是空白或行尾。
  注释明确写了为什么：这样 `/usr/bin`、`5/8` 这种不会被误判（【A】`dsh-tool-skill/lib/index.js:1094-1100`）。
- 只扫 `message.source.kind === "user"` 的文本块，其它来源**无法伪造**一次手势
  （【A】`dsh-tool-skill/lib/index.js:1109-1122`）。
- 命中且该名字是 `userInvocable` 的 skill ⇒ 直接把同一段 `renderSkillContent` 输出作为
  **user-role instructions context** 注入，追加在其它注入之后（【A】`dsh-tool-skill/lib/index.js:911`；README「Invocation boundary」）。
- 未知名、或被 `user-invocable: false` 禁掉的，**原样当普通文字**处理。

配套 UI：【A】`dsh-client-ui-skill/README.md` —— 在输入框打斜杠会弹建议列表（数据来自 `skills/list` Remote，
只列 user-invocable 的），选中或手打 `/name` 发送出去的都是**字面文本**，宿主两条路径同样处理；
会话里这次加载显示为可展开的 **`Instructions` 卡片**。与宿主命令同名的，仍然解析为命令
（客户端先裁决，不会变成 prompt）。

### A.3.3 两条路径的差异一览

| 维度 | 模型自动判断（A.3.1） | 用户 `/name`（A.3.2） |
|---|---|---|
| 触发者 | 模型 | 用户 |
| 有无代码匹配 | **无**，靠 description 语义 | 有，正则 `SKILL_GESTURE` |
| 能否加载 `disable-model-invocation` 的 skill | 不能（不在 catalog，工具也拒） | **能**，这是它唯一的入口（【A】`dsh-tool-skill/README.md`「Invocation boundary」） |
| 能否加载 `user-invocable: false` 的 skill | 能 | 不能 |
| 注入形状 | `skill` 工具结果里的 `<skill_content>` | 同一段 `<skill_content>`，作为 user-role 注入 |
| 模型要不要"再 load 一次" | — | 不要；catalog 明确说不要再为它调 skill 工具 |

### A.3.4 调用策略矩阵（谁看得见）

注册表保留全部 4 种组合，两个"面"各自取自己那份目录：【A】`dsh-skill/README.md`「What the registry gives you」

| `modelInvocable` | `userInvocable` | 模型 catalog / `skill` 工具 | 用户斜杠菜单与 `/name` |
|---|---|---|---|
| true | true | 有 | 有 |
| true | false | 有 | 无 |
| false | true | 无 | 有（带 user-only 前缀标记，【A】`dsh-client-ui-skill/README.md`） |
| false | false | 无 | 无 |

> **注意**：`disable-model-invocation` 与 `user-invocable` 是**两个独立开关**，不是一件事的正反面；
> 都能设成 false 把 skill 变成"谁也调不到的死文件"。

## A.4 Skill 与 Plugin 的本质区别

一句话：**Skill 是给模型的「说明书/流程知识」，Plugin 是跑在 Cordis 里的「代码模块」。**

### A.4.1 五维对比

| 维度 | Skill | Plugin |
|---|---|---|
| **装载位置** | 文件系统扫描根：`<project>/.dsh/skills`、`<project>/.agents/skills`、`customSkillDirs`、`<dshHome>/skills`、`<agentsHome>/skills`、bundled 目录；或 provider 在内存里 `ctx.skills.register(...)`。【A】`dsh-skill-filesystem/README.md`「Roots and priority」；【A】`dsh-skill/README.md`「Embedded skills」 | profile 的 `node_modules`（`E:\dsh-data\profiles\desktop\node_modules`），由 bundle 层 + `cordis.patch.yml` 的 plugin row 声明并 mount 进 Cordis 容器。【P】`package.json`（`dsh.profile.bundles`）、【P】`cordis.yml`、【P】`cordis.patch.yml`；【A】`dsh-plugin-manager/README.md`「Use this package」 |
| **生效方式** | 纯数据注入：catalog 一段摘要 + 按需一段正文进对话，**不改进程行为**。【A】`dsh-tool-skill/README.md`「What the model gets」 | 提供 Cordis service / 注册工具 / 挂 Remote / 加 UI 面板，**改进程行为**。【A】`dsh-skill/README.md`「When to choose it」（"the plugin adds a service"）、【A】`dsh-client-ui-plugin-manager/README.md`「Summary」 |
| **权限** | 无特权。skill 只是文字；它让你去跑 `scripts/xxx.ps1` 时，**那条命令本身仍要过沙箱/审批**。例：`diagnose-windows-sandbox-acl` 的 SKILL.md 明写「request approval for that one command and run it unconfined」，且「Unconfined does not elevate the Windows token」（【A】`dsh-sandbox-windows-acl/assets/diagnose-windows-sandbox-acl/SKILL.md`） | 代码在**宿主进程内 in-process** 执行，**在工作区沙箱之外**；安装/管理动作要 `danger-full-access` 或逐次审批。原文：`installed Host code executes in-process outside the workspace sandbox`（【A】`dsh-plugin-manager/README.md:31`） |
| **可卸载性** | 删目录/删文件即可；watcher 让下一个 step 消失，**不用重启**。也可只在 frontmatter 写 `disable-model-invocation: true` 软关掉。【A】`dsh-skill-filesystem/README.md`「Change detection」 | 关掉 = 在 `cordis.patch.yml` 写 `disabled: true` 覆盖；卸载 = 改 `dsh.profile.bundles` + `pnpm remove`。**无 HMR 时运行中的 composition 要重启才变**（"restart-required"）。【A】`dsh-plugin-manager/README.md`「Use this package」「Known Limitations」 |
| **失败影响** | 隔离：非法条目**跳过并告警**，registry 保留上一份好目录，会话照常；模型只看到「少了一个 skill」，无法区分「不存在」和「写错了」。【A】`dsh-skill-filesystem/README.md`「Observable success and failures」「Known Limitations」；【A】`dsh-skill/README.md`（"an invalid name returns no skill rather than throwing"） | 可波及：坏 bundle 会以 `error` 留在 `listBundles` 里且**不能被启用**；装失败要回滚 `package.json` + `pnpm-lock.yaml`；未声明兼容性的插件被 startup 拒；版本豁免要人签字 `acceptRisk`（警告"可能崩溃或丢数据"）。【A】`dsh-plugin-manager/README.md:42`、「Version compatibility and exemptions」、「Failure behavior」 |

再补一条容易混的：**skill 可以"由 plugin 提供"**（`dsh-skill-office`、`dsh-sandbox-windows-acl`、`dsh-skill-badge`
都是 plugin 形态的 skill provider）。所以「skill vs plugin」不是互斥分类：
**plugin 是装载机制，skill 是内容形态**。一个 plugin 可以只是"把 7 篇说明书塞进 catalog"，不注册任何工具。

### A.4.2 UI 上分别在哪看

| 看什么 | 在哪 | 证据 |
|---|---|---|
| **Skill** | ① 输入框打斜杠的建议列表；② 会话里加载后的可展开 `Instructions` 卡片 | 【A】`dsh-client-ui-skill/README.md`「Summary」「Use this package」 |
| **Skill（管理面板）** | 侧边栏 **"Skill Center"**（与 Plugins / Schedule / 任务板并列的中心页面）：按来源分层列出、搜索、改 `disable-model-invocation` 开关、编辑 SKILL.md、删除进 `.trash`；**Create** 标签页在 `~/.dsh/skills` 或 `.dsh/skills` 下生成标准 SKILL.md。**这是第三方插件且默认关闭**（row `web-ui-skill-explorer` 带 `disabled: true`），要在 Plugins 里开。 | `E:\dsh-data\profiles\desktop\node_modules\@linxin666\dsh-client-ui-skill-explorer\README.md`「What it does」；关闭标记见 `E:\dsh-data\profiles\desktop\node_modules\@linxin666\dsh-web-all\cordis.patch.yml:118-121` |
| **Plugin** | 侧边栏 **Plugins** 页：开关 bundle 与其 plugin row、安装/卸载、看 pnpm 输出、给注册了配置页的插件改配置。 | 【A】`dsh-client-ui-plugin-manager/README.md`「Summary」（"the **Plugins** entry in the Web sidebar"） |
| **Plugin（只读清单）** | 设置里的插件清单（"Settings keeps the read-only inventory"） | 【A】`dsh-client-ui-plugin-manager/README.md`「Summary」；对应包【A】`dsh-client-ui-settings-plugin-inventory/` |

> 讲给新手的一句话：**"我想让模型多会一件事" → 装/写 skill（改文件，秒生效）；
> "我想让程序多一个能力（工具 / 面板 / 服务）" → 装 plugin（动依赖，可能要重启）。**

---
# B. 本会话实际可用的 Skill

> 任务书列了 19 条（原文写"15 个"是估数）。**本会话 catalog 的实际条目数是 19**，
> 与系统提示里的 `<available_skills>` 完全一致，下文逐条覆盖，一条不漏。

## B.0 速查表

| # | skill | 来源根（rank） | 一行用途 |
|---|---|---|---|
| 1 | developing-with-streamlit | user-agents (500) | Streamlit 全套开发/美化/部署，按版本发现官方参考文档 |
| 2 | security-best-practices | user-agents (500) | 按语言+框架做安全最佳实践审查，出报告 |
| 3 | grill-master | project-agents (200) | 反复盘问，直到达成可测试的共识 |
| 4 | prd-writer | project-agents (200) | 交互式写「企业级、agent 可执行」的 PRD |
| 5 | spec-writer | project-agents (200) | 从对话+仓库上下文写结构化 PRD |
| 6 | slice-the-spec | project-agents (200) | PRD → 垂直切片的 Kanban 待办（HITL/AFK 标注） |
| 7 | spec-to-plan | project-agents (200) | PRD → `./plans/` 下的分阶段实施计划 |
| 8 | ui-ux-pro-max | project-agents (200) | UI/UX 设计智能库（样式/配色/字体/UX 规则 + 检索脚本） |
| 9 | math-ai-change-safety | project-agents (200) | 本项目跨层改动的安全落地与审查 |
| 10 | math-ai-frontend-qa | project-agents (200) | 本项目 Vue 学生端流程的 QA |
| 11 | math-ai-model-quality-eval | project-agents (200) | 本项目视觉/数学/RAG/Agent 质量评估 |
| 12 | office | bundled (600) | Office 任务路由（选对下面 6 个之一） |
| 13 | office-docx | bundled (600) | Word 创建/读取/编辑/校验 |
| 14 | office-xlsx | bundled (600) | Excel 读取/创建/编辑/校验 |
| 15 | office-pptx | bundled (600) | PowerPoint 创建/读取/编辑/校验 |
| 16 | office-render | bundled (600) | 用 LibreOffice Kit 出图做视觉检查 |
| 17 | office-export-pdf | bundled (600) | Office → PDF |
| 18 | office-recalculate | bundled (600) | 刷新电子表格公式缓存并核验 |
| 19 | diagnose-windows-sandbox-acl | bundled (600) | Windows 沙箱 ACL 拒绝的诊断 + 修复 |

**共同前提**：19 个 skill 的 frontmatter 里都没有 `disable-model-invocation: true` 或 `user-invocable: false`，
因此它们既在模型 catalog 里，也都能被斜杠菜单与 `/name` 手动点名。

---

## B.1 developing-with-streamlit

- **文件**：`C:\Users\HUAWEI\.agents\skills\developing-with-streamlit\SKILL.md`（24 行）+ `scripts/discover.py`
- **description 要点**（原文摘）："Use for ALL Streamlit tasks: creating, editing, debugging, beautifying, styling, theming, optimizing, or deploying Streamlit apps. Also custom components, st.components.v2, HTML/JS/CSS work. Discovers and loads version-matched reference docs from the user's installed Streamlit (>=1.57)." 后面还挂了一串触发词（streamlit、dashboard、app.py、beautify、CSS、theme、session state、cache、fragment、slow rerun、deploy…）。
- **另有一个非 DSH 键**：`allowed-tools: Bash(python (dollar){CLAUDE_SKILL_DIR}/scripts/discover.py:*)` —— DSH 不解析它（见 A.1.2）。
- **内部步骤**：
  1. 跑发现脚本：`python <SKILL_DIR>/scripts/discover.py --project-dir <USER_PROJECT_DIR>`；
  2. 脚本要么在 stdout 打印**一个路径**（exit 0）——那是用户装的 Streamlit(>=1.57) 自带的 SKILL.md，读它，它再指向 `references/` 里的分主题文档（dashboard、theme、layout、session state、custom components…）；
  3. 要么在 stderr 打印 `ERROR:` 块（非 0）——按提示处理后重跑；
  4. `--project-dir` 必须传：脚本要相对它解析 `.venv`、`../.venv`、`Pipfile`、`poetry.lock`、`pdm.lock`、`uv.lock`，以匹配**用户实际装的版本**。
- **真实调用例**：
  - 用户："我这个 Streamlit 页面太丑了，帮我把主题改成深色，加个圆角卡片布局。"
  - 模型：`skill("developing-with-streamlit")` → 用**用户的 python** 跑 `discover.py --project-dir <项目根>` → 拿到该版本自带的 SKILL.md → 按它指向的 theme/layout 参考文档写 `config.toml` 与 CSS。
  - 产出：改好的 `app.py` / `.streamlit/config.toml`，API 与用户安装的版本严格对齐（不是模型记忆里的旧版）。

## B.2 security-best-practices

- **文件**：`C:\Users\HUAWEI\.agents\skills\security-best-practices\SKILL.md`（86 行）+ `references/` 11 篇 + `LICENSE.txt`
- **description 原文**（注意它是**强触发条件**）："Perform language and framework specific security best-practice reviews and suggest improvements. Trigger only when the user explicitly requests security best practices guidance, a security review/report, or secure-by-default coding help. Trigger only for supported languages (python, javascript/typescript, go). Do not trigger for general code review, debugging, or non-security tasks."
- **内部步骤**：
  1. 先**识别本项目全部语言与框架**（前后端都要，别只看一半）；
  2. 按 `<language>-<framework>-<stack>-security.md` 到 `references/` 找文档，**把相关的全读**；也可退回 `<language>-general-<stack>-security.md`；
  3. 三种模式：① 默认 = 从此只写 secure-by-default 代码；② 被动 = 干活路上发现高危就打标记告诉用户；③ 出报告 = 按严重度分节、每条给数字 ID、关键项给一句话影响说明，写进 `security_best_practices_report.md`（引用代码**必须带行号**）；
  4. 修复：一次只修一条，写清"依据哪条最佳实践"，考虑回归风险，遵循用户既有的 commit / 测试流程；
  5. Overrides 段：项目文档要求绕过某条实践时可以绕过、"不要跟用户吵"，并建议把理由写进项目文档。
- **两条硬性告诫**：公网资源 ID 别用自增小整数（用 UUID4 / 随机 hex）；**别把"没有 TLS"报成漏洞**，也**别乱加 HSTS / secure cookie**（非 TLS 部署会直接打挂）。
- **实测存在的 references（11 篇）**：`python-fastapi-web-server-security.md`、`python-django-…`、`python-flask-…`、`javascript-typescript-vue-web-frontend-security.md`、`javascript-typescript-react-…`、`javascript-typescript-nextjs-…`、`javascript-general-web-frontend-…`、`javascript-express-…`、`javascript-jquery-…`、`golang-general-backend-…`
  ⇒ **本仓库（FastAPI + Vue 3）正好同时命中后端 `python-fastapi-web-server-security.md` 与前端 `javascript-typescript-vue-web-frontend-security.md`。**
- **真实调用例**：
  - 用户："帮我审一下 `app/api/` 的认证和 CORS，出一份安全报告。"
  - 模型：load skill → 判定 Python+FastAPI / TypeScript+Vue → 读那两篇 references → 扫代码 → 写 `security_best_practices_report.md`（执行摘要 + 按严重度分节 + 编号 + 行号 + 修复建议）→ 报告路径，问是否逐条修。
  - 产出：`security_best_practices_report.md` + 口头摘要。

## B.3 grill-master

- **文件**：【W】`.agents/skills/grill-master/SKILL.md`（78 行）；`metadata: {author: kambleakash0, version: 1.0.0}`，另有惰性的 `triggers: /grill, /grill-master, /grill-me`
- **description 原文**："Relentlessly interview the user when they want to learn about a topic, plan, or design until you both reach a shared, testable understanding, before any planning or implementation."
- **内部步骤（7 步）**：
  1. 用 2–3 句复述目标，请用户确认或纠正；
  2. 找出设计/逻辑树的**主干分支**（领域、目标、数据模型、接口、UX、约束、边界、集成、风险）；
  3. **每个分支一次只问一个聚焦问题**，把假设显式化，追问边界与失败模式；
  4. **能用代码答的绝不问用户**：查仓库/知识库，先简述事实，再用它问下一个问题；
  5. "未知的未知"环节：问"最不确定什么 / 最可能在哪被后来的事打脸 / 哪个假设最容易错"；
  6. 问题自然变少时，用自己的话总结（目标/关键决定/约束/遗留问题/风险），请用户**明确确认**；
  7. 只有用户确认后，才建议切到规划/实现 skill（如 `/spec-writer`），可把总结当上下文带过去。
- **6 条硬规则**：确认前不许出任何文档/计划/PRD/架构；一次一个问题；用户在盘问中途要计划就礼貌拒绝继续盘问；优先查仓库而不是让用户回忆；推断必须说出口；"够清楚"就停，不追求完美。
- **真实调用例**：
  - 用户："`/grill-master` 我想给错题本加个「按知识点自动聚类」。"
  - 模型：load skill → "我先复述一下……对吗？" → 一次一问（谁用？聚类粒度？`app/data/` 里已有标签体系能否复用？Qdrant 要不要重算？失败边界？）→ 中间自己去读 `app/services/` 与迁移文件 → 最后给总结请确认 → 确认后才建议 `/spec-writer` 或 `/spec-to-plan`。
  - 产出：一份被用户口头确认的共识摘要；**不产出任何文件**（这正是它的设计目的）。

## B.4 prd-writer

- **文件**：【W】`.agents/skills/prd-writer/SKILL.md`（215 行）+ `references/template.md`（16 节模板）+ `references/epic-sizing.md`（史诗切分尺度）；`metadata: {author: thomasrohde}`
- **description 原文**："Write enterprise-ready, agent-executable Product Requirements Documents (PRDs) through interactive guided sessions with ambiguity tracking. Produces PRDs that coding agents can execute with low drift, low rework, and strong governance."
- **核心哲学**：PRD 要同时是三样东西——**产品契约**、**给编码 agent 的执行契约**、**治理工件**。弱 PRD 会把歧义推进 agent 循环，变成漂移、重试、噪音 PR。
- **内部步骤（5 个 Phase）**：
  - **P1 理解项目**：4 轮访谈、每轮 1–2 问 —— ① 基础（做什么/给谁/为什么现在）② 范围与边界（in/out of scope、禁止的做法）③ 技术上下文（已有仓库、栈是否已定、合规安全约束）④ 交付形状（如何分期、谁审批、done 长什么样）。
  - **P2 逐节起草**：解释该节 → 用 AskUserQuestion 收集 → 起草 → 请用户确认。用户说"不知道/先跳过"就**打歧义标签**继续，不阻塞。
  - **P3 歧义追踪**：维护内部 tracker，文末**必须**加 `## Appendix: Unresolved Ambiguity Log` 表（`# / Section / Topic / What's Missing / Impact / Suggested Next Step`），定稿前把表拿给用户问"能不能现在解决几条"。
  - **P4 写文件**：存成 `PRD.md`（或用户指定位置），用 `references/template.md` 的 16 节结构。
  - **P5 建议配套文件**：`AGENTS.md` / `PLAN.md` / `IMPLEMENT.md` / `DECISIONS.md` / `STATUS.md`，问用户要不要一起搭。
- **模板 16 节**：Document Control、Executive Summary、Problem Statement、Scope、Personas and Scenarios、Functional Requirements、Non-Functional Requirements、Tech Stack Decision、Architecture and Repo Boundaries、Build/Run/Validate Contract、Security/Risk/Compliance、Observability and Operational Readiness、Phase Plan、Epic Cards、Open Questions and Decision Log、Definition of Done。
  其中 **Tech Stack 是一等章节**（要写备选方案、被否原因、以及 agent 不许擅自替换的护栏）；**Build/Run/Validate Contract 要求给出 setup / run / lint / test / build / security scan 的精确命令**；**Phase Plan 的每条史诗必须是 `- [ ] E0: 名称 — 目标` 复选框**，让 PRD 兼作进度板。
- **反模式清单**（会当场驳回）："用什么栈你定"、"顺手重构一下"、"测试看着加"、"production ready" 但没有安全/可观测性要求、纯主观验收标准、没有 non-goals、没有命令级验证、一个巨型实现阶段。
- **真实调用例**：
  - 用户："`/prd-writer` 我要给这个数学助手加一个「个性化周报」。"
  - 模型：load skill → 只问 Round 1 三问 → 逐节推进（Functional Requirements 每条扩成「唯一 ID + 描述 + 理由 + Must/Should/Could + 验收标准 + 可测性说明」；Phase Plan 先读 `references/epic-sizing.md` 控粒度）→ 末尾给歧义表让用户裁决 → 落盘 `PRD.md`。
  - 产出：`PRD.md`（16 节 + 歧义附录）+ 可选配套文件。

## B.5 spec-writer

- **文件**：【W】`.agents/skills/spec-writer/SKILL.md`（140 行）；`metadata: {author: kambleakash0}`
- **description 原文**："Create a comprehensive Product Requirements Document from conversation and repo context. Use when the user wants a PRD, product spec, feature requirements, or similar documentation."
- **与 prd-writer 的定位差异**：prd-writer 是"重流程 + 治理 + 歧义台账"；**spec-writer 是"轻量、8 步走完、10 节模板"**，前提是歧义已经用 `/grill-master` 盘出去了（若想法还模糊，它会把用户推回 grill-master）。
- **内部步骤（8 步，可压缩）**：
  1. 收一段**长而具体**的问题描述（问题 / 给谁 / 为什么现在 / 已有想法或约束；鼓励粘文档而不是重打）；
  2. 探仓库、**交叉验证用户的断言**（哪里一致、哪里矛盾、哪里沉默）；
  3. 列 2–3 个备选方案 + 取舍（复杂度/交付时间/风险/UX），确认哪个作为主方案；
  4. 需要时做深度实现访谈（流程、状态、输入输出、失败模式、权限、性能）；
  5. 敲死 in scope / out of scope（含 MVP vs 全量、phase 划分）；
  6. 轻量勾画模块与架构，**标出可独立测试的深模块**（方便后面 TDD）；
  7. 按 10 节模板写 PRD；
  8. 可选：按仓库约定落成 GitHub issue 或 markdown。
- **10 节模板**：Summary / Problem Statement / Goals and Non-Goals / User Stories（长编号清单，`As an <actor>, I want <feature>, so that <benefit>`）/ Functional Requirements / Non-Functional Requirements / Implementation Notes and Architecture / Out of Scope / Risks and Open Questions / Success Metrics。
- **真实调用例**：
  - 用户："帮我写个 spec，把错题本改成支持「同类题推荐」。"
  - 模型：load skill → 要一段长描述 → 读 `app/api/`、`app/data/`、`frontend/src/api/` 核对现状（"你提到已有 Qdrant 相似度检索，代码里确实有，但只在 X 路径用"）→ 给 3 个备选（复用现有向量 / 新知识图谱 / 混合）→ 定方案 → 写 10 节 PRD。
  - 产出：一份可直接喂给 `/slice-the-spec` 或 `/spec-to-plan` 的 PRD。

## B.6 slice-the-spec

- **文件**：【W】`.agents/skills/slice-the-spec/SKILL.md`（113 行）
- **description 原文**："Turn a PRD into a Kanban-ready backlog of vertically sliced issues, with clear dependencies and HITL/AFK flags."
- **三个必须先讲清的概念**：
  - **垂直切片 / 曳光弹（tracer bullet）**：一条薄但**打通所有层**（数据 → 领域 → API → UI）的端到端功能，而不是"先把数据库表建好"这种横向切片；
  - **HITL**（Human-In-The-Loop）：需要人做决定（设计评审、干系人签字、高风险重构）；
  - **AFK**（Away-From-Keyboard）：安全到可以交给 agent 自主实现并合并。**优先 AFK，但人的判断必须显式标 HITL。**
- **内部步骤（6 步）**：定位并读懂 PRD（多份先确认用哪份）→ 探代码库（现有架构、集成点、既有模式如 feature flag / 后台任务）→ 起草少量垂直切片 → 每片定义 `标题 / 类型(HITL|AFK) / 描述（引用具体 user story 与 PRD 章节）/ 验收标准 / Blocked by`，并保证**至少有一条无阻塞、立刻能开工** → 把切片表拿给用户盘（粒度是否合适 / 依赖对不对 / 要不要合并拆分 / HITL 标得对不对），迭代到批准 → 生成 GitHub-ready 的 issue 正文（含上下文、任务、验收标准、PRD 链接、HITL/AFK 标记）。
- **规则**：**少而精**（几条高杠杆，不要几十个微 issue）；每条 issue 拿到 PRD + 仓库就能干；优先"点亮一条窄但真实的路径"；不许把人的决策藏进 AFK 里。
- **真实调用例**：
  - 用户："PRD 写完了，帮我拆成能并行的 issue。"
  - 模型：load skill → 读 `PRD.md` → 扫 `app/`、`frontend/`、`agent_core/` → 提 4 条切片：①「错题相似度打分服务（AFK）」②「同类题推荐 API + 契约测试（AFK）」③「错题本页面推荐区（HITL：需设计确认）」④「推荐效果埋点与周报联动（HITL）」→ 问粒度/依赖 → 批准后逐条输出 issue 正文。
  - 产出：可直接建单的 issue 正文列表 + 依赖关系说明。

## B.7 spec-to-plan

- **文件**：【W】`.agents/skills/spec-to-plan/SKILL.md`（147 行）
- **description 原文**："Turn a PRD into a multi-phase implementation plan using tracer-bullet vertical slices."
- **内部步骤（7 步）**：确认 PRD 在上下文里（不在就请用户粘/给路径）→ 轻量扫仓库 → **先定"耐久架构决定"**（路由形态、表结构、核心模型、认证授权、第三方边界）→ 起草垂直切片（每片可独立演示/验证；**不写易变细节**如文件名/函数签名；**要写耐久决定**如路由路径、schema 形状、模型名）→ 分成 **2–5 个阶段**（前面的阶段先去风险、先能演示、先立模式）→ 把阶段号/标题/覆盖的 user story 拿给用户盘并迭代到批准 → 落到 `./plans/<feature>.md`（目录不存在就建）。
- **计划模板结构**：`# Plan: <Feature Name>` + `> Source PRD: <link>` + `## Architectural decisions`（Routes / Schema / Key models / Auth / Third-party services）+ `## Phases`，每阶段 `#### What to build`（讲端到端行为，不讲逐层实现）+ `#### Acceptance criteria`。
- **规则**：停在计划层，不写具体文件改动（那是 `/tdd` 之类执行 skill 的活）；按风险与价值排序；保持垂直；把耐久决定写在头部让下游的人和 agent 复用。
- **真实调用例**：
  - 用户："按这份 PRD 出个分阶段计划，我想先看两周能不能出个能演示的版本。"
  - 模型：load skill → 读 PRD → 扫代码 → 头部写死决定（如"路由 `/api/v1/error-book/recommend`；新增表 `recommendation_cache`；认证沿用既有 `get_current_user` 依赖"）→ 切 3 阶段（Phase 1 打通一条推荐链路并演示 → Phase 2 补缓存与降级 → Phase 3 埋点与周报）→ 用户确认 → 写 `plans/error-book-recommend.md`。
  - 产出：一个 `./plans/*.md` 计划文件。

## B.8 ui-ux-pro-max

- **文件**：【W】`.agents/skills/ui-ux-pro-max/SKILL.md`（659 行，45 KB，主体就是规则库）；文中引用 `scripts/search.py`
- **description 要点**（原文很长，关键部分）："UI/UX design intelligence for web and mobile. Includes 50+ styles, 161 color palettes, 57 font pairings, 161 product types, 99 UX guidelines, and 25 chart types across 10 stacks … Actions: plan, build, create, design, implement, review, fix, improve, optimize, enhance, refactor, and check UI/UX code …"
- **何时用 / 何时不用（原文判据）**：
  - **Must Use**：设计新页面（Landing/Dashboard/Admin/SaaS/App）、做或重构 UI 组件、选配色/字体/间距/布局体系、审查 UI 代码的可访问性与一致性、做导航/动画/响应式、做产品级设计决策；
  - **Skip**：纯后端逻辑、只涉及 API/数据库、与界面无关的性能优化、基建/DevOps、非可视脚本；
  - 一句话判据：**"这个任务会改变功能看起来 / 感觉起来 / 怎么动 / 怎么交互吗？"会，就用。**
- **优先级表（1→10）**：① 可访问性 CRITICAL（对比度 4.5:1、alt、键盘导航、aria-label）② 触控与交互 CRITICAL（44×44px、8px 间距、loading 反馈、别只靠 hover）③ 性能 HIGH（WebP/AVIF、懒加载、CLS<0.1）④ 样式选择 HIGH（匹配产品类型、SVG 图标不用 emoji）⑤ 布局与响应式 HIGH（移动优先、无横向滚动、禁缩放）⑥ 字体与色彩 MEDIUM（正文 16px、行高 1.5、语义色 token）⑦ 动画 MEDIUM（150–300ms、动效要有意义、尊重 reduced-motion）⑧ 表单与反馈 MEDIUM（可见 label、错误就近、渐进披露）⑨ 导航（可预测返回、底部导航≤5、深链）⑩ 图表与数据 LOW（图例、tooltip、别只靠颜色）。
- **使用流程（4 步）**：
  1. 分析需求（产品类型 / 目标人群 / 风格关键词 / 技术栈）；
  2. **必须先跑设计系统生成**：`python3 skills/ui-ux-pro-max/scripts/search.py "<产品> <行业> <关键词>" --design-system [-p "项目名"]`，它并行查 product/style/color/landing/typography 并用 `ui-reasoning.csv` 推理，返回 pattern + style + colors + typography + effects + 反模式；
  2b. 想跨会话复用就加 `--persist`，生成 `design-system/MASTER.md` 与 `design-system/pages/<page>.md`（页面级覆盖优先于 MASTER）；
  3. 需要细节再按域查：`--domain product|style|color|typography|chart|ux|google-fonts|landing|react|web|prompt`；
  4. 按栈查实现规范：`--stack react-native`（原文只列了 `react-native` 一个可用 stack）。
- **⚠️ 现实校验（必须告诉用户）**：这份 SKILL.md 的 Step 1 / Step 4 写死了 **React Native**（"React Native (this project's only tech stack)"、`--stack react-native`），
  而**本仓库前端是 Vue 3**。所以它在本项目里真正有用的是**设计知识部分**（10 类规则、配色/字体/风格建议），
  而不是它的 stack 规范；文中那串 `skills/ui-ux-pro-max/scripts/search.py` 相对路径是从另一个项目布局照搬的，
  **本仓库不存在该脚本**（见附录 C.4）。
- **真实调用例**：
  - 用户："`/ui-ux-pro-max` 学生端 Dashboard 看着不专业，帮我重做视觉。"
  - 模型：load skill → 判定 = Dashboard + 教育工具类 + 目标人群大学生 → 查 Quick Reference 的 ①可访问性 ⑤布局 ⑥字体与色彩 ⑨导航 ⑩图表 → 给出配色 token / 字号阶 / 间距体系 / 卡片与图表规范 → 落地成 `frontend/` 里的 CSS 变量与组件改动 → 按文末 Pre-Delivery Checklist（视觉质量/交互/明暗模式/布局/可访问性）自检。
  - 产出：带理由的设计系统建议 + 实际前端改动（本项目应配合 `$math-ai-frontend-qa` 验收）。

## B.9 math-ai-change-safety

- **文件**：【W】`.agents/skills/math-ai-change-safety/SKILL.md`（29 行）—— 本项目自建，结构固定为 `Input / Execute / Output / Verify / Do Not`
- **description 原文**："Safely implement or review cross-layer changes in this Math AI Assistant that affect FastAPI APIs, Pydantic schemas, SQLAlchemy/Alembic data, memory/error-book/profile state, Qdrant, Agent tools, or frontend contracts. Use for architecture-impact analysis, API compatibility reviews, migration planning, and student-data consistency validation."
- **Input**：收集期望行为、受影响角色、触达路径、兼容性预期、是否涉及生产存量数据；**动手前先看** route、请求/响应模型、service、repository/model、migration、前端 client、tests。
- **Execute 4 步**：
  1. 沿 `frontend/src/api/` → `app/api/` → `app/services/` → `app/data/`（及相关 `agent_core/`、`tools/`、`prompts/`、Redis、Qdrant）画出影响面，说明受影响的契约与所有权边界；
  2. **保持公共 API 行为**；新增字段要显式 Pydantic 校验；**同一次改动里更新所有第一方调用方**；学生范围数据必须有鉴权归属检查；
  3. 持久化改动要讲清 SQL 真源、向量副作用、幂等键、失败/重试行为、修复路径；schema 改动**先查模型兼容与存量数据约束，再写 Alembic revision**；
  4. 加聚焦回归测试：优先覆盖最可能断的边界（鉴权/隔离、事件重复投递、旧 payload 兼容、空库升级、SQL/Qdrant 分叉）。
- **Output**：影响面图、兼容性决定、不变量、改动的测试、迁移命令（若有）、残余运维风险。
- **Verify**：跑受影响的 pytest；迁移/服务改动在栈可用时验证**空 PostgreSQL 升到 head**；`scripts/verification/verify_memory_pipeline.py` 只能在一次性隔离环境跑；前端契约变了就跑前端 test/build。
- **Do Not**：不许加运行时裸 SQL 迁移；不许悄悄改变 API 字段语义；不许用默认用户/共享 session；不许为了测试去改 `data/math_ai.db` 或 Qdrant 存储；不许在没有审计与明确授权时做破坏性数据修复。
- **真实调用例**：
  - 用户："给错题本接口加个 `difficulty` 字段，前端也要用。"
  - 模型：load skill → 读错题路由、`app/services/`、`app/data/models`、`frontend/src/api/` 与相关测试 → 说明影响面（Pydantic 响应模型 / Alembic 迁移 / 前端类型 / 旧客户端兼容）→ 加显式字段 + 迁移 + 更新第一方调用方 → 补"旧 payload 兼容"与"用户隔离"两条 pytest → 跑 `python -m pytest tests -q` 与 `npm run build`。
  - 产出：跨层改动 + 影响面报告 + 测试证据 + 迁移命令。

## B.10 math-ai-frontend-qa

- **文件**：【W】`.agents/skills/math-ai-frontend-qa/SKILL.md`（30 行）
- **description 原文**："Verify Vue 3 student-facing flows in this Math AI Assistant, especially chat/math rendering, error book, knowledge learning, profile, and dashboard UI. Use after frontend changes, API-client contract changes, responsive layout work, or when diagnosing a visual or interaction regression; combine Vitest/build evidence with browser-based runtime QA."
- **Input**：列出改动的 route/component/store/API 调用、主任务、期望的 loaded/empty/error 三态、目标视口尺寸；**起服务前先读**相关路由与既有 API client。
- **Execute 5 步**：
  1. 做 QA 清单：把**每一条用户可见的声明与控件**都映射到一个功能检查和视觉状态；除改动流程外必须覆盖一个失败态或空态；
  2. 在 `frontend/` 跑 `npm run test`（有覆盖时）再 `npm run build`；
  3. 起正常 Vite 应用，用内置 `browser:control-in-app-browser` 做运行时验证；**检查桌面 + 390px 宽移动视口**、路由跳转、loading/error 处理、键盘/焦点，以及涉及时的 KaTeX/Markdown 渲染；
  4. 把前端实际发出的 payload 与渲染字段，对照 FastAPI 的请求/响应模型；
  5. 行为确定时补一个聚焦的 Vitest 组件/store 测试；提交级 Playwright **只在仓库明确引入 `\@playwright/test` 且有稳定 mock 后端之后**才提议，不为一次性检查加浏览器依赖。
- **Verify 门槛**：生产 build 必须成功；**没有通过可见用户输入实际点过的交互不许签收**；视觉中心型的改动**没看过渲染结果不许签收**。
- **Do Not**：不许拿 DOM 变更或 mock store 当 UI 证据终稿；不许只靠截图证明功能行为；不许在共享环境改用户数据；不许声称有 Playwright 覆盖而实际没跑。
- **真实调用例**：
  - 用户："我把对话页的公式渲染改了，帮我验一下。"
  - 模型：load skill → 列出 chat 路由/消息组件/KaTeX 管线 → `npm run test` + `npm run build` → 起 Vite → 浏览器里发一条含 LaTeX 的消息、切到 390px、制造一次网络失败 → 截图/记录观察 → 对照 API 模型确认字段 → 报告。
  - 产出：QA 清单 + 命令与结果 + 视口覆盖 + 失败态结论 + 契约不一致项。

## B.11 math-ai-model-quality-eval

- **文件**：【W】`.agents/skills/math-ai-model-quality-eval/SKILL.md`（30 行）
- **description 原文**："Evaluate a Math AI Assistant behavior involving Qwen-VL-style visual question understanding, Qwen-Max-style mathematical answers, classification, RAG retrieval, agent planning, tool calls, or learning recommendations. Use when changing prompts/models/tools/retrieval, investigating answer quality, or creating repeatable AI quality regression cases."
- **Input**：拿一份**有代表性、不含敏感信息**的评测集或可复现的失败样例；定义用户意图、给定图像/文本、期望数学结果、必须满足的解释性质、允许用的工具/来源、期望的学习数据副作用。
- **Execute 5 步**：
  1. **先定失败边界**：视觉抽取 / 归一化 / 检索 / agent 规划与工具调用 / 数学推理 / 流式与格式渲染 / 记忆与画像推荐；
  2. 建小矩阵：正常、歧义或噪声、畸形、**错但看起来对**四类；**图像得出的断言与数学断言分开，检索证据单独放**；
  3. 逐项打分：抽取保真、最终答案正确、推理可验证性、检索接地、工具/计划正确性、中文数学与 LaTeX 渲染、安全性、**有无跨用户记忆泄漏**；
  4. 解析/路由/元数据/工具调用/答案结构优先用**确定性断言**；开放式数学质量用人审 golden answer；**不许用一次成功 prompt 就宣称模型质量**；
  5. 稳定用例固化成 pytest，放 `test_vision_tool*`、`test_classifier.py`、`test_task_planner.py`、`test_rag_*`、`test_v3_prompt_system.py` 附近。
- **Verify**：默认 mock 掉模型/网络跑定向测试（除非明确授权做集成评测）；跑真模型要记录模型/配置、时间戳、输入、成本与延迟约束，并脱敏学生数据与密钥。
- **Do Not**：流畅≠正确；不许把 prompt 和代码一起未度量地改；不许把真实学生图像/会话存进 fixture；不许未经数学验证就把模型输出当真源。
- **真实调用例**：
  - 用户："换了视觉解析的 prompt 之后判题好像变差了，帮我评估。"
  - 模型：load skill → 要一组非敏感样例 → 归类失败在"视觉抽取"还是"数学推理" → 建 8 条矩阵（含一条"错但看起来对"）→ 逐条打分表 → 对稳定项写 pytest（mock 模型）→ 报告。
  - 产出：评测表（case / 证据 / 通过判据 / 观察结果 / 根因边界 / 后续测试）+ 新增回归用例。

## B.12 office

- **文件**：【A】`dsh-skill-office/assets/office/SKILL.md`（15 行）+ `references/sidecar.md`
- **description 原文**："Create, edit, inspect, or convert Office documents, spreadsheets, presentations, and PDFs. Load to choose the relevant workflow."
- **它是一条纯粹的路由规则**（全文就 4 条）：
  - 创建/读取/编辑：Word → `office-docx`，PowerPoint → `office-pptx`，Excel → `office-xlsx`；
  - 要图片、要视觉检查、或任务本质是**布局/间距/尺寸/对齐**：→ `office-render`（**即使没明说要视觉检查**）；
  - 刷公式结果：`office-recalculate`；
  - Office → PDF：`office-export-pdf`。
  - 另两句重要纪律：**尊重用户"跳过渲染"的要求**；新建文件/改内容/写公式/顺手加粗表头这类"附带格式"不需要渲染；**`Do not reload skills`**。
- **真实调用例**：
  - 用户："把这份题库统计做成 Excel，要能求和。"
  - 模型：load `office`（路由）→ 判定 Excel 创建 → load `office-xlsx` → 建工作簿（含 `=SUM(...)`）→ 因为"要能求和"意味着要看**算出来的值**，再 load `office-recalculate` 刷新并核验 → `present` 交付。
  - 产出：`report.xlsx`（公式已算出、已重开核验）。

## B.13 office-docx

- **文件**：【A】`dsh-skill-office/assets/office-docx/SKILL.md`（40 行）
- **description 原文**："Create, read, edit, and validate Word documents (.docx)."
- **步骤梗概**：
  1. **环境**：用 `load_workspace_dependencies` 返回的 Python 路径 + 自带库（默认 `python-docx`）；**不要装包、不要去系统里找 Python**；只有工具不可用才退回已配置环境；
  2. **文件卫生**：脚本/中间件/成品都放任务工作区；**运行时和 skill 目录是只读资源**；脚本按任务命名（`edit_docx.py`），**别叫 `inspect.py` / `docx.py` / `zipfile.py`**（会遮蔽要导入的库）；
  3. **编辑**：按文本或位置定位目标，只读它的 runs 与格式；**别写 `paragraph.text =`**（会把 run 级格式全毁）；除非要求原地改，一律存新文件；只在改动涉及其它结构时再读那些结构（重建文档会丢不支持的特性）；
  4. **排版**：标题/正文用段落样式；表格尺寸按所在节算，注意合并单元格与嵌套表；**中日韩文本可能需要在 `run.font.name` 之外显式设 `w:eastAsia`**；
  5. **不做假的修订**：python-docx 不分页不渲染；普通替换/变色/批注**不要**伪装成 tracked changes；真要修订就保留原 package part；直接写 OOXML part 时必须**新建 ZIP 并逐个复制未改成员**（追加同名成员会把包弄坏）；
  6. **校验并交付**：重开保存的文件，核对要求的内容、相关格式，以及必须保留的未改内容；然后 `present({"files":[{"path":"report.docx"}]})`（present 只暴露原文件路径、不复制字节，所以文件要留在原地）。
- **何时升级到 `office-render`**：用户要图/要视觉检查；或**改动本身就是样式、字体颜色、间距、尺寸、文本对齐**——这时即使没人说"检查一下"，也要 load `office-render` 看那一页（除非用户明确跳过）。
- **真实调用例**：
  - 用户："生成一份《本周学习报告》Word，两页以内，标题加粗，中文字体用宋体。"
  - 模型：load `office` → `office-docx` → `load_workspace_dependencies` 拿 Python → 写 `build_report.py`（`add_heading` / `add_paragraph(style=...)`，中文 run 显式设 `w:eastAsia`）→ 运行 → 用 python-docx 重开核验 → `present` 交付。
  - 产出：`学习报告.docx`（+ `build_report.py`）。

## B.14 office-xlsx

- **文件**：【A】`dsh-skill-office/assets/office-xlsx/SKILL.md`（52 行）
- **description 原文**："Read, create, edit, and validate Excel workbooks, data, and formulas (.xlsx)."
- **步骤梗概**：
  1. 环境同 B.13，默认自带 `openpyxl` + `pandas`；脚本别叫 `openpyxl.py` / `pandas.py`；
  2. **读与改**：改已有工作簿用 `openpyxl`；**要保住公式必须 `data_only=False`**；动手前先看 sheet 名、受影响单元格的类型/公式/样式/合并区/引用区；保存后**重开**核验；
  3. **pandas ≠ 工作簿**：DataFrame 直接覆盖写回会丢 sheet/公式/图表/格式；分析结果要用 openpyxl 写回**目标区域**；`XlsxWriter` 只能新建、不能读改；
  4. **类型语义**：数字/日期/布尔/标识符要保成目标单元格类型；格式不等于类型转换；
  5. **写公式 ≠ 算出结果**：openpyxl/XlsxWriter 不求值；`data_only=True` 读到的是**可能缺失或过期**的缓存值。需要刷新就 load `office-recalculate`；**不许把公式换成常量、也不许把过期值当新算结果报**；
  6. **格式兼容**：不要把 `.xls` / `.xlsb` / 加密 / 启用宏的文件改名成 `.xlsx`；`keep_vba=True` 只能保住 VBA 包内容，既不能执行也不能编辑宏；
  7. **校验**：重开核对 sheet 名/值/类型/公式/样式/合计（**这些检查不算求值、也不判断外观**）；`present` 交付。
- **何时必须渲染**：用户要图/要视觉检查；或**任务主目标就是外观**（单元格填充色、文本对齐、间距、尺寸）——即使没说"检查一下"也要 `office-render`。**但**新建工作簿、纯数据/公式改动**不因为**顺手加粗表头、加个数字格式就必须渲染（原文专门强调了这点）。
- **真实调用例**：
  - 用户："这是 30 道题的得分 CSV，帮我做成 Excel，加个平均分公式，表头加粗，列宽调大。"
  - 模型：load `office` → `office-xlsx` → `openpyxl` 建表 + `=AVERAGE(...)` + 表头 `Font(bold=True)` + `column_dimensions` 宽 → 因为用户要"看到平均分"，再 load `office-recalculate` → 用 `data_only=True/False` 两种方式重开核验 → `present`。
  - 产出：`scores.xlsx`（公式在、缓存值已算）。

## B.15 office-pptx

- **文件**：【A】`dsh-skill-office/assets/office-pptx/SKILL.md`（64 行）
- **description 原文**："Create, read, edit, and validate PowerPoint presentations (.pptx)."
- **步骤梗概**：
  1. 环境同上（默认 `python-pptx`）；脚本别叫 `pptx.py` / `zipfile.py`；
  2. 改已有演示：先看 layout、文本 run、图片、表格、图表；**只改要求的内容**，保住混合文本格式，存新文件；**重建幻灯片会丢掉不支持的动画、SmartArt 等扩展内容**；
  3. 新建：用 `python-pptx` 做可编辑文本/表格/图表；**用本地图片资源，不要网络图片 URL**；显式设幻灯片尺寸、字号、图表数据；
  4. 版式检查：文字/图片是否溢出；标题串起来是否成一条主线；**图表标签要和源数据一致**；"段落居中"不等于"文本框居中"——要真正居中得同时把文本框相对 `presentation.slide_width` 居中再重开核验；原生图表的**内嵌工作簿也是交付物**，里面必须是正确数据；
  5. 交付前用 python-pptx 重开核对页数/内容/格式/图表数据/备注；然后 `present`。
- **何时 load `office-render`**：要图/要视觉检查；以及外观导向的样式、间距、尺寸、对齐改动（除非用户明确跳过）。
- **真实调用例**：
  - 用户："做一份 5 页的季度学习总结 PPT，第 2 页放柱状图，标题居中。"
  - 模型：load `office` → `office-pptx` → 写 `edit_pptx.py`（16:9、`CategoryChartData` + `add_chart`、标题段落与文本框双居中）→ 运行 → python-pptx 重开核验 → 因"标题居中"属外观诉求，load `office-render` 出第 1 页图确认真的居中 → `present`。
  - 产出：`quarterly.pptx`（+ 脚本）。

## B.16 office-render

- **文件**：【A】`dsh-skill-office/assets/office-render/SKILL.md`（31 行）
- **description 原文**："Render requested document images or inspect visual layout with LibreOffice Kit."
- **前置**：用安装好的 **LibreOffice Kit CLI**，绝对 node 与 CLI 路径由正文（加载时注入）给出；Bash 里 `'<node>' '<cli>'`，PowerShell 里 `& '<node>' '<cli>'`。**sidecar 缺失时**按 `../office/references/sidecar.md` 处理：**先问用户是否愿意下载，同意后才装**；**不许**调系统 `soffice`、**不许** `npx`、**不许**装替代渲染器绕过。
- **能力自检**：只为"看"而生成图片前，先确认当前模型**能读图**；不能就做完内容与结构检查，然后如实说"视觉检查不可用"，**不许**生成读不了的预览、不许反复重试读图、不许换模型。用户明确要的图片导出仍然可以交付。
- **命令**：
  `
  "<node>" "<cli>" render --input <final-file> --output-dir <new-directory> --pages "1,3,4"
  "<node>" "<cli>" render --input <final-workbook.xlsx> --output-dir <new-directory> --sheet <exact-name> --range <A1-range>
  `
- **目录纪律**：只检查用的预览要建**私有、随机命名**的临时父目录（POSIX `mktemp -d "./.dsh-office.XXXXXXXX"`；PowerShell 用 `.dsh-office-` + GUID），并把**尚未创建**的子目录作为 `--output-dir`；路径全部加引号；检查完**只删那个父目录**（渲染失败也要删）；**绝不用固定目录名、绝不删工作区**；回复里不许链接或嵌入已删除的预览。
- **读输出**：读返回的 JSON manifest（图片路径、页数、碎片矩形、缺字体诊断），再用会话的读图工具看；检查裁切、对齐、标题、表宽、对比度、图表标签、数字格式。**"命令成功"或"图读成功了"都不等于预览可用**；不许靠猜的文本几何判断溢出。
- **空白 / 失败预览的铁律**：有内容的文档渲染出全透明或纯白 = 渲染器失败；需要像素判断时先把 RGBA 合成到白底。**只检查一次，不许重读同一张图**；出现空白就**立刻停止本任务的视觉检查**（这条覆盖前面"改完再渲一次"的建议）——不许换范围/换页/换 DPI/换格式/导出诊断再试。之后只能给出**恰好一句**状态：英文 `Content and structure checks passed; visual inspection was not completed.` 或中文「内容与结构检查通过；视觉检查未完成。」；**不许**加渲染说明、不许解释为什么停、不许描述像素、**不许说"全部检查通过"**。
- **现实提醒**：LibreOffice 输出可能与 Word/PowerPoint/Excel 不同；图片**不证明**动画/媒体播放、**不刷新**源工作簿的公式缓存、**不保证**原生应用保真度。
- **真实调用例**：
  - 用户："这份 PPT 第 3 页文字好像压到图表了，帮我看看。"
  - 模型：load `office` → `office-render`（路由规则：视觉检查）→ 建 `.dsh-office-<guid>/render` → `render --input deck.pptx --output-dir …/render --pages "3"` → 读 manifest → 读图 → 报"第 3 页标题框与图表重叠约 X"→ 删父目录。
  - 产出：结论（文字）+ 必要的源文件修改；**不交付**预览图（除非用户要）。

## B.17 office-export-pdf

- **文件**：【A】`dsh-skill-office/assets/office-export-pdf/SKILL.md`（18 行）
- **description 原文**："Convert an Office document to a requested PDF with LibreOffice Kit."
- **步骤**：同一套 LibreOffice Kit 前置与 sidecar 纪律 → `convert --input <final-office-file> --output <new-file.pdf>`（在工作区生成**新** PDF，保住源文件，路径加引号）→ 校验：命令结果、输出非空、文件签名以 `%PDF-` 开头，**只报这个程度的验证**；除非用户要求更深检查，**不要**去找 PDF 阅读器、不要生成图片、不要装工具。
- 电子表格的 PDF 分页跟随工作簿的打印设置；**只在被要求时**改这些设置。失败就保住源文件并如实说明；**不许**对没改过的源反复转换、**不许**用转换去排查失败的预览。只做 PDF 导出就到此为止；**只有**用户另外要图片/视觉检查时才 load `office-render`。
- **真实调用例**：
  - 用户："把这个 docx 转成 PDF 发我。"
  - 模型：load `office` → `office-export-pdf` → `convert --input report.docx --output report.pdf` → 检查非空 + `%PDF-` → `present` 交付。
  - 产出：`report.pdf`。

## B.18 office-recalculate

- **文件**：【A】`dsh-skill-office/assets/office-recalculate/SKILL.md`（18 行）
- **description 原文**："Refresh spreadsheet formula caches and verify calculated values with LibreOffice Kit."
- **步骤**：同一套 CLI 前置 → `recalculate --input <workbook.xlsx> --output <recalculated.xlsx>`（保住原工作簿，在工作区写新文件）→ **核验**：用 `load_workspace_dependencies` 的 Python + openpyxl，**同时以 `data_only=False` 与 `data_only=True` 打开**，确认公式还在、缓存结果符合期望逻辑与合计、单元格类型正确、要求保留的 sheet/样式/数据没变。
- **边界**：重算**不**验证业务逻辑、**不**保证 Excel 专有特性兼容。引擎不可用或命令失败：保住工作簿、如实说"计算值无法刷新"；**不许**把公式换成常量、**不许**把过期/缺失缓存当新结果交付。
- **真实调用例**：
  - 用户："这个 xlsx 里公式算出来是空的，帮我补上数。"
  - 模型：load `office` → `office-recalculate` → `recalculate --input in.xlsx --output out.xlsx` → openpyxl 双模式打开核验 `=SUM(B2:B3)` 仍在且缓存等于期望值 → `present`。
  - 产出：`out.xlsx`（公式 + 已算缓存）+ 核验结果。

## B.19 diagnose-windows-sandbox-acl

- **文件**：【A】`dsh-sandbox-windows-acl/assets/diagnose-windows-sandbox-acl/SKILL.md`（63 行）+ `scripts/diagnose-windows-sandbox-acl.ps1`
- **description 原文**："Use on Windows for unexpected DSH sandbox access denials: workspace writes or listing fail, or an ordinarily readable path cannot be read. One bundled command inspects the path and every ancestor and repairs the ACL problems it proves in that same run. Expected confinement denials need no ACL repair."
- **何时用**：**意外的**拒绝——工作区写入/列目录失败、或本该能读的路径读不了。**预期的**拒绝不要修（工作区外写入、`read-only` 下任何写入、管道隔代子进程的 `spawn EPERM`、ConstrainedLanguage 报错）。
- **一条命令，既诊断也修复**（没有"模式"开关，不许拆成两步）：
  `
  & '<skill-dir>\scripts\diagnose-windows-sandbox-acl.ps1' -Path '<失败路径>' -AllowRoot '<被授权目录>' -Out '<恢复信息目录>'
  exit $LASTEXITCODE
  `
  它读该路径与**每一级祖先**，并在同一次运行里修好它证明的问题：缺 `WRITE_DAC` / `WRITE_OWNER` 的目录补当前登录用户的完全控制；移除 `S-1-15-2-*` 形式的 AppContainer 包 ACE（祖先前先）；若目录处于沙箱无法 provision 的状态，还会在同一轮里对该子树做有界搜索（会报 `truncated`）。每项改动**先备份再复读验证**。`-AllowRoot` 限定只改该目录及其**内部**。
- **必须**：**在沙箱外（要审批）跑一次**——脚本要写权限，受限 token 写不了，**受限运行永远没用**；`-Out` 要持久、属用户，**不要**放 skill 资源目录（skill 卸载会被删）；一次只传一个路径。
- **审批文案纪律**（写提示的极好范例）：**用用户的语言写人话**：说清碰哪个文件夹、会把登录用户的完全控制加在哪里、会移除哪些外来包条目、文件内容与所有者不变、打印的恢复命令能撤销每一项；**不许**在请求里出现错误码、`WRITE_DAC` / `WRITE_OWNER`、`S-1-15-2-*`、`icacls`、ACL/ACE 这些词——要写"Windows 文件权限"。一次只问一条命令。
- **读结果**：所有记录都会进 stdout、`-Out/acl-report-*.jsonl` 和最后一行 `RECAP`；**工具输出只留尾巴，所以先读 RECAP**。**只信 `verification` 记录，不信 `completed` 动作**。按 `details.nextAction` 决定：`verify_original_confined_operation`（修好且已验证 → 回到受限环境重试原操作）/ `stop`（没修成或被拒 → 报告并停）/ `restore_pending_then_stop`（回滚未验证 → 按打印顺序执行恢复命令后停）。
- **停止后仍欠用户一个决定**：要说清阻塞对象与缺的权限、改了什么回滚了什么、恢复命令顺序、报告路径；并请用户把会话临时切到**完全权限**（full access），以及把会话作为反馈发出去。正文给了中英双语话术模板。
- **Never**：手工改 ACL、改所有者、删 deny ACE、递归替换子权限；**不要**提权/UAC/`runas` 跑脚本；**不要**为了够到祖先而放宽 `-AllowRoot`；**不要**重复一次被拒或失败的调用。
- **真实调用例**：
  - 场景：本会话里 `pwsh` 写工作区某子目录报"file access denied"（沙箱拒绝），而那是本会话**工作区内**的合法写入 ≡ **意外**拒绝。
  - 模型：load `diagnose-windows-sandbox-acl` → 用一句中文人话请求批准"运行这条 PowerShell 修文件权限" → 沙箱外跑那**一条**命令 → 读 `RECAP` → 若 `nextAction=verify_original_confined_operation`，回到受限模式重试原写入。
  - 产出：修好的 ACL + `acl-report-*.jsonl` + 每个改动的 `acl-backup-<id>.json` / `.ps1` 与 `ROLLBACK` 命令。

---

## 附录 A：本会话 Skill 装载链路（可当架构图讲）

```
                      ┌──────────────────────────────────────────────┐
磁盘扫描根             │ dsh-skill-filesystem (provider, rank 100→600) │
 .dsh/skills           │  读 SKILL.md frontmatter → 候选(name, desc, …) │
 .agents/skills  ────► │  监听目录 → invalidate()                      │
 ~/.dsh/skills         └──────────────┬───────────────────────────────┘
 ~/.agents/skills                     │ ctx.skills.registerProvider()
 内置 office assets                   ▼
 内置 windows-acl assets  ┌────────────────────────────┐
 插件内存注册 ──────────► │ dsh-skill (registry)       │ 合并 / 去重 / 校验 / 缓存目录
                          └───────────┬────────────────┘
                                      │ list() / get()
                                      ▼
                          ┌────────────────────────────────────────┐
                          │ dsh-tool-skill (消费者)                 │
                          │  agent/pre-step: digest 变了 → 追加一条  │
                          │    user-role <available_skills> 消息    │
                          │  注册 skill 工具 → <skill_content>      │
                          │  /name 手势 → 同一段 <skill_content>    │
                          └────────────────────────────────────────┘
```

挂载点（本实例实证）：【A】`dsh-base/cordis.patch.yml:308-315` 挂 `skill` / `skill-filesystem` / `tool-skill`；
【A】`dsh-web-app/cordis.patch.yml:511-515` 把宿主层的 `skill-filesystem` 与 `tool-skill` **关掉**（"presets own local discovery"），
改由每个 preset 自己挂（【A】`dsh-web-app/presets/standard.patch.yml:37-40`）；
注册表 `dsh-skill` 留在宿主层，preset 的 provider 注册进该 preset 的层，agent 读合并后的目录。
（【A】`dsh-web-app/cordis.patch.yml:502-509` 的注释把这条分层设计讲得很清楚。）

## 附录 B：证据文件索引

| 主题 | 证据 |
|---|---|
| 注册表、合并、校验、`renderSkillContent` | 【A】`dsh-skill/README.md`、【A】`dsh-skill/lib/index.js:45-84, 566` |
| 发现、frontmatter、rank 表、watcher | 【A】`dsh-skill-filesystem/README.md`、【A】`dsh-skill-filesystem/lib/index.js:130-200` |
| catalog 模板 / 替换模板 / digest / pre-step | 【A】`dsh-tool-skill/README.md`、【A】`dsh-tool-skill/lib/index.js:930-1014` |
| `/name` 手势正则与扫描范围 | 【A】`dsh-tool-skill/lib/index.js:1094-1122` |
| 工具 schema 与错误 | 【A】`dsh-tool-skill/lib/index.js:789-793, 867` |
| invocation policy 矩阵 | 【A】`dsh-skill/README.md`「What the registry gives you」；【A】`dsh-client-ui-skill/README.md`（user-only 标记） |
| 斜杠菜单与 Instructions 卡片 | 【A】`dsh-client-ui-skill/README.md` |
| Skill Center 面板（opt-in） | `E:\dsh-data\profiles\desktop\node_modules\@linxin666\dsh-client-ui-skill-explorer\README.md`；关闭标记 `…\dsh-web-all\cordis.patch.yml:118-121` |
| Plugins 页 / 只读清单 | 【A】`dsh-client-ui-plugin-manager/README.md`、【A】`dsh-client-ui-settings-plugin-inventory/` |
| plugin 安装/卸载/失败回滚/版本豁免 | 【A】`dsh-plugin-manager/README.md`（「Use this package」「Version compatibility」「Failure behavior」「Known Limitations」） |
| plugin 在宿主进程内、沙箱之外 | 【A】`dsh-plugin-manager/README.md:31` |
| office skill provider 与 assetRoot | 【A】`dsh-skill-office/README.md`、【A】`dsh-skill-office/lib/index.js:101`、【A】`dsh-desktop-host/lib`（第 9、84 行） |
| windows-acl 自带 skill provider | 【A】`dsh-sandbox-windows-acl/lib/types-Cl_DXjhk.js:1138` |
| badge skill（本会话未启用） | 【A】`dsh-skill-badge/README.md` |
| profile 组成 | 【P】`cordis.yml`、【P】`cordis.patch.yml`、【P】`package.json` |

## 附录 C：明确标注「未在源码中找到依据」的点

1. **没有任何"按任务内容自动匹配并加载 skill"的匹配器代码**。catalog 末尾那句自然语言规则
   （【A】`dsh-tool-skill/lib/index.js:978`）是唯一的"语义触发"机制，判断权在模型。
2. **没有找到 `triggers:` frontmatter 键的解析代码**——`dsh-skill-filesystem` README 列出的合法键里没有它
   （【A】`dsh-skill-filesystem/README.md`「Skill format」）。所以 `/grill`、`/spec` 这类"别名"在本实例**不生效**。
3. **`whenToUse` 是否出现在任何模型可见文本里，未在源码中找到依据**：catalog 模板只渲染 name + description
   （【A】`dsh-tool-skill/lib/index.js:966-989`）；它在 Skill Center 的行里展示（第三方 README）。
4. **`ui-ux-pro-max` 的 `scripts/search.py` 在本仓库不存在**（SKILL.md 里写的是 `skills/ui-ux-pro-max/scripts/search.py`
   这种相对路径，像是从另一个项目布局照搬的）；**未找到该脚本文件**，因此"跑设计系统生成"这一步在本仓库大概率不可执行。
5. **`developing-with-streamlit` 的 `scripts/discover.py` 内容未读**（本报告只依据 SKILL.md 说明），
   其行为细节（退出码、输出格式）以 SKILL.md 描述为准。
6. **`dsh-badge` 是否曾在本 profile 启用过**，未在源码/配置中找到痕迹；本会话目录里没有它。
