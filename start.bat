@echo off
chcp 65001 >nul
echo ========================================
echo    数学 AI 助手 - 一键启动脚本
echo ========================================
echo.

echo [1/4] 正在清理旧进程...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8000 ^| findstr LISTENING') do (
    echo     发现占用端口的进程: %%a
    taskkill /F /PID %%a >nul 2>&1
)
echo     ✓ 清理完成
echo.

echo [2/4] 正在检查前端资源...
if not exist "frontend\dist\index.html" (
    echo     未发现构建的前端资源，正在构建...
    cd frontend
    call npm run build
    cd ..
    echo     ✓ 前端构建完成
) else (
    echo     ✓ 前端资源已就绪
)
echo.

echo [3/4] 正在启动服务器...
echo.
echo     访问地址: http://localhost:8000
echo     API 文档: http://localhost:8000/docs
echo     按 Ctrl+C 停止服务器
echo.
echo ----------------------------------------
python main.py

pause
