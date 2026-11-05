"""사용자 말 이해하기: 업무 분류 + 세부 정보(날짜·장소·금액) 추출.

1) 규칙 기반(키워드·정규식)으로 항상 먼저 처리합니다 → AI가 없어도 동작
2) classify 역할에 모델이 연결돼 있으면 모델 판단을 더해 빈칸을 채웁니다
"""
from __future__ import annotations

import json
import re
from datetime import date, timedelta

from . import llm
from .store import load_tasks

STOP_PLACES = {"다음", "이번", "지난", "국내", "해외", "당일", "장기", "단기", "주말", "오늘", "내일",
               "어제", "모레", "갑자기", "급하게", "다음주", "이번주", "지난주"}


def _squash(s: str) -> str:
    return re.sub(r"\s+", "", s)


def classify_keywords(message: str, tasks: list[dict] | None = None) -> tuple[str | None, dict]:
    tasks = tasks or load_tasks()
    msg = _squash(message)
    scores = {}
    for t in tasks:
        s = 0.0
        for kw in t.get("keywords", []):
            if _squash(kw) in msg:
                s += 1 + 0.2 * len(_squash(kw))
        scores[t["id"]] = round(s, 2)
    best = max(scores, key=scores.get) if scores else None
    if not best or scores[best] == 0:
        return None, scores
    return best, scores


def extract_slots(message: str, today: date | None = None) -> dict:
    today = today or date.today()
    slots: dict = {}

    # 금액
    m = re.search(r"(\d[\d,]*(?:\.\d+)?)\s*만\s*원", message)
    if m:
        slots["amount_won"] = int(float(m.group(1).replace(",", "")) * 10000)
    else:
        m = re.search(r"(\d[\d,]{3,})\s*원", message)
        if m:
            slots["amount_won"] = int(m.group(1).replace(",", ""))

    # 날짜
    dates: list[date] = []
    for mm, dd in re.findall(r"(\d{1,2})\s*월\s*(\d{1,2})\s*일", message):
        d = _safe_date(today.year, int(mm), int(dd))
        if d:
            dates.append(d)
    if not dates:
        for mm, dd in re.findall(r"(?<![\d.])(\d{1,2})[./](\d{1,2})(?![\d.])", message):
            d = _safe_date(today.year, int(mm), int(dd))
            if d:
                dates.append(d)
    relative = {"그저께": -2, "어제": -1, "오늘": 0, "내일": 1, "모레": 2}
    if not dates:
        for word, delta in relative.items():
            if word in message:
                dates.append(today + timedelta(days=delta))
                break

    if dates:
        slots["start_date"] = dates[0].isoformat()
        if len(dates) > 1:
            slots["end_date"] = max(dates).isoformat()
        else:
            # "3일부터 4일까지", "3일~5일" 처럼 월 없이 끝나는 날짜
            m = re.search(r"(?:~|부터)\s*(\d{1,2})\s*일\s*(?:까지)?", message)
            if m and "까지" in message or (m and "~" in message):
                end = _safe_date(dates[0].year, dates[0].month, int(m.group(1)))
                if end and end >= dates[0]:
                    slots["end_date"] = end.isoformat()

    # 기간(일수)
    m = re.search(r"(\d+)\s*박\s*(\d+)\s*일", message)
    if m:
        slots["days"] = int(m.group(2))
    else:
        m = re.search(r"(?<![월\d])(\d{1,2})\s*일\s*(?:간|동안)?\s*(?:연가|휴가|연차|병가|공가|출장|쉬)", message)
        if m and not re.search(r"월\s*" + m.group(1) + r"\s*일", message):
            slots["days"] = int(m.group(1))
        elif "하루" in message:
            slots["days"] = 1
    if "start_date" in slots and "end_date" not in slots and slots.get("days", 0) > 1:
        start = date.fromisoformat(slots["start_date"])
        slots["end_date"] = (start + timedelta(days=slots["days"] - 1)).isoformat()
    if "start_date" in slots and "end_date" in slots and "days" not in slots:
        slots["days"] = (date.fromisoformat(slots["end_date"]) - date.fromisoformat(slots["start_date"])).days + 1

    # 출장지
    for place in re.findall(r"([가-힣]{2,6}?)(?:으로|로|에)?\s*출장", message):  # '세종으로' → '세종'
        if place not in STOP_PLACES and not place.endswith(("다음", "이번")):
            slots["destination"] = place
            break

    # 품목(물품 구매)
    qty = r"(?:\d+\s*(?:대|개|권|박스|세트|장|부)\s*)?"
    money = r"(?:\d[\d,]*(?:\.\d+)?\s*만?\s*원\s*(?:짜리|어치)?\s*(?:정도|가량|쯤)?\s*)?"
    m = re.search(r"([가-힣A-Za-z]+(?:\s[가-힣A-Za-z]+)?)\s*" + qty + money + r"(?:을|를)?\s*(?:구입|구매)", message)
    if not m:  # "회의실 프로젝터 300만원짜리 사야 해요", "토너 사려고요" 같은 말투
        m = re.search(r"([가-힣A-Za-z]+(?:\s[가-힣A-Za-z]+)?)\s*" + qty + money + r"(?:을|를)?\s*(?:사야|사려|살려|사고|살\s)",
                      message)
    if m and m.group(1) not in ("물품", "이거", "그거", "뭐", "무엇"):
        slots["item"] = m.group(1)
    return slots


