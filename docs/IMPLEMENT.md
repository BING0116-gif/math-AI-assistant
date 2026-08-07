# 执行手册：多用户安全隔离与生产数据一致性修复

> 本文件给出实现约束和验证方法，不提供可能与仓库漂移的整段替换代码。

## 1. 开始前

1. 不使用当前损坏的 `venv` 作为成功证据；创建新环境。
2. 记录 `git status --short`，不得覆盖用户已有的 `app/data/database.py` 修改。
3. 记录 pytest 基线。
4. 所有测试使用隔离数据库和唯一用户 fixture。

建议命令：

```powershell
py -3.10 -m venv .venv-security
.\.venv-security\Scripts\python.exe -m pip install -r requirements.txt
.\.venv-security\Scripts\python.exe -m pytest --collect-only -q
.\.venv-security\Scripts\python.exe -m pytest tests -q
```

如果 `py` 不可用，先安装/定位有效 Python；不得通过修改测试跳过环境问题。

## 2. 认证上下文

目标文件：

- `app/middleware/auth_middleware.py`
- `app/data/database.py`
- `app/data/repositories.py`
- `app/security/access_control.py`

实现约束：

- token 验证只提取 subject，不代表用户仍有效。
- 在请求中查询用户，并验证 `is_active`。
- 同时写入字符串 `user_id` 和完整 `current_user`。
- 确保后续访问的字段已经加载，或使用稳定认证 DTO。
- 数据库错误记录安全日志并返回服务错误；绝不回退匿名身份。

搜索所有回退：

```bash
rg -n '"anonymous"|"default"|user_id\s+or\s+session_id|request\.state\.user_id' app agent_core
```

## 3. 会话和流式路径

目标文件：

- `agent_core/agent.py`
- `app/services/stream_handler.py`
- `app/api/chat_api.py`
- `app/api/agent_api.py`

实施顺序：

1. 先修改最底层历史获取、清理、上下文构建签名。
2. 将复合键集中到一个函数，避免各调用点自行拼接。
3. 逐层修改所有调用者，类型签名中不允许 `user_id=None`。
4. 覆盖文本、识图、多模态有图和无图分支。
5. 行为记录、记忆持久化和 Thought 使用同一个认证 user ID。
6. 不在本次引入 Redis。

验证：

```bash
rg -n '_get_session_history|clear_history|stream_recognize|stream_multimodal|_build_context' agent_core app
python -m pytest tests/test_security_isolation.py -v
```

## 4. 鉴权边界

目标文件：

- `app/config/middleware_config.py`
- `app/middleware/auth_middleware.py`
- `app/api/error_api.py`
- `app/api/memory_dashboard.py`
- `main.py`

约束：

- 删除中间件内部的第二份默认免鉴权集合。
- 路径匹配必须有精确测试，避免 `/api/auth/login-extra` 被前缀误放行。
- 错题和画像的 user ID 来自 request state。
- Mock Router 在创建 app 时根据 settings 注册，以便测试分别创建 DEBUG true/false 的 app；不要修改全局 settings 后复用同一 app。
- Dashboard 的所有子路由逐项枚举并测试。

## 5. Thought 所有权

先确认 Thought recorder 当前是否为全局/策略级实例。如果是，先按复合身份分区，再添加端点校验。

读取算法：

1. 从 `request.state.user_id` 取得用户。
2. 用 `(user_id, session_id)` 查询 Thought。
3. 查不到统一返回 404。
4. 不通过扫描其他用户会话判断“是不是别人的”。

测试必须先由用户 A 产生一条 Thought，再由 A/B 分别读取。仅对任意字符串请求并断言 403/404不构成所有权测试。

## 6. EventIdempotency

目标文件：

- `app/data/models.py`
- `app/api/events_api.py`
- 必要的 repository/service

禁止：

- 内存字典。
- `SELECT` 不存在后再执行业务的 check-then-act。
- 捕获所有 IntegrityError 后一律当作重复事件。

推荐流程：

1. 在短事务中插入 `pending` 记录。
2. 唯一键冲突时只在确认冲突约束为 event ID 后返回重复。
3. 取得处理权后执行业务。
4. 成功更新 `processed`；失败更新 `failed` 并记录可重试信息。
5. 根据事件业务的事务能力明确“业务成功但状态更新失败”的补偿方式。

并发测试使用两个独立数据库 session 同时提交相同 event ID。

## 7. 外键迁移

先运行只读审计，输出数量而不是敏感内容：

- `memories.user_id IS NULL`
- `user_profiles.user_id IS NULL`
- 长度超过 36
- 不存在对应 `users.id`
- 重复画像记录

发现孤儿时停止自动迁移并更新 `STATUS.md`。不得自动创建 `default` 用户。

迁移应：

- 将类型统一为 `String(36)`。
- 为两个外键使用显式名称。
- 使用 `ON DELETE RESTRICT`。
- 提供 downgrade。
- 在 PostgreSQL 空库和带代表性数据的数据库各执行一次。

## 8. Refresh Token

测试流程：

1. 登录并保存 refresh token。
2. 确认 token payload 类型为 refresh 且有 JTI。
3. 调用现有撤销/登出机制撤销该 refresh token；若 API 只能撤销 Access Token，应先修正撤销契约。
4. 使用同一 refresh token 调用 `/api/auth/refresh`。
5. 精确断言 401，并检查数据库记录 `is_revoked=true`。

不得只撤销 Access Token 后声称 refresh token 已撤销。

## 9. Compose 与 CI

Compose：

- web 默认使用 db 服务。
- 生产必需密钥使用 `${VAR:?message}` 或等价启动校验。
- 本地 SQLite 放到单独 override/env 示例。

CI 冷启动 job：

1. checkout。
2. 创建仅用于 CI 的随机/固定非生产密钥。
3. `docker compose up -d --build`。
4. 等待 db、redis、web 健康，设置超时。
5. 对空库执行 Alembic。
6. 查询实际 dialect。
7. 检查关键表、两个外键和 SQLite 文件不存在。
8. 失败时输出 `docker compose ps` 与日志。
9. `if: always()` 执行 `docker compose down -v`。

该 job 必须在 pull request 运行，不能只在 main push 后构建镜像。

## 10. 8 条测试的最低断言

- 未登录：参数化 4 类端点，逐个精确断言 401。
- 错题跨用户：创建 A 数据；B 列表和数据库范围都不含 A 数据。
- 画像跨用户：B 对 A 的读写均失败，A 数据未改变。
- 会话串线：响应历史或底层 history 中不存在另一用户标记文本。
- Thought：A 可读，B 对同 session ID 得 404。
- Mock：分别构造 DEBUG false/true app，false 为 404。
- Refresh：数据库撤销状态和 HTTP 401 都验证。
- Alembic：新 PostgreSQL database 升级 head，并通过 inspector 检查表/外键。

禁止：

- `pass`
- 仅注释步骤
- `assert status_code in (200, 404)`
- 因实现困难而 skip 安全测试
- 用 mock 掉被验证的权限/数据库核心逻辑

