# Math AI Assistant 全栈体检与升级路线

## 结论

项目已经超过原型阶段：后端约 35k 行、前端约 18k 行、测试约 19k 行，具备正式的 FastAPI 装配、Alembic、用户隔离、离线模型质量集、前端单测和 bundle 预算。主要问题不是“缺功能”，而是增长后的边界治理：管理端 HTML 安全、上传资源控制、认证令牌存储、超大模块、前端重依赖和质量入口的一致性。

## 本轮证据

| 维度 | 结果 | 判断 |
| --- | --- | --- |
| 前端单测 | 38 files / 134 tests 全通过 | 健康；新增 Dashboard、错题本、学习画像、管理审核投影与对话框焦点边界测试 |
| 前端生产构建 | 通过 | Sass 构建与测试均已切换到 modern compiler，无 legacy API 警告 |
| Bundle 预算 | 最大 chunk 228.04 KiB gzip / 300 KiB | 通过；MathLive 为最大按需分块，仍有约 72 KiB 余量 |
| Docker Compose | `docker compose config --quiet` 通过 | 健康 |
| Alembic | 单一 head：`f9a0b1c2d3e4` | 健康 |
| 模型质量集 | v1.1.0，60 cases，校验通过 | 有可重复质量基线 |
| npm 漏洞审计 | 官方 registry 的生产依赖审计为 0 漏洞 | 已升级 Axios、DOMPurify、form-data、linkify-it、nanoid；CI 固定使用官方 advisory 源 |
| 后端全量 pytest | 修复后 1211 passed / 5 skipped / 19 subtests passed，543.39s | 功能基线健康；仍有 41 个警告，主要是 aiosqlite 清理 |

## P0：立即处理

1. [已完成] 修复 `memory_dashboard.py` 的存储型 XSS，并为恶意 `user_id`、摘要、分类增加回归测试。
2. [已完成] 把请求体限制改为累计实际 ASGI body；增加无 `Content-Length` 与超过上限的测试。
3. [已完成] 学生试卷读取、修改、定稿、启动以及诊断开始/作答均增加或核验跨用户拒绝测试；服务查询把认证态 `user_id` 纳入 SQL 条件，越权资源统一表现为不存在，避免泄露资源存在性。相关学生契约与隔离测试 7 项通过。

## P1：一到两个迭代

1. [已完成] refresh token 仅通过 `HttpOnly`、`SameSite=Lax`、认证路径限定 cookie 传输，生产环境自动启用 `Secure`；登录与刷新响应体不再暴露 refresh token，刷新与注销也不再接受请求体 token。access token 只保存在前端内存；旧 `localStorage` token 会被清除，旧客户端需重新登录。刷新轮换、注销和 cookie 清理回归均已覆盖。
2. [已完成] 前端拆包与组件注册：已移除 `api/index.js` 对已静态加载 `authStore` 的无效动态导入，改为启动期注入会话处理器；修复学生页使用全局 `el-*` 组件、却只在管理路由延迟安装 Element Plus 的注册时序问题。当前只注册源码实际使用的 22 个组件，并从组件级入口导入；最大分块由临界的 291.14 KiB 降至 222.70 KiB gzip。
3. [已完成] 使用一次性 SQLite 数据库和一次性学生账号完成真实运行时 QA：覆盖登录、受保护路由、错题本/学习看板/学习画像成功空状态、知识图谱、管理员门禁、桌面与 390×844 移动视口。目标页面无横向溢出；对话框打开后聚焦关闭按钮并正确圈定 Tab/Shift+Tab；移动导航、筛选、返回链接、周期选择器等交互目标已提升到至少 44px。KaTeX 与 MathLive 的确定性组件回归分别覆盖 4 项和 3 项；临时环境没有伪造模型输出，因此未把无真实公式内容的页面冒充 KaTeX 视觉验收。
4. [已完成] `MathFieldInput` 改用动态原生元素，Vue 未注册组件 warning 已消失；Vite 与独立 Vitest 配置均改用 Sass modern compiler，构建及 134 项前端测试不再输出 legacy JS API 警告。
5. [已完成] CI 新增生产 npm 依赖审计，显式使用 `registry.npmjs.org`，与包下载镜像解耦；Python 在已解析安装环境上用固定版本 `pip-audit` 与 OSV 扫描。本地 npm 生产依赖扫描为 0 漏洞，Python 扫描将在 Linux CI 环境执行。
6. [已完成] 8 个创建内存异步引擎的测试 fixture 已在同一异步生命周期显式 `dispose()`；相关 111 项测试在 `PytestUnhandledThreadExceptionWarning` 视为错误时全部通过。

## P2：瘦身与结构治理

