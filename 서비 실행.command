#!/bin/bash
# 서비 켜기 (이 창을 닫거나 Control+C를 누르면 꺼집니다)
cd "$(dirname "$(readlink "$0" 2>/dev/null || echo "$0")")" || exit 1
if [ ! -x ".venv/bin/python" ]; then
  echo "  아직 설치되지 않았어요. '설치.command'를 먼저 열어 주세요."
  read -r -p "  창을 닫으려면 Enter 키를 누르세요..." _
  exit 1
fi
exec .venv/bin/python run.py
