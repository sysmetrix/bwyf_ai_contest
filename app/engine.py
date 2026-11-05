"""비서 엔진: 업무 정의(공통) + 기관 프로필 + 규정 검색 결과를 합쳐 안내를 만듭니다.

기한 계산, 전결권자 판정, 체크리스트는 규칙으로 처리합니다(AI 불필요, 결과가 흔들리지 않음).
answer 역할에 모델이 연결돼 있으면, 찾은 근거만 써서 안내 문장을 다듬습니다.
"""
from __future__ import annotations

import re
from datetime import date, timedelta

from . import helpdesk, llm
from .rules import get_index
from .store import append_history, load_profile, load_tasks
from .understand import understand


# ---------- 프로필 값 다루기 ----------
def get_value(profile: dict, key: str):
    cur = profile
    for part in key.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def term(profile: dict, standard: str) -> str:
    return (profile.get("terms") or {}).get(standard, standard)


def won(n) -> str:
    if n is None:
        return "[확인 필요]"
    n = int(n)
    if n >= 10000 and n % 10000 == 0:
        return f"{n // 10000:,}만원"
    return f"{n:,}원"


def approver_for(profile: dict, amount: int | None) -> tuple[str | None, str]:
    thresholds = (profile.get("approval") or {}).get("thresholds") or []
    if not thresholds:
        return None, "전결 기준이 프로필에 없습니다"
    desc = " / ".join(
        (f"{won(t['max_won'])} 이하 {t['approver']}" if t.get("max_won") else f"그 이상 {t['approver']}")
        for t in thresholds)
    if amount is None:
        return None, desc
    for t in thresholds:
        if t.get("max_won") is None or amount <= t["max_won"]:
            return t["approver"], desc
    return thresholds[-1]["approver"], desc


def line_until(profile: dict, approver: str | None) -> list[str]:
    line = (profile.get("approval") or {}).get("line") or []
    if approver and approver in line:
        return line[: line.index(approver) + 1]
    return line


PARTICLES = {"을": ("을", "를"), "를": ("을", "를"), "이": ("이", "가"), "가": ("이", "가"),
             "은": ("은", "는"), "는": ("은", "는"), "과": ("과", "와"), "와": ("과", "와")}


def _has_batchim(word: str) -> bool:
    ch = word.strip()[-1:] if word.strip() else ""
    if not ("가" <= ch <= "힣"):
        return False
    return (ord(ch) - 0xAC00) % 28 != 0


def line_text(profile: dict, ctx: dict) -> str:
    if ctx["line"] and ctx["approver"]:
        return " → ".join(ctx["line"])
    thresholds = (profile.get("approval") or {}).get("thresholds") or []
    if not thresholds:
        return " → ".join(ctx["line"]) if ctx["line"] else "[확인 필요]"
    first = thresholds[0]["approver"]
    base = " → ".join(line_until(profile, first))
    rest = [t["approver"] for t in thresholds[1:] if t["approver"] != first]
    return base + (f" (금액이 크면 {'·'.join(dict.fromkeys(rest))}까지)" if rest else "")


def render(template: str, profile: dict, ctx: dict) -> str:
    def value(token: str) -> str:
        if token.startswith("용어:"):
            return term(profile, token[3:])
        if token.startswith("값:"):
            key, _, fmt = token[2:].partition("|")
            v = get_value(profile, key)
            if v is None:
                return "[확인 필요]"
            return won(v) if fmt == "원" else str(v)
        if token == "결재선":
            return line_text(profile, ctx)
        if token == "전결권자":
            return ctx["approver"] or "금액에 따라 다름"
        return "{" + token + "}"

    def repl(m: re.Match) -> str:
        v = value(m.group(1))
        particle = m.group(2)
        if particle:
            pair = PARTICLES[particle]
            particle = pair[0] if _has_batchim(v) else pair[1]
        return v + (particle or "")

    return re.sub(r"\{([^{}]+)\}(을|를|이|가|은|는|과|와)?(?![가-힣])|\{([^{}]+)\}",
                  lambda m: repl(m) if m.group(1) else value(m.group(3)), template)


