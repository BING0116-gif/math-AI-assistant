# PRD：多用户安全隔离与生产数据一致性修复

> 文档编号：PRD-SEC-2026-001  
> 状态：Ready for implementation  
> 日期：2026-07-29  
> 唯一事实源：本文件。`PLAN.md`、`IMPLEMENT.md`、`STATUS.md`、`DECISIONS.md` 不得改变本文件的需求范围。

## 1. 目标

修复认证上下文断裂、跨用户会话/错题/画像泄露、敏感接口越权、生产数据库配置错位、事件幂等失效和长期记忆孤儿数据问题，并建立可复现的测试与 Docker 冷启动验证。

成功标准：

- 未认证请求不能访问错题本、识图、Thought、Dashboard。
- 普通用户只能访问自己的错题、画像、会话和 Thought。
- 所有 Agent 路径使用 `(user_id, session_id)` 隔离上下文。
- 生产 Compose 只连接 PostgreSQL；SQLite 只允许显式开发配置。
- 事件去重跨重启、跨进程有效，且并发请求不会重复执行业务。
- 空 PostgreSQL 数据库可以通过 Alembic 启动。
- 8 条关键安全测试及 Docker 冷启动 CI 通过。

## 2. 范围

### 2.1 本次必须完成

1. 认证中间件从数据库加载有效用户，同时设置：
   - `request.state.user_id: str`
   - `request.state.current_user`
2. 删除业务代码中的匿名、`default` 用户和 `user_id or session_id` 等身份回退。
3. Agent 会话键统一为 `f"{user_id}:{session_id}"`；文本、识图、多模态及“多模态无图片”路径强制传递 `user_id`。
4. 从免鉴权名单移除错题本、识图和 Agent Thought，并将免鉴权配置收敛为单一来源。
5. Thought 按认证用户和会话隔离，并验证会话归属。
6. Mock Router 仅在 `DEBUG=true` 时注册；Dashboard 所有入口要求管理员角色。
7. Compose 默认使用 PostgreSQL；SQLite 仅用于显式本地开发。
8. 使用 `EventIdempotency` 表实现原子幂等。
9. 为 `memories.user_id`、`user_profiles.user_id` 制定并执行外键迁移。
10. 修复健康检查对数据库 engine 的过期引用。
11. 重建测试环境并增加 8 条关键测试。
12. 增加真正启动 Compose、迁移空库并检查数据库方言的冷启动 CI。

### 2.2 独立收口项（不阻塞安全修复）

以下来自代码审计，但必须放入独立 PR；不得混入 P0/P1 安全补丁：

- Agent 创建和定时任务迁入 lifespan。
- 合并 `/api/chat` 与 `/api/chat/react`。
- 清理未使用的 `app/api/__init__.py` Router。
- 重新命名/隔离 Alembic schema migration 与一次性业务数据导入。

### 2.3 明确不在范围内

- 强制将会话历史迁移到 Redis。
- 新增管理员角色体系或管理员创建 CLI。当前 `role` 字段已经支持字符串 `admin`；测试通过 fixture 创建管理员。
- 前端 UI、LLM、Prompt、RAG、Qdrant、推荐算法改造。
- 与本次安全验收无关的通用重构。

## 3. 功能需求

### FR-1：认证上下文统一

认证中间件验证 Access Token 后，必须使用 token 中的用户 ID 查询数据库。

验收标准：

- 用户不存在、被禁用或 token 无效时返回 401。
- 成功时同时设置 `user_id` 和 `current_user`，两者指向同一用户。
- `verify_resource_ownership` 和 `require_admin_role` 正常工作。
- 数据库查询异常不得降级为匿名用户。
- 明确数据库 session 生命周期，避免把不可用的延迟加载 ORM 对象泄漏到请求后续阶段。

### FR-2：会话上下文隔离

验收标准：

- `_get_session_history` 和所有相关读取、清除接口都要求 `user_id` 与 `session_id`。
- 内部键为 `f"{user_id}:{session_id}"`。
- 文本、识图、多模态、有图和无图分支全部传递认证用户 ID。
- 缺少 `user_id` 时立即失败，不得使用 `anonymous`、`default` 或 session ID 替代。
- 两个用户使用相同 session ID 时不能读取或影响对方历史。

说明：本次只要求正确隔离键；存储介质保持现状。Redis 持久化另行设计。

### FR-3：鉴权名单与资源隔离

验收标准：

- `NO_AUTH_PATHS` 只有 `middleware_config.py` 一个来源。
- `/api/error-book`、`/api/recognize`、`/api/agent/thought/*` 不在免鉴权名单中。
- 未认证请求返回 401。
- 错题和画像 API 不接受客户端提供的 user ID 作为授权依据；资源范围来自认证上下文。
- 跨用户访问返回 403，或在需要防资源枚举时统一返回 404；同类接口必须保持一致。

### FR-4：Thought 会话归属

Thought 必须按 `(user_id, session_id)` 存储或索引。仅仅检查“某个 session ID 是否存在”不构成归属验证。

验收标准：

- 创建会话/Thought 时记录所有者。
- 读取时使用认证用户 ID 和 session ID 查询，不扫描其他用户的 key。
- 不存在或不属于当前用户的会话返回统一的 404，避免泄露 session ID 是否存在。
- 普通管理员默认也不能读取用户 Thought；若未来确有审计需求，需单独决策并记录审计日志。
- Thought 响应不得包含密钥、完整系统 Prompt 或工具凭据。

### FR-5：Mock 与 Dashboard

验收标准：

