# 前端重构 Phase 1：职责与契约审计

| 模块 | 当前职责 | 权威来源 / 契约 | Phase 2/3 决策 |
|---|---|---|---|
| `LayoutDefault` | 侧栏、顶栏和页面插槽 | 仅负责 UI 外壳 | 保留行为，Phase 2 迁移到 `AppShell` |
| `Sidebar` | 新建对话、本地历史、导航、主题 | `chatStore`；localStorage | 拆分为导航、历史和账号操作 |
| `TopBar` | 菜单/主题控件和插槽 | 父级页面 | 替换为统一外壳顶栏 |
| `ChatView` | 输入框、SSE、图片输入、推荐、错题操作 | `api/chat.js`、各 store | 拆分输入、流状态、消息操作和上下文检查器 |
| `KnowledgeCatalogView` | 课程/目录树加载和知识点跳转 | `api/knowledge.js` | 将状态迁移到 service/store |
| `KnowledgeLearningView` | 知识点和已发布学习资源展示 | `getKnowledgePointLearning()` | 保留现有契约；练习反馈由 Phase 3 负责 |
| `ErrorBookView` | 错题列表、筛选、详情和 CRUD UI | `api/errorBook.js`、`errorBookStore` | 服务端仍是权威来源 |
| `chatStore` | 本地对话、当前会话、消息修改 | `math_ai_chats` localStorage | 后端契约成为权威前，暂作为旧草稿层 |
| `errorBookStore` | 列表和修改请求状态 | 错题本 API | 增加明确的加载和错误状态 |
| `api/index.js` | Axios 认证头和 HTTP 错误归一化 | localStorage 中的 `auth_token` | 集中管理类型化 API 错误 |
| `api/chat.js` | Fetch 封装和 SSE 解析 | `/api/chat`、`/api/recognize`、`/api/chat/multimodal` | 保留事件语义，并封装到 service |
| `utils/markdown.js` | Markdown/KaTeX 渲染和清理 | API 返回的 Markdown | 统一渲染负责人 |
| `utils/storage.js` | 浏览器存储访问 | localStorage | 仅保存 UI 偏好和草稿 |

## API 示例

### 聊天流

请求：`POST /api/chat`

```json
{"message":"求极限 lim(x→0) sin(x)/x","session_id":"test-session"}
```

响应类型：`text/event-stream`。JSON `data` 块可能包含 `content`、`type: "done"` 或可见的 `type: "error"`。

### 知识目录

- `GET /api/knowledge/courses`
- `GET /api/knowledge/courses/{courseId}/tree`
- `GET /api/knowledge/points/{pointId}`
- `GET /api/knowledge/points/{pointId}/learning`

前端当前使用已发布课程树和已发布学习内容接口。对于不稳定或不存在的接口，必须明确显示状态；Phase 2 不得伪造看起来真实的回退数据。

### 错题本

- `GET /api/error-book`
- `POST /api/error-book`
- `PUT /api/error-book/{errorId}`
- `DELETE /api/error-book/{errorId}`

后端数据是权威来源；Pinia 只负责协调页面状态和请求状态。

## 当前边界问题

- 在完成行为基线前，`ChatView.vue` 和 `Sidebar.vue` 过大，不适合直接拆分。
- 本地存在对话状态，而后端也已有聊天模型，迁移归属尚未最终确定。
- 聊天流辅助函数重复构造认证头。
- 多个组件使用 `v-html`，需要统一 sanitizer/KaTeX 的归属。
- 现有上下文菜单曾使用 emoji 图标；这是已冻结的技术债，不属于 Phase 1 页面重写范围。
