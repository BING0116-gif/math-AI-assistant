# 知微 · 智能数学学习系统

面向大学数学学习的全栈 AI 助手。项目把数学问答、图片题目理解、知识学习、错题复盘、学习画像和个性化练习放在同一条学习闭环中。

当前正式课程范围是高等数学上册完整路径（版本 3.0，98 个知识点）：**函数、极限与连续，导数与微分，中值定理与导数应用，不定积分，定积分，定积分的应用**。系统同时保留内容导入、题库审核、智能检测和自主考试等扩展能力，适合继续演进为课程化的数学学习平台。

> 当前应用版本：`1.6.0`（由 `app/config/settings.py` 提供）

## 能力概览

学生端提供：

- 智能数学对话：多轮会话、流式回答、追问与澄清、工具调用。
- 图片题目理解：识别题目和公式，并将结果交给数学解题链路。
- 知识目录：课程树、知识点学习内容、资源和掌握度。
- 错题本：错题 CRUD、错因与掌握度、复习状态、可验证变式训练。
- 学习画像：学习行为、技能聚合、画像报告和个性化建议。
- RAG 推荐：结合题目向量检索、画像和知识点进行推荐，并在向量服务不可用时降级。
- 专项练习：按课程、知识点和题型创建练习会话，提交作答并查看结果。
- 智能检测：生成检测会话、保存草稿答案、提交并查看检测报告。
- 自主考试：考试会话、断点恢复、交卷和报告，支持 AI 总结（需要可用的 AI 配置）。
- 学习闭环：今日学习概览、到期复习、学习活动和看板。

管理员端提供：

- 题库内容导入：上传源文档、解析候选题、质量审核、发布/撤回和审计记录。
- 内容 AI 分析：`mock`、`deepseek` 和预留的 `qwen` provider。
- 题目查重、题型能力检查、内容覆盖率和能力就绪度检查。
- 管理员记忆维护、画像批量刷新和题目向量同步。

当前内容导入可以识别更多题型，但专项练习、检测和考试的确定性自动判题主要支持：`choice`、`judge`、`numeric_fill`、`expression_fill`。证明题、主观题等内容可以进入审核流程，是否可自动评分取决于题目能力标记。

## 系统架构

```text
┌──────────────────────────────┐
│ Vue 3 + Vite 学生端          │  frontend/
│ Pinia / Vue Router / KaTeX    │
└──────────────┬───────────────┘
               │ /api（开发代理或 Nginx 反向代理）
┌──────────────▼───────────────┐
│ FastAPI 应用                  │  app.application:app
│ 认证 / API / 中间件 / 任务    │
├──────────────┬───────────────┤
│ 业务服务      │ Math Agent    │
│ app/services  │ agent_core/   │
└──────┬───────┴──────┬────────┘
       │              │
       │              ├── LLM / Vision API（可关闭）
       │              ├── Qdrant（题目和记忆向量）
       │              └── Redis（缓存、限流、短期任务）
       │
       └── PostgreSQL（生产事实源）
           SQLite（本地开发和测试兼容模式）
```

正式 ASGI 入口是 `app.application:app`。根目录 `main.py` 只保留兼容入口，旧脚本执行 `python main.py` 时默认监听 `8100`，新部署和开发命令请直接使用 Uvicorn 入口。

## 目录结构

```text
app/
├── api/                 FastAPI 路由（认证、聊天、知识、错题、练习、考试等）
├── config/              Pydantic Settings 和模型能力登记
├── data/                SQLAlchemy 模型、仓储、Alembic 迁移
├── middleware/          认证、安全头、输入校验、限流
├── security/            所有权、RBAC、审计和加密
├── services/            业务服务、RAG、记忆、画像、内容管线
└── application.py       应用装配和全局路由注册
agent_core/              MathAgent、提示上下文、记忆持久化和规划
tools/                   Agent 工具注册与实现
prompts/                 系统提示、ReAct、分类和动态参数提示
frontend/                Vue 3 + Vite 前端、Pinia store 和 Vitest 测试
scripts/                 seed、迁移、内容导入、运维和验证脚本
data_processing/         题目和内容处理工具
tests/                   后端单元、集成、安全、RAG 和 Agent 测试
evaluations/             模型质量评测数据和报告
ops/                     Prometheus 与数学可视化实验资产
docs/                    本地开发文档和阶段报告
```

