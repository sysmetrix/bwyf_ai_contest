@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist "python\python.exe" (
    echo.
    echo  [오류] 압축을 먼저 풀어 주세요. 압축 파일 안에서 바로 실행하면 설치되지 않습니다.
    echo  압축 파일을 마우스 오른쪽 버튼으로 눌러 "압축 풀기"를 한 뒤, 풀린 폴더에서 다시 실행하세요.
    echo.
    pause
    exit /b 1
)
"python\python.exe" tools\install.py
