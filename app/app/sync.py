"""결재시스템 다시 맞추기 — 무엇이 바뀌었는지 찾아서 알려 줍니다.

설치할 때 한 번 읽어 두면 그 뒤로는 설정할 일이 없어야 합니다. 다만 기관
안에서 규정이 개정되거나 서식이 바뀌면 서비도 다시 읽어야 합니다.

본문을 전부 다시 받지는 않습니다. 결재시스템이 문서마다 개정일과 판번호를
함께 주기 때문에, 목록만 받아 지난번과 비교하면 무엇이 바뀌었는지 알 수
있습니다. 바뀐 것만 다시 읽습니다.

바뀐 사실은 조용히 넘기지 않고 담당자에게 알립니다. 규정이 언제 어떻게
바뀌었는지 제때 아는 것이 서무 담당자에게 가장 쓸모 있기 때문입니다.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from . import intranet, store


def _snapshot_path(org_id: str) -> Path:
    return store.org_dir(org_id) / "intranet_sync.json"


def _load(org_id: str) -> dict:
    try:
        return json.loads(_snapshot_path(org_id).read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save(org_id: str, data: dict) -> None:
    _snapshot_path(org_id).write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _fingerprint() -> dict:
    """목록만 받아 문서별 '지금 판'을 만듭니다. 본문은 받지 않습니다."""
    out: dict[str, dict] = {}
    cfg = intranet.get_intranet_config()
    if not cfg:
        return out
    client = intranet.IntranetClient(
        base_url=cfg.get("base_url"),
        api_key=__import__("os").environ.get(cfg.get("api_key_env", "INTRANET_API_KEY")))
    if not client.is_configured():
        return out
    org = cfg.get("org_id")
    for kind, items in (("규정", client.list_regulations(org_id=org)),
                        ("서식", client.list_forms(org_id=org))):
        for f in items:
            out[f"{kind}:{f.id}"] = {"kind": kind, "id": f.id, "title": f.title,
                                     "updated_at": f.updated_at, "version": f.version}
    return out


def check(org_id: str) -> dict:
    """바뀐 것이 있는지만 봅니다. 아무것도 고치지 않습니다."""
    now = _fingerprint()
    if not now:
        return {"ok": False, "error": "결재시스템에 연결하지 못했습니다"}
    before = (_load(org_id).get("documents") or {})

    added = [now[k] for k in now if k not in before]
    removed = [before[k] for k in before if k not in now]
    changed = [now[k] for k in now if k in before
               and (now[k].get("updated_at"), now[k].get("version"))
               != (before[k].get("updated_at"), before[k].get("version"))]

    return {"ok": True, "first_time": not before,
            "added": added, "changed": changed, "removed": removed,
            "total": len(now),
            "checked_at": datetime.now().isoformat(timespec="seconds"),
            "last_synced": _load(org_id).get("synced_at")}


def apply(org_id: str) -> dict:
    """바뀐 것을 반영합니다. 다음 질문부터 새 규정으로 답합니다."""
    res = check(org_id)
    if not res.get("ok"):
        return res
    now = _fingerprint()
    _save(org_id, {"documents": now,
                   "synced_at": datetime.now().isoformat(timespec="seconds")})
    from . import rules
    rules.invalidate(org_id)
    res["applied"] = True
    return res


def message(res: dict) -> str:
    """담당자에게 보여 줄 한 줄. 바뀐 게 없으면 빈 문자열입니다."""
    if not res.get("ok"):
        return ""
    if res.get("first_time"):
        return f"결재시스템에서 규정·서식 {res['total']}건을 읽어 두었습니다."
    bits = []
    for label, key in (("개정", "changed"), ("새로 올라온", "added"), ("내려간", "removed")):
        items = res.get(key) or []
        if items:
            names = ", ".join(f"{i['title']}" for i in items[:3])
            more = f" 외 {len(items) - 3}건" if len(items) > 3 else ""
            bits.append(f"{label} 문서 {len(items)}건 ({names}{more})")
    return " / ".join(bits)
