"""예시 기관 서식을 다시 만듭니다(덮어씀): python tools/make_forms.py

서식 내용은 app/standard_forms.py 에 있습니다. 실제 기관은 서식 보관함의 '기본 서식 넣기'를 쓰세요.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.standard_forms import generate  # noqa: E402

if __name__ == "__main__":
    for org in ("demo-agency", "demo-city"):
        print(org, generate(org, only_missing=False))
    print("서식 템플릿 생성 완료")
