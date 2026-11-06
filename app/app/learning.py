"""이 PC에서만 배우는 개인 학습 — 쓸수록 손이 덜 가게.

서비가 제안한 값을 사람이 고치면, 그 고침을 기억해 다음부터 처음부터 그렇게
채웁니다. 자주 쓰는 장소·품목·사업명·결재선도 함께 기억합니다.

**이 파일은 이 PC를 떠나지 않습니다.**

  - 저장 위치는 기관 폴더 안의 `개인학습.json` 하나입니다.
  - 밖으로 보내는 코드가 없습니다. AI도 이 기기 안의 모델만 씁니다.
  - 그래서 대외비가 섞여도 기관 밖으로 나가지 않습니다.
  - 무엇을 배웠는지 사람이 그대로 볼 수 있고(`summary`), 지울 수 있습니다(`forget`).
  - 부서를 옮기면 'PC 옮기기'(transfer)로 이 파일까지 함께 가져갑니다.

배우지 않는 것: 사람 이름·연락처처럼 남의 개인정보로 보이는 값, 그리고 한 번만
쓰인 값(우연일 수 있어 두 번 이상 쓰여야 기억합니다).
"""
from __future__ import annotations

import json
import re
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from typing import Any

from . import store

FILE = "개인학습.json"
MIN_SEEN = 2          # 두 번 이상 쓰인 값만 기억합니다(우연 제외)
KEEP = 8              # 항목마다 기억할 값의 수
MAX_LEN = 60          # 이보다 긴 값은 기억하지 않습니다

# 기억할 항목. 사람 이름·연락처는 넣지 않습니다.
FIELDS = ("destination", "item", "amount_won", "days", "사업명", "예산과목", "거래처")
LINE_KEY = "approval_line"

_PHONE = re.compile(r"\d{2,4}-\d{3,4}-\d{4}")
_EMAIL = re.compile(r"[^@\s]+@[^@\s]+")
_RRN = re.compile(r"\d{6}\s*-\s*\d{7}")


def _path(org_id: str) -> Path:
    return store.org_dir(org_id) / FILE


def _load(org_id: str) -> dict:
    try:
        return json.loads(_path(org_id).read_text(encoding="utf-8"))
    except Exception:
        return {"users": {}, "version": 1}


def _save(org_id: str, data: dict) -> None:
    data["updated"] = datetime.now().isoformat(timespec="seconds")
    _path(org_id).write_text(json.dumps(data, ensure_ascii=False, indent=2),
                             encoding="utf-8")


def _looks_personal(v: str) -> bool:
    """남의 개인정보로 보이면 기억하지 않습니다."""
    t = str(v)
    return bool(_PHONE.search(t) or _EMAIL.search(t) or _RRN.search(t))


def _ok(value: Any) -> bool:
    if value is None:
        return False
    t = str(value).strip()
    return bool(t) and len(t) <= MAX_LEN and not _looks_personal(t)


def _bucket(data: dict, user_id: str, task_id: str) -> dict:
    u = data.setdefault("users", {}).setdefault(user_id or "_", {})
    return u.setdefault(task_id or "_", {"fields": {}, "line": {}, "count": 0})


# ---------- 배우기 ----------

def record_use(org_id: str, user_id: str | None, task_id: str | None,
               slots: dict | None, approval_line: list | None = None) -> None:
    """기안을 한 건 올릴 때마다 쓰인 값을 세어 둡니다."""
    data = _load(org_id)
    b = _bucket(data, user_id or "", task_id or "")
    b["count"] = int(b.get("count", 0)) + 1
    for k, v in (slots or {}).items():
        if k in FIELDS and _ok(v):
            b["fields"].setdefault(k, {})
            key = str(v)
            b["fields"][k][key] = int(b["fields"][k].get(key, 0)) + 1
    if approval_line:
        key = " → ".join(str(x) for x in approval_line)
        if _ok(key):
            b["line"][key] = int(b["line"].get(key, 0)) + 1
    # '지난번처럼' 을 위해 마지막 건을 통째로 남겨 둡니다.
    b["last"] = {"at": datetime.now().isoformat(timespec="seconds"),
                 "slots": {k: v for k, v in (slots or {}).items() if k in FIELDS and _ok(v)},
                 "approval_line": list(approval_line or [])}
    _save(org_id, data)


