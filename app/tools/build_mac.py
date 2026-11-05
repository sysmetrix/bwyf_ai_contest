"""맥(macOS)용 설치판을 만듭니다: python tools/build_mac.py

결과: (프로젝트 상위 폴더)/서비_Mac설치판_v버전.zip
맥에는 python.org의 Python 3.10 이상이 있어야 합니다. 압축을 풀고 '설치.command'를 열면
서비 전용 실행 환경(.venv)을 폴더 안에 만들고 패키지를 설치한 뒤 서비를 켭니다.
Windows 설치판과 같은 규칙으로 파일을 고릅니다(예시 기관만, API 키·질문 기록 제외).
"""
from __future__ import annotations

import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_windows import ROOT, _clean_config, _skip, _version  # noqa: E402

FIND_PY = r'''
PY=""
for c in python3.14 python3.13 python3.12 python3.11 python3.10 python3 /usr/local/bin/python3 /opt/homebrew/bin/python3; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
    PY="$c"; break
  fi
done
'''

INSTALL = r'''#!/bin/bash
# 서비 설치: 이 폴더 안에 서비 전용 실행 환경(.venv)을 만들고 필요한 패키지를 설치한 뒤 서비를 켭니다.
cd "$(dirname "$0")" || exit 1
echo ""
echo "  서비(서무비서) 설치를 시작합니다..."
echo ""
''' + FIND_PY + r'''
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
# 바탕화면에 바로가기(누르면 서비가 켜짐)
ln -sf "$PWD/서비 실행.command" "$HOME/Desktop/서비.command" 2>/dev/null && echo "  바탕화면에 '서비' 바로가기를 만들었어요."
echo ""
echo "  설치가 끝났습니다. 다음부터는 바탕화면의 '서비' 또는 '서비 실행.command'만 열면 됩니다."
echo "  지금 서비를 켭니다. (이 창을 닫거나 Control+C를 누르면 서비가 꺼져요)"
echo ""
exec .venv/bin/python run.py
'''

RUN = r'''#!/bin/bash
# 서비 켜기 (이 창을 닫거나 Control+C를 누르면 꺼집니다)
cd "$(dirname "$(readlink "$0" 2>/dev/null || echo "$0")")" || exit 1
if [ ! -x ".venv/bin/python" ]; then
  echo "  아직 설치되지 않았어요. '설치.command'를 먼저 열어 주세요."
  read -r -p "  창을 닫으려면 Enter 키를 누르세요..." _
  exit 1
fi
exec .venv/bin/python run.py
'''

STOP = r'''#!/bin/bash
# 켜져 있는 서비 끄기
cd "$(dirname "$0")" || exit 1
if [ -x ".venv/bin/python" ]; then .venv/bin/python run.py --stop; else echo "  설치된 서비가 없어요."; fi
sleep 2
'''

GUIDE = """서비(서무비서) 맥 설치 안내
==========================

필요한 것
- macOS 12 이상, 인터넷 연결(처음 설치할 때만)
- Python 3.10 이상: https://www.python.org/downloads/macos/ 에서 macOS용을 받아 설치
  (맥에 기본으로 들어 있는 python3는 버전이 낮을 수 있어요. 설치 파일이 알아서 확인해요)

설치
1. 이 압축 파일을 '응용 프로그램'이나 '문서' 폴더에 풀어 주세요. (다운로드 폴더에 두어도 되지만 지우지 마세요)
2. 풀린 '서비' 폴더 안의 '설치.command'를 Control 키를 누른 채 클릭(또는 오른쪽 클릭) → '열기'를 누르세요.
   - 처음에는 "확인되지 않은 개발자" 경고가 떠요. 이때 '열기'를 누르면 됩니다.
   - 그래도 막히면: 시스템 설정 → 개인정보 보호 및 보안 → 아래쪽 '그래도 열기'
3. 터미널 창이 열리고 설치가 진행돼요(1~3분). 끝나면 브라우저에 서비가 열립니다.

다음부터
- 바탕화면의 '서비'를 열면 서비가 켜지고 브라우저가 열려요.
- 켜져 있는 동안 터미널 창이 하나 떠 있어요. 그 창을 닫거나 Control+C를 누르면 서비가 꺼져요.
- '서비 끄기.command'로 끌 수도 있어요.

데이터
- 만든 기관·규정·서식·설정은 모두 이 '서비' 폴더 안에 저장돼요. 폴더째 옮기면 그대로 옮겨져요.
- Windows PC와 주고받을 때는 서비의 [설정 → PC 옮기기]에서 .seobi 파일로 옮기면 돼요(양쪽 호환).

Windows와 다른 점
- 작업 표시줄(메뉴 막대) 아이콘 대신 터미널 창이 떠 있어요.
- 자동 업데이트는 Windows 설치판에서만 돼요. 맥은 새 압축 파일을 받아 이 폴더에 덮어쓰면 됩니다
  (data 폴더, config.yaml, .env는 남겨 두세요).
"""


def _add(z: zipfile.ZipFile, arc: str, data: bytes, executable: bool = False) -> None:
    info = zipfile.ZipInfo(arc, date_time=(2026, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3  # 유닉스: 맥에서 풀 때 실행 권한이 유지되도록
    info.external_attr = ((0o100755 if executable else 0o100644) & 0xFFFF) << 16
    z.writestr(info, data)


def build() -> Path:
    out = ROOT.parent / f"서비_Mac설치판_v{_version()}.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(ROOT.rglob("*")):
            rel = p.relative_to(ROOT)
            if p.is_dir() or _skip(rel) or rel.parts[0] == "python":
                continue
            data = (_clean_config(p.read_text(encoding="utf-8"), None).encode("utf-8")
                    if rel.as_posix() == "config.yaml" else p.read_bytes())
            _add(z, f"서비/{rel.as_posix()}", data)
        for name, body in [("설치.command", INSTALL), ("서비 실행.command", RUN), ("서비 끄기.command", STOP)]:
            _add(z, f"서비/{name}", body.replace("\r\n", "\n").encode("utf-8"), executable=True)
        _add(z, "서비/맥 설치 안내.txt", GUIDE.encode("utf-8"))
        _add(z, "서비/outputs/.gitkeep", b"")
    print(f"  완성: {out}  ({out.stat().st_size / 1024 / 1024:.1f} MB)")
    return out


if __name__ == "__main__":
    build()