# ---------- 안내 만들기 ----------
def answer(org_id: str, message: str, today: date | None = None, log: bool = True,
           user_id: str | None = None, ai_summary: bool = True, understood: dict | None = None,
           history: list | None = None) -> dict:
    """ai_summary=False: AI 문장 다듬기를 빼고 바로 답합니다(화면은 나중에 /api/chat/summary로 문장만 받아 바꿈).
    understood: 앞에서 이미 알아낸 업무·정보(task_id, slots)를 다시 분류하지 않고 씁니다."""
    today = today or date.today()
    profile = load_profile(org_id)
    tasks = {t["id"]: t for t in load_tasks()}
    if understood is not None:
        u = {"task_id": understood.get("task_id"), "slots": understood.get("slots") or {},
             "method": understood.get("method") or "규칙(키워드)", "ai": None}
    else:
        u = understand(message, today)
    task = tasks.get(u["task_id"]) if u["task_id"] else None
    index = get_index(org_id)
    org = profile.get("org", {})
    base = {"org": {"id": org_id, "name": org.get("name"), "type": org.get("type")},
            "message": message, "understanding": {"method": u["method"], "ai": u["ai"],
                                                  "slots": u["slots"]}}

    if helpdesk.is_followup(message, history) and llm.role_enabled("answer"):
        # "방금 거 줄여 줘"처럼 앞 답을 고쳐 달라는 말은 새 업무로 분류하지 않고 대화로 이어서 씁니다
        follow = helpdesk.ai_general_answer(org_id, org.get("name") or org_id, message, history, evidence=[])
        if follow:
            return {**base, **follow}
    topic = helpdesk.detect(message, task_found=task is not None)
    if topic:
        return {**base, **helpdesk.answer_topic(org_id, org.get("name") or org_id, topic, message)}
    if task is None:
        return {**base, **helpdesk.answer_unknown(org_id, org.get("name") or org_id, message, history)}

    slots = u["slots"]
    amount = slots.get("amount_won")
    approver, approval_basis = approver_for(profile, amount)
    line = line_until(profile, approver)
    ctx = {"line": line, "approver": approver}

    # 기관이 절차를 직접 다듬어 뒀으면(task_overrides) 그걸 쓰고, 아니면 공통 템플릿을 씁니다.
    override_steps = (profile.get("task_overrides") or {}).get(task["id"], {}).get("steps")
    steps_custom = bool(override_steps)
    steps = [_explain_missing(render(s, profile, ctx)) for s in (override_steps or task.get("steps", []))]
    docs = [render(s, profile, ctx) for s in task.get("required_docs", [])]
    next_actions = [render(s, profile, ctx) for s in task.get("next_actions", [])]
    # 제안(tips): 정해진 답이 아니라 "이런 걸 챙기면 좋다"는 참고용 안내입니다.
    # 재난·애도기간 고려처럼 업무마다 다른 제안을 여기 계속 추가할 수 있는 공용 틀입니다.
    tips = [render(s, profile, ctx) for s in task.get("tips", [])]

    # 기한
    deadline = None
    if task.get("deadline"):
        spec = task["deadline"]
        days = get_value(profile, spec["key"])
        label = render(spec["label"], profile, ctx)
        if days is None:
            deadline = {"label": label, "text": None, "missing": True, "due": None}
        else:
            base_iso = slots.get(spec["base"]) or (slots.get("start_date") if spec["base"] == "end_date" else None)
            if spec["direction"] == "after":
                text = f"{spec['base_label']}부터 {days}일 이내"
            else:
                text = f"{spec['base_label']} {days}일 전까지"
            due = None
            if base_iso:
                b = date.fromisoformat(base_iso)
                due_d = b + timedelta(days=days) if spec["direction"] == "after" else b - timedelta(days=days)
                due = due_d.isoformat()
                text += f" → {due_d.month}월 {due_d.day}일까지"
                if due_d < today:
                    text += " (이미 지났어요. 담당자에게 바로 알려 주세요)"
            deadline = {"label": label, "text": text, "due": due, "days": days}

    # 근거 조문
    queries = [message] + [render(q, profile, ctx) for q in task.get("rule_queries", [])]
    # 여러 검색어의 점수를 합산 → 여러 관점에서 동시에 맞는 조문이 위로
    combined: dict[tuple, list] = {}
    for q in queries:
        for art, score in index.search(q, k=5):
            key = (art.file, art.ref)
            if key in combined:
                combined[key][1] += score
            else:
                combined[key] = [art, score]
    ranked = sorted(combined.values(), key=lambda x: x[1], reverse=True)
    evidence = [a.as_dict(s) for a, s in ranked[:4]]

    # 개인 보충(관행 메모): 공통·기관 규정 층 외에 담당자 개인이 보충해 두는 층. 규정과 충돌하면 경고합니다.
    practice, warnings = [], []
    for note in profile.get("practice_notes") or []:
        if note.get("task") not in (None, task["id"]):
            continue
        conflict = None
        for key, claimed in (note.get("claims") or {}).items():
            actual = get_value(profile, key)
            if actual is not None and claimed != actual:
                conflict = f"규정 기준은 {actual}, 메모는 {claimed} → 규정 기준으로 안내합니다"
        practice.append({"text": note["text"], "conflict": conflict})
        if conflict:
            warnings.append(f"개인 보충(관행 메모) '{note['text']}'가 규정과 다릅니다. {conflict}")

    if task.get("needs_amount") and amount is None:
        warnings.append("금액을 알려 주시면 전결권자와 견적 기준을 정확히 짚어 드릴게요.")

    form = None
    if task.get("form"):
        fpath = (profile.get("forms") or {}).get(task["form"])
        ext = fpath.rsplit(".", 1)[-1].upper() if fpath and "." in fpath else None
        form = {"id": task["form"], "available": bool(fpath), "path": fpath, "ext": ext,
                "name": term(profile, FORM_NAMES.get(task["form"], task["name"])),
                "fills": FORM_FILLS.get(task["form"], [])}

    result = {**base,
              "task": {"id": task["id"], "name": task["name"], "category": task["category"]},
              "steps": steps, "required_docs": docs, "deadline": deadline,
              "approval": {"approver": approver, "line": line, "basis": approval_basis,
                           "amount_won": amount},
              "evidence": evidence, "practice": practice, "warnings": warnings, "tips": tips,
              "form": form, "next_actions": next_actions, "steps_custom": steps_custom,
              "lead": render(task.get("summary", ""), profile, ctx)}
    if helpdesk.wants_writing(message) and llm.role_enabled("answer"):
        # 글을 써 달라는 요청: 규정으로 확인한 사실(기한·전결·절차)을 넘겨 AI가 초안을 씁니다
        facts = "\n".join([f"- 업무: {task['name']}"] + [f"- {x}" for x in steps]
                           + ([f"- 기한: {deadline['label']} {deadline['text']}"] if deadline and deadline.get("text") else [])
                           + ([f"- 전결권자: {approver}"] if approver else []))
        written = helpdesk.ai_general_answer(org_id, org.get("name") or org_id, message, history,
                                             facts=facts, evidence=evidence)
        if written:
            return {**base, **written, "related_task": result["task"]}
    if ai_summary:
        result["summary"], result["summary_by"] = _summary(result, profile)
    else:
        result["summary"], result["summary_by"] = _template_summary(result), "규칙"
        result["summary_pending"] = llm.role_enabled("answer")
    result["user_id"] = user_id
    if log:
        try:
            result["history_id"] = append_history(org_id, {
                "task": task["name"], "task_id": task["id"], "message": message[:60],
                "user_id": user_id, "deadline_due": deadline["due"] if deadline else None,
                "next_actions": next_actions})
        except OSError:
            pass
    return result