def _safe_date(y: int, m: int, d: int) -> date | None:
    try:
        return date(y, m, d)
    except ValueError:
        return None


def understand(message: str, today: date | None = None, override: dict | None = None) -> dict:
    tasks = load_tasks()
    kw_task, scores = classify_keywords(message, tasks)
    slots = extract_slots(message, today)
    result = {"task_id": kw_task, "slots": slots, "method": "규칙(키워드)",
              "keyword_scores": scores, "ai": None}

    # 키워드만으로 업무가 분명하면 AI 분류를 건너뜁니다(답이 1~2초 빨라짐). 애매할 때만 AI에게 묻습니다.
    ranked = sorted(scores.values(), reverse=True) + [0, 0]
    clear = override is None and kw_task is not None and ranked[0] >= 1.4 and ranked[1] <= ranked[0] * 0.5
    ai = None if clear else _classify_with_model(message, tasks, today or date.today(), override)
    if ai is not None:
        result["ai"] = {"provider": ai["provider"], "model": ai["model"], "ok": ai["ok"],
                        "error": ai.get("error"), "seconds": ai.get("seconds")}
        if ai["ok"] and ai["data"] is not None:
            data = ai["data"]
            valid = {t["id"] for t in tasks} | {"none"}
            tid = data.get("task_id")
            if tid in valid:
                result["task_id"] = None if tid == "none" else tid
                result["method"] = "AI 모델"
            for k in ("destination", "start_date", "end_date", "item"):
                v = data.get(k)
                if v and k not in slots and (k not in ("start_date", "end_date") or _iso_ok(v)):
                    slots[k] = v
            amt = data.get("amount_won")
            if isinstance(amt, (int, float)) and amt > 0 and "amount_won" not in slots:
                slots["amount_won"] = int(amt)
            if "start_date" in slots and "end_date" in slots and "days" not in slots:
                try:
                    slots["days"] = (date.fromisoformat(slots["end_date"]) -
                                     date.fromisoformat(slots["start_date"])).days + 1
                except ValueError:
                    pass
    return result


def _iso_ok(v: str) -> bool:
    try:
        date.fromisoformat(str(v))
        return True
    except ValueError:
        return False


def _classify_with_model(message: str, tasks: list[dict], today: date,
                         override: dict | None) -> dict | None:
    if override is None and not llm.role_enabled("classify"):
        return None
    task_list = "\n".join(f"- {t['id']}: {t['name']} ({', '.join(t.get('keywords', [])[:5])})"
                          for t in tasks)
    system = ("당신은 공공기관 서무 업무 분류기입니다. 사용자의 말을 읽고 아래 업무 중 하나를 고르고, "
              "말에 나온 정보만 추출합니다. 말에 없는 정보는 null로 둡니다. JSON 하나만 출력합니다.\n"
              f"오늘 날짜: {today.isoformat()}\n업무 목록:\n{task_list}\n"
              "- none: 위 업무가 아님\n"
              '출력 형식: {"task_id": "...", "destination": null, "start_date": "YYYY-MM-DD 또는 null", '
              '"end_date": "YYYY-MM-DD 또는 null", "amount_won": null, "item": null}')
    res = llm.chat("classify", [{"role": "system", "content": system},
                                {"role": "user", "content": message}],
                   override=override, max_tokens=200, timeout=None if override else 60)
    return {"ok": res.ok, "provider": res.provider, "model": res.model, "error": res.error,
            "seconds": round(res.seconds, 2), "data": llm.parse_json(res.text)}


def eval_classifier(questions: list[dict], override: dict | None = None,
                    use_model: bool = True) -> dict:
    """테스트 세트로 업무 분류 정확도를 잽니다(모델 비교용)."""
    rows, correct, seconds = [], 0, 0.0
    tasks = load_tasks()
    for item in questions:
        if use_model:
            ai = _classify_with_model(item["q"], tasks, date.today(), override)
            data = (ai or {}).get("data") or {}
            got = data.get("task_id") if ai and ai["ok"] else "(연결 실패)"
            seconds += (ai or {}).get("seconds") or 0
            err = (ai or {}).get("error")
        else:
            tid, _ = classify_keywords(item["q"], tasks)
            got, err = tid or "none", None
        ok = got == item["expected"]
        correct += ok
        rows.append({"q": item["q"], "expected": item["expected"], "got": got, "ok": ok, "error": err})
    n = len(questions) or 1
    failed = [r for r in rows if r["got"] == "(연결 실패)"]
    if use_model and rows and len(failed) == len(rows):
        return {"accuracy": None, "correct": 0, "total": len(questions), "avg_seconds": 0.0,
                "rows": rows, "error": failed[0]["error"]}
    return {"accuracy": round(correct / n, 3), "correct": correct, "total": len(questions),
            "avg_seconds": round(seconds / n, 2) if use_model else 0.0, "rows": rows}


def describe_slots(slots: dict) -> str:
    return json.dumps(slots, ensure_ascii=False)
