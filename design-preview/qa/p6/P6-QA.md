# P6 全量 QA 记录

日期：2026-09-30

## 范围与验收清单

| 学生可见范围 | 功能与视觉验证 | 证据 |
| --- | --- | --- |
| 首页与聊天 | 首页在 Vite 运行环境成功加载；Composer 在 AI 能力不可用时禁用并展示结构化降级提示。 | 本次浏览器运行检查；`qa/p23` 与 `screenshots/00-home.png`、`02-chat-dark.png` |
| Dashboard / 错题本 / 画像 | 亮暗两态与 375px 截图已在此前阶段留档，统计卡、图表和错题空态具备对应视觉证据。 | `qa/p23`、`qa/p24`、`screenshots/01-dashboard.png`、`03-error-book.png`、`04-profile.png` |
| 知识目录与学习 | 目录、学习资源、图谱及亮暗移动端截图已留档。 | `qa/p26`、`qa/p3` |
| 学以致用 | 练习、考试、智能组卷的配置、作答、交卷总览、结果/报告均已可见回归。 | `qa/p4/P4-QA.md` 与同目录截图 |
| 登录与基础件 | LoginDialog、BaseDialog、BaseButton、EmptyState、StatusBadge 覆盖在现有 Vitest 中。 | 126 项 Vitest 通过 |
| 管理端 | Admin Review、Papers、Readiness 已完成令牌化，生产构建包含对应路由分包。 | 生产构建产物 |

## 命令与结果

- `npx vitest run --maxWorkers=1 --minWorkers=1`：34 个测试文件、126 个测试通过。当前 Windows 环境下以单 worker 执行，避免默认并行时的内存不足。
- `npm run build`（`NODE_OPTIONS=--max-old-space-size=2048`）：通过，4214 个模块完成转换。
- `npm run budget`：通过；初始 gzip 226.28 KB / 650 KB，最大分包 gzip 222.70 KB / 300 KB。
- P3 旧色值门禁、P5 legacy 样式入口与已移除依赖门禁：通过。
- `git diff --check`：通过。

## 浏览器运行证据

- 重新启动 SQLite 本地后端后，`/openapi.json` 返回 200，Vite 首页可加载且设计令牌样式正常渲染。
- 本地 Qdrant、Redis 不可用时，首页明确显示 AI 能力降级提示，并禁用需要 AI 的 Composer 控件；布局、可读性和焦点可达性保持正常。
- P4 已完成窄屏走查：组卷配置、答题、交卷总览与结果页未出现应用级横向滚动，按钮与题目导航可操作。

## 契约与已知边界

- 本次视觉重构未修改 `src/api/` 的请求/响应契约、路由路径或鉴权语义；Vitest 中 API、store、router guard 测试均通过。
- Qdrant/Redis 未在本地启动，因此依赖 AI/RAG 的能力按既有降级路径显示不可用；练习、考试、智能组卷的 SQL 主流程已在 P4 完成运行时回归。
- 方案原列出的 `NotesLibraryView` / `NoteWorkspaceView` 及路由不存在于当前仓库，未虚构新增页面。
