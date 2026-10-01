# P4 QA 记录

日期：2026-09-30

## 补充走查（2026-10-01，暗色与移动端留档）

初始走查截图仅有 light-1440，本节按 §12.2 矩阵补齐暗色与 375px 证据，同日合并入分支：

- 新增暗色 1440：`login-page`、`applyhub`、`practice-setup`、`practice-runner`（真实会话答题流）、`practice-result`、`exam-setup`、`assessment-setup`。
- 新增亮色 375：`login-page`、`applyhub`、`practice-result`。
- 登录页（P4 LoginDialog 之外的独立 `/login` 路由页，随管理端工作流引入）在亮/暗/375 三态走查通过；主标题经 `text-wrap: balance` + 字号 clamp 校准后无孤字换行。
- 练习全流程（选题 → 5 题作答 → 完成练习 → 结果页）在暗色下实测通过，KaTeX 公式、选项、导航与语义色正常。
- 走查方法备注：IAB 截图表面偶发 3s 准备超时，等待后重试即恢复；低分辨率整页截图中 1.75 stroke 细线图标会因缩放近似隐形，经原分辨率裁查确认渲染正常，非缺陷。

## 初始走查（2026-09-30）

## 覆盖范围

- `ApplyHubView`
- `PracticeSetupView` / `PracticeSessionView` / `PracticeResultView`
- `ExamSetupView` / `ExamSessionView` / `ExamReportView`
- `AssessmentSetupView` / `AssessmentSessionView` / `AssessmentResultView`
- `SubmitOverview`
- `LoginDialog`、`BaseButton`、`EmptyState`、`StatusBadge`

## 运行验证

- 后端题型、组卷、考试与评估服务测试：43 passed。
- 补充组卷判分与题型模板测试：27 passed。
- 前端 Vitest（单 worker，避免当前环境并发内存不足）：34 个测试文件，126 passed。
- P3 硬编码颜色门禁：通过。
- 前端低内存构建（`vite build --minify=false`）：成功，4215 modules transformed。

## 可见流程

已登录测试账号后完成智能组卷：规则蓝图生成 10 题，填写并保存答案，交卷前总览显示未答题提示，确认交卷后进入报告页并显示 `70 / 100`、`7 / 10`。

judge 题报告显示：`你的答案：true`、`正确答案：对`，确认 `paper_generator` 的布尔判分修复已在运行时生效。

## 响应式观察

组卷配置、答题、交卷总览和结果页已在窄屏视口完成可见走查；页面未出现应用级横向滚动，按钮和题目导航保持可操作。

## 已知环境限制

- 标准 `npm run build` 已完成模块转换，但在 gzip 统计阶段因运行环境内存限制退出；低内存、关闭压缩的构建成功。
- 本地 Qdrant/Redis 未启动，后端按既有降级路径运行；组卷与交卷 SQL 流程不依赖这两个服务。
- 方案中的 `NotesLibraryView` / `NoteWorkspaceView` 及对应路由在当前仓库不存在，因此本轮未新增不存在的业务页面。