## 数据存储边界

| 组件 | 职责 | 说明 |
|---|---|---|
| PostgreSQL | 用户、课程、知识点、题目、错题、记忆、画像、学习记录和事件 | 生产环境的唯一权威事实源 |
| SQLite | 本地开发和测试 | 默认 `data/math_ai.db`，不保证与 PostgreSQL 的全部方言特性一致 |
| Qdrant | 题目和用户记忆的向量索引 | 可重建投影，不保存权威业务状态 |
| Redis | 缓存、限流和短期任务状态 | 不作为永久学习数据源 |

题目发布后的向量同步通过 outbox 事件完成；Qdrant 或 embedding 暂时不可用时，确定性的 SQL 主链仍可运行，但推荐、查重和 readiness 可能降级。

## 快速开始：本地开发

### 前置条件

- Python 3.10 或更高版本（Docker 镜像使用 Python 3.12）。
- Node.js 18 或更高版本及 npm。
- 本地开发可以只使用 SQLite；完整运行建议准备 PostgreSQL、Redis 和 Qdrant。
- 需要真实 AI 时，准备文本模型或视觉模型对应的 API Key。

### 1. 准备 Python 环境

```powershell
py -3.10 -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

如果仓库中已经存在可用的 `venv`，可以直接复用，不必重复创建。

### 2. 配置环境变量

```powershell
Copy-Item .env.example .env
```

本地最小配置建议至少填写：

```env
APP_ENV=development
DEBUG=true
JWT_SECRET_KEY=请替换为至少32个字符的随机字符串
ENCRYPTION_KEY=请填写Fernet生成的base64密钥
AI_ENABLED=false
RAG_ENABLED=false
REDIS_URL=
```

这组配置可以在没有外部 AI、Redis 和 Qdrant 的情况下启动基础 API。需要 AI 时，把 `AI_ENABLED` 改为 `true`，并填写 `LLM_API_KEY`（文本链路）或 `DASHSCOPE_API_KEY`（视觉链路）。完整变量说明见 [.env.example](.env.example)。

可以用下面的命令生成 Fernet 密钥，再把输出写入 `ENCRYPTION_KEY`：

```powershell
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

生产环境必须使用强随机的 `JWT_SECRET_KEY` 和持久化的 `ENCRYPTION_KEY`，不能依赖默认值或启动时生成的临时密钥。

### 3. 迁移数据库并启动后端

```powershell
python -m alembic -c app/data/alembic.ini upgrade head
python -m uvicorn app.application:app --host 127.0.0.1 --port 8000 --reload
```

应用启动时会再次执行幂等的 Alembic `upgrade head`，并在数据库可用时初始化第一阶段高等数学课程目录。需要手动重建本地 SQLite 开发库时，使用带确认保护的脚本：

```powershell
python scripts/reset_dev_db.py --dry-run
python scripts/reset_dev_db.py --yes
```

### 4. 启动前端

另开一个 PowerShell 窗口：

```powershell
cd frontend
npm ci
npm run dev
```

Vite 默认监听 `http://127.0.0.1:5173`，并把 `/api` 代理到 `http://127.0.0.1:8000`。后端地址不同步时可以覆盖：

```powershell
$env:VITE_API_TARGET = "http://127.0.0.1:8100"
npm run dev
```

访问地址：

