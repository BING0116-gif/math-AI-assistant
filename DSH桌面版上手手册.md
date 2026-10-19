# DeepSeek Harness 桌面版 · 上手手册

> 一页纸版本。想深挖看同目录的 `DSH桌面版完全指南.md`。本机版本 0.2.1-rc.1。

## 1. 三分钟上手

1. 打开 DeepSeek Harness（F:\DSH\DeepSeek Harness.exe）。**它只允许一个实例**：再点一次不会开第二个，而是把已有窗口叫到前台——没有任何提示，别以为没反应。
2. 左侧选或新建一个**工作区（Workspace）**：它就是这次会话能读写哪个目录。
3. 新建会话时先确认两件事，不然会莫名其妙「它看不到文件/它乱改文件」：
   - **智能体预设**（标准 / 创造 / 极简 / PTC）—— 决定它能用哪些工具。
   - **权限**（只读 / 工作区可写 / 完全放开）—— 决定它能改到哪。
4. 直接在输入框说人话就行。要它先想清楚再动手，就 `/plan` 或明说「先出方案别改文件」。

## 2. 界面速览：只有三栏，别找菜单树

| 位置 | 是什么 | 关键点 |
|---|---|---|
| 左栏 | 工作区 + 会话列表 | 会话绑定目录；归档只是从列表里过滤掉，数据还在 |
| 中栏 | 会话本体（**视图环**：Chat ⇄ Trajectory） | 右上角切换聊天视图与轨迹视图 |
| 右栏 | dock 标签：文件 / 终端 / 浏览器 / 文档预览 / 待办 / 作业 / 目标…… | 面板都是插件注册进来的，插件关掉面板就没了 |

**Trajectory（轨迹）是排查神器**：一步一条，能看到模型想了什么、调了哪个工具、参数是什么、返回什么、耗时多少。出问题第一件事就是切过去看它卡在哪一步。

## 3. 常用指令（真的能用的斜杠命令）

| 命令 | 作用 | 什么时候用 |
|---|---|---|
| `/plan` | 进入计划模式：只调研、不改文件，等你批准 | 动大手术前 |
| `/goal <目标>` | 设定一个跨多轮持续推进的目标 | 「帮我把全仓库测试修绿」 |
| `/compact` | 手动压缩上下文 | 会话很长、开始变慢或忘事 |
| `/permission` | 调整本次会话的权限档 | 要它改文件了 |
| `/model` | 切换模型 | 简单活换便宜模型 |
| `/file` | 把文件挂进对话 | 让它读某个具体文件 |
| `/export` | 导出会话（含子会话与附件，ZIP） | 存档、交接 |
| `/feedback` | 对这条回复给反馈 | 质量回传（会触发日志上传） |

**没有斜杠但等价的口语指令**（直接说就行）：

- 「切到只读模式」→ 权限降到 read-only。
- 「先给我一个计划，我批准后再动手」→ 计划模式。
- 「这一步别问了，直接做完再汇报」→ 减少 ask_user 打断。
- 「把结果写进 xxx.md」→ 产出物落盘。

> 注意：**别的 Skill 里写的 `/grill` 之类前缀不生效**。DSH 只认「`/` + 技能名」这一种手势（例如 `/grill-master`），技能 frontmatter 里的 `triggers:` 字段不会被解析。

## 4. 权限三档：选哪个

| 档位 | 能做 | 审批 | 什么时候用 |
|---|---|---|---|
| **只读 read-only** | 读文件、跑只读命令 | 需要时问你（ask） | 让它审代码、查资料 |
| **工作区可写 workspace-write**（默认） | 读写**当前工作区**内的文件 | ask | 日常干活 |
| **完全放开 danger-full-access** | 任意路径 | **never（不问了）** | 只在明确要动工作区外的东西时，用完切回来 |

被拒绝时的正确反应：先看提示是 `[sandbox: file access denied under <mode> mode]`（策略拒绝）还是别的；**「File sandbox enforcement is partial on this host」是常态提示，不是错误**，别为此去放开权限。

## 5. 模式怎么选（Agent preset）

| 模式 | 一句话 | 场景 |
|---|---|---|
| **标准 Standard** | 工具齐全的老实编码 Agent | 日常默认（建议手动切回这个） |
| **创造 Creator** | 标准 + 现场读改装配 + 4 个装配技能 + 插件管理工具 | 做插件、改预设 |
| **极简 Minimal** | 只给持久 shell + 看图 + 压缩，**不能读写文件** | 纯命令行探索 |
| **PTC** | 标准 + 呈现层工具 | 需要结构化产物 |

⚠️ **本机默认是 Creator（`cordis`），不是 Standard。** 想改：设置 → 通用 → 智能体预设。改默认只影响**新会话**。

## 6. 装插件 / 加技能

### 装插件（bundle）

1. 侧栏 **Plugins** 页 → 搜索/安装 → 它会跑 `pnpm add`，进度实时可见。
2. 失败会自动回滚 `package.json` 和 `pnpm-lock.yaml`，**环境不会被搞坏**，放心重试。
3. 提示 pnpm 拦了 build 脚本 → 点 **「Allow these scripts and retry」**。
4. 装完没出现？多半是这个包**没有 `dsh.bundle.patch`**（只是普通依赖，不是插件 bundle）。
5. 改了配置要生效：开 HMR 就即时生效，否则**重启**。

### 加技能（Skill）

