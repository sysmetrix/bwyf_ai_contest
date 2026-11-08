"""기관 프로필 초안 만들기: 기관 규정 폴더를 읽어 프로필 값을 찾고 근거를 붙입니다.

1) 공통 추출 규칙(정규식)으로 먼저 찾습니다 → AI 없이도 동작
2) draft 역할에 모델이 연결돼 있으면, 규칙으로 못 찾은 값을 모델에게 조문을 주고 물어봅니다
3) 관행 메모가 규정 값과 다르면 '충돌'로 표시합니다
"""
from __future__ import annotations

import copy
import re
from . import llm
from .engine import get_value
from .rules import Article, get_index
from .store import load_profile, load_tasks, org_dir

APPROVERS = r"(팀장|실장|과장|국장|부장|원장|대표이사|이사장|사무관|본부장|센터장|관장)"

# 항목별 추출 규칙: key, 화면 이름, 찾을 패턴(첫 그룹 = 값), 값 변환
FIELD_RULES = [
    {"key": "deadlines.travel_settlement_days", "label": "여비 정산 기한(복귀 후 일수)",
     "patterns": [r"복귀한\s*날부터\s*(\d+)\s*일\s*이내[^.\n]*?(?:정산|청구)",
                  r"(?:정산|청구)[^.\n]*?복귀[^.\n]*?(\d+)\s*일\s*이내"],
     "convert": int, "unit": "일"},
    {"key": "deadlines.leave_request_days_before", "label": "연가 신청 기한(사용일 며칠 전)",
     "patterns": [r"사용일\s*(\d+)\s*일\s*전까지[^.\n]*?신청", r"연가[^.\n]*?(\d+)\s*일\s*전까지"],
     "convert": int, "unit": "일 전"},
    {"key": "allowances.daily_won", "label": "일비(1일)",
     "patterns": [r"일비는\s*1일\s*([\d,]+)\s*원"],
     "convert": lambda s: int(s.replace(",", "")), "unit": "원"},
    {"key": "purchase.single_quote_limit_won", "label": "견적서 1부 기준 금액",
     "patterns": [r"추정가격\s*(\d[\d,]*)\s*만원\s*미만[^.\n]*?견적서\s*1부"],
     "convert": lambda s: int(s.replace(",", "")) * 10000, "unit": "원"},
]

TERM_RULES = [
    # (표준 용어, 기관 규정에서 찾을 정의 패턴)
    ("지급 요청", r'"(지급요청|지출결의|지급청구|지출요청)"이란'),
]

FORM_HINTS = {"travel_settlement": ["travel_settlement", "정산", "청구", "여비"],
              "travel_request": ["travel_request", "출장 신청", "출장신청", "출장 명령", "출장명령"],
              "leave_request": ["leave_request", "연가", "휴가"],
              "sick_leave": ["sick_leave", "병가"],
              "purchase_request": ["purchase_request", "구매", "물품"],
              "event_plan": ["event_plan", "행사"],
              "draft_document": ["draft_document", "기안"]}


def _find(articles: list[Article], patterns: list[str]):
    for art in articles:
        for pat in patterns:
            m = re.search(pat, art.text)
            if m:
                return m.group(1), art
    return None, None


def _approval_from(articles: list[Article]):
    """'별표(전결 기준)'에서 '50만원 이하: 팀장 전결' 같은 줄을 읽어 기준표를 만듭니다."""
    for art in articles:
        rows = re.findall(r"(\d[\d,]*)\s*만원\s*(이하|초과)[^\n]*?" + APPROVERS, art.text)
        if len(rows) >= 2:
            thresholds = []
            for amount, kind, who in rows:
                won = int(amount.replace(",", "")) * 10000
                thresholds.append({"max_won": won if kind == "이하" else None, "approver": who})
            if thresholds[-1]["max_won"] is not None:
                thresholds.append({"max_won": None, "approver": thresholds[-1]["approver"]})
            return thresholds, art
    return None, None


def _line_from(articles: list[Article]):
    """'담당, 팀장, 실장, 대표이사 순으로 결재한다' 같은 문장에서 결재선을 읽습니다."""
    for art in articles:
        m = re.search(r"([가-힣]+(?:\s*,\s*[가-힣]+)+)\s*순으로\s*결재", art.text)
        if m:
            return [p.strip() for p in m.group(1).split(",")], art
    return None, None


def _src(art: Article | None) -> dict | None:
    if art is None:
        return None
    return {"label": art.label, "file": art.file, "layer": art.layer, "text": art.text[:300]}


