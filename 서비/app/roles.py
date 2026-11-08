"""역할 판정 — 사람이 적어 넣는 값이 아니라, 규정에서 계산해 냅니다.

판정 근거는 둘입니다.

  1. 결재시스템(인트라넷)에서 읽어 온 **내 직급·직위**
  2. 기관 규정에서 읽어 온 **전결표**

전결표에 내 직급이 결재권자로 나오면 그 범위에서 결재자입니다. 어디에도
나오지 않으면 담당자입니다. 역할은 둘 중 하나로 갈리는 꼬리표가 아니라
"무엇을 전결할 수 있는가"의 목록입니다. 센터장도 본인 출장은 기안하므로
누구나 담당자가 될 수 있고, 결재 권한만 사람마다 다릅니다.
"""
from __future__ import annotations

from typing import Any


def _approver_rank(profile: dict, approver: str | None) -> int | None:
    if not approver:
        return None
    table = (profile.get("approval") or {}).get("approver_ranks") or {}
    if approver in table:
        return table[approver]
    for name, rank in table.items():          # '실장·관장·센터장' 같은 표기까지
        if name and name in approver:
            return rank
    return None


def authority(profile: dict, user: dict | None, tasks: list[dict] | None = None) -> dict:
    """이 사람이 무엇을 전결할 수 있는지 규정에서 뽑아냅니다."""
    ap = profile.get("approval") or {}
    rank = (user or {}).get("rank")
    if rank is None:
        rank = ap.get("default_rank")

    names = {t["id"]: t.get("name", t["id"]) for t in (tasks or [])}
    approves: list[dict[str, Any]] = []

    # 직급으로 갈리는 업무 (복무·출장, 외부강의 신고)
    for rule in ap.get("by_rank") or []:
        for cond in rule.get("when") or []:
            if _approver_rank(profile, cond.get("approver")) != rank:
                continue
            lo, hi = cond.get("rank_min"), cond.get("rank_max")
            who = []
            if lo is not None:
                who.append(f"{lo}급 이하")
            if hi is not None:
                who.append(f"{hi}급 이상")
            tl = [names.get(t, t) for t in (rule.get("tasks") or [])]
            approves.append({
                "scope": f"{rule.get('name', '')} — {', '.join(who) or '전체'} 신청 건",
                "tasks": rule.get("tasks") or [],
                "task_names": tl,
                "basis": rule.get("basis", ""),
            })

    # 금액으로 갈리는 전결 (구매·지출)
    prev = None
    for t in ap.get("thresholds") or []:
        cap = t.get("max_won")
        if _approver_rank(profile, t.get("approver")) == rank:
            if cap is None:
                scope = f"금액 전결 — {prev:,}원 초과" if prev else "금액 전결 — 전액"
            elif prev:
                scope = f"금액 전결 — {prev:,}원 초과 {cap:,}원 이하"
            else:
                scope = f"금액 전결 — {cap:,}원 이하"
            approves.append({"scope": scope, "tasks": [], "task_names": [],
                             "basis": "기관 전결 기준"})
        prev = cap or prev

    return {
        "user_id": (user or {}).get("id"),
        "name": (user or {}).get("name"),
        "title": (user or {}).get("title"),
        "dept": (user or {}).get("dept"),
        "rank": rank,
        "is_approver": bool(approves),
        "role": "결재자" if approves else "담당자",
        "approves": approves,
        "source": "기관 전결표에서 계산함",
    }
