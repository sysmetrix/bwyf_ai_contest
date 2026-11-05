#!/bin/bash
# 켜져 있는 서비 끄기
cd "$(dirname "$0")" || exit 1
if [ -x ".venv/bin/python" ]; then .venv/bin/python run.py --stop; else echo "  설치된 서비가 없어요."; fi
sleep 2
