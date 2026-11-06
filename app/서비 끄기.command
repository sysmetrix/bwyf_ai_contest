#!/bin/bash
# 서비 끄기 — 화면의 서비와 뒤에서 도는 서버를 함께 끕니다.
cd "$(dirname "$0")" || exit 1
pkill -f "desktop/node_modules/electron" 2>/dev/null
if [ -x ".venv/bin/python" ]; then .venv/bin/python run.py --stop 2>/dev/null; fi
echo "  서비를 껐습니다."
sleep 1
