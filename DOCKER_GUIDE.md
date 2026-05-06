# 🐳 数学AI助手 Docker 开发指南

## 🚀 快速开始（3步）

### 1️⃣ 确保 Docker Desktop 正在运行
检查右下角任务栏，Docker 鲸鱼图标是否显示为绿色（Engine running）。

### 2️⃣ 在项目根目录打开终端
在 VS Code 中，按 `Ctrl+` 打开终端，确保你在项目根目录（有 `docker-compose.yml` 的目录）。

### 3️⃣ 启动服务
```bash
docker-compose up --build
```

首次运行会下载镜像，需要 5-10 分钟，请耐心等待。

## 🌐 访问应用

启动成功后，浏览器打开：
```
http://localhost:8000
```

## 📋 常用命令

| 命令 | 作用 |
|------|------|
| `docker-compose up` | 启动服务 |
| `docker-compose up --build` | 重新构建镜像并启动 |
| `docker-compose down` | 停止并删除服务 |
| `docker-compose logs -f` | 查看实时日志 |

## 👥 团队协作

**队友只需这样做：**
1. 克隆项目：`git clone <仓库地址>`
2. 创建 `.env` 文件（从 `.env.example` 复制）
3. 运行：`docker-compose up`

就可以了！所有人的环境完全一致！

## ⚠️ 常见问题

### 问题：端口被占用
**解决**：修改 `docker-compose.yml` 中的端口映射，例如改为 `"8001:8000"`。

### 问题：构建失败
**解决**：检查网络连接，或者使用国内镜像源。

---

## 💡 本地开发备选方案

如果 Docker 还是遇到问题，先用本地环境开发：

```bash
python -m venv venv
venv\Scripts\activate.bat
pip install -r requirements.txt
python main.py
```
