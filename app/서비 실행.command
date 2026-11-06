#!/bin/bash
# 서비 켜기 — 화면 구석에 서비가 나타납니다. (브라우저는 쓰지 않습니다)
cd "$(dirname "$(readlink "$0" 2>/dev/null || echo "$0")")" || exit 1

ELEC="desktop/node_modules/electron/dist/Electron.app/Contents/MacOS/Electron"
if [ ! -x "$ELEC" ]; then
  echo "  아직 준비가 안 됐어요. '설치.command'를 먼저 열어 주세요."
  read -r -p "  창을 닫으려면 Enter 키를 누르세요..." _
  exit 1
fi

# 이미 떠 있으면 하나만 띄웁니다. (이 스크립트 자신은 세지 않도록 실행파일 경로로 봅니다)
if pgrep -f "Electron.app/Contents/MacOS/Electron" >/dev/null 2>&1; then
  echo "  서비가 이미 화면에 떠 있어요."
  sleep 1
  exit 0
fi

cd desktop || exit 1
exec "node_modules/electron/dist/Electron.app/Contents/MacOS/Electron" .
