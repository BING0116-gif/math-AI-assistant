# 进度跟踪：多用户安全隔离与生产数据一致性修复

> 最后更新：2026-07-29  
> 当前状态：核心实现完成，等待可用项目 Python 环境执行 pytest 和真实 Docker 冷启动

## 阶段状态

| Phase | 状态 | 证据 |
|---|---|---|
| 0 测试基线 | 阻塞 | 原 `venv` 指向不可用的 `F:\anaconda\python.exe` |
| 1 认证与路由 | 已实现 | 静态编译通过；免鉴权和身份回退扫描通过 |
| 2 用户/会话隔离 | 已实现 | Agent、Thought、短期记忆均使用用户复合键 |
| 3 数据一致性 | 已实现 | 数据库原子幂等、刷新轮换、外键迁移已添加 |
| 4 Compose/CI | 已实现待运行 | `docker compose config --quiet` 通过；冷启动 job 已添加 |
| 5 回归交付 | 进行中 | 关键测试已添加，pytest 尚未执行 |

## 已确认事实

- `users.id` 为 `String(36)`。
- `memories.user_id`、`user_profiles.user_id` 当前为 `String(64)` 且无用户外键。
- 中间件只设置 `request.state.user_id`。
- `NO_AUTH_PATHS` 存在两个来源。
- Compose web 默认连接 SQLite。
- `EventIdempotency` 模型存在，事件 API 仍使用内存字典。
- CI 已新增 Compose 空卷冷启动 job，等待实际运行。
- 已新增双用户同 session ID 隔离测试，等待 pytest 执行。

## 当前阻塞

| 阻塞 | 影响 | 下一步 |
|---|---|---|
| 原 venv 的解释器路径不可用 | 无法执行 pytest | 由用户恢复 `F:\anaconda` 或重建其既有 venv；本次不再下载依赖 |
| 现有数据是否有孤儿记录未知 | 外键迁移不可安全执行 | 运行只读数据审计 |

## 证据记录模板

每完成一个 Phase，追加：

```text
日期：
提交：
执行命令：
通过/失败：
失败是否为基线已有：
日志或报告路径：
剩余风险：
```

## 范围保护

- P2 lifespan、chat 合并、Router/迁移工具清理不计入本安全修复进度。
- Redis 会话迁移不在本次范围。
- 不创建管理员 CLI。

## 本次验证证据

```text
Python 静态编译：
C:\Users\HUAWEI\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m compileall -q app agent_core scripts tests
结果：通过

Compose 配置：
设置仅用于验证的 DB_PASSWORD/JWT_SECRET_KEY/ENCRYPTION_KEY 后执行 docker compose config --quiet
结果：通过

身份回退扫描：
rg -n 'return "default"|user_id or session_id|getattr(...anonymous)|user_id: str = "anonymous"' app agent_core
结果：无匹配

pytest：
未执行。原 venv 的 pyvenv.cfg 指向 F:\anaconda，但该解释器当前不可访问。
```
