"""인트라넷(그룹웨어) 연동 — 부천여성청소년재단 gw.bwyf.or.kr

규정·서식·기안을 인트라넷과 동기화합니다.

연결 설정:
  config.yaml의 intranet 섹션에서 활성화:

    intranet:
      enabled: true
      base_url: https://gw.bwyf.or.kr
      api_key_env: INTRANET_API_KEY          # .env에서 읽음
      use_regulations: true                  # 인트라넷 규정 사용
      use_forms: true                        # 인트라넷 서식 사용

자격 증명:
  .env 파일에:
    INTRANET_API_KEY=your-api-key-here
    INTRANET_USER=admin_user
    INTRANET_PASSWORD=password

인트라넷 API 엔드포인트:
  POST   /api/v1/auth/token              — 인증
  GET    /api/v1/regulations             — 규정 목록
  GET    /api/v1/regulations/{id}/file   — 규정 다운로드
  GET    /api/v1/templates/forms         — 서식 목록
  GET    /api/v1/templates/{id}/file     — 서식 다운로드
  POST   /api/v1/documents/draft         — 기안 임시저장
  POST   /api/v1/documents/{id}/submit   — 기안 상신
  GET    /api/v1/documents/{id}/status   — 기안 상태 조회
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

import httpx

from . import store


def _friendly(exc: Exception) -> str:
    """담당자가 읽고 무엇을 해야 할지 알 수 있는 말로 바꿉니다."""
    if isinstance(exc, httpx.ConnectError):
        return "결재시스템에 연결할 수 없습니다(켜져 있는지, 주소가 맞는지 확인해 주세요)"
    if isinstance(exc, httpx.TimeoutException):
        return "결재시스템이 제때 답하지 않았습니다"
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        if code in (401, 403):
            return "결재시스템이 접근을 거부했습니다(API 키를 확인해 주세요)"
        if code == 404:
            return "결재시스템에서 그 주소를 찾지 못했습니다"
        return f"결재시스템이 오류를 돌려주었습니다(HTTP {code})"
    text = str(exc)
    if "Connection refused" in text or "Errno 61" in text:
        return "결재시스템에 연결할 수 없습니다(켜져 있는지 확인해 주세요)"
    return text[:160]


@dataclass
class IntranetFile:
    """인트라넷 문서 정보"""
    id: str
    title: str
    category: str  # regulations, forms, approvals
    org_id: str    # 기관 ID
    updated_at: str
    version: str = "1.0"
    url: str = ""
    metadata: dict = field(default_factory=dict)


@dataclass
class DraftResult:
    """기안 저장 결과"""
    ok: bool
    doc_no: str | None = None
    url: str | None = None
    error: str | None = None
    state: str = "draft"  # draft, submitted
    created_at: str | None = None

    def as_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v is not None}


class IntranetClient:
    """부천여성청소년재단 그룹웨어 API 클라이언트"""

    def __init__(self, base_url: str | None = None, api_key: str | None = None):
        self.base_url = (base_url or os.environ.get("INTRANET_BASE_URL") or "https://gw.bwyf.or.kr").rstrip('/')
        self.api_key = api_key or os.environ.get("INTRANET_API_KEY")
        self.timeout = 30
        self._token: str | None = None
        self._token_expires: float = 0

    def is_configured(self) -> bool:
        """인트라넷 연동이 설정되었는지 확인.

        같은 PC에서 도는 가상 인트라넷은 키 없이도 씁니다. 바깥 주소일 때만
        키를 요구합니다(키 없이 실제 결재망에 말을 걸지 않도록).
        """
        if self.api_key:
            return True
        host = self.base_url.split("//", 1)[-1].split("/", 1)[0].split(":")[0]
        return host in ("127.0.0.1", "localhost", "::1")

    def _headers(self) -> dict:
        """API 요청 헤더"""
        h = {"Content-Type": "application/json"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

    def _get(self, path: str, params: dict | None = None) -> Any:
        """GET 요청"""
        try:
            with httpx.Client(timeout=self.timeout) as client:
                r = client.get(
                    f"{self.base_url}{path}",
                    headers=self._headers(),
                    params=params
                )
                r.raise_for_status()
                return r.json() if r.text else {}
        except httpx.TimeoutException:
            return {"error": "결재시스템이 제때 답하지 않았습니다"}
        except httpx.ConnectError:
            return {"error": "결재시스템에 연결할 수 없습니다(켜져 있는지 확인해 주세요)"}
        except Exception as e:
            return {"error": _friendly(e)}

    def _post(self, path: str, data: dict | None = None, files: dict | None = None) -> Any:
        """POST 요청"""
        try:
            with httpx.Client(timeout=self.timeout) as client:
                kwargs = {"headers": self._headers()}
                if files:
                    kwargs["files"] = files
                    # multipart 경계는 httpx 가 정해야 하므로 Content-Type 만 뺍니다.
                    kwargs["headers"] = {k: v for k, v in kwargs["headers"].items()
                                         if k.lower() != "content-type"}
                elif data:
                    kwargs["json"] = data

                r = client.post(f"{self.base_url}{path}", **kwargs)
                r.raise_for_status()
                return r.json() if r.text else {}
        except Exception as e:
            return {"error": _friendly(e)}

    # ========== 규정 관리 ==========

    def list_regulations(self, org_id: str | None = None, category: str = "all") -> list[IntranetFile]:
        """규정 목록 가져오기

        Args:
            org_id: 기관 ID (생략하면 전사 규정)
            category: "all", "finance", "hr", "general" 등

        Returns:
            규정 파일 목록
        """
        if not self.is_configured():
            return []

        params = {}
        if org_id:
            params["org_id"] = org_id
        if category != "all":
            params["category"] = category

        result = self._get("/api/v1/regulations", params)

        if "error" in result:
            print(f"⚠️  규정 조회 오류: {result['error']}")
            return []

        files = []
        for item in result.get("data", []):
            files.append(IntranetFile(
                id=item.get("id", ""),
                title=item.get("title", ""),
                category=item.get("category", "general"),
                org_id=item.get("org_id", ""),
                updated_at=item.get("updated_at", ""),
                version=item.get("version", "1.0"),
                url=item.get("url", ""),
                metadata=item.get("metadata", {})
            ))
        return files

    def download_regulation(self, file_id: str) -> bytes | None:
        """규정 파일 다운로드

        Args:
            file_id: 규정 ID

        Returns:
            파일 바이너리 또는 None
        """
        if not self.is_configured():
            return None

        try:
            with httpx.Client(timeout=self.timeout) as client:
                r = client.get(
                    f"{self.base_url}/api/v1/regulations/{file_id}/file",
                    headers=self._headers()
                )
                r.raise_for_status()
                return r.content
        except Exception as e:
            print(f"⚠️  규정 다운로드 실패 ({file_id}): {e}")
            return None

    # ========== 서식 관리 ==========

    def list_forms(self, org_id: str | None = None, category: str = "all") -> list[IntranetFile]:
        """서식 목록 가져오기

        Args:
            org_id: 기관 ID
            category: "all", "travel", "leave", "purchase" 등

        Returns:
            서식 파일 목록
        """
        if not self.is_configured():
            return []

        params = {}
        if org_id:
            params["org_id"] = org_id
        if category != "all":
            params["category"] = category

        result = self._get("/api/v1/templates/forms", params)

        if "error" in result:
            print(f"⚠️  서식 조회 오류: {result['error']}")
            return []

        files = []
        for item in result.get("data", []):
            files.append(IntranetFile(
                id=item.get("id", ""),
                title=item.get("title", ""),
                category=item.get("category", "general"),
                org_id=item.get("org_id", ""),
                updated_at=item.get("updated_at", ""),
                version=item.get("version", "1.0"),
                url=item.get("url", ""),
                metadata=item.get("metadata", {})
            ))
        return files

    def download_form(self, form_id: str, format: str = "docx") -> bytes | None:
        """서식 파일 다운로드

        Args:
            form_id: 서식 ID
            format: "docx", "hwpx", "pdf"

        Returns:
            파일 바이너리 또는 None
        """
        if not self.is_configured():
            return None

        try:
            with httpx.Client(timeout=self.timeout) as client:
                r = client.get(
                    f"{self.base_url}/api/v1/templates/{form_id}/file",
                    headers=self._headers(),
                    params={"format": format}
                )
                r.raise_for_status()
                return r.content
        except Exception as e:
            print(f"⚠️  서식 다운로드 실패 ({form_id}): {e}")
            return None

    # ========== 기안 저장/상신 ==========

    def submit_draft(
        self,
        title: str,
        content: str,
        form_category: str,
        org_id: str,
        approvers: list[str] | None = None,
        attachments: dict[str, bytes] | None = None,
        submit: bool = False,
        fields: dict | None = None
    ) -> DraftResult:
        """기안 저장 또는 상신

        Args:
            title: 기안 제목
            content: 기안 내용 (HTML 또는 텍스트)
            form_category: 서식 분류 (travel_settlement, leave_request 등)
            org_id: 기관 ID
            approvers: 결재자 목록 (직책 또는 사용자 ID)
            attachments: 첨부파일 {filename: bytes, ...}
            submit: False=임시저장, True=상신

        Returns:
            DraftResult
        """
        if not self.is_configured():
            return DraftResult(ok=False, error="인트라넷 API 키가 설정되지 않았습니다")

        payload = {
            "title": title,
            "content": content,
            "category": form_category,
            "org_id": org_id,
            "approvers": approvers or [],
            "state": "submitted" if submit else "draft",
            "created_at": datetime.now().isoformat(),
            # 서식 칸을 채우는 데 쓰는 값입니다(장소·기간·금액·기한·결재선 등).
            "fields": fields or {},
        }

        # 파일이 있으면 multipart/form-data로 전송
        if attachments:
            files = {f"file_{i}": (name, data) for i, (name, data) in enumerate(attachments.items())}
            files["metadata"] = (None, json.dumps(payload, ensure_ascii=False),
                                 "application/json")
            result = self._post("/api/v1/documents/draft", files=files)
        else:
            result = self._post("/api/v1/documents/draft", data=payload)

        if "error" in result:
            return DraftResult(ok=False, error=result["error"])

        data = result.get("data", {})
        return DraftResult(
            ok=True,
            doc_no=data.get("doc_no"),
            url=data.get("url"),
            state="submitted" if submit else "draft",
            created_at=data.get("created_at")
        )

    def submit_document(self, doc_no: str) -> dict:
        """임시저장해 둔 기안을 상신합니다. 사람이 누를 때만 부릅니다."""
        return self._post(f"/api/v1/documents/{doc_no}/submit")

    def get_draft_status(self, doc_no: str) -> dict:
        """기안 상태 조회

        Args:
            doc_no: 문서 번호

        Returns:
            {
                "doc_no": "2026-00001",
                "title": "출장 정산",
                "state": "draft|submitted|approved|rejected",
                "created_at": "...",
                "approvals": [...]
            }
        """
        if not self.is_configured():
            return {"error": "인트라넷 API 키가 설정되지 않았습니다"}

        result = self._get(f"/api/v1/documents/{doc_no}/status")

        if "error" in result:
            return {"error": result["error"]}

        return result.get("data", {})

    # ========== 기관 정보 ==========

    def list_orgs(self) -> list[dict]:
        """인트라넷에 등록된 모든 기관 목록

        Returns:
            [{"id": "...", "name": "...", "type": "..."}, ...]
        """
        if not self.is_configured():
            return []

        result = self._get("/api/v1/orgs")

        if "error" in result:
            print(f"⚠️  기관 조회 오류: {result['error']}")
            return []

        return result.get("data", [])

    def get_org_profile(self, org_id: str) -> dict:
        """기관 프로필 조회

        Returns:
            {
                "id": "demo-city",
                "name": "○○시청",
                "type": "local",  # local, central, agency
                "rules": {...},
                "approvals": {...}
            }
        """
        if not self.is_configured():
            return {}

        result = self._get(f"/api/v1/orgs/{org_id}")

        if "error" in result:
            print(f"⚠️  기관 프로필 조회 오류 ({org_id}): {result['error']}")
            return {}

        return result.get("data", {})

    # ========== 사용자 정보 ==========

    def get_user_profile(self, user_id: str) -> dict:
        """사용자 정보 조회

        Returns:
            {
                "id": "user123",
                "name": "김철수",
                "dept": "총무과",
                "position": "과장",
                "email": "..."
            }
        """
        if not self.is_configured():
            return {}

        result = self._get(f"/api/v1/users/{user_id}")

        if "error" in result:
            return {}

        return result.get("data", {})


def get_intranet_config() -> dict | None:
    """config.yaml에서 인트라넷 설정 읽기"""
    cfg = store.load_config()
    intranet_cfg = cfg.get("intranet", {})

    if not intranet_cfg.get("enabled"):
        return None

    return intranet_cfg


def is_intranet_enabled() -> bool:
    """인트라넷 연동이 활성화되어 있는지 확인"""
    cfg = get_intranet_config()
    return cfg is not None and cfg.get("enabled", False)


# ========== 인트라넷 기반 데이터 로드 함수 ==========

def strip_frontmatter(text: str) -> str:
    """맨 위 --- 사이의 메타데이터를 걷어냅니다.

    인트라넷이 돌려주는 파일은 원본 그대로라 메타데이터가 붙어 있습니다.
    조문으로 쪼개기 전에 떼지 않으면 조문 제목이 "---" 로 잡힙니다.
    """
    if not text.startswith("---"):
        return text
    end = text.find("\n---", 3)
    return text[end + 4:].lstrip("\n") if end >= 0 else text


def fetch_intranet_regulations(org_id: str) -> list[dict]:
    """인트라넷에서 규정 목록 로드

    Returns:
        [
            {"id": "...", "title": "여비조례", "layer": "intranet", "content": "..."},
            ...
        ]
    """
    cfg = get_intranet_config()
    if not cfg:
        return []

    client = IntranetClient(
        base_url=cfg.get("base_url"),
        api_key=os.environ.get(cfg.get("api_key_env", "INTRANET_API_KEY"))
    )

    if not client.is_configured():
        return []

    regulations = client.list_regulations(org_id=cfg.get("org_id") or org_id)
    result = []

    for reg in regulations:
        content = client.download_regulation(reg.id)
        if content:
            result.append({
                "id": reg.id,
                "title": reg.title,
                "layer": "intranet",
                "category": reg.category,
                "content": strip_frontmatter(content.decode("utf-8", errors="replace")),
                "url": reg.url,
                "updated_at": reg.updated_at
            })

    return result


def fetch_intranet_forms(org_id: str) -> list[dict]:
    """인트라넷에서 서식 목록 로드

    Returns:
        [
            {"id": "...", "title": "출장 정산서", "category": "travel_settlement", "url": "..."},
            ...
        ]
    """
    cfg = get_intranet_config()
    if not cfg:
        return []

    client = IntranetClient(
        base_url=cfg.get("base_url"),
        api_key=os.environ.get(cfg.get("api_key_env", "INTRANET_API_KEY"))
    )

    if not client.is_configured():
        return []

    forms = client.list_forms(org_id=cfg.get("org_id") or org_id)
    return [
        {
            "id": f.id,
            "title": f.title,
            "category": f.category,
            "url": f.url,
            "metadata": f.metadata
        }
        for f in forms
    ]


if __name__ == "__main__":
    # 테스트
    client = IntranetClient()

    if client.is_configured():
        print("✅ 인트라넷 연동 설정됨")

        # 기관 목록
        orgs = client.list_orgs()
        print(f"📋 기관 ({len(orgs)}개)")
        for org in orgs:
            print(f"  - {org.get('name')}")

        # 첫 기관의 규정
        if orgs:
            org_id = orgs[0]["id"]
            regs = client.list_regulations(org_id=org_id)
            print(f"📄 규정 ({len(regs)}개) - {org_id}")
            for reg in regs[:3]:
                print(f"  - {reg.title}")
    else:
        print("❌ 인트라넷 API 키가 설정되지 않았습니다")
        print("   .env 파일에 INTRANET_API_KEY를 설정하세요")

def fetch_intranet_form_texts(org_id: str) -> list[dict]:
    """서식 '내용'까지 내려받습니다.

    서식에는 어떤 칸을 채워야 하는지, 언제 쓰는지, 근거가 무엇인지가 적혀 있어
    규정만큼이나 자주 답이 됩니다(예: 관내업체를 안 쓰면 F12 사유서를 씁니다).
    그래서 규정과 같은 방식으로 찾아볼 수 있게 본문을 가져옵니다.
    """
    cfg = get_intranet_config()
    if not cfg or not cfg.get("use_forms", True):
        return []

    client = IntranetClient(
        base_url=cfg.get("base_url"),
        api_key=os.environ.get(cfg.get("api_key_env", "INTRANET_API_KEY"))
    )
    if not client.is_configured():
        return []

    out = []
    for f in client.list_forms(org_id=cfg.get("org_id") or org_id):
        raw = client.download_form(f.id)
        if not raw:
            continue
        out.append({
            "id": f.id,
            "title": f"{f.id} {f.title}",
            "layer": "form",
            "category": f.category,
            "content": strip_frontmatter(raw.decode("utf-8", errors="replace")),
        })
    return out

def fetch_org_members(org_id: str) -> list[dict]:
    """결재시스템의 조직도를 읽습니다. 직급·직위가 역할 판정의 근거입니다."""
    cfg = get_intranet_config()
    if not cfg:
        return []
    client = IntranetClient(
        base_url=cfg.get("base_url"),
        api_key=os.environ.get(cfg.get("api_key_env", "INTRANET_API_KEY")))
    if not client.is_configured():
        return []
    res = client._get(f"/api/v1/orgs/{cfg.get('org_id') or org_id}/members")
    if "error" in res:
        return []
    return res.get("data") or []


def fetch_pending_approvals(approver: str | None = None) -> list[dict]:
    """결재를 기다리는 문서. 결재자에게 브리핑할 거리입니다."""
    cfg = get_intranet_config()
    if not cfg:
        return []
    client = IntranetClient(
        base_url=cfg.get("base_url"),
        api_key=os.environ.get(cfg.get("api_key_env", "INTRANET_API_KEY")))
    if not client.is_configured():
        return []
    res = client._get("/api/v1/approvals/pending",
                      {"approver": approver} if approver else None)
    if "error" in res:
        return []
    return res.get("data") or []