1. 在 `你项目\.agents\skills\<名字>\SKILL.md` 建文件（用户级放 `C:\Users\HUAWEI\.agents\skills\`）。
2. frontmatter 只认这几个键：`name` / `description` / `whenToUse` / `metadata` / `disable-model-invocation` / `user-invocable`。写错类型会被**整条丢弃**。
3. **只扫一层深**：`<root>/<name>/SKILL.md` 或 `<root>/<name>.md`，嵌套更深不会被发现。
4. 调用：输入框打 `/` 会出菜单，或直接 `/技能名`；也可以让模型自己判断（它只看得到名字 + 一句截断到 500 字的描述）。

## 7. 踩坑清单（现象 → 原因 → 处置）

| # | 现象 | 原因 | 处置 |
|---|---|---|---|
| 1 | 找不到 Trajectory 轨迹面板 | 设置 → 通用 → 「显示代码工作视图」被关了 | 打开它（顺带会放出 PTC / 极简两个预设） |
| 2 | 找不到「极简 / PTC」模式 | 同上，同一个开关 | 同上 |
| 3 | 新建会话默认是「创造」模式 | `selectedDefault: cordis` 优先于 `default: standard` | 设置 → 通用 → 智能体预设改回 Standard |
| 4 | 老会话里少了新装插件的工具 | 预设只对**新建会话**生效 | 开个新会话 |
| 5 | 第二次双击图标「没反应」 | 单实例锁：抢不到就直接 `app.quit()`，静默退出 | 去任务栏找已存在的窗口 |
| 6 | 改了 `cordis.patch.yml` 没变化 | 未开 HMR，装配只在启动时读一次 | 重启 harness |
| 7 | 插件开关点不动 / 灰的 | 那是 **agent-preset 的 row**，插件页对它只读 | 改预设（Creator 模式）或改 preset 的 patch 文件 |
| 8 | 自己写的技能不被发现 | 放错目录（`.claude\skills` **不是** DSH 扫描根） | 移到 `项目\.agents\skills\` |
| 9 | `/grill` 没反应 | `triggers:` 字段不被解析 | 用 `/grill-master` 全名 |
| 10 | 图片读不了（`modlens_read_image` 报 Cannot find module） | 本机 modlens 是 git 源码包装的，`dist/` 没构建，且没配视觉引擎 | 重装构建版或直接用支持视觉的模型 |
| 11 | `weknora_*` 工具调不通（fetch failed） | 后端 `localhost:8080` 不存在、也没有 `WEKNORA_*` 环境变量 | 起服务或卸载该插件 |
| 12 | 看起来「卡住」不动了 | 90% 是在**等你审批**：当前档位下这次工具调用需要确认 | 看中栏输入框/审批条；切 Trajectory 看是否有 pending 标记 |
| 13 | 命令跑得特别慢 | 每命令起新进程 + 沙箱 runner；首次授权要全树传播（可达数十秒） | 预期内；批量操作用一条命令合并 |
| 14 | 沙箱里 `Get-NetTCPConnection` / `tasklist` 报拒绝访问 | 受限令牌下 WMI/CIM 不可用，属设计行为 | 换成 `netstat -ano`，或到**普通 PowerShell** 里查 |
| 15 | 提示账号/模型不对 | 默认模型行在 `cordis.patch.yml` 的 `agent-default-model` | 设置 → 模型 覆盖，别手改 YAML |
| 16 | 会话越跑越慢、越来越忘事 | 上下文到阈值开始压缩，工具结果超 8192 字符会被裁剪 | `/compact`；或新开会话 |

## 8. 五步故障排查（按顺序，别跳）

1. **它是不是在等你？** 看输入框是否被审批条接管、Trajectory 里最后一次工具调用是否停在开始标记。
2. **模型层是不是在重试？** 网络/限流会有重试记录；切 Trajectory 看 request 步骤耗时。
3. **是不是有个长命令在跑？** 右栏「作业 Jobs」看后台任务。
4. **是不是锁住了？** 看三个锁文件有没有残留：`profiles\desktop\package.json.lock`、`profiles\desktop\lock`、`E:\dsh-data\task-board\ledger-v2.lock`（内容是 PID）。**PID 还活着就别删。**
5. **进程还在吗？** 普通 PowerShell 里 `netstat -ano | findstr LISTENING` 找 Host；再 `Get-Process -Id <PID>` 看 CPU。

> 详细版（含每条命令、每个日志目录含义）看完全指南第 7 章。

## 9. 路径备忘（本机专用）

```
程序            F:\DSH\DeepSeek Harness.exe
官方源码        F:\DSH\resources\app.asar\dsh\node_modules\@deepseek-ai\<包名>\   (asar 归档，见指南 5.2)
数据根          E:\dsh-data\
你的 profile    E:\dsh-data\profiles\desktop\
你的覆盖层      E:\dsh-data\profiles\desktop\cordis.patch.yml      ← 唯一该手改的配置
bundle 清单     E:\dsh-data\profiles\desktop\package.json          → dsh.profile.bundles
第三方插件      E:\dsh-data\profiles\desktop\node_modules\<包名>\   ← 可直接用编辑器打开
插件操作日志    E:\dsh-data\profiles\desktop\.plugin-manager\logs\operation-*\
会话数据        E:\dsh-data\sessions\--<目录名>--\<会话id>\session.v*.jsonl
会话归档        E:\dsh-data\dsh-session-archive\
项目技能        <你的项目>\.agents\skills\
用户技能        C:\Users\HUAWEI\.agents\skills\
```

## 10. 三条心法

1. **权限、预设、工作区，是三个独立旋钮。** 「它改了我的文件」通常是工作区选错或权限给高；「它不会用某工具」通常是预设里没这个工具。
2. **插件给能力，技能给方法，预设给组合。** 想让它「换个做法」→ 加技能；想让它「多一种能力」→ 装插件；想让它「这次只带这几样」→ 换预设。
3. **看不懂就切 Trajectory。** 它是唯一能告诉你「刚才到底发生了什么」的地方。
