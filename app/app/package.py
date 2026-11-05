"""결재 패키지 — 기안 직전까지 사람이 확인할 수 있는 한 묶음.

서비가 규정에서 뽑아낸 것(제목·본문·결재선·전결권자·기한·근거 조문)과
서식 초안 파일을 한 폴더에 모아 manifest.json 으로 묶습니다.

이 패키지가 인트라넷 자동화(connector)의 **유일한 입력**입니다.
자동화가 스스로 규정을 해석하지 않게 하려는 분리입니다. 자동화는
"무엇을 쓸지" 모르고, "어디에 넣을지"만 압니다.

상태(state)는 한 방향으로만 흐릅니다:
    draft    초안을 만들었다
    ready    사람이 확인·보정을 마쳤다 (자동화에 넘겨도 된다)
    staged   인트라넷에 입력까지 끝났다 (상신 전, 사람 검증 대기)
    submitted 사람이 상신했다
    done     후속 업무까지 끝났다
서비는 절대 submitted 로 스스로 넘기지 않습니다. 상신은 사람이 합니다.
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any

from . import engine, forms, llm, store

STATES = ["draft", "ready", "staged", "submitted", "done"]


def _dir(org_id: str, pkg_id: str) -> Path:
    return store.org_dir(org_id) / "packages" / pkg_id


def _manifest_path(org_id: str, pkg_id: str) -> Path:
    return _dir(org_id, pkg_id) / "manifest.json"


def _slug(text: str, limit: int = 40) -> str:
    s = re.sub(r"[^0-9A-Za-z가-힣 ._-]", "", str(text or "")).strip()
    return (s[:limit] or "기안").replace(" ", "_")


# ---------- 본문 ----------

def _body_text(r: dict, profile: dict) -> str:
    """기안문 본문. 규정에서 확인된 값만 씁니다. 지어내지 않습니다."""
    task = r.get("task") or {}
    slots = (r.get("understanding") or {}).get("slots") or {}
    lines: list[str] = []

    lines.append(f"{task.get('name', '기안')}에 대하여 다음과 같이 요청합니다.")
    lines.append("")
    n = 1
    if slots.get("start_date"):
        period = slots["start_date"]
        if slots.get("end_date") and slots["end_date"] != slots["start_date"]:
            period += f" ~ {slots['end_date']}"
        lines.append(f"  {n}. 기 간: {period}"); n += 1
    if slots.get("destination"):
        lines.append(f"  {n}. 장 소: {slots['destination']}"); n += 1
    if slots.get("item"):
        lines.append(f"  {n}. 품 목: {slots['item']}"); n += 1
    if slots.get("amount_won"):
        lines.append(f"  {n}. 금 액: {engine.won(slots['amount_won'])}"); n += 1

    ap = r.get("approval") or {}
    if ap.get("approver"):
        basis = (ap.get("basis") or "").strip()
        lines.append(f"  {n}. 전결권자: {ap['approver']}" + (f" ({basis})" if basis else "")); n += 1
    dl = r.get("deadline") or {}
    if dl.get("text"):
        lines.append(f"  {n}. {dl.get('label', '기한')}: {dl['text']}"); n += 1

    docs = r.get("required_docs") or []
    if docs:
        lines.append("")
        lines.append(f"붙임  {', '.join(docs)} 각 1부.  끝.")
    else:
        lines.append("")
        lines.append("끝.")
    return "\n".join(lines)


def _title(r: dict) -> str:
    task = r.get("task") or {}
    slots = (r.get("understanding") or {}).get("slots") or {}
    today = date.today()
    head = f"({today.month}.{today.day}.)"
    bits = [task.get("name", "기안")]
    if slots.get("destination"):
        bits.insert(0, slots["destination"])
    return head + " ".join(bits)


# ---------- 만들기 ----------

def build(org_id: str, message: str, *, user_id: str | None = None,
          understood: dict | None = None, with_form: bool = True) -> dict:
    """질문 하나로 결재 패키지를 만듭니다. AI 문장 다듬기는 쓰지 않습니다(사실만 담습니다)."""
    r = engine.answer(org_id, message, user_id=user_id, ai_summary=False,
                      understood=understood, log=False)
    if not r.get("task"):
        raise ValueError("어떤 업무인지 먼저 정해야 결재 패키지를 만들 수 있어요")

    profile = store.load_profile(org_id)
    pkg_id = f"{date.today():%Y%m%d}-{uuid.uuid4().hex[:6]}"
    d = _dir(org_id, pkg_id)
    (d / "붙임").mkdir(parents=True, exist_ok=True)

    body = _body_text(r, profile)
    (d / "기안문.txt").write_text(body, encoding="utf-8")

    attachments: list[dict] = []
    form = r.get("form") or {}
    if with_form and form.get("available"):
        try:
            made = forms.make_draft(org_id, form["id"], message)
            # make_draft 는 'file' 키에 outputs/ 아래 상대경로를 돌려줍니다.
            rel = made.get("file") or made.get("path")
            src = (store.ROOT / rel) if rel else None
            if src and src.exists():
                dest = d / "붙임" / src.name
                dest.write_bytes(src.read_bytes())
                attachments.append({"name": form.get("name") or src.stem,
                                    "file": str(dest.relative_to(d)).replace("\\", "/"),
                                    "ext": src.suffix.lstrip(".").upper()})
        except Exception as exc:                      # 서식이 없거나 채우기 실패해도 패키지는 만듭니다
            attachments.append({"name": form.get("name") or "서식", "file": None,
                                "error": str(exc)[:160]})

    manifest = {
        "id": pkg_id,
        "state": "draft",
        "created": datetime.now().isoformat(timespec="seconds"),
        "org_id": org_id,
        "org_name": (profile.get("org") or {}).get("name"),
        "user_id": user_id,
        "message": message,
        "task": r.get("task"),
        "title": _title(r),
        "body": body,
        "slots": (r.get("understanding") or {}).get("slots") or {},
        "method": (r.get("understanding") or {}).get("method"),
        "steps": r.get("steps") or [],
        "deadline": r.get("deadline"),
        "approval": r.get("approval"),
        # 결재선은 approval 안에 들어 있습니다(예전 키 이름을 쓰면 늘 빈 값이 됩니다).
        "approval_line": (r.get("approval") or {}).get("line") or [],
        "required_docs": r.get("required_docs") or [],
        "evidence": [{"doc": e.get("title"), "article": e.get("ref") or e.get("heading"),
                      "label": e.get("label"), "file": e.get("file"),
                      "layer": e.get("layer_label")}
                     for e in (r.get("evidence") or [])],
        "warnings": r.get("warnings") or [],
        "attachments": attachments,
        "history": [{"at": datetime.now().isoformat(timespec="seconds"), "state": "draft",
                     "note": "서비가 규정에서 뽑아 만들었습니다"}],
        "intranet": None,
    }
    _manifest_path(org_id, pkg_id).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


# ---------- 읽기 / 고치기 ----------

def load(org_id: str, pkg_id: str) -> dict:
    p = _manifest_path(org_id, pkg_id)
    if not p.exists():
        raise ValueError("그 결재 패키지를 찾지 못했어요")
    return json.loads(p.read_text(encoding="utf-8"))


def save(org_id: str, manifest: dict) -> dict:
    _manifest_path(org_id, manifest["id"]).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def list_all(org_id: str, limit: int = 30) -> list[dict]:
    root = store.org_dir(org_id) / "packages"
    if not root.exists():
        return []
    out = []
    for d in sorted(root.iterdir(), reverse=True):
        p = d / "manifest.json"
        if p.is_file():
            try:
                m = json.loads(p.read_text(encoding="utf-8"))
                out.append({k: m.get(k) for k in
                            ("id", "state", "created", "title", "task", "intranet")})
            except Exception:
                pass
        if len(out) >= limit:
            break
    return out


EDITABLE = {"title", "body", "slots", "approval_line", "required_docs"}


def correct(org_id: str, pkg_id: str, changes: dict, note: str = "사람이 보정") -> dict:
    """사람이 확인하며 고친 값을 반영합니다. 고칠 수 있는 항목만 받습니다."""
    m = load(org_id, pkg_id)
    if m["state"] not in ("draft", "ready"):
        raise ValueError("이미 인트라넷으로 넘어간 건은 여기서 고칠 수 없어요")
    touched = []
    for k, v in (changes or {}).items():
        if k in EDITABLE and v is not None:
            m[k] = v
            touched.append(k)
    if touched:
        m["history"].append({"at": datetime.now().isoformat(timespec="seconds"),
                             "state": m["state"], "note": f"{note}: {', '.join(touched)}"})
    return save(org_id, m)


def set_state(org_id: str, pkg_id: str, state: str, note: str = "") -> dict:
    if state not in STATES:
        raise ValueError("알 수 없는 상태입니다")
    m = load(org_id, pkg_id)
    if STATES.index(state) < STATES.index(m["state"]):
        raise ValueError("결재 패키지 상태는 되돌릴 수 없어요")
    m["state"] = state
    m["history"].append({"at": datetime.now().isoformat(timespec="seconds"),
                         "state": state, "note": note})
    # 상신까지 끝나면 후속 업무를 할 일 목록에 올립니다
    if state == "submitted":
        try:
            store.append_history(org_id, {
                "task_id": (m.get("task") or {}).get("id"),
                "task_name": (m.get("task") or {}).get("name"),
                "message": m.get("title"),
                "user_id": m.get("user_id"),
                "deadline_label": (m.get("deadline") or {}).get("label") or "처리 기한",
                "deadline_due": (m.get("deadline") or {}).get("due") or date.today().isoformat(),
                "package_id": m["id"],
            })
        except Exception:
            pass
    return save(org_id, m)


# ---------- 첨부 ----------
# 담당자가 영수증·증빙을 그 자리에서 끌어다 놓으면 패키지 붙임으로 들어갑니다.
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
DOC_EXT = {".pdf", ".docx", ".hwp", ".hwpx", ".xlsx", ".txt", ".csv"}
ALLOWED_EXT = IMAGE_EXT | DOC_EXT
MAX_BYTES = 20 * 1024 * 1024


def add_attachment(org_id: str, pkg_id: str, filename: str, data: bytes,
                   label: str | None = None) -> dict:
    """붙임 파일 한 건을 패키지에 넣습니다. 원본 서식·규정은 건드리지 않습니다."""
    m = load(org_id, pkg_id)
    if m["state"] not in ("draft", "ready"):
        raise ValueError("이미 인트라넷으로 넘어간 건에는 붙임을 더할 수 없어요")

    safe = Path(filename or "첨부").name                      # 경로 성분 제거
    ext = Path(safe).suffix.lower()
    if ext not in ALLOWED_EXT:
        raise ValueError(f"넣을 수 없는 형식입니다({ext or '확장자 없음'}). "
                         "이미지·PDF·문서 파일만 됩니다")
    if not data:
        raise ValueError("빈 파일입니다")
    if len(data) > MAX_BYTES:
        raise ValueError(f"파일이 너무 큽니다({len(data)//1024//1024}MB). 20MB까지 됩니다")

    folder = _dir(org_id, pkg_id) / "붙임"
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / safe
    stem, i = dest.stem, 1
    while dest.exists():                                      # 같은 이름이면 번호를 붙입니다
        dest = folder / f"{stem}_{i}{ext}"; i += 1
    dest.write_bytes(data)

    item = {"name": label or dest.stem,
            "file": str(dest.relative_to(_dir(org_id, pkg_id))).replace("\\", "/"),
            "ext": ext.lstrip(".").upper(),
            "kind": "image" if ext in IMAGE_EXT else "doc",
            "bytes": len(data),
            "added": datetime.now().isoformat(timespec="seconds")}
    m.setdefault("attachments", []).append(item)
    m["history"].append({"at": item["added"], "state": m["state"],
                         "note": f"붙임 추가: {dest.name}"})
    save(org_id, m)
    return m


def remove_attachment(org_id: str, pkg_id: str, rel: str) -> dict:
    m = load(org_id, pkg_id)
    if m["state"] not in ("draft", "ready"):
        raise ValueError("이미 인트라넷으로 넘어간 건은 고칠 수 없어요")
    base = _dir(org_id, pkg_id)
    keep = []
    for a in m.get("attachments") or []:
        if a.get("file") == rel:
            f = (base / rel).resolve()
            if f.is_file() and str(f).startswith(str(base.resolve())):
                f.unlink(missing_ok=True)
            continue
        keep.append(a)
    m["attachments"] = keep
    save(org_id, m)
    return m


# ---------- 영수증 읽기 ----------
RECEIPT_PROMPT = (
    "이 영수증 사진에서 다음만 JSON 하나로 뽑아 주세요. 보이지 않으면 null 로 두고, "
    "절대 지어내지 마세요.\n"
    '{"store":"상호명","amount":숫자만(원),"date":"YYYY-MM-DD","approval_no":"승인번호","items":"주요 품목"}'
)


def read_receipt(org_id: str, pkg_id: str, rel: str) -> dict:
    """붙인 영수증 이미지를 이 기기의 모델로 읽어 금액·상호·날짜를 뽑습니다.
    실패해도 붙임은 그대로 남습니다. 뽑은 값은 사람이 고칠 수 있게 돌려만 줍니다."""
    import base64
    m = load(org_id, pkg_id)
    base = _dir(org_id, pkg_id)
    f = (base / rel).resolve()
    if not f.is_file() or not str(f).startswith(str(base.resolve())):
        raise ValueError("그 붙임을 찾지 못했어요")
    if f.suffix.lower() not in IMAGE_EXT:
        raise ValueError("이미지 파일만 읽을 수 있어요")

    b64 = base64.b64encode(f.read_bytes()).decode()
    res = llm.vision("draft", RECEIPT_PROMPT, [b64], max_tokens=320)
    if not res.ok:
        return {"ok": False, "error": res.error or "영수증을 읽지 못했어요"}
    data = llm.parse_json(res.text) or {}
    if not data:
        return {"ok": False, "error": "읽은 내용에서 값을 찾지 못했어요", "raw": (res.text or "")[:200]}
    return {"ok": True, "model": res.model, "seconds": round(res.seconds, 1), "data": data}
