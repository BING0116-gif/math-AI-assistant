# 前端重构 Phase 1：核心冒烟路径

这是进入 Phase 2 视觉改造前必须重复执行的最小冒烟测试集。

| 编号 | 路径 | 输入 | 预期输出 | 清理方式 |
|---|---|---|---|---|
| P1 | 注册 → 登录 → 首页 | 一组一次性用户名和密码 | 认证响应包含 access/refresh token；`/` 可以渲染 | 使用隔离测试账号 |
| P2 | 首页 → 文本提问 | `求极限 lim(x→0) sin(x)/x` | `POST /api/chat` 返回 SSE；页面显示回答；流式响应可以完成或取消 | 使用隔离的 `session_id` |
| P3 | 首页 → 图片提问 | 剪贴板粘贴或上传图片 | `POST /api/recognize` 或 `/api/chat/multimodal` 返回可见结果或错误 | 删除临时图片 |
| P4 | 课程目录 → 学习页 | 打开 `/knowledge` 并选择已发布知识点 | 课程树和 `/knowledge/points/:pointId/learn` 加载已发布内容 | 只读，不需要清理 |
| P5 | 回答 → 错题本 CRUD | 创建错题、更新掌握度/笔记、删除错题 | CRUD 响应可见，且数据只属于当前用户 | 使用一次性测试记录 |

## 数据隔离要求

- 每次运行使用一个测试用户、一个 `session_id` 和一次性错题记录。
- 用户 A 不能看到用户 B 的对话、图片或错题记录。
- 网络失败必须可见并提供恢复路径；不能只显示空白区域。
- 必须能区分“基线本来就失败”和“本次改动新引入的失败”。

## 当前路由表

| 路由 | 页面 |
|---|---|
| `/` | `HomeView.vue` |
| `/chat`、`/chat/:chatId` | `ChatView.vue` |
| `/knowledge` | `KnowledgeCatalogView.vue` |
| `/knowledge/points/:pointId/learn` | `KnowledgeLearningView.vue` |
| `/error-book`、`/error-book/:errorId` | `ErrorBookView.vue` |