- 学生端：<http://127.0.0.1:5173>
- API 根状态：<http://127.0.0.1:8000/>
- 健康检查：<http://127.0.0.1:8000/api/health>
- 详细健康检查：<http://127.0.0.1:8000/api/health/detailed>
- 就绪检查：<http://127.0.0.1:8000/api/health/ready>
- Swagger / ReDoc：仅 `DEBUG=true` 时开放 `/docs` 和 `/redoc`
- OpenAPI JSON：<http://127.0.0.1:8000/openapi.json>

### 本地开发常用脚本

```powershell
# 初始化第一阶段函数、极限与连续知识目录
python scripts/seed_calculus_knowledge.py

# 准备上册完整路径（98 知识点）3.0 草稿
python scripts/seed_calculus_knowledge.py --include-phase5-draft

# 通过逐章 content gates 发布 3.0 为默认版本（幂等，可重复执行）
python scripts/seed_calculus_knowledge.py --publish-phase5

# 查看题库和 Qdrant 的只读对账结果
python scripts/operations/recovery.py qdrant-sync

# 编译检查
python -m compileall -q app agent_core scripts tests
```

## Docker Compose

Compose 会启动五个服务：FastAPI `web`、Nginx `frontend`、PostgreSQL 15、Redis 7 和 Qdrant。

先在 `.env` 或当前 PowerShell 会话中设置 Compose 必填项：

```powershell
$env:DB_PASSWORD = "change-this-password"
$env:JWT_SECRET_KEY = "change-this-to-a-long-random-secret"
$env:ENCRYPTION_KEY = "生成的Fernet密钥"
docker compose up --build
```

默认端口：

| 服务 | 容器端口 | 宿主端口 |
|---|---:|---:|
| Frontend / Nginx | 80 | 3000 |
| FastAPI | 8000 | 8000 |
| PostgreSQL | 5432 | 5432 |
| Qdrant HTTP | 6333 | 16333 |
| Qdrant gRPC | 6334 | 16334 |
| Redis | 6379 | 仅 Compose 内网 |

启动后访问 <http://127.0.0.1:3000>。`web` 容器的入口脚本会先执行 Alembic 迁移，再启动 `app.application:app`。如需只校验配置：

```powershell
docker compose config
```

### 在本机启用对话内数学动画

MathAnimator 是聊天 Agent 的教学工具，不是独立页面。Windows 本地完整启动请使用：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start_with_animation.ps1
```

脚本会启动 `db/redis/qdrant/web/frontend`，用宿主机 Node 构建前端、构建或复用审核过的固定模板 renderer，
并在宿主机后台启动专用动画 worker。它只为本次进程注入动画开关和镜像 digest，
不会修改 `.env`；FastAPI 容器不会获得 Docker socket。脚本会为前端和 API 避开 Windows 动态保留/占用端口并在
完成时显示实际访问地址。首次构建 renderer 会耗时较长。

状态和停止命令：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/animation_status.ps1
powershell -ExecutionPolicy Bypass -File scripts/stop_with_animation.ps1
```

启用后，在聊天中提问“为什么导数是切线斜率”或明确要求动画演示时，Agent 会在适合的
固定模板范围内创建动画，并把生成状态和视频放在当前 AI 回复中。当前可信模板只覆盖
`y=x²` 在 `x=1` 的割线趋近切线，以及 `y=x²` 在 `[0,2]` 的黎曼和。

如果只想验证离线 API，可在 Compose 环境中设置 `AI_ENABLED=false` 和 `RAG_ENABLED=false`；真实内容 AI 仍由 `CONTENT_AI_PROVIDER` 单独控制。

## 关键配置说明

