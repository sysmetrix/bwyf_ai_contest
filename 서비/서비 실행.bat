@echo off
chcp 65001 >nul
REM 서비를 화면에 띄웁니다. 서버는 서비가 알아서 켭니다.
cd /d "%~dp0"
if exist "desktop\node_modules\electron\dist\electron.exe" (
  start "" "desktop\node_modules\electron\dist\electron.exe" "desktop"
) else (
  echo   화면 위젯이 들어 있지 않아 서버만 켭니다.
  "python\python.exe" run.py --browser
  pause
)
