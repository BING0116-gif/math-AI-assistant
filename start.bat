@echo off
chcp 65001 >nul
echo ========================================
echo    数学 AI 助手 - 开发模式启动脚本
echo ========================================
echo.

:: ═══════════════════════════════════════════
:: [1/5] 激活 Python 虚拟环境
:: ═══════════════════════════════════════════
echo [1/5] 激活 Python 虚拟环境...
if not exist "venv\Scripts\activate.bat" (
    echo     [!] 未找到 venv，正在创建虚拟环境...
    python -m venv venv
    if errorlevel 1 (
        echo     [×] 创建虚拟环境失败，请确认已安装 Python 3.10+
        pause
        exit /b 1
    )
    echo     ✓ 虚拟环境创建完成
)
call venv\Scripts\activate.bat
echo     ✓ 虚拟环境已激活
echo.

:: ═══════════════════════════════════════════
:: [2/5] 检查 Python 依赖（仅首次或变更时安装）
:: ══════════════════════════════════════════
echo [2/5] 检查 Python 依赖...
venv\Scripts\python -c "import fastapi, langchain, qdrant_client, sqlalchemy" 2>nul
if errorlevel 1 (
    echo     [!] 检测到缺失依赖，正在安装...
    pip install -r requirements.txt --quiet
    if errorlevel 1 (
        echo     [!] 依赖安装失败，请检查网络连接
        pause
        exit /b 1
    )
    echo     ✓ 依赖安装完成
) else (
    echo     ✓ 依赖已就绪（跳过安装）
)
echo.

:: ═══════════════════════════════════════════
:: [3/5] 检查前端资源（仅首次或变更时构建）
:: ═══════════════════════════════════════════
echo [3/5] 检查前端资源...
if not exist "frontend\node_modules" (
    echo     [!] 未安装前端依赖，正在安装...
    cd frontend
    call npm install
    cd ..
    echo     ✓ 前端依赖安装完成
)
if not exist "frontend\dist\index.html" (
    echo     [!] 未发现构建产物，正在构建前端...
    cd frontend
    call npm run build
    cd ..
    if errorlevel 1 (
        echo     [!] 前端构建失败，请检查 Node.js 是否已安装
        pause
        exit /b 1
    )
    echo     ✓ 前端构建完成
) else (
    echo     ✓ 前端资源已就绪（跳过构建）
)
echo.

:: ═══════════════════════════════════════════
:: [4/5] 清理旧进程
:: ═══════════════════════════════════════════
echo [4/5] 清理旧进程...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8000 ^| findstr LISTENING') do (
    echo     发现占用端口的进程: %%a
    taskkill /F /PID %%a >nul 2>&1
)
echo     ✓ 清理完成
echo.

:: ═══════════════════════════════════════════
:: [5/5] 启动服务器
:: ═══════════════════════════════════════════
echo [5/5] 启动服务器...
echo.
echo     ┌─────────────────────────────────────┐
echo     │  访问地址: http://localhost:8000    │
echo     │  API 文档: http://localhost:8000/docs│
echo     │  按 Ctrl+C 停止服务器               │
echo     └─────────────────────────────────────┘
echo.
echo ----------------------------------------

python main.py

pause
