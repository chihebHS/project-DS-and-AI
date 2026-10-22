@echo off
REM Lance le backend (qui demarre lui-meme le serveur MCP) et le frontend de RecrutIA
start "RecrutIA - Backend" cmd /k ".venv\Scripts\python -m uvicorn app.main:app --port 8002 --app-dir backend"
start "RecrutIA - Frontend" cmd /k "cd frontend && npm run dev"
timeout /t 8 >nul
start http://localhost:5175
