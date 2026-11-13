@echo off
REM Lance le backend (qui démarre lui-même le serveur MCP en stdio) et le frontend de ClubIA
start "ClubIA - Backend" cmd /k "cd backend && .venv\Scripts\python -m uvicorn app.main:app --reload --reload-dir app --port 8001"
start "ClubIA - Frontend" cmd /k "cd frontend && npm run dev"
timeout /t 6 >nul
start http://localhost:5174
