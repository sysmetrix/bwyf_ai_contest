@echo off
chcp 65001 >nul
REM 서비 설치: 이 폴더 안에 서비 전용 실행 환경(.venv)을 만들고 필요한 패키지를 설치한 뒤 서비를 켭니다.
cd /d "%~dp0"
echo.
echo   서비(서무비서) 설치를 시작합니다...
echo.

where py >nul 2>&1
if %errorlevel%==0 (set "PY=py -3") else (
  where python >nul 2>&1
  if %errorlevel%==0 (set "PY=python") else (
    echo   [안내] Python 3.10 이상이 필요합니다.
    echo   1. 열리는 페이지에서 Windows용 Python을 내려받아 설치하세요.
    echo      설치할 때 "Add Python to PATH" 에 꼭 체크하세요.
    echo   2. 설치가 끝나면 이 "설치.bat" 을 다시 실행해 주세요.
    start "" "https://www.python.org/downloads/windows/"
    echo.
    pause
    exit /b 1
  )
)

echo   실행 환경을 만드는 중...
%PY% -m venv .venv
if errorlevel 1 ( echo   [오류] 실행 환경을 만들지 못했습니다. & pause & exit /b 1 )

echo   필요한 패키지를 설치하는 중... (처음 한 번만, 1~2분 걸립니다)
".venv\Scripts\python.exe" -m pip install --upgrade pip -q
".venv\Scripts\python.exe" -m pip install -r requirements.txt -q
if errorlevel 1 ( echo   [오류] 패키지 설치에 실패했습니다. 인터넷 연결을 확인해 주세요. & pause & exit /b 1 )

echo.
echo   설치가 끝났습니다. 서비를 켭니다.
echo   다음부터는 "실행.bat" 만 두 번 누르면 됩니다.
echo.
".venv\Scripts\python.exe" run.py
pause
