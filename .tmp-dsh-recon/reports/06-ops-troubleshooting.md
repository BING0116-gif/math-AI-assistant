# 06 · 桌面版"卡住 / 变慢"排查手册

> 环境：DeepSeek Harness 桌面版 0.2.1-rc.1，Electron 外壳在 `F:\DSH`，官方运行时 checkout 在 asar 内 `F:\DSH\resources\app.asar\dsh\`。
> 路径约定：
> - 相对路径（如 `dsh-atomic-write/lib/index.js:125`）都相对 `C:\Users\HUAWEI\Desktop\math AI assistant\.tmp-dsh-recon\asar\@deepseek-ai\`（已解包的官方包源码）。
> - `F:\DSH\resources\app.asar\lib\main.js` 是 Electron 外壳主进程（用 DSH 的 `read` 工具可直接按路径读）。
> - `E:\dsh-data\...` 是本机真实的 DSH_HOME 运行数据；`E:\dsh-data\profiles\desktop\node_modules\...` 是外部插件包源码。
>
> 标注规则：凡写"未在源码中找到依据"的，都是文档与代码里确实查不到、只能由读者实测确认的部分。

---

## 0. 先读懂进程树（后面所有排查都建立在这上面）

桌面版不是"一个大进程"，而是三层：

| 层 | 是什么 | 证据 |
|---|---|---|
| Electron 主进程 | 管窗口、托盘、更新、单实例锁；以 Node 模式（`ELECTRON_RUN_AS_NODE=1`）spawn 一个子进程承载真正的 harness | `F:\DSH\resources\app.asar\lib\main.js:3793-3810`（`spawn(this.node, [...entry, runtimeDir, projectDir, ...], { stdio: ["ignore","pipe","pipe","ipc"] })`） |
| Host 子进程 | `@deepseek-ai/dsh-desktop-host`，加载 `desktop` profile，起 Web 应用，把 URL 经 IPC 交回 Electron | `dsh-desktop-host/lib/index.js:219-250`（`runProfile({ profile: "desktop", args: ["--no-open","--host","127.0.0.1","--port","0"] })`） |
| 被 spawn 的命令 | 每次 `pwsh` / `bash` 调用都是全新子进程；受限模式下还要再包一层沙箱 runner | `dsh-tool-pwsh/lib/index.js:256`；`dsh-pwsh-sandbox/README.zh.md:12,78` |

两条实用推论：

1. Electron 主进程死掉时，Host 会通过 IPC `disconnect` 自杀：`process.once("disconnect", () => { stop() })`（`dsh-desktop-host/lib/index.js:325-327`）。所以正常退出不会留下野 Host；只有被强杀/崩溃才可能留下。
2. 本机实测（只读观测）：`netstat -ano` 显示 `127.0.0.1:29310` 处于 LISTENING，占用者 PID 18012；而 `E:\dsh-data\task-board\ledger-v2.lock` 的内容正是 `{"pid":18012,...}` —— board 锁的持有者就是监听 Web 端口的那个 Host 进程。这是"到底谁在卡"的第一把钥匙。

---

## A. 进程与锁

### A1 单实例机制：第二个实例会发生什么

机制（三段代码就够）：

1. 外壳启动第一件事、在任何 profile 生命周期之前抢进程级单实例锁：`claimDesktopSingleInstance(app, () => { focusPrimaryWindow() })`。抢不到就**直接 `application.quit()`**；抢到则监听 `second-instance` 并接到"聚焦主窗口"。
   证据：`F:\DSH\resources\app.asar\lib\main.js:7658-7665`、`main.js:13184-13186`。
2. `second-instance` 的处理器是 `focusPrimaryWindow`：最小化就 `restore()`，再 `show()` + `focus()`；窗口已销毁则重建；正处在强制更新流程则聚焦强制更新窗口。
   证据：`main.js:13031-13054`。
3. 只有抢到锁的进程才继续 `app.whenReady().then(main)`（`main.js:13185-13186`），因此第二个实例不会加载 profile、不会 spawn 第二个 Host。

用户看到什么：双击第二次启动时新进程静默退出，已开的窗口被唤到前台。源码里没有"已在运行"的对话框或错误文案（未在源码中找到依据）。

为什么这样设计：一个 profile 只能有一个写入者。桌面 profile 目录 `E:\dsh-data\profiles\desktop` 被多处写：Electron 侧的 profile 初始化/恢复用 `E:\dsh-data\profiles\desktop\lock`（内容是持有者 PID，冲突时报 `desktop project: another profile operation is active`，证据 `main.js:3599-3634`）；Host 侧的插件管理与配置编辑也写同一批文件。两个 Host 还会互抢第三方账本锁——本机的任务板就是活例子：`E:\dsh-data\task-board\ledger-v2.lock` 被占用时抛 `task-board ledger is already owned by process <pid>`，并提示"若该 PID 是崩溃后被复用的、且没有别的 DSH host 在跑，可手动删除"（证据：`E:\dsh-data\profiles\desktop\node_modules\@linxin666\dsh-client-ui-task-board\lib\index.js:5119-5179`）。

排查动作：如果"点了图标没反应"，先确认是不是被单实例接管——看 `netstat` 里旧端口是否还在监听、`Get-Process` 里是否已有 DeepSeek Harness；而不是反复点击。

---

### A2 文件锁：`dsh-atomic-write` 的 `withFileLock`

是什么：跨进程"读-改-写"互斥原语，配套原子替换 `writeFileAtomic`。锁是目标文件的**兄弟文件** `<文件名>.lock`，用 `wx`（独占创建）打开，内容一行 `<pid>\n`，持有者在 `finally` 里删除。
证据：`dsh-atomic-write/README.zh.md`（"使用本包"/"理解实现"）；实现见 `dsh-atomic-write/lib/index.js`。

关键判定逻辑（已对过代码）：

| 情形 | 判定 | 证据 |
|---|---|---|
| `EEXIST` | 直接就是竞争 | `dsh-atomic-write/lib/index.js:82` |
| `EPERM` | 只有"再 `lstat` 一次确认锁文件确实存在"才算竞争（兼容 Windows 独占创建的怪脾气） | `lib/index.js:83`、`README.zh.md` |
| Windows 上"确认不了"的 EPERM | 重试一次，再不行就抛出、不执行操作 | `lib/index.js:204` |
| 竞争等待 | 指数退避；上限由每次调用的 `waitMs` 决定，**默认 2000 ms** | `lib/index.js:164,191` |
| 接管（takeover） | 只有"锁里记录的 PID 已不存在（`ESRCH`）"才接管：先建 `<file>.lock.takeover-<记录 sha256 前 16 位>` 认领，再重读锁、二次探测同一条记录，确认仍是同一条记录且 PID 仍不存在，才删锁 | `lib/index.js:125`、`README.zh.md` |
| 不接管 | 空/不完整记录；记录指向仍活着的 PID（含 PID 复用）；持有者是另一用户（`EPERM`）；记录指向自己 | `README.zh.md`（"需要规划的失败"） |

哪些操作会真的拿这把锁（逐个调用点核过）：

| 操作 | 锁住的对象 | 证据 |
|---|---|---|
| 插件安装/更新/卸载（插件管理器整体变更） | 桌面 profile 的 `package.json` | `dsh-plugin-manager/lib/index.js:2374` |
| 配置编辑（cordis 补丁层写入） | 同上 `package.json` | `dsh-config-editor/lib/index.js:72` |
| profile 兼容性豁免表写入 | profile 目录下的兼容性文件 | `dsh-app-boot/lib/index.js:441` |
| 凭据写入（`.credentials.yaml`） | `E:\dsh-data\.credentials.yaml` | `dsh-credentials-local/lib/index.js:556,583,617,668` |
| 模型/附件缓存索引 | DSH_HOME 下的索引文件 | `dsh-llm-deepseek/lib/index.js:857,887,905` |
| **不拿锁**：会话事件写入 | 追加 + fsync，靠"只追加"保证一致性 | `dsh-session-persistence-jsonl/lib/index.js:3295`（"Append and fsync event lines…"） |
| **不拿锁**：`storages/*.json` | 进程内单写者 + 临时文件 + fsync + `rename` | `dsh-storage-json/lib/index.js:10-35` |
| **另一套锁**：任务板账本 | `ledger-v2.lock`（JSON：pid/token/startedAt/probe） | 见 A1 的第三方证据 |

锁残留时用户看到什么：

- 插件安装/配置保存**卡住约 2 秒**后报错（就是 `waitMs` 默认值），不会无限挂。
- 若残留锁的 PID 指向一个还活着的进程（最常见是 PID 复用），自动接管永远不会发生 → 表现为"每次都失败"，必须人工确认后删锁。
- 最坏情况：竞争者在"建认领文件"与"删锁"之间死掉，会同时留下 `<file>.lock` 与 `<file>.lock.takeover-<hash>`，两个都要删。证据：`dsh-atomic-write/README.zh.md`（"已知限制"）。

安全判定与清理（可复制）：

```powershell
# 1) 看锁里写的 PID（锁是兄弟文件：目标是 package.json，锁就是 package.json.lock）
Get-ChildItem E:\dsh-data\profiles\desktop -Filter *.lock -Force | ForEach-Object { $_.FullName; Get-Content $_.FullName }
# 2) 该 PID 还活着吗？（活着=不要删，等它或让它自己结束）
Get-Process -Id 18012 -ErrorAction SilentlyContinue | Select-Object Id,ProcessName,StartTime
# 3) 任务板账本锁（第三方插件，JSON 格式）
Get-Content E:\dsh-data\task-board\ledger-v2.lock
# 4) 确认没有任何 DSH Host 在跑之后，才删残留锁
#    删前务必确认：netstat 里没有属于该 PID 的 127.0.0.1 LISTENING
```

判定顺序很重要：**先证明"没有写者"再删**。源码只保证"PID 不存在"能自动接管；"PID 存在但其实是别人"必须人来判断。

---

### A3 端口与 Web GUI：`127.0.0.1:29310` 是不是固定的？

结论：**不是固定的。** 桌面版 Host 启动时传 `--port 0`：

- `dsh-desktop-host/lib/index.js:234-240`：`args: ["--no-open","--host","127.0.0.1","--port","0"]`
- Web 应用的 webserver 行：`port: !!js ctx.webStartup.port ?? 3080`（`dsh-web-app/cordis.patch.yml:184`）——命令行给的端口优先，没给才 3080。
- `port: 0` 的含义：`dsh-host-webserver/README.zh.md` 写明"`port` 为 0 时请求 OS 分配端口；之后用 `ctx.webServer.port` 读取正在监听的端口"。
- Host 起来后把真实 URL 交回 Electron：`ctx.connection.authenticatedUrl(...)` → IPC `{type:"ready", url}`（`dsh-desktop-host/lib/index.js:342-349`）。

所以 29310 是本次运行操作系统分配的临时端口，换一次启动就可能变。这就是"别在脚本里硬编码 29310"的原因，也是"端口占用"在桌面版基本不成立的原因——除非手工用 `--port` 固定过。

真的 EADDRINUSE 会怎样：不是静默卡住，而是插件初始化被拒绝，诊断里带配置字段与解析后的路径（不含文件内容）。证据：`dsh-host-webserver/README.zh.md`（"失败时的行为"）。

验证命令（本机 Windows，注意在哪跑）：

```powershell
# 能用：netstat 在沙箱里也能跑（本机实测通过）
netstat -ano | Select-String ":29310"
# 拿到 PID 后看是谁（Get-Process 按 PID 可用）
Get-Process -Id 18012 | Select-Object Id,ProcessName,CPU,WorkingSet64,StartTime
# 这台机器上还有哪些 127.0.0.1 的监听（找"到底几个 host"）
netstat -ano | Select-String "LISTENING" | Select-String "127.0.0.1"
```

在 DSH 的沙箱工具里会失败的两个命令（本机实测，务必知悉）：

- `Get-NetTCPConnection` → `拒绝访问`（走 CIM/WMI）。
- `tasklist` → `ERROR: Access denied`。

原因见 B 节：受限令牌的 restricting SID 列表里没有 Authenticated Users，WMI 命名空间安全检查失败，因此 CIM cmdlet 在所有受限模式下都不可用（`dsh-sandbox-windows-acl/README.zh.md`："Authenticated Users 在两种列表中都不存在——WMI 命名空间安全检查失败（0x80041003），因此 CIM cmdlet 与 Get-ComputerInfo 在所有受限模式下都不可用"）。
→ 端口/进程类排查请放在 DSH 之外的普通 PowerShell，或至少用 `netstat`。

---

### A4 定位"到底是哪个进程卡住"

在普通 PowerShell（非 DSH 工具）里按顺序做，全部只读：

```powershell
# 1 谁在占端口（Host 是否还活着）
netstat -ano | Select-String ":29310"

# 2 全部相关进程：名字、CPU 秒数、内存、启动时间
Get-Process | Where-Object { $_.ProcessName -match "DeepSeek|dsh|electron|pwsh|node" } |
  Select-Object Id,ProcessName,@{n='CPU_s';e={[math]::Round($_.CPU,1)}},
                @{n='WS_MB';e={[math]::Round($_.WorkingSet64/1MB)}},StartTime |
  Sort-Object CPU_s -Descending | Format-Table -AutoSize

# 3 命令行 + 父进程（Host 的命令行里能看到 dsh-desktop-host）
Get-CimInstance Win32_Process -Filter "Name='DeepSeek Harness.exe'" |
  Select-Object ProcessId,ParentProcessId,@{n='Cmd';e={$_.CommandLine}} | Format-List

# 4 某个 PID 的父进程链（一路往上找到 Electron 主进程）
$p0 = 18012
while ($p0) {
  $p = Get-CimInstance Win32_Process -Filter "ProcessId=$p0"
  if (-not $p) { break }
  "{0,-6} {1,-24} <- parent {2}" -f $p.ProcessId, $p.Name, $p.ParentProcessId
  $p0 = $p.ParentProcessId
}

# 5 句柄规模（只看总数；本机未随包提供逐句柄工具）
Get-Process -Id 18012 | Select-Object Handles,Threads,WorkingSet64
```

判读要点：

- Host 子进程的命令行里会出现 `--expose-internals ...\@deepseek-ai\dsh-desktop-host\lib\index.js`（对应 `main.js:3793-3804`）。看到它就说明这是 Host，不是 Electron 主进程。
- 正在跑命令的会话会额外出现 `pwsh.exe`/`bash.exe` 以及沙箱 runner 子进程；卡在"命令"上时它们 CPU 往往接近 0、父链指向 Host。
- 逐句柄/逐文件占用查询（`handle.exe`、Restart Manager）未在源码中找到依据，本机也未随包提供；第 5 项只能给句柄总数。

---

## B. 沙箱

### B1 三档在 Windows 上分别怎么实现

统一语义由 `dsh-sandbox-policy` 决定，`dsh-fs-sandbox` 负责"文件写入/编辑"侧，`dsh-sandbox-local` + `dsh-sandbox-windows-acl` 负责"命令/子进程"侧。

| 档位 | 文件写入（`ctx.fs`，`dsh-fs-sandbox`） | 命令/子进程（Windows ACL runner） |
|---|---|---|
| `read-only` | 所有变更抛 `FS_SANDBOX_DENIED` | 受限令牌 restricting SID = 登录 SID + Everyone（不含写 SID），令牌降为 Low 完整性；不授予任何可写根 |
| `workspace-write` | 目标规范化后必须落在会话工作区根或平台临时区之下，否则 `FS_SANDBOX_DENIED` | restricting 列表再加**工作区写 SID**（由规范工作区路径确定性派生）与**每会话私有临时目录 SID**；授权同时写：能力 SID 允许 ACE + 对 world SID 拒绝 `FILE_DELETE_CHILD` + Low 完整性标签 |
| `danger-full-access` | 不加围栏，直接委托 | 不隔离（执行器直接继承） |

证据：`dsh-fs-sandbox/README.zh.md`（"围栏行为"）、`dsh-sandbox-windows-acl/README.zh.md`（"机制"/"模式与令牌列表"）、`dsh-sandbox-local/README.zh.md`（"平台 profile"）。

策略优先级：已批准的显式模式 > 会话日志里最后一条 `sandbox/mode` 事件 > 部署默认值；工作区根来自会话不可变 `cwd`；默认值是 `read-only`（故障安全）。证据：`dsh-sandbox-policy/README.zh.md`（"解析优先级"/"最小配置"）。

在哪里配置：

- 部署默认：`@deepseek-ai/dsh-sandbox-policy` 的 `mode` / `workspaceRoot`。
- 会话级：UI 权限选择器 / 权限预设（`dsh-permission-presets` 的 `presets` 表把"沙箱模式 + 审批策略"捆成一个名字，`/permission` 命令切换）。证据：`dsh-permission-presets/README.zh.md`。
- profile 层覆盖：`E:\dsh-data\profiles\desktop\cordis.patch.yml` 是按 id 定向改 config 的补丁层（文件头自述："id-targeted config overrides, disables, and insert lists"）。

为什么会出现 `File sandbox enforcement is partial on this host.`

这句话不是错误，而是后端对自己隔离强度的诚实交代：Windows ACL 档只能管写入、读不受限；NTFS 硬链接是"文件对象别名"（同一对象可从工作区外别名写入）；被别的 AppContainer 工具用包 SID 标记过的目录树对 Low 完整性子进程不可读。因此 provider 报 `enforcement: 'partial'`，工具层把这条事实渲染成一句提示。

证据：`dsh-sandbox-local/README.zh.md`（"已知限制：Windows ACL 只能实现部分强制执行"）、`dsh-tools/lib/index.js:1240`（`if (value.sandbox?.enforcement === "partial") parts.push("File sandbox enforcement is partial on this host.")`）；同一逻辑也在 PTC 渲染里，见 `dsh-tools/lib/types/ptc.js:284`。

用户看到什么：几乎每次 `run_code` / 受限命令的结果尾部会带这一句——它是恒定提示，不代表这次被拒绝。

---

### B2 被拒绝时该看什么

四个必须区分的信号：

| 信号 | 含义 | 证据 |
|---|---|---|
| `[sandbox: file access denied under <mode> mode]` | **策略性拒绝**：bash 内核拒绝与 fs 围栏拒绝共用这一个模型可见标记，后面还跟一句"本轮可申请更宽权限"的引导 | `dsh-sandbox/lib/index.js:56-74`（`sandboxDenialMarker` + 同轮升级提示）；工具侧渲染 `dsh-tools/lib/index.js:1241` |
| `denied: true`（结构化字段） | 本次调用范围内**确实有操作被拒** | `dsh-tools/lib/index.js:1225-1233`（结果 schema 的 `sandbox.denied`） |
| `enforcement: 'partial'` | 只是"覆盖范围有限"的自述，与是否被拒无关 | 同上 `:1229-1232` |
| runner 失败：`windows-acl-run: <detail>` + 退出码 127 | **沙箱坏了**，命令根本没跑；seam 归类为"损坏的沙箱"而不是"拒绝" | `dsh-sandbox-windows-acl/README.zh.md`（"隔离 runner"/"失败与恢复"） |
| `SANDBOX_UNAVAILABLE` | 平台没有可用 runner：**拒绝执行**，绝不静默无隔离运行 | `dsh-sandbox-local/README.zh.md`（"失败与恢复"） |

处置决策：

- **预期内拒绝**（写工作区之外、`read-only` 下任何写、受限孙进程 `spawn(..., {stdio:'pipe'})` 的 EPERM、ConstrainedLanguage 下 `Add-Type` 失败）→ 不要修 ACL，改路径、改模式，或让会话升权重试。
- **意外拒绝**（工作区内的写/列目录失败；本来能读的路径读不了）→ 用 `diagnose-windows-sandbox-acl` 技能，而不是"直接换 danger-full-access"。该技能：
  - 一条命令同时诊断 + 修复：读取目标路径与每一级祖先，对缺少有效 `WRITE_DAC`/`WRITE_OWNER` 的目录补当前用户完全控制 ACE，并从源头移除显式 AppContainer 包允许 ACE（`S-1-15-2-*`），每处改动都重新读取验证；每处改动前备份 DACL 并打印回滚脚本；
  - **必须不受限执行**（受限运行会把自己的限制误读成"缺权限"），所以要么会话临时切完全权限，要么走一次审批；
  - 不删 deny ACE、不改所有者、不递归替换子项权限；结束时给出 `nextAction`（`verify_original_confined_operation` / `stop` / `restore_pending_then_stop`）。
  证据：`dsh-sandbox-windows-acl/assets/diagnose-windows-sandbox-acl/SKILL.md:10-51`；技能注册条件见 `dsh-sandbox-local/README.zh.md`（"当内置 Windows runner 与技能注册表同时可用时…注册 ACL 诊断技能"）。

---

### B3 沙箱如何让命令变慢

按影响从大到小，每条都有出处：

1. **首次授权是急切的全树传播（几十秒级）**。`workspace-write` 第一次给某工作区做授权时，`SetNamedSecurityInfoW` 的可继承 ACE 会立刻遍历每个后代；README 明说"大型工作区树上以数十秒计"。按"每机器每工作区"只付一次，之后靠"精确 ACE 跳过"变得很便宜；但新工作区/刚克隆的大仓库第一次受限命令看起来就像卡住。证据：`dsh-sandbox-windows-acl/README.zh.md`（"授权物化是急切的全树传播"）。
2. **每条命令一个新进程 + 一层 runner**：`pwsh -Command` 本身是全新进程，`ctx.sandbox.confine()` 再把 argv 包一层 runner（runner 建受限令牌、JOB 对象、spawn 真子进程、镜像退出码）。工具描述原文就是 "Each call runs in a fresh pwsh process"。证据：`dsh-tool-pwsh/lib/index.js:256`、`dsh-pwsh-sandbox/README.zh.md:12,78`、`dsh-sandbox-windows-acl/README.zh.md`（"隔离 runner"）。
3. **首个受限调用的 runner 功能探测**：候选 runner 按链序各探一次，`probeTimeoutMs` 默认 5000 ms；结论在 provider 生命周期内缓存。所以"刚启动后第一条受限命令慢"是预期。证据：`dsh-sandbox-local/README.zh.md`（"runner 选择"、"最小配置"表）。
4. **ACL + 完整性检查是内核双检**：写类访问要过两次访问检查（正常 SID + restricting SID），再加 Low 完整性标签的强制检查。写/删因此比普通进程贵。证据：`dsh-sandbox-windows-acl/README.zh.md`（"机制"）。
5. **`read-only` 下 PowerShell 退化为 ConstrainedLanguage**：它在临时目录造不出 AppLocker 探针文件，于是保守启动 ConstrainedLanguage（`Add-Type`、非核心 .NET 静态调用、COM、反射全失败）；`workspace-write` 交付路径通常保持 FullLanguage（除非宿主有 WDAC/AppLocker 策略）。证据：`dsh-sandbox-windows-acl/README.zh.md`（"PowerShell 语言模式因受限模式而异"）。
6. **管道相关限制**：受限**孙**进程用 `stdio:'pipe'` 会 `EPERM`（libuv 命名管道默认 SD 不带 restricting SID），inherit/ignore 可用；PowerShell 自己的管道是匿名管道，不受影响。证据：`dsh-sandbox-windows-acl/README.zh.md`（"受限孙进程的管道 stdio 捕获不可用"）。
7. **临时目录被重定向**：runner 在 spawn 前把 `TMP`/`TEMP` 改到每会话私有目录，缓存/临时产物不会命中，第一次跑要重建。证据：`dsh-sandbox-windows-acl/README.zh.md`（"隔离 runner"）。
8. **受限令牌下部分诊断命令本身就失败**（本机实测 `tasklist` 拒绝访问、`Get-NetTCPConnection` 拒绝访问；文档同样说明 `whoami`/令牌检查 cmdlet 可能失败）。这是诊断噪音，不是运行故障。证据：`dsh-sandbox-windows-acl/README.zh.md`（"已知限制"）。

---

## C. 人工确认等待（最容易"看起来卡住"的原因）

### C1 策略语义与配置位置

`dsh-user-approval` 只定义两种会话策略：

| 策略 | 语义 | 用户看到什么 |
|---|---|---|
| `ask`（默认） | 把每个需要审批的请求交给"应答者"（`approval/request` waterfall 监听器）；**没有应答者就解析为 `unavailable` 并以拒绝方式关闭**（fail closed），服务本身永远不会自己弹窗 | UI 弹出审批面板，等你点 |
| `never` | 在分发之前**确定性拒绝**每个请求（后来用 `prepend` 注册的监听器也绕不过） | 模型立刻收到"审批提示已禁用…"的拒绝，不弹窗 |

证据：`dsh-user-approval/README.zh.md`（"设置策略"/"分发"）；模型可见文本里 `never` 的原话是 "Approval prompts are disabled in this session: actions that require approval are rejected automatically"。

只有一次性授权：结果词汇里只有 `allowed-once`/拒绝/取消/不可用，**没有** allow-always、记住规则、撤销或授权库。证据：`dsh-user-approval/README.zh.md`（"已知限制"）。

配置在哪里：

| 位置 | 能改什么 | 证据 |
|---|---|---|
| 插件 config `policy: ask \| never` | 无会话级覆盖时的默认策略 | 同上 |
| 权限预设表（`dsh-permission-presets` 的 `presets`） | 把"沙箱模式 + 审批策略"捆成具名档；`defaultPreset` 决定**未来会话**的默认 | `dsh-permission-presets/README.zh.md` |
| 会话级切换（UI 权限选择器 / `/permission` 命令） | 仅当前会话；写入 `permission/preset` 事件，跨重启回放 | 同上 |
| profile 补丁层 `E:\dsh-data\profiles\desktop\cordis.patch.yml` | **可以**按 id 定向覆盖某插件行的 config（文件头自述是 id-targeted config overrides） | `E:\dsh-data\profiles\desktop\cordis.patch.yml:1-4` |

"自动批准"是什么：不是审批策略的第三档，而是另一层实验插件 `@deepseek-ai/dsh-experimental-auto-review`（本机 profile 的 bundles 里确实装了它，见 `E:\dsh-data\profiles\desktop\package.json`）。它在**每次工具调用前**用当前 agent 的模型审查待执行动作：获准的调用以 Full access 执行，**被拒绝的才转成请求你审批**；在权限选择器里以带 `EXP` 标记的「自动审查」出现，`/permission auto` 可直接切；通用设置里不提供，且只对当前会话生效。证据：`dsh-experimental-auto-review/README.zh.md`（概述 + "安装到 profile"）。

---

### C2 一次调用需要审批时，UI 长什么样

- 审批面板由浏览器侧插件渲染，**接管 Conversation 的 composer**，可按需展示关联工具详情；按钮文案就是 `Allow once` / `Reject`。证据：`dsh-client-ui-approval/README.zh.md`（"概述"）、`dsh-client-ui-approval/lib/client.js:269-270`。
- 键盘：聚焦审批详情区时 **Enter 批准、Esc 拒绝**；焦点在"拒绝"按钮上时 Enter 走按钮原生拒绝。证据：`dsh-client-ui-approval/README.zh.md`。
- **Trajectory 里**：请求在"等待输出/流式生成/重试"期间保持等待状态；进行中的记录只显示开始标记，**不会虚构耗时**；被判为中断的输出仍可检查，请求与助手记录都显示失败。证据：`dsh-client-ui-trajectory/README.zh.md`（"检查记录"与"已知限制：进行中时 Time 保持空白"）。
- **没有任何 answerer 时**：请求解析为 `unavailable` → 消费方按"拒绝"关闭（fail closed），模型收到工具失败而不是挂起。审计上先写 `approval/asked`，再写 `approval/decided`（两者都只进会话日志，模型看不到）。证据：`dsh-user-approval/README.zh.md`（"分发"/"审计"/"已知限制：没有内置应答者"）。

---

### C3 判据："它在等我"还是"它挂了"

按证据强度从高到低，四条判据：

1. **composer 状态**：审批是"接管 composer"的。屏幕上有 Allow once / Reject 面板 = 在等你；composer 正常可输入、没有面板 = 不是审批等待。（`dsh-client-ui-approval/README.zh.md`）
2. **会话日志里的开合对**：有 `approval/asked`、没有 `approval/decided` = 存在一个**未结算**的审批请求。会话日志在 `E:\dsh-data\sessions\<编码后的cwd>\<session-id>\session.v4.jsonl.zstd`（本机实测文件名就是 `session.v4.jsonl.zstd`，zstd 压缩，需解压后再 grep）。
3. **Trajectory 记录状态**：记录停在"进行中"且只有开始标记、没有耗时；请求行处于"等待输出/流式/重试"。若时间条已出现且不再增长，通常说明这一步已结束、卡在别处。（`dsh-client-ui-trajectory/README.zh.md`）
4. **退出时的"是否还有活"判定**：外壳关机前会问 Host"有没有还在干活的"——判定条件含"正在生成/正在跑工具的 agent（包括子 agent 与**等待审批的轮次**）、排队的 inbox 消息、running/stopping 的后台任务"，且有 2 秒上限（超时按"未知=可能还有活"处理，于是弹确认）。证据：`dsh-desktop-host/lib/index.js:93-102`（`hasDesktopActiveTasks` 注释明确列出 waiting-for-approval）、`F:\DSH\resources\app.asar\lib\main.js:3662-3663`（`QUIT_INSPECTION_DEADLINE_MS = 2e3`）。

反面判据（帮你排除）：如果现象是"秒级失败并出现 `denied`/拒绝文案"，那是 `never` 策略或策略拒绝，不是等待；如果是"命令不返回、CPU≈0、父链指向 Host 且没有审批面板"，看 D 表"卡在工具"那一行。

---

## D. 任务推进缓慢的系统性排查决策表

顺序原则：先看"它是否在等外部输入"（审批/沙箱/权限），再看"是否在网络里重试"，再看"是否在做长活"，最后才怀疑锁与磁盘。前三类占绝大多数，且多数不需要重启。

| # | 卡在哪 | 现象 | 验证（命令 / UI 位置） | 处置 |
|---|---|---|---|---|
| 1 | **模型网络/限流/重试**（`dsh-llm-retry`） | 长时间等待、没有新工具调用；请求状态停在"等待/流式/重试" | 会话日志里找 `llm/retry`（计划一次重试）与 `llm/retry-started`（重试开始）；Trajectory 请求行三态 | normal 模式：`EMPTY_RESPONSE/RATE_LIMIT/SERVER/TIMEOUT/TRANSPORT` 最多 5 次，退避 500 ms→10 s、10% 抖动；always 模式**无上限**直到成功/取消；提供方 `Retry-After` 会覆盖本地退避。止血：取消该轮，或把该 provider 的 `retryPolicy.mode` 改回 normal。证据：`dsh-llm-retry/README.zh.md` |
| 2 | **工具超时策略** | 某工具调用永不返回，UI 上就是"正在运行" | 看该工具是否声明 `timeoutMs`：`web_fetch`/`web_search` 默认 30 000 ms；**`bash`/`read`/`write`/`edit` 有意不声明** | 超时是协作式的：到点只 `abort` 派生信号，工具不理就继续等，模型也拿不到超时结果。长命令请改后台作业（见 #3）。证据：`dsh-tool-call-timeout-policy/README.zh.md` |
| 3 | **长时间命令 / 前台阻塞** | 前台 `pwsh`/`bash` 跑很久，占住一个工具槽 | `job_list`；看 `pwsh.exe` 子进程 CPU（A4） | 改用后台作业（`dsh-jobs`：id 形如 `<kind>-<short-uuid>`，只有属主 agent 能读/杀；进程内注册表随 Host 结束消失），用 `job_output(wait)` 收集、`job_kill` 取消。证据：`dsh-jobs/README.zh.md:12,32,53,57,89` |
| 4 | **压缩（compaction）** | 上下文很长后突然停顿几十秒，之后历史"变短了" | Trajectory 里的压缩记录（`Between turns` 区段或轮次内编号压缩）；日志里的 `compaction/*` 事件 | 三条触发路径：token 压力自动（`pressure`）、上下文溢出（`context-overflow`）、`/compact` 按需。压缩要一次模型摘要，慢是正常的；不要在压缩进行中再发消息。证据：`dsh-compaction/README.zh.md:36,78` |
| 5 | **审批等待** | 见 C3：有面板、日志里 `approval/asked` 无对应 `decided` | composer 面板 / 会话日志 | Enter 批准、Esc 拒绝；或临时调整该会话权限预设。注意 `never` 下是秒拒而不是等待 |
| 6 | **沙箱** | 首次受限命令奇慢；命令 `windows-acl-run: …` 退出 127；或 `SANDBOX_UNAVAILABLE` | 结果里的 `sandbox.mode/denied/enforcement`；`enforcement: partial` 是恒定提示不是故障 | 首跑慢 → 等工作区授权传播完成；runner 失败 → 不要换模式，按 B2 判断是否需要 ACL 诊断技能；预期外拒绝 → 诊断技能 |
| 7 | **锁** | 插件安装/配置保存在约 2 s 后失败；任务板报 `already owned by process <pid>` | A2 的 `Get-ChildItem *.lock` + `Get-Process -Id` | 先证活/死，再删残留锁（含 `.lock.takeover-*`） |
| 8 | **磁盘/日志膨胀** | 启动变慢、会话列表/看板变笨、磁盘被吃 | `E:\dsh-data` 各目录大小（见 E 节） | 见 E 节清单。注意：未在源码中找到自动清理 `.plugin-manager/logs/operation-*`、历史会话 zstd、`change-ledger/v1/git-cache.json` 的依据，清理属人工操作，删前备份 |

附：一个不属于"卡住"的高频误判——`edit` 报 `cannot modify "<path>": file has not been read — read the file, then retry`（或 `FS_STALE_VERSION`）。这是 `dsh-fs-observation-policy`：编辑前必须先读，读后文件变了要重读；**会话恢复后观察状态不保留**，所以恢复的会话必须重新读文件。证据：`dsh-fs-observation-policy/README.zh.md`（"对模型而言的变化"/"已知限制"）。

---

## E. 日志与现场取证：每个目录装什么

本机实测（只读 `ls`，未改动任何文件）：

| 路径 | 内容与用途 | 实测/证据 |
|---|---|---|
| `E:\dsh-data\logs` | DSH_HOME 顶层日志目录 | 本机当前为空目录 |
| `E:\dsh-data\profiles\desktop\.plugin-manager\logs\operation-<随机>\pnpm.log` | **每次插件包操作一个目录**，内容是该次 pnpm 运行的完整日志与诊断；目录名来自 `mkdtemp(join(logRoot,'operation-'))` | 本机有 8 个 `operation-*`（2026-10-16）；证据 `dsh-plugin-manager/lib/types/operations.js:305-316` |
| `E:\dsh-data\profiles\desktop\.plugin-manager\run.json` | 上一次包操作启动的 pnpm 进程记录（`{pid,grouped}`）。进程死了但 pnpm 树还在跑时，后续操作据此拒绝并提示"等它或停它，否则删这个文件" | 证据 `dsh-plugin-manager/lib/types/operations.js:207-251`；本机当前不存在（说明没有半途操作） |
| `E:\dsh-data\profiles\desktop\lock` | Electron 侧的 profile 变更互斥锁（内容是 PID），仅在一次 profile 变更期间存在 | 证据 `F:\DSH\resources\app.asar\lib\main.js:3599-3634`；本机当前不存在 |
| `E:\dsh-data\sessions\--<编码后的cwd>--\<session-id>\session.v4.jsonl.zstd` | **会话事件日志本体**（zstd 压缩 JSONL）：轮次/步骤/工具调用/审批 asked+decided/`sandbox/mode` 切换/`llm/retry`/压缩。一切审计的最终真源 | 本机实测：`sessions\--C-Users-HUAWEI-Desktop-math~0020AI~0020assistant--\49b65ad8-...\session.v4.jsonl.zstd`（316 KB）；格式版本见包名 `dsh-session-format-v3-to-v4` |
| `E:\dsh-data\dsh-session-archive\state.json` | 会话归档状态（很小） | 本机 48 B |
| `E:\dsh-data\task-board\ledger-v2.json` / `ledger-v2.lock` / `scheduler-v2.json` | 任务板账本、其跨进程所有权锁、调度器心跳 | 本机三件俱全；证据 `@linxin666/dsh-client-ui-task-board/lib/index.js:3988-3998,5119-5179` |
| `E:\dsh-data\storages\workspace.json` | 工作区注册表 | 本机 1.4 KB 量级 |
| `E:\dsh-data\storages\session_projcache\sessions\...` | 会话投影缓存（客户端读模型）。删了不丢数据，只是重建变慢 | 目录名 `session_projcache`；写入协议 `dsh-storage-json/lib/index.js:10-35` |
| `E:\dsh-data\change-ledger\v1\` | 工作区变更账本：`workspaces`/`worktrees`/`transactions`/`turn-outcomes`/`store-id`，以及 `git-cache.json`（本机 422 863 B，是这批文件里最大的） | 本机实测 |
| `E:\dsh-data\dsh-usage\usage-ledger.json` + `provider-snapshots.json` | 用量账本与提供方快照 | 本机 587 B / 1 819 B |
| `E:\dsh-data\dsh-runtimes\dsh-primary-runtime` | 桌面版捆绑运行时（Office/LibreOffice 等）安装根 | 证据 `dsh-desktop-host/lib/index.js:331-335`（`join(resolveDshHome(),"dsh-runtimes","dsh-primary-runtime")`） |
| `C:\Users\HUAWEI\AppData\Roaming\@deepseek-ai\dsh-desktop\` | Electron 的 userData：`Cache/`、`GPUCache/`、`Local Storage/`、`Partitions/`、`logs/`（崩溃报告目录） | 本机实测；`logs` 当前为空（无崩溃报告） |

取证顺序建议：1 `.plugin-manager\logs\operation-*\pnpm.log`（装插件出问题时）→ 2 会话 `session.v4.jsonl.zstd`（审批/重试/压缩/沙箱切换都在里面）→ 3 `task-board\*.lock` 与 `profiles\desktop\lock`（怀疑锁）→ 4 Electron `logs`（崩溃）。

---

## F. 常用快捷操作

### F1 重启整个 harness

桌面版（唯一被支持的方式）：正常退出应用再启动。

- 退出会走"退出检查"：还有活儿（含**等待审批的轮次**、排队消息、running/stopping 后台任务）或有已武装的定时提醒时会先问你；Host 2 秒内没答就算"未知"，也会问。证据：`dsh-desktop-host/lib/index.js:160-182`、`main.js:3662-3663`。
- 退出路径是有序停机：`stop()` → `shutdown(0)` → IPC 回 `shutdown-complete` → `disconnect`（`dsh-desktop-host/lib/index.js:263-267`、`325-327`）。
- **不要**直接用任务管理器杀 Electron 主进程：Host 会靠 `disconnect` 自杀，但若它卡在同步工作里，可能留下 `ledger-v2.lock` 与孤儿 `pwsh`。真发生了按 A2/A3 的方法验证后再清理。

CLI 版（`dsh` 启动器；注意 `desktop` profile 被显式拒绝，由 Electron 独占）：

```powershell
dsh web                                   # 起 web profile（等价 dsh --profile web）
dsh --profile <name> --patch .\extra.yml  # 起任意 profile 并叠一层补丁
dsh tui --resume <session>                # 启动器只吃自己的开关，后面的参数原样给 app
dsh headless "run the tests"              # 一次性任务，打印结果后退出
dsh rescue --from-default-profile web     # 用随包模板重建 rescue 再启动（profile 坏了时的救命命令）
dsh plugin --profile tui add <package>    # 装插件（转发给 pnpm）
dsh web --help                            # 看 web app 自己的开关
```

证据：`dsh/lib/bin.js:36-49`（HELP_EXAMPLES 原文）与 `dsh/lib/bin.js:35-36`（`profile "desktop" is managed exclusively by the Electron application`）。

### F2 只重启一个插件

- 首选：设置 → 插件页里开关/切换那一条。插件管理器会在可能时热重载（`reload(...)`）；装包变更的路径是"没有 HMR 就先发布运行时解析，再 reload"。证据：`dsh-plugin-manager/lib/index.js:2347-2360`、`:1936,1952`。
- 有些改动必须重启整个 DSH，UI 会明确告诉你原因（原话"请重启 DSH 使更改生效。{reason}"），五种 reason 都写在客户端 locale 里：1 这个 profile 只在启动时应用更改（no HMR）；2 装好的包解析到了另一个目录，或改动替换了 DSH 自带包；3 改动涉及 DSH 自身已加载的模块；4 改动涉及插件列表之外的插件；5 DSH 无法把已加载插件与磁盘文件做比较。证据：`dsh-client-ui-plugin-manager/lib/client.js:94-99`（中文）/ `:318-323`（英文）。
- 注意：`sandbox-local` 的 runner 选择在 provider 生命周期内缓存，装/修 runner 后必须重载插件才换选择。证据：`dsh-sandbox-local/README.zh.md`（"已知限制"）。

### F3 优雅中断一个"跑飞"的会话

源码里能确认的四条杠杆（按止损强度排序）：

| 场景 | 动作 | 结果 | 证据 |
|---|---|---|---|
| 后台作业（`bash`/`pwsh` 的 background 模式等） | `job_kill(job_id)` | 先调用生产方取消、再改状态并记录原因；属主之外看不到也停不了 | `dsh-jobs/README.zh.md:12,89` |
| 子代理跑到飞 | 对子代理发中断（`interrupt_agent`） | "请求它停下当前工作"，其会话之后仍可用 `send_message` 唤醒 | 本会话工具面 `interrupt_agent` 的语义；包 `dsh-tool-subagent-control` 存在 |
| 工具自己声明的超时（如 `web_fetch`/`web_search`） | 等 `TOOL_TIMEOUT` | 只在工具配合取消时才产生结果，否则仍等 | `dsh-tool-call-timeout-policy/README.zh.md` |
| 审批卡住 | 面板上 Esc（拒绝） | 请求以拒绝结算，轮次继续 | `dsh-client-ui-approval/README.zh.md` |

重要边界：轮次结束原因里确实有 `aborted` 与 `interrupted`（`dsh-agent-loop/lib/index.js:1010-1026`、`dsh-agent/lib/index.js:62-68`），但**"Web/桌面 UI 上有一个取消当前轮次的按钮/快捷键"未在源码中找到依据**（搜过 `cancelTurn`/`stopTurn`/`cancelSession` 等命名，无命中）。所以真正跑飞时稳妥做法是：

1. 按 A4 找到那个前台子进程（`pwsh.exe`/`bash.exe`，父链指向 Host），在 DSH 之外结束它；
2. 这样结束后，该工具调用在下一次回放里会被补成错误结果，文案是 `Its outcome is unknown.`，只允许重试只读/幂等操作；可能有副作用时须先核验外部状态。证据：`dsh-agent-loop/README.zh.md:184,198`。
3. 更彻底：按 F1 正常退出并重启（单实例锁与账本锁都随进程释放）。

---

## 附：一页速查

```text
1. 它是不是在等我？  -> 屏幕上有没有 Allow once / Reject 面板；会话日志里 approval/asked 有没有对应的 decided
2. 是不是在重试？    -> 会话日志里 llm/retry + llm/retry-started；normal 上限 5 次，always 无上限
3. 是不是长命令？    -> 有没有 pwsh/bash 子进程；改用后台作业 + job_output / job_kill
4. 是不是刚压缩？    -> Trajectory 里的压缩记录；等它写完
5. 是不是沙箱慢/坏？ -> 首跑慢=工作区授权传播；windows-acl-run…127=runner 失败/SANDBOX_UNAVAILABLE，别换模式先诊断
6. 是不是锁？        -> profiles\desktop\*.lock、task-board\ledger-v2.lock；先证 PID 死活再删
7. 还不行            -> 正常退出重启（桌面版退出会先问你有没有活儿没干完）
```

本报告未覆盖/未查证（如实标注）：

- 桌面版是否提供"取消当前轮次"的 UI 控件：未在源码中找到依据。
- `E:\dsh-data\logs` 顶层日志的写入者与格式：本机为空目录，未能取证。
- 各类日志/缓存是否有自动清理策略：未在源码中找到依据。
