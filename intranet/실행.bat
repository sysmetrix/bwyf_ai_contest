@echo off
chcp 65001 >nul
REM 가상 인트라넷을 켭니다. 처음 실행하면 필요한 것을 자동으로 설치합니다.
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo.
  echo   처음 실행입니다. 준비하는 중... ^(1~2분^)
  echo.
  where py >nul 2>&1
  if %errorlevel%==0 (py -3 -m venv .venv) else (python -m venv .venv)
  if errorlevel 1 (
    echo   [안내] Python 3.10 이상이 필요합니다. python.org 에서 설치해 주세요.
    echo   설치할 때 "Add Python to PATH" 에 꼭 체크하세요.
    start "" "https://www.python.org/downloads/windows/"
    pause & exit /b 1
  )
  ".venv\Scripts\python.exe" -m pip install --upgrade pip -q
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt -q
)

echo.
echo   가상 인트라넷을 켭니다.  http://127.0.0.1:8100
echo   끄려면 이 창에서 Ctrl+C 를 누르세요.
echo.
".venv\Scripts\python.exe" server.py
pause
