# 启动说明

## 本地开发

后端和前端现在是两个独立进程。后端不再托管 `static/` 或 `frontend/dist/`，前端由 Vite 开发服务器提供。

### 1. 启动后端

Windows：

```powershell
.\venv\Scripts\python.exe -m uvicorn app.application:app --host 127.0.0.1 --port 8100 --reload
```

也可以双击根目录的 `start.bat`，但它默认不开启热重载。

### 2. 启动前端

```powershell
cd frontend
npm run dev
```

浏览器访问 `http://127.0.0.1:5173`。Vite 会把 `/api` 请求代理到 `http://127.0.0.1:8100`。
如需使用其他本地后端端口，可设置 `BACKEND_PORT`，并将前端的 `VITE_API_TARGET` 设置为对应地址。

### 3. 只验证后端

```powershell
.\venv\Scripts\python.exe -m pytest tests -q
```

## Docker

```powershell
docker compose up --build
```

Docker 中：

- `web`：后端 API，端口 8000
- `frontend`：Nginx + Vue 构建产物，端口 3000
- `db`：PostgreSQL
- `redis`：缓存
- `qdrant`：题库向量搜索

浏览器访问 `http://127.0.0.1:3000`。

## 入口说明

真正的 FastAPI 应用入口是：

```text
app.application:app
```

根目录的 `main.py` 只是兼容入口，旧命令仍可用：

```powershell
.\venv\Scripts\python.exe main.py
```

但新代码、部署文件和生产启动统一使用 `app.application:app`。

## 题库数据

- SQLite/PostgreSQL：保存题目完整字段，用于列表、详情、筛选和后续教师端管理
- Qdrant `math_questions`：保存题目向量和检索元数据，用于语义搜索和推荐
- Chroma：已移除，不再作为项目数据源

如需把 Qdrant 题目重新同步到本地 SQLite：

```powershell
.\venv\Scripts\python.exe scripts\migration\sync_qdrant_to_sqlite.py
```
