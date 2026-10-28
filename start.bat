@echo off
echo ========================================================
echo   Starting Self-Healing AI Automation System
echo ========================================================
cd /d "%~dp0"
call .\venv\Scripts\activate
echo Opening Web Dashboard: http://localhost:8000
start http://localhost:8000
python main.py
pause
