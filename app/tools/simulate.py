"""예시 기관 시뮬레이션: 실제 담당자처럼 질문을 던져 보고, 규정에 적힌 값과 맞는지 확인합니다.

실행: python tools/simulate.py            (AI 없이 규칙 기반 — 결과가 매번 같음)
      python tools/simulate.py --ai       (연결된 AI로 문장까지 만들어 봄)
결과: 화면 표 + outputs/simulation/시뮬레이션_결과.md + 만들어진 서식 초안(.docx)
"""
from __future__ import annotations

import argparse
import shutil
import sys
import zipfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import engine, forms, llm, store  # noqa: E402
from app.engine import won  # noqa: E402

TODAY = date(2026, 11, 4)
OUT = ROOT / "outputs" / "simulation"

# 규정 문서에 적힌 값(정답). 서비가 낸 답이 아니라 규정에서 직접 옮겨 적은 것입니다.
RULES = {
    "demo-agency": {"name": "가상 ○○출연기관", "who": "김서무(총무팀)", "settle": 5, "leave": 3, "event": 7, "report": 5,
                    "daily": 25000, "cert": 7, "quote_limit": 2_000_000,
                    "approver": [(500_000, "팀장"), (5_000_000, "실장"), (None, "대표이사")],
                    "docs": {"travel": "여비규정", "service": "복무규정", "document": "문서관리규정", "event": "행사 운영 지침"},
                    "dept": "총무팀"},
    "demo-city": {"name": "가상 ○○시청", "who": "이행정(기획팀)", "settle": 7, "leave": 1, "event": 10, "report": 7,
                  "daily": 20000, "cert": 6, "quote_limit": 5_000_000,
                  "approver": [(1_000_000, "팀장"), (10_000_000, "과장"), (None, "국장")],
                  "docs": {"travel": "여비 조례", "service": "복무 조례", "document": "행정업무 운영 규정", "event": "행사·축제 운영 지침"},
                  "dept": "총무과"},
}


def approver_for(org: str, amount: int) -> str:
    for limit, who in RULES[org]["approver"]:
        if limit is None or amount <= limit:
            return who
    return ""


def days_before(iso: str, n: int) -> str:
    return date.fromordinal(date.fromisoformat(iso).toordinal() - n).isoformat()


def days_after(iso: str, n: int) -> str:
    return date.fromordinal(date.fromisoformat(iso).toordinal() + n).isoformat()


def cites(r: dict, words: str) -> bool:
    return any(words in (e.get("title", "") + e.get("label", "")) for e in r.get("evidence", []))