- `DEBUG=false` 时 Mock Router 未注册，返回 404。
- `DEBUG=true` 时 Mock 仅用于隔离的开发/测试环境；不得在生产配置中通过单个请求切换 DEBUG。
- Dashboard 的 HTML、数据和辅助端点全部执行 `require_admin_role`。
- student 返回 403，未认证返回 401，admin 返回 200。

### FR-6：生产数据库与冷启动

验收标准：

- Compose 的同步 URL 为 `postgresql://...@db:5432/...`。
- Compose 的异步 URL 为 `postgresql+asyncpg://...@db:5432/...`。
- Compose 不使用 SQLite 默认值。
- 数据库密码、JWT 密钥和加密密钥缺失时生产启动失败；不得提供可误用的 `changeme` 生产默认值。
- `.env` 可显式选择 SQLite 作为本地开发数据库。
- CI 从空 volume 启动 PostgreSQL，执行 `alembic upgrade head`，验证健康接口和实际 SQLAlchemy dialect 为 `postgresql`，并确认未创建 SQLite 数据库文件。
- CI 失败时上传 Compose 日志并执行 `docker compose down -v`。

### FR-7：事件原子幂等

验收标准：

- `EventIdempotency.event_id` 具有数据库唯一约束。
- 不使用“先查询、再执行业务、最后插入”的竞态实现。
- 首次请求通过尝试插入幂等记录取得处理权；唯一键冲突表示重复。
- 明确 `pending / processed / failed` 状态或等价状态机。
- 业务写入与幂等状态转换处于可证明一致的事务边界。
- 失败事件是否重试、何时清理必须有确定策略。
- 测试至少覆盖重复请求、并发请求和重新创建应用实例后的重复请求。

### FR-8：记忆与画像外键迁移

已确认 `users.id` 为 `String(36)`，而两个目标字段当前为 `String(64)`。

迁移策略：

1. 迁移前审计空值、长度超过 36、非现有用户和其他孤儿记录。
2. 不自动把孤儿数据归到默认用户。
3. 孤儿数据默认迁入审计/隔离表或导出后停止迁移；删除或补用户必须由人工批准。
4. 将字段统一为 `String(36)`。
5. 添加命名明确的外键，默认 `ON DELETE RESTRICT`。
6. PostgreSQL 为验收数据库；SQLite 开发测试必须显式启用 foreign keys pragma。

### FR-9：健康检查 engine

健康检查必须在调用时通过数据库模块或 getter 获取当前 engine，不得使用导入时捕获的初始变量。

## 4. 关键测试契约

必须实现下列 8 条非占位测试；禁止 `pass`、仅注释步骤、宽松的 `200 or 404` 断言：

| # | 测试 | 必须验证 |
|---|---|---|
| 1 | 未登录 | 错题本、识图、Thought、Dashboard 参数化返回 401 |
| 2 | 错题跨用户 | B 的响应和数据库查询均不包含 A 的错题 |
| 3 | 画像跨用户 | B 无法读取或更新 A 的画像 |
| 4 | 会话串线 | A/B 使用相同 session ID，历史内容双向隔离；覆盖文本、识图和无图多模态路径 |
| 5 | Thought 越权 | 先由 A 创建 Thought，B 使用同 session ID 读取时得到规定的 404 |
| 6 | Mock 越权 | `DEBUG=false` 路由为 404；Dashboard 的 student/admin 权限另有断言 |
| 7 | 刷新 Token 撤销 | refresh token 撤销后再次刷新返回 401；验证 JTI 和 token type |
| 8 | 空库 Alembic 启动 | 对新 PostgreSQL 数据库执行 `upgrade head`，检查关键表和外键 |

Docker Compose 冷启动是独立 CI Gate，不用一个普通单元测试伪装。

## 5. 验证命令

```bash
python -m pytest tests/test_security_auth.py tests/test_security_isolation.py tests/test_alembic_cold_start.py -v
python -m pytest tests/ -v
docker compose config
docker compose up -d --build
docker compose exec -T web alembic upgrade head
docker compose exec -T web python -m scripts.verify_database_backend postgresql
```

仓库级回退扫描：

```bash
rg -n '"anonymous"|"default"|user_id\s+or\s+session_id' app agent_core
```

扫描结果必须逐项审查；前端展示默认 session ID 本身可以保留，但不能再作为跨用户唯一键。

## 6. 完成定义

- [ ] P0/P1 需求全部实现。
- [ ] 8 条关键测试无跳过、无占位并全部通过。
- [ ] 全量测试相对重建后的基线无新增失败。
- [ ] Docker 空卷冷启动 CI 通过。
- [ ] 实际数据库方言为 PostgreSQL，未创建 SQLite 文件。
- [ ] 无匿名或默认用户身份回退。
- [ ] EventIdempotency 并发测试通过。
- [ ] 外键迁移对孤儿数据采取明确、可审计策略。
- [ ] 安全修复 PR 不包含 P2 通用重构。
- [ ] `STATUS.md` 记录命令、提交和证据。

## 7. 未解决问题

| 问题 | 默认处理 | 是否阻塞 |
|---|---|---|
| 现有生产数据是否包含孤儿记忆/画像 | 先运行只读审计；发现孤儿即停止迁移并报告 | 阻塞外键上线 |
| 业务成功但幂等状态更新失败的深度补偿 | 当前记录失败并允许下次同 ID 重试；复杂补偿另行设计 | 不阻塞本次修复 |
| 当前测试 Python 环境如何重建 | 使用可复现的新 venv，不修补损坏解释器 | 阻塞全部实现 |