| 变量 | 默认/示例 | 作用 |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./data/math_ai.db` | 同步数据库 URL；生产使用 PostgreSQL |
| `ASYNC_DATABASE_URL` | 留空自动推导 | 异步 SQLAlchemy URL，建议生产显式设置 `postgresql+asyncpg://...` |
| `AI_ENABLED` | `true` | 是否初始化远程 AI runtime；关闭后 AI API 返回结构化 503 |
| `LLM_API_KEY` | 留空 | 主文本模型 Key，优先于 `DASHSCOPE_API_KEY` |
| `LLM_API_BASE` / `LLM_MODEL` | DeepSeek 或兼容端点 | 数学问答、Agent 和文本解释 |
| `DASHSCOPE_API_KEY` | 留空 | 视觉链路（`qwen-vl-*`）及文本链路的兼容 fallback |
| `VISION_MODEL` | `qwen-vl-plus` | 图片和公式识别模型 |
| `RAG_ENABLED` | `true` | 启用推荐和向量链路 |
| `QDRANT_HOST` / `QDRANT_PORT` | `localhost` / `6333` | Qdrant 连接地址 |
| `VECTOR_EMBEDDING_MODEL` | `BAAI/bge-small-zh-v1.5` | 题目和记忆 embedding 模型 |
| `REDIS_URL` | `redis://localhost:6379/0` | 缓存、限流和短期任务 |
| `CONTENT_AI_PROVIDER` | `mock` | 内容审核 AI：`mock` / `deepseek` / `qwen`（qwen 当前为 stub） |
| `DEEPSEEK_API_KEY` | 留空 | `CONTENT_AI_PROVIDER=deepseek` 时使用 |
| `MINERU_EXECUTABLE` | 留空 | 可选的 MinerU 独立解析器路径 |
| `METRICS_ENABLED` | `true` | 是否提供 `/metrics` |
| `METRICS_BEARER_TOKEN` | 留空 | 设置后 `/metrics` 需要 Bearer Token |

文本模型和视觉模型是两条独立链路。没有 API Key 时应用仍可以启动，非 AI 功能继续工作；依赖 AI 的端点会返回 `AI_UNAVAILABLE`，前端会显示离线状态。

## API 分组

所有业务接口都以 `/api` 开头，前端客户端会统一注入和刷新 JWT。

| 分组 | 典型路径 | 用途 |
|---|---|---|
| 认证 | `/api/auth/register`、`/api/auth/login`、`/api/auth/refresh` | 注册、登录和令牌轮换 |
| 对话 | `/api/chat`、`/api/chat/multimodal`、`/api/chat/sessions` | 文本/图片问答和会话 |
| 知识 | `/api/knowledge/courses`、`/api/knowledge/points/{id}/learning` | 课程目录和学习内容 |
| 错题 | `/api/error-book`、`/api/error-book/{id}/review` | 错题和复习状态 |
| 画像 | `/api/profile/me`、`/api/profile/me/report` | 画像、技能和建议 |
| 推荐 | `/api/recommend/questions`、`/api/recommend/vector-search` | RAG 推荐和语义检索 |
| 练习 | `/api/practice/sessions` | 专项练习会话 |
| 检测 | `/api/assessments/sessions` | 智能检测会话 |
| 考试 | `/api/exams/sessions` | 自主考试、恢复和报告 |
| 学习闭环 | `/api/learning/today`、`/api/learning/reviews/due` | 今日任务、复习和活动 |
| 管理内容 | `/api/admin/content/*` | 导入、审核、发布和内容 AI |
| 健康 | `/api/health`、`/api/health/ready` | 存活、依赖和就绪探针 |

以运行时的 OpenAPI 为准，不建议把过时的接口列表复制到业务代码或外部文档中。`/api/papers/*` 仍保留兼容接口，但路由已标记 deprecated。

## 数据库迁移和内容初始化

只通过 `app/data/alembic/versions/` 中的 Alembic 迁移修改数据库结构，不要在运行时使用 `create_all` 或手工 SQL 代替迁移。

```powershell
python -m alembic -c app/data/alembic.ini current
python -m alembic -c app/data/alembic.ini upgrade head
python -m alembic -c app/data/alembic.ini downgrade -1
```

