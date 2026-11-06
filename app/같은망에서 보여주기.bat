@echo off
chcp 65001 >nul
REM 같은 사무실 망의 다른 PC에서도 열어 볼 수 있게 서무비서를 켭니다.
REM 시연이 끝나면 창을 닫아 주세요.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo   먼저 "설치.bat" 을 실행해 주세요.
  pause & exit /b 1
)
".venv\Scripts\python.exe" run.py --host 0.0.0.0 --no-browser
pause
