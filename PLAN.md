# 实施计划：多用户安全隔离与生产数据一致性修复

> 需求事实源：`PRD.md`。本计划只安排执行顺序，不增加需求。

## 总体策略

安全修复拆为 6 个可独立验证的垂直切片。测试随切片实现，不把所有测试推迟到最后。P2 通用重构另开 PR。

## Phase 0：建立可复现基线

- [ ] 使用有效 Python 解释器创建全新 venv。
- [ ] 安装锁定依赖并记录 Python、pip、pytest 版本。
- [ ] 执行 pytest 收集和全量测试，记录已有失败。
- [ ] 准备 PostgreSQL 测试实例和独立测试数据库。
- [ ] 检查 `.env`、Compose 与 CI 所需密钥，不输出秘密值。

Gate：

- pytest 能正常收集测试。
- `STATUS.md` 记录基线命令、通过数、失败数和失败清单。

## Phase 1：认证与路由边界

- [ ] 中间件从数据库加载有效用户并设置两个 request state 字段。
- [ ] 删除默认/匿名身份回退。
- [ ] `NO_AUTH_PATHS` 收敛为单一来源。
- [ ] 错题本、识图、Thought 从免鉴权名单移除。
- [ ] Mock 仅 DEBUG 注册。
- [ ] Dashboard 全部端点要求 admin。
- [ ] 修复健康检查 engine 获取方式。
- [ ] 同步实现未登录、Mock、Dashboard 权限测试。

Gate：

- 未认证敏感请求精确返回 401。
- DEBUG=false 的 Mock 返回 404。
- student/admin Dashboard 权限符合 PRD。

## Phase 2：用户数据与会话隔离

- [ ] Agent 所有历史 API 改为 `(user_id, session_id)`。
- [ ] 文本、识图、多模态有图/无图分支强制传递 user ID。
- [ ] 错题和画像只从认证上下文确定用户范围。
- [ ] Thought 按复合身份存储/查询并执行所有权检查。
- [ ] 同步实现错题、画像、会话、Thought 隔离测试。

Gate：

- 用户 A/B 使用相同 session ID 时双向不串历史。
- 跨用户数据读取或更新失败。
- 仓库身份回退扫描通过人工审查。

## Phase 3：数据库一致性

- [ ] 用唯一约束插入实现 EventIdempotency 原子占位。
- [ ] 定义并实现事件状态机和事务边界。
- [ ] 增加重复、并发、应用重建后的幂等测试。
- [ ] 对 memory/profile 用户字段执行只读数据审计。
- [ ] 依据审计结果生成 PostgreSQL Alembic 迁移。
- [ ] 增加外键和空库迁移测试。
- [ ] 实现 refresh token 撤销测试并修复发现的问题。

Gate：

- 并发相同 event ID 只有一个请求取得处理权。
- 空 PostgreSQL 数据库 `upgrade head` 成功。
- 外键存在且无默认用户数据修补。

## Phase 4：Compose 与冷启动 CI

- [ ] Compose 默认 URL 改为 PostgreSQL。
- [ ] 移除生产可误用的数据库默认密码。
- [ ] SQLite 只由显式本地配置启用。
- [ ] 新增数据库后端验证脚本。
- [ ] CI 使用空 volume 启动 Compose、执行迁移和健康检查。
- [ ] CI 检查实际 dialect 和 SQLite 文件。
- [ ] CI 始终收集日志并清理 volume。

Gate：

- 本地和 CI 冷启动均通过。
- Web 确认连接 `db:5432` 的 PostgreSQL。

## Phase 5：回归与交付

- [ ] 8 条关键测试全部为真实断言，无 `pass` 或 skip。
- [ ] 全量 pytest 与 Phase 0 基线比较，无新增失败。
- [ ] 执行 Compose config、冷启动和迁移验证。
- [ ] 更新 `STATUS.md` 与 `DECISIONS.md`。
- [ ] 审查 diff，确保没有混入 P2 重构。

## 独立后续 PR

1. 生命周期与多 worker 定时任务。
2. Chat 端点合并及前端兼容迁移。
3. Router 与迁移工具命名清理。
4. 如确有跨进程会话持久化需求，再单独设计 Redis session store、TTL 和故障策略。

## 回滚边界

- 认证/会话改动：按单个垂直切片回滚，不恢复匿名回退。
- 外键迁移：必须提供 Alembic downgrade；上线前保留审计导出。
- Compose：回滚应用版本时不得把生产数据切回 SQLite。
- 幂等：回滚代码时保留表和记录，避免重新处理历史事件。