def make_draft(org_id: str, use_model: bool = True) -> dict:
    profile = load_profile(org_id)
    index = get_index(org_id)
    org_articles = [a for a in index.articles if a.layer in ("org", "dept")]
    draft = copy.deepcopy(profile)
    fields = []

    for rule in FIELD_RULES:
        raw, art = _find(org_articles, rule["patterns"])
        current = get_value(profile, rule["key"])
        value, by = None, None
        if raw is not None:
            value, by = rule["convert"](raw), "규칙"
        fields.append({"key": rule["key"], "label": rule["label"], "unit": rule["unit"],
                       "value": value, "current": current, "by": by, "source": _src(art)})

    thresholds, art = _approval_from(org_articles)
    fields.append({"key": "approval.thresholds", "label": "전결 기준", "unit": "",
                   "value": thresholds, "current": get_value(profile, "approval.thresholds"),
                   "by": "규칙" if thresholds else None, "source": _src(art)})
    line, art = _line_from(org_articles)
    fields.append({"key": "approval.line", "label": "결재선", "unit": "",
                   "value": line, "current": get_value(profile, "approval.line"),
                   "by": "규칙" if line else None, "source": _src(art)})

    terms_found = {}
    for standard, pat in TERM_RULES:
        raw, art = _find(org_articles, [pat])
        if raw:
            terms_found[standard] = (raw, art)
    for standard, (raw, art) in terms_found.items():
        fields.append({"key": f"terms.{standard}", "label": f"용어: {standard}", "unit": "",
                       "value": raw, "current": (profile.get("terms") or {}).get(standard),
                       "by": "규칙", "source": _src(art)})

    # 서식 파일 연결
    forms_dir = org_dir(org_id) / "forms"
    form_files = sorted(p.name for p in forms_dir.glob("*") if p.is_file()) if forms_dir.exists() else []
    for form_id, hints in FORM_HINTS.items():
        exact = [f for f in form_files if f.lower().startswith(form_id + ".")]
        match = exact[0] if exact else next((f for f in form_files if any(h in f.lower() for h in hints[1:])), None)
        fields.append({"key": f"forms.{form_id}", "label": f"서식: {form_id}", "unit": "",
                       "value": f"forms/{match}" if match else None,
                       "current": (profile.get("forms") or {}).get(form_id),
                       "by": "파일 이름" if match else None,
                       "source": {"label": f"forms/{match}", "file": "", "layer": "org", "text": ""}
                       if match else None})

    # AI로 빈칸 보완
    model_info = None
    missing = [f for f in fields if f["value"] is None and not f["key"].startswith("forms.")]
    if use_model and missing and llm.role_enabled("draft"):
        model_info = _fill_with_model(missing, _articles_for(index, missing, org_articles))

    # 상태 판정 + 초안 반영
    for f in fields:
        if f["value"] is None:
            f["status"] = "missing"
        elif f["current"] in (None, "", [], {}):
            f["status"] = "new"
        elif f["current"] == f["value"]:
            f["status"] = "same"
        else:
            f["status"] = "changed"
        if f["value"] is not None:
            _set(draft, f["key"], f["value"])
            draft.setdefault("sources", {})[f["key"]] = (f["source"] or {}).get("label")

    conflicts = check_conflicts(draft)
    return {"org_id": org_id, "fields": fields, "conflicts": conflicts, "draft": draft,
            "model": model_info,
            "rule_files": sorted({a.file for a in org_articles})}


