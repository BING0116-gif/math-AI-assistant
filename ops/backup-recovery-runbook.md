# Math AI Assistant 备份、恢复和 Qdrant 重建 Runbook

本文描述生产恢复的顺序。所有命令先在隔离环境执行；没有明确的 `--apply`、`--execute` 或生产变更审批时，只做 dry-run 和校验。

## 目标和边界

SQL（PostgreSQL）是学习事实、用户、题目、记忆和任务状态的唯一事实源。Qdrant 是可重建的检索投影，Redis 是缓存、限流和短期派生状态。`runtime/content` 保存上传 PDF 和解析输入，`runtime/notes` 保存笔记 revision/asset，`runtime/animations` 保存动画产物；三者都必须与 SQL 元数据一起备份。

目标值：SQL 和文件 RPO 15 分钟；Qdrant RPO 由最近一次 SQL 快照承担；Redis RPO 为 0（允许全部丢失）。SQL 恢复 RTO 30 分钟，文件恢复 RTO 30 分钟，Qdrant 全量重建 RTO 60 分钟，Redis 丢失后的服务恢复 RTO 10 分钟。

## 1. 备份前检查

```powershell
docker compose config --quiet
.\venv\Scripts\python.exe scripts/verification/backup_restore_dry_run.py
```

确认 PostgreSQL、Redis、Qdrant 健康；记录当前 Alembic revision、Qdrant collection 名称/点数、文件根目录和备份对象存储位置。dry-run 检查器只读取目录，不创建备份、不删除文件、不连接生产数据库执行写入。

## 2. PostgreSQL 备份

使用自带脚本生成 custom-format dump，并记录 SHA-256：

```powershell
.\scripts\operations\postgres_backup_restore.ps1 `
  -Action backup `
  -BackupPath D:\isolated-backups\math_ai_$(Get-Date -Format yyyyMMddHHmmss).dump
```

备份文件和校验值必须上传到受控、加密、异地存储。不要把 dump 放进仓库、`data/math_ai.db` 或 Qdrant storage。

## 3. 文件备份

备份以下目录及其权限/时间戳，目录名必须来自环境变量：

```text
CONTENT_STORAGE_ROOT   (默认 runtime/content)
NOTE_STORAGE_ROOT      (默认 runtime/notes)
ANIMATION_STORAGE_ROOT (默认 runtime/animations)
```

建议使用支持校验和断点续传的对象存储同步工具。同步前后保存文件数量、总字节数和清单哈希。只复制目录内容，不跟随符号链接，不把工作区其他目录纳入备份。

## 4. 隔离恢复演练

在独立 PostgreSQL 数据库恢复并校验，不得使用生产数据库名：

```powershell
.\scripts\operations\postgres_backup_restore.ps1 `
  -Action verify `
  -BackupPath D:\isolated-backups\math_ai_example.dump `
  -RestoreDatabase math_ai_restore_verify
```

恢复后运行 Alembic 状态检查、关键表计数和应用只读健康检查。文件备份恢复到隔离目录后，将 `CONTENT_STORAGE_ROOT`、`NOTE_STORAGE_ROOT`、`ANIMATION_STORAGE_ROOT` 指向隔离目录。

## 5. Qdrant 重建

先从 SQL 恢复题目和记忆，再只读对账：

```powershell
python scripts/verification/qdrant_reconcile.py --kind question
python scripts/verification/qdrant_reconcile.py --kind memory --user-id <user-id>
```

确认差异报告后，显式执行重建。重建使用稳定点 ID 和 upsert，可重复执行；网络错误由重试参数处理：

```powershell
python scripts/verification/qdrant_reconcile.py --kind question --execute --retries 3 --rate-limit 0.05
python scripts/verification/qdrant_reconcile.py --kind memory --user-id <user-id> --execute --retries 3 --rate-limit 0.05
```

全量题目同步也可使用：

```powershell
python scripts/operations/recovery.py qdrant-sync
```

该命令保持 dry-run；只有增加 `--apply` 才修改 Qdrant。重建完成后再次运行对账，missing/stale/version mismatch 必须为零。

## 6. Redis 丢失的影响和恢复

Redis 丢失不会删除 PostgreSQL 事实。影响包括缓存未命中、画像/推荐派生缓存丢失、限流窗口重置和短期 Agent 状态丢失。服务可以先以缓存冷启动方式恢复；不要把 Redis 备份当作用户事实备份。恢复后按用户或全局清理残留键：

```powershell
python scripts/operations/recovery.py redis-recover --user-id <user-id>
```

该脚本默认只报告匹配键，只有 `--apply` 才删除。

## 7. 恢复后对账

按顺序执行：

1. PostgreSQL 表计数、Alembic revision、用户/记忆/题目抽样校验。
2. 文件清单与 SQL storage key 对账：`python scripts/operations/reconcile_note_storage.py`。
3. Qdrant question/memory 对账，确认缺失、过期、错误 collection、用户范围和 embedding 版本均为空。
4. Outbox health 检查；必要时用 `scripts/operations/recovery.py replay --event-id <id>` 重放 dead 事件。
5. Redis health 检查和应用只读 smoke test。

任何一步失败都保留恢复任务为失败状态，记录错误和重试次数；禁止在对账未通过时宣布恢复完成。

## 8. 证据和回滚

每次演练保存：执行时间、操作者、备份路径、SHA-256、数据库名、Alembic revision、三类文件清单哈希、Qdrant 对账 JSON、Redis 匹配键数量和最终 smoke-test 结果。生产恢复前先冻结写入或记录恢复时间点；恢复到错误数据库时销毁隔离数据库并重新从备份演练，不覆盖生产库。