FORM_NAMES = {"travel_settlement": "여비 정산서", "leave_request": "연가 신청서", "purchase_request": "구매 요청서",
              "travel_request": "출장 신청서", "sick_leave": "병가 신청서", "event_plan": "행사 계획서",
              "draft_document": "기안문"}
FORM_FILLS = {"travel_settlement": ["출장지", "출장 기간", "일비", "제출 기한", "결재선"],
              "leave_request": ["사용 기간", "사용 일수", "신청 기한", "승인권자"],
              "purchase_request": ["품목", "추정 금액", "견적 기준", "전결권자", "결재선"],
              "travel_request": ["출장지", "출장 기간", "예상 일비", "결재선"],
              "sick_leave": ["사용 기간", "사용 일수", "증빙 서류", "승인권자"],
              "event_plan": ["행사 일시", "소요 예산", "계획 기안 기한", "결과보고 기한", "전결권자", "결재선"],
              "draft_document": ["소요 금액", "전결권자", "결재선"]}


def _explain_missing(step: str) -> str:
    """기관 프로필에 값이 없을 때 '[확인 필요]'를 그대로 보여주지 않고 이유를 말해 줍니다."""
    if "[확인 필요]" not in step:
        return step
    step = step.replace("결재선: [확인 필요]", "결재선은 기관 프로필에서 정해 주세요")
    if "[확인 필요]" in step:
        step = step.replace("[확인 필요]", "○") + " (이 기관의 기준은 규정에서 찾지 못했어요. 기관 프로필에서 정해 주세요)"
    return step


