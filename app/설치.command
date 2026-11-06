#!/bin/bash
# 서비 설치: 이 폴더 안에 서비 전용 실행 환경(.venv)을 만들고 필요한 패키지를 설치한 뒤 서비를 켭니다.
cd "$(dirname "$0")" || exit 1
echo ""
echo "  서비(서무비서) 설치를 시작합니다..."
echo ""

PY=""
for c in python3.14 python3.13 python3.12 python3.11 python3.10 python3 /usr/local/bin/python3 /opt/homebrew/bin/python3; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
    PY="$c"; break
  fi
done

if [ -z "$PY" ]; then
  echo "  [안내] Python 3.10 이상이 필요합니다."
  echo "  1. 열리는 페이지(python.org)에서 macOS용 Python을 내려받아 설치하세요."
  echo "  2. 설치가 끝나면 이 '설치.command'를 다시 열어 주세요."
  open "https://www.python.org/downloads/macos/" 2>/dev/null
  echo ""
  read -r -p "  창을 닫으려면 Enter 키를 누르세요..." _
  exit 1
fi
echo "  사용할 Python: $("$PY" --version)"
if [ ! -x ".venv/bin/python" ]; then
  "$PY" -m venv .venv || { echo "  [오류] 실행 환경을 만들지 못했어요. 위 메시지를 캡처해서 알려 주세요."; read -r _; exit 1; }
fi
# 최신 Python에서 PyYAML 완성본이 없을 때 컴파일 도구 없이 설치되도록 합니다
export PYYAML_FORCE_LIBYAML=0
.venv/bin/python -m pip install --disable-pip-version-check -q --upgrade pip
if ! .venv/bin/python -m pip install --disable-pip-version-check -q -r requirements.txt; then
  echo ""
  echo "  [오류] 패키지 설치에 실패했습니다. 인터넷 연결을 확인하고, 위 메시지를 캡처해서 알려 주세요."
  read -r -p "  창을 닫으려면 Enter 키를 누르세요..." _
  exit 1
fi
chmod +x "서비 실행.command" "서비 끄기.command" 2>/dev/null

# 화면에 떠 있는 서비(위젯)를 쓰려면 Electron 이 필요합니다.
if [ ! -x "desktop/node_modules/electron/dist/Electron.app/Contents/MacOS/Electron" ]; then
  if command -v npm >/dev/null 2>&1; then
    echo "  화면에 띄울 서비를 준비하는 중... (처음 한 번, 2~4분)"
    (cd desktop && npm install --silent) || echo "  [안내] 위젯 준비에 실패했어요. 인터넷 연결을 확인해 주세요."
  else
    echo "  [안내] Node.js 가 없어 화면 위젯을 준비하지 못했어요."
    echo "         https://nodejs.org 에서 설치한 뒤 이 파일을 다시 열어 주세요."
  fi
fi

# 바탕화면에 바로가기(누르면 서비가 켜짐)
ln -sf "$PWD/서비 실행.command" "$HOME/Desktop/서비.command" 2>/dev/null && echo "  바탕화면에 '서비' 바로가기를 만들었어요."
echo ""
echo "  설치가 끝났습니다. 다음부터는 바탕화면의 '서비' 또는 '서비 실행.command'만 열면 됩니다."
echo "  지금 서비를 켭니다. 화면 구석에 서비가 나타나요."
echo ""
exec ./"서비 실행.command"