def record_correction(org_id: str, user_id: str | None, task_id: str | None,
                      before: dict, after: dict) -> list[str]:
    """서비가 제안한 값과 사람이 고친 값이 다르면, 고친 쪽을 더 세게 기억합니다.

    사람이 일부러 고친 값이라 그냥 쓰인 값보다 믿을 만합니다.
    """
    data = _load(org_id)
    b = _bucket(data, user_id or "", task_id or "")
    changed = []

    bs, as_ = (before or {}).get("slots") or {}, (after or {}).get("slots") or {}
    for k in FIELDS:
        new = as_.get(k)
        if new is None or str(new) == str(bs.get(k) or ""):
            continue
        if not _ok(new):
            continue
        b["fields"].setdefault(k, {})
        b["fields"][k][str(new)] = int(b["fields"][k].get(str(new), 0)) + 2   # 고침은 2점
        changed.append(k)

    bl = " → ".join(str(x) for x in ((before or {}).get(LINE_KEY) or []))
    al = " → ".join(str(x) for x in ((after or {}).get(LINE_KEY) or []))
    if al and al != bl and _ok(al):
        b["line"][al] = int(b["line"].get(al, 0)) + 2
        changed.append(LINE_KEY)

    if changed:
        _save(org_id, data)
    return changed


# ---------- 쓰기 ----------

def suggest(org_id: str, user_id: str | None, task_id: str | None) -> dict:
    """다음 기안에 미리 채워 줄 값. 두 번 이상 쓰인 것만 돌려줍니다."""
    b = _bucket(_load(org_id), user_id or "", task_id or "")
    out: dict[str, Any] = {}
    for k, counts in (b.get("fields") or {}).items():
        top, n = _top(counts)
        if top is not None and n >= MIN_SEEN:
            out[k] = _cast(k, top)
    top_line, n = _top(b.get("line") or {})
    if top_line and n >= MIN_SEEN:
        out[LINE_KEY] = [x.strip() for x in top_line.split("→") if x.strip()]
    return out


def _top(counts: dict) -> tuple[Any, int]:
    if not counts:
        return None, 0
    k, n = Counter(counts).most_common(1)[0]
    return k, n


def _cast(field: str, value: str) -> Any:
    if field in ("amount_won", "days"):
        try:
            return int(value)
        except (TypeError, ValueError):
            return value
    return value


# ---------- "지난번처럼" ----------
# 배운 값을 서비가 알아서 끼워 넣지는 않습니다. 어디로 가는지는 사람에게 묻습니다.
# 사람이 "어제 갔던 곳으로 다시 올려 줘" 처럼 **직접 가리킬 때만** 꺼내 씁니다.

_WHEN = r"(지난번|저번|전번|어제|지난주|지난달|그때|예전|기존)"
_PTL  = r"[에의을를이가은는도만]*\s*"          # 조사가 끼어도 걸리게
_WHAT = r"(이?랑|처럼|같[은이]|갔던|했던|썼던|올렸던|보냈던|그대로|거기|그곳|출장|구매|신청|기안)"

_REPEAT = re.compile(
    _WHEN + _PTL + _WHAT
    + r"|같은\s*(곳|데|장소|품목|내용|걸로|것으로)"
    + r"|(똑같이|그대로)\s*(올려|해\s*줘|만들어)"
    + r"|다시\s*(한\s*번\s*)?(올려|작성|해\s*줘)"
)


def _norm(t: str) -> str:
    return re.sub(r"\s+", "", (t or "")).strip()


def _phrases(org_id: str, user_id: str | None) -> dict:
    data = _load(org_id)
    u = (data.get("users") or {}).get(user_id or "_") or {}
    return (u.get("_말투") or {}).get("지난번", {})


def remember_phrase(org_id: str, user_id: str | None, message: str) -> None:
    """'지난 건을 가리킨 말'로 확인된 표현을 기억합니다.

    사람마다 말투가 다릅니다. 한 번 확인되면 다음부터는 규칙처럼 즉시 알아듣습니다.
    쓸수록 그 사람 말투에 맞춰집니다.
    """
    key = _norm(message)[:40]
    if not key:
        return
    data = _load(org_id)
    u = data.setdefault("users", {}).setdefault(user_id or "_", {})
    box = u.setdefault("_말투", {}).setdefault("지난번", {})
    box[key] = int(box.get(key, 0)) + 1
    _save(org_id, data)


def wants_repeat(message: str, org_id: str | None = None,
                 user_id: str | None = None, *, ai: bool = False) -> bool:
    """사람이 지난 건을 가리키고 있는지. 세 겹으로 봅니다.

      1. 흔한 표현은 규칙으로 즉시 (0초)
      2. 그 사람이 전에 쓴 말투면 즉시 (쓸수록 넓어집니다)
      3. 그래도 모르겠고 ai=True 면 이 기기의 모델에게 한 번 묻습니다
    """
    t = message or ""
    if _REPEAT.search(t):
        return True

    if org_id is not None:
        key = _norm(t)
        for learned in _phrases(org_id, user_id):
            # 전에 쓴 말과 같거나, 그 말이 이번 말 안에 들어 있으면 같은 뜻으로 봅니다.
            if learned and (learned == key or learned in key or key in learned):
                return True

    if not ai:
        return False
    return _ask_model(t)


_ASK = ("다음 말이 '전에 했던 것과 같게 해 달라'는 뜻인지만 판단하세요. "
        "예 또는 아니오 한 글자만 답하세요.\n말: ")


