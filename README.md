# 数学 AI 助手

面向高等数学学习的 AI 助手，提供智能问答、错题本、知识目录、学习内容和题库检索能力。

## 当前架构

```text
frontend/                 Vue 3 + Vite 学生端
app/application.py        FastAPI 应用组装入口
app/api/                  HTTP API
app/services/             业务服务
app/data/                 SQLAlchemy 模型、仓储和 Alembic
agent_core/               Agent、记忆和任务规划
tools/                    Agent 工具注册与实现
prompts/                  模型提示词
scripts/                  导入、迁移、检查和验证脚本
qdrant_storage/           本地 Qdrant 数据（题库向量）
data/math_ai.db           本地 SQLite 数据（题库主数据）
docs/                     当前开发文档
docs/archive/             历史文档和旧迁移材料
tests/                    自动化测试
```

## 数据存储职责

- SQLite/PostgreSQL：保存题目完整字段，负责列表、详情、筛选和后续教师端管理。
- Qdrant `math_questions`：保存题目向量和检索元数据，负责语义搜索与推荐。
- Chroma：已移除，不再作为项目数据源。

当前本地题库已经同步：SQLite 和 Qdrant 均为 176 道题。

## 本地开发启动

后端和前端是两个独立进程。

启动后端：

```powershell
.\venv\Scripts\python.exe -m uvicorn app.application:app --host 127.0.0.1 --port 8000 --reload
```

启动前端：

```powershell
cd frontend
npm run dev
```

访问学生端：`http://127.0.0.1:5173`

API 地址：`http://127.0.0.1:8000`

当 `.env` 中 `DEBUG=true` 时，API 文档地址为 `http://127.0.0.1:8000/docs`。

Windows 下也可以运行根目录的 `start.bat`，它只启动后端；前端需要在另一个终端运行 `npm run dev`。

## Docker 启动

```powershell
docker compose up --build
```

访问：`http://127.0.0.1:3000`

Docker 服务包括：Vue/Nginx、FastAPI、PostgreSQL、Redis 和 Qdrant。

## 题库脚本

导入题库：

```powershell
python scripts/import/import_pdf.py questions.pdf
python scripts/import/batch_import.py data/template_import_questions.csv
python scripts/import/vl_import.py questions.pdf --preview
```

同步 Qdrant 到本地 SQLite：

```powershell
python scripts/migration/sync_qdrant_to_sqlite.py
```

检查 Qdrant：

```powershell
python scripts/inspection/inspect_qdrant.py
```

## 数据库迁移

正式结构迁移统一使用 Alembic：

```powershell
alembic -c app/data/alembic.ini upgrade head
```

旧 SQL 迁移文件已经归档到 `docs/archive/migrations/`，不再作为运行迁移入口。

`app/data/legacy_migrations.py` 仅用于一次性迁移旧 JSON 用户/错题数据，不负责数据库 schema 迁移。

## 测试

```powershell
.\venv\Scripts\python.exe -m pytest tests -q
```

前端构建：

```powershell
cd frontend
npm run build
```

## 兼容入口

正式 ASGI 入口是：

```text
app.application:app
```

根目录 `main.py` 仍保留为兼容入口，旧命令 `python main.py` 仍可运行，但新部署统一使用 `app.application:app`。
