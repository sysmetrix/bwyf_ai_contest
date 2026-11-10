"""전자결재 연동 — 결재 패키지를 인트라넷 기안으로 올립니다.

**서비는 절대 스스로 상신하지 않습니다.** 기안을 '임시저장' 상태로 만들어 두는
데까지만 하고 멈춥니다. 상신은 사람이 인트라넷에서 눈으로 확인한 뒤 누릅니다.
이 모듈에 `submit()` 이 있는 이유는, 사람이 서비 화면에서 "상신" 버튼을 직접
눌렀을 때 그 의사를 전달하기 위해서입니다. 자동 흐름에서는 호출되지 않습니다.

연결은 config.yaml 의 `approval` 로 고릅니다.

    type: mock          외부 서버 없이 그 자리에서 가짜 문서번호를 돌려줍니다.
                        시연·개발 기본값입니다. 네트워크를 쓰지 않습니다.
    type: amaranth_10   더존 아마란스 10 OpenAPI 규격으로 실제 호출합니다.

자격 증명은 파일에 적지 않습니다. config 에는 환경변수 '이름'만 두고
(api_key_env), 값은 실행 중인 서버가 os.environ 에서 읽습니다.
"""
from __future__ import annotations

import json
import os
import random
import string
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

from . import store

MOCK_STORE = store.ROOT / "data" / "approval_mock.json"


@dataclass
class SendResult:
    ok: bool
    provider: str
    doc_no: str | None = None          # 인트라넷이 매긴 문서번호
    url: str | None = None             # 사람이 열어 확인할 주소
    state: str = "draft"               # draft(임시저장) / submitted(상신됨)
    error: str | None = None
    seconds: float = 0.0
    meta: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {"ok": self.ok, "provider": self.provider, "doc_no": self.doc_no,
                "url": self.url, "state": self.state, "error": self.error,
                "seconds": round(self.seconds, 2), **({"meta": self.meta} if self.meta else {})}


# ---------- 설정 ----------

def _config() -> tuple[dict, str]:
    cfg = store.load_config()
    ap = cfg.get("approval") or {}
    name = ap.get("provider") or "mock"
    provider = (ap.get("providers") or {}).get(name) or {"type": "mock"}
    return provider, name


def settings() -> dict:
    """화면에 보여 줄 현재 연결 상태. 키 값은 절대 돌려주지 않습니다."""
    cfg = store.load_config()
    ap = cfg.get("approval") or {}
    out = {"provider": ap.get("provider") or "mock", "providers": {}}
    for name, p in (ap.get("providers") or {}).items():
        env = p.get("api_key_env")
        out["providers"][name] = {
            "type": p.get("type"),
            "base_url": p.get("base_url"),
            "api_key_env": env,
            "api_key_set": bool(env and os.environ.get(env)),   # 값이 아니라 '있는지'만
            "company_code": p.get("company_code"),
            "form_id": p.get("form_id"),
        }
    return out


def save_provider(name: str) -> dict:
    cfg = store.load_config()
    ap = cfg.setdefault("approval", {"provider": "mock", "providers": {"mock": {"type": "mock"}}})
    if name not in (ap.get("providers") or {}):
        raise ValueError("알 수 없는 결재 연결입니다")
    ap["provider"] = name
    store._write_config_keep_comments(cfg)
    return settings()


def enabled() -> bool:
    provider, _ = _config()
    return provider.get("type") in ("mock", "amaranth_10")


# ---------- 보낼 거리 만들기 ----------

def _attachments(org_id: str, manifest: dict) -> list[Path]:
    """원본 서식은 건드리지 않습니다. 패키지 안에 만들어 둔 사본만 보냅니다."""
    base = store.org_dir(org_id) / "packages" / manifest["id"]
    out: list[Path] = []
    for a in manifest.get("attachments") or []:
        rel = a.get("file")
        if not rel:
            continue
        p = (base / rel).resolve()
        if p.is_file() and str(p).startswith(str(base.resolve())):   # 경로 탈출 차단
            out.append(p)
    return out