生产数据库推荐 PostgreSQL；迁移前请完成备份，并确认 `DATABASE_URL` / `ASYNC_DATABASE_URL` 指向目标环境。Qdrant 只保存可重建索引，迁移或发布后应通过 outbox 和只读对账检查 SQL 与向量索引的一致性。

## 测试与质量门槛

### 后端

```powershell
python -m pytest tests -q
```

本 README 更新时在 Windows 本地执行的结果是：**1168 passed、5 skipped、8 failed、8 warnings、19 subtests passed**。失败集中在 `test_llm_robustness.py`、`test_question_dedup.py` 和 `test_readiness_matrix.py` 的日志/能力断言，属于全量运行时的既有测试隔离问题（这三个文件单独执行时全部通过），不能视为全量测试通过；提交前请先确认这些失败是否属于当前环境编码或实现回归。

### 前端

```powershell
cd frontend
npm test
npm run build
```

本次验证结果：**21 个测试文件、76 个测试通过；生产构建通过**。构建仍会提示 Sass legacy API、`authStore` 动态/静态导入和大 chunk（约 1 MB）警告，这些是后续性能与工程清理项，不是构建失败。

### CI

`.github/workflows/ci.yml` 包含后端测试和覆盖率、前端测试与构建、Compose 空库冷启动和 Docker 构建。CI 的后端 job 会关闭真实 AI（`AI_ENABLED=false`），因此无需在 CI 中提交任何模型密钥。

## 安全与数据隔离约定

- 密钥只从环境变量读取；`.env`、真实学生数据、模型输出和运行时数据不得提交。
- 所有用户范围数据必须按认证得到的 `user_id` 隔离，不能使用默认用户或共享 session key。
- JWT、敏感字段加密、CSP、安全头、速率限制、RBAC 和审计由后端统一处理。
- PostgreSQL 是生产事实源，Qdrant 是可重建投影；删除用户数据时要同时考虑 SQL、缓存、事件和向量索引。
- 内容 AI 默认是 `mock`，mock 结果默认禁止正式发布；只有在明确的开发/联调场景才设置 `ALLOW_MOCK_PUBLISH=true`。

## 已知边界

- 课程当前覆盖高等数学上册（第 1–6 章，98 知识点）；第 7 章及之后（微分方程、多元微积分等）尚未建设，高中数学不属于当前正式产品范围。
- AI、Qdrant、Redis 都可以降级，但降级时对应能力会返回结构化错误或减少推荐能力。
- `CONTENT_AI_PROVIDER=qwen` 目前是预留 stub；需要真实内容分析时使用 `deepseek` 并配置 `DEEPSEEK_API_KEY`。
- 前端生产包仍有较大的 vendor chunk，适合后续继续做路由和依赖拆分。
- 全量后端测试当前存在 8 个失败，发布前应处理或明确豁免原因。

## 进一步阅读

- [docs/README.md](docs/README.md)：本地架构、开发、API 和运维文档索引。
- [docs/当前功能状态基线_V1.0.md](docs/当前功能状态基线_V1.0.md)：功能完成度和已知风险基线。
- [docs/CODE_WIKI.md](docs/CODE_WIKI.md)：代码导航和模块说明。
- [AGENTS.md](AGENTS.md)：仓库约定、数据迁移和验证要求。

## 贡献流程

1. 先确认改动是否跨越 API、数据模型、记忆/画像、Qdrant 或前端契约。
2. 数据库结构只新增 Alembic 迁移，并补充回滚、已有数据和索引一致性检查。
3. API 变更同步更新 Pydantic 模型、前端 API 封装、文档和回归测试。
4. Python 改动运行受影响的 pytest；前端改动运行 `npm test` 和 `npm run build`。
5. 不提交 `.env`、数据库文件、Qdrant 存储、`frontend/dist`、运行时上传内容或本地测试产物。