def scenarios(org: str) -> list[dict]:
    R = RULES[org]
    return [
        {"id": "S1", "title": "출장 가기 전 신청", "q": "11월 12일부터 13일까지 세종으로 출장 가야 하는데 뭐부터 해요?",
         "task": "travel_request", "form": "travel_request",
         "checks": lambda r: [("근거: " + R["docs"]["travel"], cites(r, R["docs"]["travel"]))],
         "form_checks": {"출장 일수": "2일", "예상 일비": f"{R['daily'] * 2:,}원"}},
        {"id": "S2", "title": "출장 다녀와서 여비 정산", "q": "11월 12일부터 13일까지 세종 출장 다녀와서 정산해야 해요",
         "task": "travel_settlement", "form": "travel_settlement",
         "checks": lambda r: [(f"정산 기한 = 복귀일+{R['settle']}일 ({days_after('2026-11-13', R['settle'])})",
                               (r.get("deadline") or {}).get("due") == days_after("2026-11-13", R["settle"])),
                              ("근거: " + R["docs"]["travel"], cites(r, R["docs"]["travel"]))],
         "form_checks": {"일비": f"{R['daily'] * 2:,}원"}},
        {"id": "S3", "title": "연가 신청", "q": "12월 24일부터 2일 휴가 내려고요",
         "task": "annual_leave", "form": "leave_request",
         "checks": lambda r: [(f"신청 기한 = 사용일-{R['leave']}일 ({days_before('2026-12-24', R['leave'])})",
                               (r.get("deadline") or {}).get("due") == days_before("2026-12-24", R["leave"])),
                              ("근거: " + R["docs"]["service"], cites(r, R["docs"]["service"]))],
         "form_checks": {"사용 일수": "2일"}},
        {"id": "S4", "title": "병가 4일 (진단서 필요 없음)", "q": "몸살이 심해서 11월 5일부터 4일 병가 내야 해요",
         "task": "sick_leave", "form": "sick_leave",
         "checks": lambda r: [(f"절차에 진단서 기준 {R['cert']}일", any(f"{R['cert']}일 이상" in s for s in r["steps"])),
                              ("근거: " + R["docs"]["service"], cites(r, R["docs"]["service"]))],
         "form_checks": {"증빙 서류": f"없음 (연속 {R['cert']}일 미만)"}},
        {"id": "S5", "title": "병가 8일 (진단서 필요)", "q": "수술 때문에 11월 5일부터 8일 병가를 써야 해요",
         "task": "sick_leave", "form": "sick_leave", "checks": lambda r: [],
         "form_checks": {"증빙 서류": f"진단서 첨부 (연속 {R['cert']}일 이상)"}},
        {"id": "S6", "title": "물품 30만원", "q": "워크숍 물품 30만원어치 사야 해요",
         "task": "purchase", "form": "purchase_request",
         "checks": lambda r: [(f"전결권자 = {approver_for(org, 300_000)}", r["approval"]["approver"] == approver_for(org, 300_000))],
         "form_checks": {"견적 기준": "견적서 1부"}},
        {"id": "S7", "title": "물품 300만원", "q": "회의실 프로젝터 300만원짜리 사야 해요",
         "task": "purchase", "form": "purchase_request",
         "checks": lambda r: [(f"전결권자 = {approver_for(org, 3_000_000)}", r["approval"]["approver"] == approver_for(org, 3_000_000))],
         "form_checks": {"견적 기준": "견적서 1부" if 3_000_000 < R["quote_limit"] else "2인 이상 견적"}},
        {"id": "S8", "title": "행사 개최 (예산 80만원)", "q": "12월 10일에 주민 설명회 행사를 열려고 하는데 예산은 80만원이에요",
         "task": "event_hosting", "form": "event_plan",
         "checks": lambda r: [(f"계획 기안 기한 = 행사일-{R['event']}일 ({days_before('2026-12-10', R['event'])})",
                               (r.get("deadline") or {}).get("due") == days_before("2026-12-10", R["event"])),
                              (f"전결권자 = {approver_for(org, 800_000)}", r["approval"]["approver"] == approver_for(org, 800_000)),
                              ("재난·애도기간 제안 표시", bool(r.get("tips")))],
         "form_checks": {"결과보고 기한": f"행사일부터 {R['report']}일 이내", "전결권자": approver_for(org, 800_000)}},
        {"id": "S9", "title": "일반 기안", "q": "업무협약 체결 기안을 올려야 하는데 결재선이 어떻게 돼요?",
         "task": "general_approval", "form": "draft_document",
         "checks": lambda r: [("근거: " + R["docs"]["document"], cites(r, R["docs"]["document"]))],
         "form_checks": {"수신": "내부결재"}},
        {"id": "S10", "title": "부서 보충 지침이 먼저 나오는지", "q": "출장 정산할 때 영수증은 어떻게 첨부해요?",
         "task": "travel_settlement", "form": None,
         "checks": lambda r: [(f"근거에 {R['dept']} 보충 지침(부서 층)", any(e["layer"] == "dept" for e in r.get("evidence", [])))]},
        {"id": "S11", "title": "서비에게 묻기: 규정 어디서 찾아?", "q": "너 규정을 어디서 찾는거야?",
         "task": None, "form": None,
         "checks": lambda r: [("서비 안내로 답함", r.get("kind") == "help"),
                              ("이 기관 문서 7개(기관 6+부서 1)를 보여 줌",
                               len([d for d in r.get("docs", []) if d["layer"] != "common"]) == 7)]},
        {"id": "S12", "title": "업무 밖 질문", "q": "오늘 점심 메뉴 추천해 줘",
         "task": None, "form": None,
         "checks": lambda r: [("업무로 억지 분류하지 않음", r.get("task") is None)]},
    ]


