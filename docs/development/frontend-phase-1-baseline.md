# 前端重构 Phase 1：基线记录

> 范围：`plans/frontend-refactor/phase-1-baseline-and-design-freeze.md`
> 记录日期：2026-08-05

## 文档目的

本文档用于记录前端重构前的可复现基线。它描述当前仓库状态，不代表所有依赖和服务在每台本地机器上都已经正常运行。

## 当前技术栈

| 领域 | 当前值 | 来源 |
|---|---|---|
| 前端 | Vue 3 + Vite + Pinia + Vue Router + Element Plus + SCSS | `frontend/package.json` |
| 图谱渲染 | Three.js | `frontend/package.json` |
| 后端 | `main.py` 中的 FastAPI 应用 | `main.py` |
| 开发环境数据库回退 | `DATABASE_URL` 默认使用 SQLite | `app/config/settings.py` |
| Compose 默认数据库 | PostgreSQL 15 Alpine | `docker-compose.yml` |
| 缓存 | Redis 7 Alpine | `docker-compose.yml` |
| 向量数据库 | Qdrant `latest` 镜像 | `docker-compose.yml` |
| 已观测 Node 版本 | 系统 v24.15.0 / bundled v24.14.0 | 本地命令输出 |
| 已观测 Python 版本 | bundled 3.12.13 | 本地命令输出 |

Compose 会强制要求 `DB_PASSWORD`、`ENCRYPTION_KEY` 和 `JWT_SECRET_KEY`。这些值必须在本地提供，不能提交到仓库。

## 复现命令

除非特别说明，以下命令均从仓库根目录执行：

```powershell
cd frontend
npm.cmd install
npm.cmd run build

cd ..
python -m pytest tests/test_knowledge_catalog.py -q
python -m alembic -c app/data/alembic.ini heads

$env:DB_PASSWORD = '<local-secret>'
$env:ENCRYPTION_KEY = '<local-secret>'
$env:JWT_SECRET_KEY = '<local-secret>'
docker compose config --quiet
```

当前机器的 PowerShell 会阻止执行 `npm.ps1`，因此使用 `npm.cmd`。

## 2026-08-05 记录的基线结果

| 检查项 | 结果 | 证据 / 阻塞原因 |
|---|---|---|
| `npm run build` | 受限 shell 中阻塞 | `npm.ps1` 被策略阻止；改用 `npm.cmd` 后，受限 shell 又报告 Vite 配置解析权限错误，需要在真实开发环境重新执行。 |
| `tests/test_knowledge_catalog.py` | bundled 运行时无法执行 | bundled Python 未安装 `pytest`，需要使用项目虚拟环境或 CI。 |
| Alembic heads | 等待真实 Python 环境 | 同上，需要项目虚拟环境或 CI。 |
| Compose 配置 | 缺少密钥时阻塞 | Compose 要求提供 `DB_PASSWORD`。 |

以上是基线环境限制，不是已接受的 Phase 1 失败。真实环境可用后，应将待定结果替换为实际命令输出。

### 真实环境复跑结果

2026-08-05 在受限 shell 外执行 `npm.cmd run build` 成功：完成 1789 个模块转换，构建耗时 8.35 秒。过程中出现 Sass legacy JS API 弃用警告以及 `KnowledgeCatalogView`、`element-plus` 的大 chunk 警告；这些问题记录为后续优化项，不属于 Phase 1 页面布局工作。

## Phase 1 交付物索引

- [核心冒烟路径](./frontend-core-paths.md)
- [职责与契约审计](./frontend-contract-audit.md)
- [设计与范围冻结](./frontend-design-freeze.md)
- [已知失败与技术债](./frontend-known-issues.md)
- [可重复执行的验证脚本](../../scripts/verify_frontend_phase1.ps1)

## 退出检查清单

- [x] 已明确保留现有未提交改动。
- [x] 已记录运行时、依赖、Compose、迁移和前端构建命令。
- [x] 五条核心用户路径都有固定输入和预期输出。
- [x] 已梳理页面、组件、store、API 和存储职责。
- [x] 已冻结路由、视觉、交互和本阶段范围外规则。
- [x] 已为已知阻塞项记录下一步处理方式。
- [ ] 真实开发环境已经替换所有待定命令结果。

## 环境规则

1. 验证 Compose 或生产行为时，不得隐式使用 SQLite。
2. 数据库迁移验证必须使用全新的 PostgreSQL 数据库。
3. API Key、签名密钥和加密密钥必须放在受控环境变量中，不能进入版本库。
4. 每个阻塞项都要记录命令、退出码和关键输出。
5. 准备验证环境时，不得删除或重置现有未提交改动。
