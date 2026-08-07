@echo off
chcp 65001 >nul
echo Math AI Assistant backend
echo.

if not exist "venv\Scripts\python.exe" (
    echo [ERROR] venv\Scripts\python.exe not found.
    echo Create the environment and install requirements.txt first.
    pause
    exit /b 1
)

echo Starting backend at http://127.0.0.1:8000
echo API docs are available when DEBUG=true: http://127.0.0.1:8000/docs
echo Press Ctrl+C to stop.
echo.

venv\Scripts\python.exe -m uvicorn app.application:app --host 127.0.0.1 --port 8000
pause
