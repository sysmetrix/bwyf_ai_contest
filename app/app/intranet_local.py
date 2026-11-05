"""로컬 규정 파일 기반 인트라넷 시뮬레이션

개발/테스트 목적으로 로컬 파일 시스템의 규정을 인트라넷 API 응답으로 변환합니다.
"""
from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime

from .store import org_dir, COMMON


def _scan_local_regulations(base_path: Path) -> list[dict]:
    """로컬 규정 파일을 인트라넷 규정 형식으로 변환

    Returns:
        [
            {
                "id": "common-travel",
                "title": "공통 여비 지침",
                "category": "finance",
                "org_id": "common",
                "updated_at": "2026-01-01T00:00:00",
                "version": "1.0"
            },
            ...
        ]
    """
    regulations = []

    # 공통 규정
    common_rules = base_path / "common" / "rules"
    if common_rules.exists():
        for f in sorted(common_rules.glob("*.md")):
            regulations.append({
                "id": f"common-{f.stem}",
                "title": f.stem,
                "category": _categorize_regulation(f.stem),
                "org_id": "common",
                "updated_at": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
                "version": "1.0",
                "file_path": str(f)
            })

    # 기관별 규정
    orgs_path = base_path / "orgs"
    if orgs_path.exists():
        for org_dir_path in sorted(orgs_path.glob("*")):
            if not org_dir_path.is_dir():
                continue

            org_id = org_dir_path.name
            rules_path = org_dir_path / "rules"

            if rules_path.exists():
                for f in sorted(rules_path.glob("*.md")):
                    if "dept" not in str(f):  # 부서 규정은 제외
                        regulations.append({
                            "id": f"{org_id}-{f.stem}",
                            "title": f.stem,
                            "category": _categorize_regulation(f.stem),
                            "org_id": org_id,
                            "updated_at": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
                            "version": "1.0",
                            "file_path": str(f)
                        })

    return regulations


def _categorize_regulation(title: str) -> str:
    """규정 제목에서 카테고리 자동 분류"""
    title_lower = title.lower()

    categories = {
        "여비": "finance",
        "출장": "finance",
        "회계": "finance",
        "물품": "procurement",
        "구매": "procurement",
        "기안": "general",
        "결재": "general",
        "복무": "hr",
        "인사": "hr",
        "행사": "event",
        "문서": "admin"
    }

    for keyword, category in categories.items():
        if keyword in title_lower:
            return category

    return "general"


def _read_local_file(file_path: str) -> str:
    """로컬 파일 읽기"""
    try:
        return Path(file_path).read_text(encoding="utf-8")
    except Exception as e:
        return f"파일 읽기 실패: {e}"


def get_local_regulations_data(base_path: Path) -> dict:
    """로컬 규정 데이터를 인트라넷 API 응답 형식으로 반환"""
    regs = _scan_local_regulations(base_path)

    return {
        "ok": True,
        "data": regs,
        "count": len(regs),
        "source": "local_filesystem"
    }


def get_local_regulation_content(file_id: str, base_path: Path) -> dict:
    """로컬 규정 내용 가져오기"""
    regs = _scan_local_regulations(base_path)

    for reg in regs:
        if reg["id"] == file_id:
            content = _read_local_file(reg["file_path"])
            return {
                "ok": True,
                "data": {
                    "id": reg["id"],
                    "title": reg["title"],
                    "content": content,
                    "category": reg["category"],
                    "org_id": reg["org_id"],
                    "updated_at": reg["updated_at"],
                    "file_path": reg["file_path"]
                }
            }

    return {
        "ok": False,
        "error": f"규정을 찾을 수 없습니다: {file_id}"
    }


def list_local_orgs(base_path: Path) -> dict:
    """로컬 기관 목록"""
    orgs = []

    orgs_path = base_path / "orgs"
    if orgs_path.exists():
        for org_dir_path in sorted(orgs_path.glob("*")):
            if org_dir_path.is_dir() and (org_dir_path / "profile.yaml").exists():
                orgs.append({
                    "id": org_dir_path.name,
                    "name": org_dir_path.name.replace("-", " ").title(),
                    "type": "local"
                })

    return {
        "ok": True,
        "data": orgs
    }


def print_local_regulations_summary(base_path: Path) -> None:
    """로컬 규정 요약 출력"""
    regs = _scan_local_regulations(base_path)

    print("\n📋 로컬 규정 목록\n")
    print(f"총 {len(regs)}개 규정\n")

    # 기관별 정렬
    by_org = {}
    for reg in regs:
        org = reg["org_id"]
        if org not in by_org:
            by_org[org] = []
        by_org[org].append(reg)

    for org_id in sorted(by_org.keys()):
        org_regs = by_org[org_id]
        print(f"🏢 {org_id.upper()} ({len(org_regs)}개)")

        for reg in org_regs:
            print(f"  • {reg['title']} [{reg['category']}]")

        print()


class IntranetClient_Mock:
    """테스트용 Mock 인트라넷 클라이언트"""

    def __init__(self, base_path: Path | None = None):
        from .store import ROOT
        self.base_path = base_path or (ROOT / "data")

    def is_configured(self) -> bool:
        """로컬 규정이 있는지 확인"""
        return (self.base_path / "orgs").exists()

    def list_regulations(self, org_id: str | None = None):
        """로컬 규정 목록"""
        from .intranet import IntranetFile

        regs_data = get_local_regulations_data(self.base_path)

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


if __name__ == "__main__":
    from .store import ROOT

    # 테스트
    data = get_local_regulations_data(ROOT / "data")
    print(json.dumps(data, indent=2, ensure_ascii=False))

    print("\n" + "=" * 60 + "\n")

    print_local_regulations_summary(ROOT / "data")
