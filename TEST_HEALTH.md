# TEST_HEALTH.md — 测试健康度清零报告

> 任务：全量跑通全部测试，修复所有失败与可修警告，消除测试间污染。
> 纪律：每个修复独立 commit（精确路径暂存，不 push）；不动 `docs/archive/`、`qdrant_storage/`、`data/`、`.env`；不引入新依赖。

## 最终结果（2026-09-23）

| 指标 | Phase 0 基线 | 最终 | 变化 |
|---|---|---|---|
| 总测试 | 1182 | 1184 | +2（防回归测试） |
| 失败 | **8** | **0** | 全清 |
| 警告 | 10 | **1** | 仅剩 starlette 第三方内部弃用 |
| 单文件 ≡ 全量行为 | 不一致（8 个假失败） | 一致 | 污染源根除 |

验收命令：`python -m pytest tests -q` → `1179 passed, 5 skipped, 1 warning in ~2:40`

## 修复明细（7 个 commit，均未 push）

| Commit | 主题 | 根因 |
|---|---|---|
| `349ab3a` | alembic env.py `fileConfig` 加 `disable_existing_loggers=False` | 进程内跑迁移会静默禁用所有已创建的应用 logger（`app.services.*`），导致 7 个测试全量运行时 caplog 断言失败、单文件运行通过；**生产侧进程内自动升级同样会丢日志**。附带新增 `tests/test_alembic_logging_hygiene.py` 防回归。`math_verifier.py` 里的自愈补丁即此 bug 下游。 |
| `f463493` | `test_readiness_matrix` 注入确定的 `get_db_session` mock | `check_assessment` 经全局 `async_session_factory` 查章节计数，行为取决于"工厂是否被先前测试的 `init_db` 残留"——单文件时工厂为 None 走 except，全量时真实查询。补 chapter_count=0 分支正向覆盖。 |
| `e859a06` | v3 prompt 测试不再 `return True` | 消除 5×`PytestReturnNotNoneWarning`；`run_all_tests` 循环化，异常即失败，pytest/脚本双模式语义一致。 |
| `200f046` | `error_api.py` `body.dict()` → `model_dump()` | PydanticDeprecatedSince20（V3 将移除）。 |
| `493308f` | `test_memory_persistence_batch` 自带 sqlite 隔离环境 | 模块 fixture 原依赖环境 `DATABASE_URL`（本地指向未启动的 PostgreSQL 时连接拒绝）或他人残留的全局工厂；现强制 sqlite 临时库、结束重置全局状态。另修裸协程 mock（补 `asynccontextmanager`+`yield`）消除 coroutine-never-awaited。 |
| `5fdcbd2` | `pytest.ini` `cache_dir = .pytest_tmp/.pytest_cache` | 根目录 `.pytest_cache` 被外部进程锁定（空目录仍 WinError 5），每次运行产生 PytestCacheWarning；重定向后保留缓存功能。 |
| `454a59b` | `test_system_integration` 清理段用当前 session 的 repo | `user_repo` 绑定已关闭 session，在其上 `delete()` 使旧 session 复活并持有 1 条无人归还的 aiosqlite 连接（GC 时 SAWarning）。 |

## 遗留与建议

1. **starlette `anyio.abc.BlockingPortal` DeprecationWarning**：第三方内部弃用，升级 starlette 后自动消失；升级前无法在项目侧消除。
2. **`app/data/database.py` `close_db()` 不重置 `async_session_factory`**：dispose 后 factory 仍指向已废弃引擎。本次测试侧已绕开（fixture 手动置 None），建议后续在 `close_db` 内一并重置并补测试。
3. **测试全局状态卫生模式**：任何调用 `init_db()` 的测试都会替换全局引擎/工厂且不恢复，是本轮两类"单文件过、全量挂"的共同土壤。新测试应参照 `test_memory_persistence_batch` 的隔离 fixture 模式。

## 方法论沉淀（供复用）

- "单文件通过、全量失败" → 优先怀疑测试间全局状态污染（logger 状态、模块级单例、环境变量）。
- 定位手段：污染场景最小组合复现 > 猜测。本轮用了二分组合、诊断测试转正为防回归测试、GC 对象计数（`gc.get_objects()` 过滤 `aiosqlite.Connection`）三种手段。
- `fileConfig`/`dictConfig` 默认 `disable_existing_loggers=True` 是 Python logging 的经典暗坑，凡进程内跑迁移/重载配置的代码都应显式关闭该行为。