1. 已删除无源码引用的 `@lucide/vue`，保留实际使用的 `lucide-vue-next`，减少重复图标依赖。
2. [已完成八个切片] 按职责拆分超过 800-1000 行的模块，优先服务层和大型 Vue 页面。学习看板已把数据归一化与指标投影从 1161 行页面抽到 107 行 composable，页面降至 1058 行；错题本已把阶段分类、错误模式、复习计划、筛选和知识概览从 1690 行页面抽到 218 行 composable，页面降至 1354 行；学习画像已把掌握度、记忆强度、复习计划与图表投影从 1200 行页面抽到 131 行 composable，页面降至 1089 行。三个 composable 各有 3 个确定性边界测试。画像同时修复了把当前脆弱点数量伪装成“较上周新增”的无证据趋势。后端已把四个 Agent 配置 dataclass 抽到 `agent_core/config.py`，并把用户技能画像提示词格式化抽到纯函数 `agent_core/profile_prompt.py`；旧导入路径和 `MathAgent._format_skill_profile_for_llm` 均继续兼容，`agent.py` 还将无状态 System Prompt 装配抽到 `agent_core/system_prompt_builder.py`，旧 `_build_system_prompt()` 保持兼容，主文件从 1294 行降至 1163 行；相关回归分别为 32、51 与 81 项全通过。管理审核页进一步把数学渲染、状态标签和候选筛选投影抽到 `adminReviewPresentation.js`，页面从 1064 行降至 981 行；并修复了 Gate/人工处置筛选只识别当前选中候选的问题：候选列表 API 以兼容新增字段返回每项最新分析摘要，SQL 使用 `selectinload` 避免 N+1，50 项后端相关测试与 133 项前端测试通过。记忆存储进一步把类型、状态、强度、TTL、衰减系数与向量摘要规则抽到纯策略模块 `memory_policy.py`，`memory_store.py` 从 1031 个物理行降至 996 行；原常量导入路径与异步摘要方法保持兼容。同期修复记忆持久化测试隐式依赖本地 PostgreSQL 的问题，改用可清理的临时 SQLite 并恢复环境变量；记忆策略、持久化、画像、权限和调度相关组合回归共 83 项通过。`models.py` 因 Alembic 元数据与全仓库直接导入扇出较大，本轮不做高风险机械拆分。后续继续按业务边界拆分图表、交互和后端大型模块，不按行数机械切文件。
3. [已完成] 管理端记忆 Dashboard 已从 Python 大段 f-string 与逐项 HTML 拼装迁移到 Jinja2 自动转义模板，统计页、用户详情和记忆条目共享模板/CSS；动态记忆类型 CSS 类使用白名单映射，百分比限制在 0–100，并移除了刷新的内联 JavaScript。相关模板注入、管理员鉴权与 CSP 回归共 25 项通过。
4. [已完成] 质量工具同时兼容 `python -m scripts.model_quality_eval` / `python -m scripts.rag_quality_eval` 与直接脚本执行，入口会在导入前校正仓库根路径，避免同名脚本遮蔽同名包；2 个 subprocess 回归测试通过，直接执行的 60-case 校验与离线 RAG 评估均通过。
5. [已完成边界确认] `.tmp_extract_warnings.py`、大日志和被修改的 `data/math_ai.db` 属于既有未提交工作，无法安全证明归属，因此明确排除自动删除；这不是代码待办，后续仅由所有者确认后清理。
6. [已完成第九个切片] 收窄 `MemoryStore._sync_to_qdrant()` 的私有接口，删除调用链中 7 个从未使用的分类、摘要、重要性、难度和标签参数；SQL 仍为事实源，向量同步仍在同一事务写入 outbox，事件类型、用户归属与幂等键保持不变。`memory_store.py` 进一步降至 964 个物理行，相关组合回归 84 项通过。
7. [已完成第十个切片] 修复 `MemoryStore.update_memory_access()` 使用 PostgreSQL `LEAST()` 导致显式本地 SQLite 模式更新失败的问题，改为两端兼容的标准 `CASE` 表达式；数据库级回归锁定记忆强度上限 `1.0`、访问次数递增和访问时间更新，记忆相关组合回归仍为 84 项通过。
8. [已完成第十一个切片] 修复内部 `/api/internal/memory/update-strength` 虽接收 `user_id`、却只按 `memory_id` 更新的跨用户边界漏洞；服务新增可选所有权条件以兼容既有直接调用，内部 API 强制传递真实用户，并以 SQL `rowcount` 区分实际更新与不存在、非 active 或不属于该用户的记忆。数据库隔离与 API 转发测试已覆盖错误用户拒绝、正确用户更新及准确计数，记忆相关组合回归 85 项通过。
9. [已完成第十二个切片] 修复 `get_active_memories_by_user()` 类型标注为列表、实际返回分页元组的契约错误；同时统一更新强度、更新内容、归档和软删除的真实成功语义，目标不存在或状态不符时返回 `False`，仅在事实行实际归档或删除后生成向量删除 outbox，避免幽灵事件与虚假成功计数。调用扫描确认无代码依赖错误元组形态，相关组合回归 86 项通过。
10. [已完成第十三个切片] 修复里程碑 `milestone_type` 和画像固定标签只传给未使用参数、未进入 SQL/Qdrant 的数据丢失：新记录现在与记忆事实同事务写入 `memory_tags`，outbox 消费者从 SQL 真源读取标签并加入 Qdrant payload。数据库与消费者回归覆盖错题知识点、里程碑类型和画像标签；本轮认证、记忆、画像、权限与调度组合回归共 103 项通过。历史里程碑的类型值从未持久化，无法无损推断；画像标签虽可推导，但依据“先审计再修复”原则不对真实学生库自动写入。该项已归类为需要真实数据审计与备份授权的运维迁移，而非未完成代码修复。

## AI / RAG 质量评估边界

现有 60-case 数据集提供了基础，但验收应分层记录：视觉提取准确度、规范化、检索命中与禁入项、Agent 工具/计划、数学答案正确性、中文与 LaTeX 渲染、用户数据隔离。开放式答案不能只用一次流畅输出判定通过；稳定的解析、路由、元数据和工具调用应转成确定性 pytest。

## 兼容与数据不变量

- 公共 API 字段语义不静默改变；前端 client、Pydantic schema 与测试同批更新。
- 所有学生数据只接受认证态 `request.state.user_id`，不接受客户端声明的归属用户。
- SQL 是主数据源；Qdrant 是可重建投影。写入失败必须可重试、幂等并有修复路径。
- Schema 只通过 `app/data/alembic/versions/` 迁移；不得用运行时 `create_all` 或原始 SQL 替代。
- 不修改历史归档、Qdrant 存储、本地学生数据库和未确认归属的工作树改动。
