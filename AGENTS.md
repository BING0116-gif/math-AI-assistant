# Math AI Assistant

## 目标与架构

这是面向大学数学学习的 AI 助手：数学问答、多模态题目理解、错题本、学生记忆与画像、知识图谱、RAG 推荐和学习分析。

- `frontend/`：Vue 3 + Vite 学生端；组件、Pinia、路由和 API 客户端。
- `app/`：FastAPI 应用装配、HTTP API、业务服务、安全中间件和任务。
- `app/data/`：SQLAlchemy 模型、仓储和 Alembic 迁移；生产/Compose 使用 PostgreSQL，本地 SQLite 必须显式配置。
- `agent_core/`、`tools/`、`prompts/`：数学 Agent、任务规划、工具注册和模型提示。
- `data_processing/`、`scripts/`：题库导入、视觉解析、迁移、审计和验证。
- `tests/`：pytest 单元、集成、安全与 Agent/RAG/视觉测试。

正式 ASGI 入口为 `app.application:app`；`main.py` 只保留兼容入口。运行时依赖 PostgreSQL、Redis、Qdrant，题目主数据在 SQL，向量检索数据在 Qdrant。

## 约定

- Python 使用 async 边界、Pydantic 请求模型、SQLAlchemy 异步会话；保持现有分层，避免在路由中复制业务逻辑。
- 前端沿用 Vue 3、现有设计 tokens、组件与 API 封装；不要同时维护冲突的 JS/TS 路由或 store 实现。
- API 变更必须兼容现有客户端，或同时更新客户端、请求/响应模型、文档与测试；不要静默改变字段语义或认证要求。
- 所有用户范围数据必须按真实 `user_id` 隔离；不得使用默认用户、共享 session key 或绕过权限检查。
- 只从环境变量读取密钥；不要提交 `.env`、令牌、真实学生数据或模型输出中的敏感内容。
- 新依赖必须有明确的复用价值、许可证/安全检查和锁文件更新；不要为一次性脚本添加运行时依赖。

## 数据库与模型变更

- 只使用 `app/data/alembic/versions/` 的 Alembic 迁移修改 schema；禁止新增运行时原始 SQL 迁移或 `create_all` 作为替代。
- 迁移必须可在空 PostgreSQL 数据库上升级到 `head`，并考虑已有数据、外键、幂等、回滚/恢复与 Qdrant 同步影响。
- 修改 Memory、Error Book、Profile、Learning Record 或事件处理时，保证 user ownership、事件幂等和 SQL/Qdrant 一致性；先审计再破坏性修复。

## 验证

- Python 改动：执行受影响 pytest；可用时执行 `python -m pytest tests -q`。当前仓库记录的 venv 解释器可能失效，不能伪称未运行的测试已通过。
- 前端改动：在 `frontend/` 执行 `npm run test`（有覆盖时）和 `npm run build`。
- API、迁移、认证或多服务改动：补充/更新回归测试，必要时验证 `docker compose config`、空库 Alembic 升级和相关端点。
- UI 改动：同时做桌面与移动可视检查；在采用 Playwright 之前，使用内置 Browser 工具或现有 Vitest 流程，不要偷偷引入浏览器依赖。

## 项目 Skills

- 使用 `$math-ai-change-safety` 处理跨层功能、API/Schema、迁移或学生数据改动。
- 使用 `$math-ai-model-quality-eval` 评估视觉解析、RAG、Agent 或数学回答质量。
- 使用 `$math-ai-frontend-qa` 验证 Vue 学生流程、Dashboard 或前端回归。
- UI 设计决策使用 `$ui-ux-pro-max`；需求澄清、PRD 和计划使用已有 `grill-master`、`prd-writer`、`spec-writer`、`spec-to-plan` 与 `slice-the-spec`。

不要修改 `docs/archive/` 中的历史资料、`qdrant_storage/`、`data/math_ai.db`、`.env` 或用户未提交的文件，除非任务明确要求且范围已核实。