def _payload(manifest: dict, provider: dict) -> dict:
    """아마란스 10 기안 등록 본문. 규정에서 확인된 값만 담습니다."""
    ap = manifest.get("approval") or {}
    return {
        "companyCode": provider.get("company_code"),
        "formId": provider.get("form_id"),
        "title": manifest.get("title"),
        "contents": manifest.get("body"),
        "drafterId": manifest.get("user_id"),
        "approvalLine": manifest.get("approval_line") or [],
        "keepAsDraft": True,                 # 임시저장. 상신은 사람이 합니다.
        "reference": {
            "taskId": (manifest.get("task") or {}).get("id"),
            "taskName": (manifest.get("task") or {}).get("name"),
            "approver": ap.get("approver"),
            "approvalBasis": ap.get("basis"),
            "deadline": (manifest.get("deadline") or {}).get("text"),
            "evidence": manifest.get("evidence") or [],
            "packageId": manifest.get("id"),
        },
    }


# ---------- mock ----------

def _mock_read() -> dict:
    try:
        return json.loads(MOCK_STORE.read_text(encoding="utf-8"))
    except Exception:
        return {"documents": {}}


def _mock_write(data: dict) -> None:
    MOCK_STORE.parent.mkdir(parents=True, exist_ok=True)
    MOCK_STORE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _mock_send(manifest: dict, files: list[Path], provider: dict) -> SendResult:
    """외부 서버 없이 인트라넷에 올라간 것처럼 흉내 냅니다. 시연 기본값입니다."""
    t0 = time.perf_counter()
    today = datetime.now()
    tail = "".join(random.choices(string.digits, k=4))
    doc_no = f"{provider.get('company_code') or 'DEMO'}-{today:%Y%m%d}-{tail}"

    data = _mock_read()
    data.setdefault("documents", {})[doc_no] = {
        "doc_no": doc_no,
        "state": "draft",
        "title": manifest.get("title"),
        "contents": manifest.get("body"),
        "drafter": manifest.get("user_id"),
        "approval_line": manifest.get("approval_line") or [],
        "attachments": [f.name for f in files],
        "package_id": manifest.get("id"),
        "created": today.isoformat(timespec="seconds"),
    }
    _mock_write(data)
    return SendResult(ok=True, provider="mock", doc_no=doc_no, state="draft",
                      url=f"/api/approval/mock/{doc_no}",
                      seconds=time.perf_counter() - t0,
                      meta={"note": "가상 결재함에 임시저장했습니다. 실제 결재망으로 나가지 않았습니다.",
                            "attachments": [f.name for f in files]})


def _mock_submit(doc_no: str) -> SendResult:
    data = _mock_read()
    doc = (data.get("documents") or {}).get(doc_no)
    if not doc:
        return SendResult(ok=False, provider="mock", error="가상 결재함에 그 문서가 없습니다")
    doc["state"] = "submitted"
    doc["submitted"] = datetime.now().isoformat(timespec="seconds")
    _mock_write(data)
    return SendResult(ok=True, provider="mock", doc_no=doc_no, state="submitted")


def mock_document(doc_no: str) -> dict | None:
    return (_mock_read().get("documents") or {}).get(doc_no)


def mock_documents(limit: int = 30) -> list[dict]:
    docs = list((_mock_read().get("documents") or {}).values())
    docs.sort(key=lambda d: d.get("created") or "", reverse=True)
    return docs[:limit]


# ---------- 아마란스 10 ----------

def _amaranth_client(provider: dict) -> tuple[httpx.Client | None, str | None]:
    base = (provider.get("base_url") or "").rstrip("/")
    if not base:
        return None, "결재 서버 주소가 설정되지 않았습니다"
    env = provider.get("api_key_env")
    key = os.environ.get(env) if env else None
    if env and not key:
        return None, f"환경변수 {env}에 API 키가 없습니다"
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    return httpx.Client(base_url=base, headers=headers, timeout=30.0), None


