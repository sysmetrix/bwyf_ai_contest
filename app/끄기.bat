@echo off
chcp 65001 >nul
REM 켜져 있는 서비를 끕니다. 화면의 서비와 뒤에서 도는 서버를 함께 끕니다.
cd /d "%~dp0"

REM 화면 위젯 끄기
taskkill /F /IM electron.exe >nul 2>&1

REM 서버 끄기 (설치판은 python\, 소스에서 쓸 때는 .venv\)
if exist "python\python.exe" (
  "python\python.exe" run.py --stop
) else if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" run.py --stop
) else (
  python run.py --stop
)
REM 서비가 띄운 AI 끄기 (설치판에 함께 담긴 것만. 따로 깔아 쓰시는 것은 건드리지 않습니다)
if exist "ollama\ollama.exe" (
  taskkill /F /IM ollama.exe >nul 2>&1
)

echo   서비를 껐습니다.
timeout /t 2 >nul