def run(use_ai: bool) -> int:
    original = llm.role_enabled
    if not use_ai:
        llm.role_enabled = lambda role: False
    else:
        store.load_secrets_into_env()
    try:
        return _run(use_ai)
    finally:
        llm.role_enabled = original


def _run(use_ai: bool) -> int:
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    rows, md, fails = [], [], 0
    md.append(f"# 서비 예시 기관 시뮬레이션 결과\n\n- 기준일: {TODAY.isoformat()} · 모드: {'AI 연결' if use_ai else '규칙 기반(AI 없음)'}\n")
    for org in RULES:
        R = RULES[org]
        md.append(f"\n## {R['name']} — {R['who']}\n\n| # | 상황 | 업무 | 확인 | 결과 |\n|---|---|---|---|---|")
        for sc in scenarios(org):
            r = engine.answer(org, sc["q"], today=TODAY, log=False)
            got_task = (r.get("task") or {}).get("id")
            checks = [("업무 = " + str(sc["task"]), got_task == sc["task"])] + sc["checks"](r)
            if sc.get("form"):
                d = forms.make_draft(org, sc["form"], sc["q"], today=TODAY)
                out = ROOT / d["file"]
                target = OUT / f"{org}_{sc['id']}_{sc['form']}.docx"
                shutil.copy2(out, target)
                out.unlink()
                with zipfile.ZipFile(target) as z:
                    xml = z.read("word/document.xml").decode("utf-8")
                checks.append(("서식에 빈 자리표시 {{ }} 없음", "{{" not in xml))
                for k, want in sc.get("form_checks", {}).items():
                    checks.append((f"서식 '{k}' = {want}", str(d["filled"].get(k, "")).startswith(want)))
            ok = all(c[1] for c in checks)
            fails += 0 if ok else 1
            rows.append((org, sc["id"], sc["title"], ok, [c for c in checks if not c[1]]))
            detail = "<br>".join(("✅ " if c[1] else "❌ ") + c[0] for c in checks)
            md.append(f"| {sc['id']} | {sc['title']}<br><small>“{sc['q']}”</small> | {(r.get('task') or {}).get('name') or r.get('kind')} "
                      f"| {detail} | {'통과' if ok else '**확인 필요**'} |")
        md.append("\n**안내 예시 (S2 여비 정산)**\n")
        r = engine.answer(org, scenarios(org)[1]["q"], today=TODAY, log=False)
        md.append(f"> {r['summary']}\n")
        md.append("\n".join(f"{i}. {s}" for i, s in enumerate(r["steps"], 1)))
        if r.get("warnings"):
            md.append("\n" + "\n".join(f"⚠ {w}" for w in r["warnings"]))
    total = len(rows)
    md.insert(1, f"\n**결과: {total - fails}/{total} 통과**\n")
    report = OUT / "시뮬레이션_결과.md"
    report.write_text("\n".join(md) + "\n", encoding="utf-8")

    for org, sid, title, ok, bad in rows:
        print(f"{'통과' if ok else '확인필요'}  {RULES[org]['name']:<10} {sid:<4} {title}")
        for name, _ in bad:
            print(f"          ❌ {name}")
    print(f"\n결과: {total - fails}/{total} 통과 · 보고서: {report}")
    return fails


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ai", action="store_true", help="연결된 AI까지 써서 시뮬레이션")
    sys.exit(1 if run(ap.parse_args().ai) else 0)
