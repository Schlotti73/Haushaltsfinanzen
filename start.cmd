@echo off
cd /d "%~dp0"

echo Starte Backend...
start "HHP Backend" cmd /k "cd backend && .venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"

timeout /t 2 /nobreak >nul

echo Starte Frontend...
start "HHP Frontend" cmd /k "cd frontend && "C:\Program Files\nodejs\node.exe" node_modules/vite/bin/vite.js --port 5173"

echo.
echo Backend:  http://localhost:8000
echo Frontend: http://localhost:5173