def _amaranth_send(manifest: dict, files: list[Path], provider: dict) -> SendResult:
    t0 = time.perf_counter()
    client, err = _amaranth_client(provider)
    if err:
        return SendResult(ok=False, provider="amaranth", error=err,
                          seconds=time.perf_counter() - t0)
    try:
        with client:
            r = client.post("/approval/documents", json=_payload(manifest, provider))
            r.raise_for_status()
            body = r.json()
            doc_no = body.get("docNo") or body.get("documentNo") or body.get("id")
            if not doc_no:
                return SendResult(ok=False, provider="amaranth",
                                  error="결재 서버가 문서번호를 돌려주지 않았습니다",
                                  seconds=time.perf_counter() - t0, meta={"response": body})

            sent, failed = [], []
            for f in files:                       # 붙임은 한 건씩, 실패해도 기안은 남깁니다
                try:
                    with open(f, "rb") as fh:
                        a = client.post(f"/approval/documents/{doc_no}/attachments",
                                        files={"file": (f.name, fh)}, headers={"Accept": "application/json"})
                        a.raise_for_status()
                    sent.append(f.name)
                except Exception as exc:
                    failed.append({"file": f.name, "error": _short(exc)})

            return SendResult(ok=True, provider="amaranth", doc_no=doc_no, state="draft",
                              url=body.get("url") or body.get("viewUrl"),
                              seconds=time.perf_counter() - t0,
                              meta={"attachments": sent, **({"attachment_errors": failed} if failed else {})})
    except Exception as exc:
        return SendResult(ok=False, provider="amaranth", error=_short(exc),
                          seconds=time.perf_counter() - t0)


def _amaranth_submit(doc_no: str, provider: dict) -> SendResult:
    t0 = time.perf_counter()
    client, err = _amaranth_client(provider)
    if err:
        return SendResult(ok=False, provider="amaranth", error=err)
    try:
        with client:
            r = client.post(f"/approval/documents/{doc_no}/submit")
            r.raise_for_status()
        return SendResult(ok=True, provider="amaranth", doc_no=doc_no, state="submitted",
                          seconds=time.perf_counter() - t0)
    except Exception as exc:
        return SendResult(ok=False, provider="amaranth", error=_short(exc),
                          seconds=time.perf_counter() - t0)


def _short(exc: Exception) -> str:
    if isinstance(exc, httpx.ConnectError):
        return "결재 서버에 연결할 수 없습니다(주소·망 확인)"
    if isinstance(exc, httpx.TimeoutException):
        return "결재 서버 응답 시간 초과"
    if isinstance(exc, httpx.HTTPStatusError):
        return f"HTTP {exc.response.status_code}: {exc.response.text[:140]}"
    return str(exc)[:160]


# ---------- 바깥에서 부르는 두 가지 ----------

def send(org_id: str, manifest: dict) -> SendResult:
    """결재 패키지를 인트라넷에 기안으로 올립니다(임시저장까지만)."""
    provider, name = _config()
    files = _attachments(org_id, manifest)
    kind = provider.get("type")
    if kind == "amaranth_10":
        res = _amaranth_send(manifest, files, provider)
    elif kind == "mock":
        res = _mock_send(manifest, files, provider)
    else:
        res = SendResult(ok=False, provider=name, error=f"지원하지 않는 결재 연결 유형: {kind}")
    res.provider = name
    return res


def submit(doc_no: str) -> SendResult:
    """사람이 '상신' 버튼을 직접 누른 경우에만 호출됩니다."""
    provider, name = _config()
    kind = provider.get("type")
    if kind == "amaranth_10":
        res = _amaranth_submit(doc_no, provider)
    elif kind == "mock":
        res = _mock_submit(doc_no)
    else:
        res = SendResult(ok=False, provider=name, error=f"지원하지 않는 결재 연결 유형: {kind}")
    res.provider = name
    return res
