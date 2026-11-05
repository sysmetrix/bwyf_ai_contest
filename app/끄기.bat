@echo off
chcp 65001 >nul
REM 켜져 있는 서비를 끕니다.
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" run.py --stop
) else (
  echo   아직 설치가 안 됐습니다.
)
pause