def draft_task_steps(org_id: str, task_id: str) -> dict:
    """기관 규정에서 '이 업무를 실제로 어떻게 처리하는지'를 찾아 절차 초안을 제안합니다.
    규정에 분명히 없는 내용은 만들어 내지 않고, 그럴 땐 제안 없이 공통 절차를 그대로 씁니다.
    제안은 담당자가 확인·수정한 뒤 저장해야 반영됩니다(자동 저장 아님)."""
    tasks = {t["id"]: t for t in load_tasks()}
    task = tasks.get(task_id)
    if task is None:
        raise ValueError("알 수 없는 업무입니다")

    index = get_index(org_id)
    queries = [task["name"]] + task.get("rule_queries", [])
    combined: dict[tuple, list] = {}
    for q in queries:
        for art, score in index.search(q, k=5):
            key = (art.file, art.ref)
            if key in combined:
                combined[key][1] += score
            else:
                combined[key] = [art, score]
    ranked = sorted(combined.values(), key=lambda x: x[1], reverse=True)
    org_articles = [a for a, _ in ranked if a.layer in ("org", "dept")][:6]

    if not org_articles:
        return {"ok": False, "steps": None, "evidence": [],
                "error": "이 업무와 관련된 기관 규정을 찾지 못했어요. 공통 절차를 그대로 씁니다."}
    if not llm.role_enabled("draft"):
        return {"ok": False, "steps": None, "evidence": [_src(a) for a in org_articles],
                "error": "AI 연결이 없어요(연결 안 해도 아래 근거 조문은 참고할 수 있어요)."}

    text = "\n\n".join(f"[{a.label}]\n{a.text}" for a in org_articles)[:6000]
    system = ("당신은 공공기관 서무 절차를 정리하는 도우미입니다. 아래 조문만 근거로 "
              f"'{task['name']}' 업무를 이 기관에서 실제로 처리하는 순서를 정리합니다. "
              "조문에 분명히 적히지 않은 내용은 추측해서 만들지 않습니다. "
              "조문이 절차를 설명하기에 부족하면 steps를 빈 배열로 둡니다. "
              'JSON 하나만 출력합니다. 형식: {"steps": ["1단계 문장", "2단계 문장", ...]}')
    res = llm.chat("draft", [{"role": "system", "content": system},
                             {"role": "user", "content": f"조문:\n{text}"}], max_tokens=600)
    data = llm.parse_json(res.text) or {}
    steps = [s.strip() for s in (data.get("steps") or []) if isinstance(s, str) and s.strip()]
    return {"ok": res.ok and bool(steps), "steps": steps or None,
            "evidence": [_src(a) for a in org_articles],
            "provider": res.provider, "model": res.model,
            "error": None if steps else (res.error or "조문에서 절차를 찾지 못했어요. 공통 절차를 그대로 씁니다.")}


def check_conflicts(profile: dict) -> list[dict]:
    out = []
    for i, note in enumerate(profile.get("practice_notes") or []):
        for key, claimed in (note.get("claims") or {}).items():
            actual = get_value(profile, key)
            if actual is not None and actual != claimed:
                out.append({"index": i, "note": note.get("text"), "key": key,
                            "note_value": claimed, "rule_value": actual,
                            "source": (profile.get("sources") or {}).get(key)})
    return out


def _set(d: dict, key: str, value) -> None:
    parts = key.split(".")
    cur = d
    for p in parts[:-1]:
        cur = cur.setdefault(p, {})
    cur[parts[-1]] = value


FIELD_QUERIES = {
    "deadlines.travel_settlement_days": "여비 정산 복귀 이내 제출 정산서",
    "deadlines.leave_request_days_before": "연가 신청 사용일 전까지 신청",
    "allowances.daily_won": "일비 1일 지급 금액 원",
    "purchase.single_quote_limit_won": "견적서 1부 2인 이상 견적 추정가격 수의계약",
    "approval.thresholds": "전결 기준 금액 이하 팀장 실장 대표이사",
    "approval.line": "결재 순서 담당 팀장 실장 결재선",
}


def _articles_for(index, missing: list[dict], fallback: list[Article]) -> list[Article]:
    """항목마다 관련 조문을 찾아 모읍니다. 큰 매뉴얼은 앞부분만 보내면 값을 못 찾기 때문입니다."""
    picked: list[Article] = []
    for f in missing:
        q = FIELD_QUERIES.get(f["key"]) or f["label"]
        for art, _ in index.search(q, k=3, layers={"org", "dept"}):
            if art not in picked:
                picked.append(art)
    return picked or fallback


def _fill_with_model(missing: list[dict], articles: list[Article]) -> dict:
    text = "\n\n".join(f"[{a.label}]\n{a.text}" for a in articles)[:6000]
    wanted = {f["key"]: f["label"] for f in missing}
    system = ("당신은 공공기관 규정을 읽고 설정값을 찾는 도우미입니다. 아래 조문에 '분명히 적힌' 값만 "
              "찾습니다. 없으면 null입니다. 숫자는 숫자로(금액은 원 단위), JSON 하나만 출력합니다. "
              '형식: {"키": {"value": 값, "source": "조문 이름"}}')
    user = f"찾을 항목: {wanted}\n\n조문:\n{text}"
    res = llm.chat("draft", [{"role": "system", "content": system},
                             {"role": "user", "content": user}], max_tokens=400)
    data = llm.parse_json(res.text) or {}
    filled = 0
    for f in missing:
        item = data.get(f["key"])
        if isinstance(item, dict) and item.get("value") not in (None, ""):
            f["value"] = item["value"]
            f["by"] = f"AI ({res.model})"
            f["source"] = {"label": str(item.get("source") or "AI 추출 — 조문 확인 필요"),
                           "file": "", "layer": "org", "text": ""}
            filled += 1
    return {"provider": res.provider, "model": res.model, "ok": res.ok,
            "error": res.error, "filled": filled}