def _ask_model(message: str) -> bool:
    """이 기기의 모델에게 짧게 묻습니다. 프롬프트가 짧아 빠릅니다."""
    try:
        from . import llm
        if not llm.role_enabled("classify"):
            return False
        res = llm.chat("classify",
                       [{"role": "user", "content": _ASK + message[:120]}],
                       max_tokens=4, timeout=12)
        return bool(res.ok and res.text and res.text.strip().startswith(("예", "네", "y", "Y")))
    except Exception:
        return False


def last_used(org_id: str, user_id: str | None, task_id: str | None) -> dict | None:
    """마지막으로 실제 올린 건의 값. '지난번처럼' 일 때만 씁니다."""
    b = _bucket(_load(org_id), user_id or "", task_id or "")
    return (b.get("last") or {}) or None


def repeat_slots(org_id: str, user_id: str | None, task_id: str | None,
                 slots: dict) -> tuple[dict, list[str], dict | None]:
    """지난 건의 값으로 빈 칸을 채웁니다. 날짜는 오늘 기준으로 다시 잡습니다.

    사람이 이번에 말한 값은 절대 덮지 않습니다.
    """
    last = last_used(org_id, user_id, task_id)
    out, filled = dict(slots or {}), []

    # "어제 갔던 곳" 처럼 지난 때를 가리키는 말 때문에 날짜가 과거로 잡혔으면
    # 그건 이번 일정이 아닙니다. 비워서 사람이 말하거나 묻게 합니다.
    today = date.today().isoformat()
    if str(out.get("start_date") or "") < today and out.get("start_date"):
        for k in ("start_date", "end_date", "days"):
            out.pop(k, None)

    if not last:
        return out, [], None
    for k, v in (last.get("slots") or {}).items():
        # 날짜는 지난 건 것을 그대로 쓰면 안 됩니다. 이번에 말한 날짜를 씁니다.
        if k in ("start_date", "end_date", "days"):
            continue
        if k in FIELDS and out.get(k) in (None, "", []) and _ok(v):
            out[k] = _cast(k, str(v))
            filled.append(k)
    return out, filled, last


# ---------- 보여 주기 · 지우기 ----------

LABELS = {"destination": "자주 가는 곳", "item": "자주 사는 것",
          "amount_won": "자주 쓰는 금액", "days": "자주 쓰는 일수",
          "사업명": "사업명", "예산과목": "예산과목", "거래처": "거래처",
          LINE_KEY: "자주 쓰는 결재선"}


def summary(org_id: str, user_id: str | None = None) -> dict:
    """무엇을 배웠는지 사람이 그대로 볼 수 있게 풀어 줍니다."""
    data = _load(org_id)
    tasks = {t["id"]: t.get("name", t["id"]) for t in store.load_tasks()}
    users = data.get("users") or {}
    picked = {user_id: users.get(user_id or "_", {})} if user_id else users

    out = []
    for uid, by_task in picked.items():
        for tid, b in (by_task or {}).items():
            items = []
            for k, counts in (b.get("fields") or {}).items():
                top = Counter(counts).most_common(KEEP)
                vals = [{"값": v, "쓴 횟수": n} for v, n in top if n >= MIN_SEEN]
                if vals:
                    items.append({"항목": LABELS.get(k, k), "key": k, "값들": vals})
            line = Counter(b.get("line") or {}).most_common(3)
            if line:
                items.append({"항목": LABELS[LINE_KEY], "key": LINE_KEY,
                              "값들": [{"값": v, "쓴 횟수": n} for v, n in line if n >= MIN_SEEN]})
            if items:
                out.append({"user_id": uid, "task_id": tid,
                            "업무": tasks.get(tid, tid), "올린 건수": b.get("count", 0),
                            "배운 것": items})
    return {"org_id": org_id, "updated": data.get("updated"), "learned": out,
            "file": str(_path(org_id)),
            "note": "이 자료는 이 PC 안에만 있습니다. 부서를 옮기면 'PC 옮기기'로 함께 가져갈 수 있습니다."}


def forget(org_id: str, user_id: str | None = None,
           task_id: str | None = None, key: str | None = None) -> dict:
    """배운 것을 지웁니다. 범위를 좁혀 하나만 지울 수도 있습니다."""
    data = _load(org_id)
    users = data.get("users") or {}
    if user_id is None:
        data["users"] = {}
    elif task_id is None:
        users.pop(user_id or "_", None)
    elif key is None:
        (users.get(user_id or "_") or {}).pop(task_id, None)
    else:
        b = (users.get(user_id or "_") or {}).get(task_id) or {}
        (b.get("line") if key == LINE_KEY else b.get("fields", {})).pop(key, None) \
            if key != LINE_KEY else b.update({"line": {}})
    _save(org_id, data)
    return {"ok": True}
