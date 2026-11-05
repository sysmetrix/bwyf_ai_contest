@echo off
chcp 65001 >nul
REM 같은 사무실 망의 다른 PC에서도 열어 볼 수 있게 인트라넷을 켭니다.
REM 시연이 끝나면 창을 닫아 주세요.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo   먼저 "실행.bat" 으로 설치해 주세요.
  pause & exit /b 1
)
".venv\Scripts\python.exe" server.py --host 0.0.0.0
pause
