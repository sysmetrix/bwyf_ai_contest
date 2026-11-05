@echo off
chcp 65001 >nul
REM 서비 실행: 설치가 끝난 뒤에는 이 파일만 두 번 누르면 됩니다.
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo.
  echo   [안내] 아직 설치가 안 됐습니다. 먼저 "설치.bat" 을 실행해 주세요.
  echo.
  pause
  exit /b 1
)

echo.
echo   서비를 켭니다. 브라우저가 자동으로 열립니다.
echo   끄려면 이 창에서 Ctrl+C 를 누르거나 "끄기.bat" 을 실행하세요.
echo.
".venv\Scripts\python.exe" run.py
if errorlevel 1 (
  echo.
  echo   [오류] 서비를 켜지 못했습니다. 위 메시지를 확인해 주세요.
  echo   포트가 쓰이고 있으면 "끄기.bat" 을 먼저 실행해 보세요.
)
pause
