#!/bin/bash
set -e

# 数学 AI 助手 — Docker 入口点脚本
# 负责：1. 执行 Alembic 数据库迁移 2. 启动 uvicorn 服务器

echo "========================================"
echo "  数学 AI 助手 - Docker 启动"
echo "========================================"

# 确定数据库 URL（从环境变量或默认值）
DB_URL="${DATABASE_URL:-${ASYNC_DATABASE_URL:-sqlite:///./data/math_ai.db}}"
echo "[1/3] 数据库 URL: ${DB_URL}"

# 执行 Alembic 迁移
echo "[2/3] 执行数据库迁移 (alembic upgrade head)..."
ALEMBIC_INI="app/data/alembic.ini"
if [ -f "$ALEMBIC_INI" ]; then
    export DATABASE_URL="${DB_URL}"
    alembic -c "$ALEMBIC_INI" upgrade head
    echo "  ✓ 迁移完成"
else
    echo "  ! 未找到 alembic.ini，跳过迁移"
fi

# 启动 uvicorn 服务器
echo "[3/3] 启动 uvicorn 服务器..."
echo ""
echo "    ┌─────────────────────────────────────┐"
echo "    │  访问地址: http://0.0.0.0:8000     │"
echo "    │  API 文档: http://0.0.0.0:8000/docs │"
echo "    └─────────────────────────────────────┘"
echo ""

exec python -m uvicorn main:app --host 0.0.0.0 --port 8000