def _md(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{d.month}월 {d.day}일"


def _slot_text(r: dict) -> str:
    s = (r.get("understanding") or {}).get("slots") or {}
    when = s.get("start_date")
    if when and s.get("end_date") and s["end_date"] != when:
        when = f"{_md(when)}~{_md(s['end_date'])}"
    elif when:
        when = _md(when)
    parts = [s.get("destination"), when, s.get("days") and f"{s['days']}일",
             s.get("item"), s.get("amount_won") and won(s["amount_won"])]
    return " · ".join(str(p) for p in parts if p)


def _template_summary(r: dict) -> str:
    parts = [r.get("lead") or f"{r['task']['name']} 절차를 안내할게요."]
    if _slot_text(r):
        parts.append(f"말씀하신 내용({_slot_text(r)}) 기준으로 정리했어요.")
    dl = r.get("deadline")
    if dl and dl.get("text"):
        parts.append(f"{dl['label']} 기한은 {dl['text']}예요.")
    elif dl and dl.get("missing"):
        parts.append(f"{dl['label']} 기한은 이 기관 규정에서 찾지 못했어요. 기관 프로필에서 정해 두면 날짜까지 계산해 드려요.")
    ap = r["approval"]
    if ap.get("approver") and ap.get("amount_won"):
        parts.append(f"{won(ap['amount_won'])}이면 {ap['approver']} 전결이에요.")
    form = r.get("form")
    if form and form.get("available"):
        parts.append(f"{form['name']} 초안도 바로 만들어 드릴 수 있어요.")
    elif form:
        parts.append(f"{form['name']} 서식을 서식 보관함에 올려 두면 초안까지 만들어 드려요.")
    return " ".join(parts)


def _summary(r: dict, profile: dict) -> tuple[str, str]:
    fallback = _template_summary(r)
    if not llm.role_enabled("answer"):
        return fallback, "규칙"
    ev = "\n".join(f"[{i + 1}] {e['label']} ({e['layer_label']}): {e['text']}"
                   for i, e in enumerate(r["evidence"]))
    facts = f"- 핵심: {r.get('lead')}\n" if r.get("lead") else ""
    facts += "\n".join(f"- {s}" for s in r["steps"])
    if r.get("deadline") and r["deadline"].get("text"):
        facts += f"\n- 기한: {r['deadline']['label']} {r['deadline']['text']}"
    elif r.get("deadline"):
        facts += f"\n- 기한: {r['deadline']['label']} 기한은 이 기관 규정에서 찾지 못함(지어내지 말 것)"
    if _slot_text(r):
        facts += f"\n- 질문에서 알아낸 내용: {_slot_text(r)}"
    system = ("당신은 공공기관 서무비서 '서비'입니다. 아래 '정해진 안내'와 '근거 조문'에 있는 내용만 사용해 "
              "담당자에게 2~3문장으로 친절하게 요약합니다. 질문한 상황(장소·날짜·금액 등)이 있으면 그걸 짚어서 시작합니다. "
              "새로운 숫자·기한·규정을 지어내지 않습니다. '정해진 안내'라는 말이나 그 출처 표시는 쓰지 말고, "
              "근거 조문을 말할 때만 [1]처럼 번호를 붙입니다.")
    user = (f"기관: {profile.get('org', {}).get('name')}\n질문: {r['message']}\n\n"
            f"정해진 안내:\n{facts}\n\n근거 조문:\n{ev}")
    res = llm.chat("answer", [{"role": "system", "content": system},
                              {"role": "user", "content": user}], max_tokens=300, timeout=150)
    if res.ok and res.text:
        text = re.sub(r"\s*\[(?:정해진|확정된) 안내[^\]]*\]", "", res.text).strip()
        return text, f"AI ({res.model})"
    return fallback, f"규칙 (AI 연결 실패: {res.error})"
