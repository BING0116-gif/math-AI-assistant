# 知微 · 智能数学学习系统

面向大学高等数学的 AI 学习助手。首批内容聚焦**函数、极限与连续**，提供智能问答、错题本、知识目录、学习分析和推荐能力。

## 当前架构

```
frontend/                 Vue 3 + Vite 学生端（7 个视图页面）
app/application.py        FastAPI 应用组装入口（正式 ASGI 入口）
app/api/                  HTTP API 路由（13 个路由模块）
app/services/             业务服务（20+ 服务模块）
app/data/                 SQLAlchemy 模型、仓储和 Alembic 迁移
agent_core/               MathAgent、记忆、任务规划和策略
tools/                    Agent 工具注册与实现（9 个内置工具）
prompts/                  模型提示词（系统、ReAct、规划、分类器）
scripts/                  导入、迁移、检查和验证脚本
tests/                    自动化测试（34 个测试文件）
docs/                     当前开发文档和功能状态基线
```

## 数据存储职责

- **PostgreSQL**：用户、课程、知识点、题目、错题、记忆、画像等所有业务数据的唯一正式事实来源。后续所有 Schema 设计、迁移和约束必须以 PostgreSQL 为准。
- **SQLite**：仅作为本地开发兼容模式和测试兼容路径存在。代码层仍支持 SQLite，但 SQLite 不保证所有 PostgreSQL 特性可用。不建议将 SQLite 作为正式业务数据存储。
- **Qdrant**：只保存可重建的题目和记忆向量索引，用于语义搜索与推荐。不保存权威业务状态。
- **Redis**：只用于缓存、限流和短期任务状态，不作为永久学习数据源。
- 不使用 Chroma（已移除）。

## 本地开发启动

后端和前端是两个独立进程。

### 前置依赖

- Python 3.10+
- Node.js 18+
- PostgreSQL（生产推荐，Docker Compose 默认使用）
- Redis（可选，缓存降级可用）
- Qdrant（可选，向量搜索降级可用）
- SQLite（本地开发兼容，默认使用）

### 环境变量

复制 `.env.example` 或创建 `.env` 文件，至少需要：

```env
# 必需：JWT 签名密钥（生产环境必须替换）
JWT_SECRET_KEY=your-strong-secret-key

# 必需：数据加密密钥（生产环境必须设置）
ENCRYPTION_KEY=your-encryption-key

# AI 功能开关（默认 true，false 强制关闭 AI 功能）
AI_ENABLED=true

# 可选：DashScope API Key（无 Key 时聊天和 AI 功能不可用）
DASHSCOPE_API_KEY=your-api-key

# 可选：LLM 配置
LLM_API_BASE=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_MODEL=qwen-max

# 可选：数据库（本地开发默认 SQLite，生产必须使用 PostgreSQL）
DATABASE_URL=sqlite:///./data/math_ai.db
# DATABASE_URL=postgresql://user:pass@localhost:5432/math_ai

# 可选：Redis
REDIS_URL=redis://localhost:6379/0
```

### 启动后端

```powershell
.\venv\Scripts\python.exe -m uvicorn app.application:app --host 127.0.0.1 --port 8100 --reload
```

### 启动前端

```powershell
cd frontend
npm run dev
```

### 访问

- **学生端**：`http://127.0.0.1:5173`
- **API 文档**：`http://127.0.0.1:8100/docs`（当 `DEBUG=true` 时）
- **API 基础地址**：`http://127.0.0.1:8100`

### 兼容入口

根目录 `main.py` 保留为兼容入口，`python main.py` 仍可运行。新部署统一使用 `app.application:app`。

## Docker 启动

```powershell
# 必须设置以下环境变量
$env:DB_PASSWORD="your_db_password"
$env:ENCRYPTION_KEY="your-encryption-key"
$env:JWT_SECRET_KEY="your-jwt-secret"

docker compose up --build
```

访问：`http://127.0.0.1:3000`

Docker 服务包括：Vue/Nginx、FastAPI、PostgreSQL 15、Redis 7、Qdrant。

## 数据库迁移

正式结构迁移使用 Alembic：

```powershell
alembic -c app/data/alembic.ini upgrade head
```

当前有 5 个迁移文件，覆盖初始表结构、记忆外键、知识目录、学习内容和资源。

## 测试

### 后端测试

```powershell
.\venv\Scripts\python.exe -m pytest tests -q
```

**全量 pytest suite**：当前未成功完整执行。存在测试初始化 / fixture / 事件循环相关错误（`ValueError: I/O operation on closed file`），导致 suite 无法正常结束。

**分文件执行累计结果**（逐文件运行后加总）：675 passed, 5 skipped, 6 failed。6 个失败全部来自 `test_api_integration.py`，因认证中间件要求 token 但测试未传入。归属 Step 0.3。

### 前端测试

```powershell
cd frontend
npm test
```

当前有 5 个测试文件、38 个测试用例，覆盖：

- **Auth Store**：登录/注册/登出、token 刷新、会话恢复、session 清理
- **API Interceptor**：Authorization 统一注入、401 刷新重放、刷新失败清理
- **Router Guard**：受保护路由未登录重定向、已登录放行
- **AgentComposer**：AI 离线状态组件行为
- **MathRenderer**：普通文本 / 合法 LaTeX / 异常输入渲染

所有测试自包含，不依赖实际后端服务或 dev server。

### 前端构建

```powershell
cd frontend
npm run build
```

当前状态：通过（含 Dart Sass 弃用警告和 chunk 大小警告）

### 前端工程入口

- **Application entry**：`frontend/src/main.js`
- **Router**：`frontend/src/router/index.js`（唯一正式 Router，含认证守卫）
- **Tests**：`npm test`（Vitest）
- **Production build**：`npm run build`（Vite）
- **Build artifact**：`frontend/dist/`（不提交 Git，构建时生成）

## 当前产品范围

- **课程**：大学高等数学
- **首批内容**：函数、极限与连续（已通过启动种子数据加载）
- **题型**：选择题、判断题、数值填空题（暂未实现判题引擎）
- **高中数学**：属于旧产品方案中的早期规划，不作为当前 MVP 开发范围

## 功能状态摘要

详见 [docs/当前功能状态基线_V1.0.md](docs/当前功能状态基线_V1.0.md)

| 模块 | 状态 |
|------|------|
| 认证（注册/登录/Token） | 已贯通 |
| 课程与知识目录 | 已贯通 |
| 聊天与 AI Agent | 已贯通（AI Enabled 条件下） |
| 数学静态可视化 | 已贯通（六类受控 MathVisualSpec、T05 关键数据复核、原生 SVG） |
| 错题本 | 已贯通 |
| 记忆系统 | 已贯通 |
| 用户画像与技能 | 已贯通 |
| 推荐系统 | 已贯通 |
| 数据管理与安全 | 已贯通 |
| 前端页面 | 已贯通 |
| 练习会话 | 仅骨架 |
| 判题引擎 | 未实现 |
| 练习页面 | 未实现 |
| 间隔复习计划 | 未实现 |
| 今日任务 | 未实现 |
| 考试/组卷/变式 | 暂缓 |
