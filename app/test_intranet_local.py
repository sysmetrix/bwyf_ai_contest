#!/usr/bin/env python3
"""인트라넷 로컬 시뮬레이션 테스트

로컬 규정 파일들을 읽어서 인트라넷 API처럼 사용합니다.
"""
import sys
from pathlib import Path

# 현재 디렉토리를 Python 경로에 추가
sys.path.insert(0, str(Path(__file__).parent))

from app import intranet_local
from app.store import ROOT


class IntranetClient_Mock:
    """테스트용 Mock 인트라넷 클라이언트"""

    def __init__(self):
        self.base_path = ROOT / "data"

    def is_configured(self) -> bool:
        """로컬 규정이 있는지 확인"""
        return (self.base_path / "orgs").exists()

    def list_regulations(self, org_id: str = None):
        """로컬 규정 목록"""
        from app.intranet import IntranetFile

        regs_data = intranet_local.get_local_regulations_data(self.base_path)

        files = []
        for reg in regs_data.get("data", []):
            if org_id is None or reg["org_id"] == org_id:
                files.append(IntranetFile(
                    id=reg["id"],
                    title=reg["title"],
                    category=reg["category"],
                    org_id=reg["org_id"],
                    updated_at=reg["updated_at"],
                    version=reg["version"]
                ))

        return files


def print_section(title: str):
    """섹션 제목 출력"""
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}\n")


def main():
    print("\n🌐 인트라넷 로컬 시뮬레이션\n")

    # 1. 로컬 기관 목록
    print_section("1️⃣  로컬 기관 목록")
    orgs_data = intranet_local.list_local_orgs(ROOT / "data")
    if orgs_data["ok"]:
        for org in orgs_data["data"]:
            print(f"  • {org['name']} (ID: {org['id']})")
    else:
        print(f"  ❌ 오류: {orgs_data['error']}")

    # 2. 로컬 규정 목록
    print_section("2️⃣  로컬 규정 목록")
    regs_data = intranet_local.get_local_regulations_data(ROOT / "data")
    if regs_data["ok"]:
        print(f"  총 {regs_data['count']}개 규정\n")

        # 카테고리별 분류
        by_category = {}
        for reg in regs_data["data"]:
            cat = reg["category"]
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(reg)

        for category in sorted(by_category.keys()):
            regs = by_category[category]
            print(f"  📁 {category} ({len(regs)}개)")
            for reg in regs[:5]:  # 최대 5개만 표시
                print(f"     • {reg['title']} ({reg['org_id']})")
            if len(regs) > 5:
                print(f"     ... 외 {len(regs)-5}개")
            print()

    # 3. 특정 규정 내용 조회
    print_section("3️⃣  규정 내용 조회 (예시)")
    regs_data = intranet_local.get_local_regulations_data(ROOT / "data")
    if regs_data["data"]:
        first_reg_id = regs_data["data"][0]["id"]
        content_data = intranet_local.get_local_regulation_content(first_reg_id, ROOT / "data")

        if content_data["ok"]:
            reg = content_data["data"]
            print(f"  📄 {reg['title']} (ID: {reg['id']})")
            print(f"     카테고리: {reg['category']}")
            print(f"     기관: {reg['org_id']}")
            print(f"     수정일: {reg['updated_at']}")
            print(f"     내용 길이: {len(reg['content'])}자")
            print(f"\n  📝 내용 미리보기:\n")

            lines = reg['content'].split('\n')
            for line in lines[:15]:
                if line.strip():
                    print(f"     {line}")
            if len(lines) > 15:
                print(f"     ... (총 {len(lines)}줄)")

    # 4. 인트라넷 클라이언트 테스트
    print_section("4️⃣  IntranetClient 연결 상태")
    client = intranet_local.IntranetClient_Mock()
    if client.is_configured():
        print("  ✅ 인트라넷 클라이언트 준비 완료")
        regs = client.list_regulations("demo-city")
        print(f"  📋 demo-city 규정: {len(regs)}개")
        for reg in regs[:3]:
            print(f"     • {reg.title}")
    else:
        print("  ⚠️  인트라넷 API 키 설정 필요")
        print("     .env 파일에 INTRANET_API_KEY 추가")

    # 5. 사용 방법
    print_section("5️⃣  로컬 규정을 서비에 적용하는 방법")
    print("""
  1️⃣  환경 설정
     .env 파일에 다음 추가:
     ```
     INTRANET_USE_LOCAL=true
     ```

  2️⃣  config.yaml 수정
     ```yaml
     intranet:
       enabled: true
       use_local: true        # 로컬 규정 사용
     ```

  3️⃣  서비 실행
     ```bash
     python run.py
     ```

  4️⃣  규정 자동 로드
     • 로컬 규정 (data/orgs/)
     • 공통 규정 (data/common/)
     → 통합 검색 인덱스 자동 생성

  5️⃣  테스트
     http://localhost:8000 접속
     → "출장 가는데 뭐 해야 해?" 질문
     → 로컬 + 인트라넷 규정 검색 결과 표시
    """)

    print_section("✅ 테스트 완료")
    print("  로컬 규정이 성공적으로 로드되었습니다!")
    print("  이제 다음 단계로 이동하세요:\n")
    print("    1. requirements.txt 설치: pip install -r requirements.txt")
    print("    2. 서버 실행: python run.py")
    print("    3. 브라우저 열기: http://localhost:8000\n")


if __name__ == "__main__":
    # Python 3.x 확인
    if sys.version_info < (3, 9):
        print("❌ Python 3.9 이상이 필요합니다")
        sys.exit(1)

    # 테스트 실행
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⏹️  사용자에 의해 중단됨")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
