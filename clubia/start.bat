@echo off
REM Lance le backend et le frontend de ClubIA dans deux fenetres
start "ClubIA - Backend" cmd /k "cd backend && .venv\Scripts\python -m uvicorn app.main:app --reload --port 8001"
start "ClubIA - Frontend" cmd /k "cd frontend && npm run dev"
timeout /t 5 >nul
start http://localhost:5174
