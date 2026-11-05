"""서식 초안 생성: 기관 서식 파일의 {{항목}} 자리에 아는 값을 채워 새 파일로 저장합니다.

원본 서식은 바꾸지 않고, 결과는 outputs/<기관>/ 에 따로 만듭니다.
"""
from __future__ import annotations

import re
import zipfile
from datetime import date, datetime
from io import BytesIO
from pathlib import Path

from docx import Document

from .engine import answer, approver_for, line_text, line_until
from .store import OUTPUTS, ROOT, org_dir

BLANK = "[확인 필요]"
PLACEHOLDER = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")


def _period(slots: dict) -> str:
    s, e = slots.get("start_date"), slots.get("end_date")
    if s and e and s != e:
        return f"{s} ~ {e}"
    return s or BLANK


def build_values(org_id: str, form_id: str, message: str, today: date | None = None) -> dict:
    today = today or date.today()
    r = answer(org_id, message, today=today, log=False, ai_summary=False)
    from .store import load_profile
    profile = load_profile(org_id)
    slots = (r.get("understanding") or {}).get("slots", {})
    amount = slots.get("amount_won")
    approver, _ = approver_for(profile, amount)
    line = line_text(profile, {"line": line_until(profile, approver), "approver": approver}) or BLANK
    deadline = (r.get("deadline") or {}).get("text") or BLANK
    days = slots.get("days")
    daily = (profile.get("allowances") or {}).get("daily_won")

    values = {"작성일": today.isoformat(), "소속": BLANK, "직급": BLANK, "출장자": BLANK, "신청자": BLANK,
              "요청자": BLANK, "사유": BLANK, "교통비": "[영수증 금액]", "숙박비": "[영수증 금액]",
              "식비": "[영수증 금액]", "업무 대행자": BLANK, "비상 연락처": BLANK}
    docs = [d for d in (r.get("required_docs") or [])[1:]]  # 첫 번째는 서식 자신
    if form_id == "travel_settlement":
        values.update({
            "출장지": slots.get("destination") or BLANK,
            "출장 기간": _period(slots),
            "출장 일수": f"{days}일" if days else BLANK,
            "일비": f"{daily * days:,}원 ({daily:,}원 × {days}일)" if daily and days else BLANK,
            "여비 합계": f"[영수증 확인 후 합산 — 일비 {daily * days:,}원 포함]" if daily and days else "[영수증 확인 후 합산]",
            "법인카드 사용액": "[법인카드로 낸 금액이 있으면 기재]",
            "붙임": ", ".join(docs) if docs else BLANK,
            "제출 기한": deadline,
            "결재선": line,
        })
    elif form_id == "leave_request":
        line_list = (profile.get("approval") or {}).get("line") or []
        values.update({
            "휴가 종류": "연가",
            "사용 기간": _period(slots),
            "사용 일수": f"{days}일" if days else BLANK,
            "신청 기한": deadline,
            "승인권자": line_list[1] if len(line_list) > 1 else BLANK,
        })
    elif form_id == "travel_request":
        values.update({
            "출장지": slots.get("destination") or BLANK,
            "출장 기간": _period(slots),
            "출장 일수": f"{days}일" if days else BLANK,
            "출장 목적": BLANK,
            "교통수단": BLANK,
            "동행자": "[없으면 '없음']",
            "예상 일비": f"{daily * days:,}원 ({daily:,}원 × {days}일)" if daily and days else BLANK,
            "결재선": line,
        })
    elif form_id == "sick_leave":
        cert = (profile.get("sick_leave") or {}).get("certificate_days")
        if cert and days:
            proof = f"진단서 첨부 (연속 {cert}일 이상)" if days >= cert else f"없음 (연속 {cert}일 미만)"
        elif cert:
            proof = f"연속 {cert}일 이상이면 진단서 첨부"
        else:
            proof = BLANK
        line_list = (profile.get("approval") or {}).get("line") or []
        values.update({
            "휴가 종류": "병가",
            "사용 기간": _period(slots),
            "사용 일수": f"{days}일" if days else BLANK,
            "증빙 서류": proof,
            "승인권자": line_list[1] if len(line_list) > 1 else BLANK,
        })
    elif form_id == "event_plan":
        report = (profile.get("deadlines") or {}).get("event_report_days")
        start = slots.get("start_date")
        values.update({
            "행사명": BLANK,
            "목적": BLANK,
            "세부 프로그램": BLANK,
            "안전 관리": "[참석 인원·장소에 맞는 비상 대피로와 응급 연락망]",
            "행사 일시": start or BLANK,
            "장소": slots.get("destination") or BLANK,
            "참석 대상": BLANK,
            "소요 예산": f"{amount:,}원" if amount else BLANK,
            "계획 기안 기한": deadline,
            "결과보고 기한": f"행사일부터 {report}일 이내" if report else BLANK,
            "전결권자": approver or "[예산에 따라 다름]",
            "결재선": line,
        })
    elif form_id == "draft_document":
        values.update({
            "제목": BLANK,
            "수신": "내부결재",
            "경유": "해당 없음",
            "붙임": "[첨부물 이름과 수량 — 없으면 지움]",
            "기안자": BLANK,
            "검토자": BLANK,
            "협조자": "[협조 부서가 있으면 기재]",
            "시행번호": "[처리과명-일련번호]",
            "접수": "(받는 기관이 기재)",
            "주소": BLANK,
            "전화": BLANK,
            "전자우편": BLANK,
            "공개 구분": "[공개 / 부분공개 / 비공개]",
            "주요 내용": BLANK,
            "소요 금액": f"{amount:,}원" if amount else "없음 [확인 필요]",
            "전결권자": approver or "[금액에 따라 다름]",
            "결재선": line,
        })
    elif form_id == "purchase_request":
        limit = (profile.get("purchase") or {}).get("single_quote_limit_won")
        if amount is not None and limit:
            quote = "견적서 1부" if amount < limit else "2인 이상 견적"
            quote += f" (기준 {limit:,}원)"
        else:
            quote = BLANK
        values.update({
            "품목": slots.get("item") or BLANK,
            "규격": BLANK,
            "수량": BLANK,
            "용도": BLANK,
            "납품 희망일": BLANK,
            "예산 과목": BLANK,
            "추정 금액": f"{amount:,}원" if amount else BLANK,
            "견적 기준": quote,
            "전결권자": approver or BLANK,
            "결재선": line,
        })
    return values


def _fill_paragraph(paragraph, values: dict, missing: set, used: set) -> None:
    text = paragraph.text
    if "{{" not in text:
        return

    def repl(m):
        used.add(m.group(1))
        v = values.get(m.group(1), BLANK)
        if v == BLANK or str(v).startswith("["):
            missing.add(m.group(1))
        return str(v)

    new = PLACEHOLDER.sub(repl, text)
    runs = paragraph.runs
    if runs:
        runs[0].text = new
        for run in runs[1:]:
            run.text = ""
    else:
        paragraph.add_run(new)


def _fill_hwpx(src: Path, out: Path, values: dict) -> tuple[set, set]:
    """HWPX(zip+XML)의 <hp:t>...</hp:t> 글자 안에서 {{항목}}을 찾아 바꿉니다."""
    missing: set = set()
    used: set = set()

    def repl(m: re.Match) -> str:
        used.add(m.group(1))
        v = values.get(m.group(1), BLANK)
        if v == BLANK or str(v).startswith("["):
            missing.add(m.group(1))
        return _xml_escape(str(v))

    with zipfile.ZipFile(src) as zin:
        buf = BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                data = zin.read(item.filename)
                if re.match(r"Contents/section\d+\.xml", item.filename):
                    text = data.decode("utf-8", errors="replace")

                    def tag_repl(tm: re.Match) -> str:
                        return "<hp:t" + tm.group(1) + ">" + PLACEHOLDER.sub(repl, tm.group(2)) + "</hp:t>"

                    text = re.sub(r"<hp:t([^>]*)>(.*?)</hp:t>", tag_repl, text, flags=re.S)
                    data = text.encode("utf-8")
                zout.writestr(item, data)
        out.write_bytes(buf.getvalue())
    return missing, used


def _xml_escape(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _docx_preview(doc) -> dict:
    """채워 넣은 뒤의 문서에서 실제 서식 모양(표)을 그대로 뽑아냅니다.
    화면에 글로만 나열하지 않고, 원본 서식과 같은 표 구조로 보여주기 위함입니다."""
    title_lines = [p.text.strip() for p in doc.paragraphs if p.text.strip()][:3]
    tables = [[[c.text for c in row.cells] for row in table.rows] for table in doc.tables]
    return {"title_lines": title_lines, "tables": tables}


def make_draft(org_id: str, form_id: str, message: str,
               today: date | None = None) -> dict:
    from .store import load_profile
    profile = load_profile(org_id)
    rel = (profile.get("forms") or {}).get(form_id)
    if not rel:
        raise ValueError("이 기관 프로필에 연결된 서식이 없습니다")
    src = (org_dir(org_id) / rel).resolve()
    if org_dir(org_id).resolve() not in src.parents or not src.exists():
        raise ValueError("서식 파일을 찾을 수 없습니다")
    ext = src.suffix.lower()
    if ext not in (".docx", ".hwpx"):
        raise ValueError("이 서식 형식은 자동 채우기를 지원하지 않습니다 (.docx, .hwpx만 가능)")

    values = build_values(org_id, form_id, message, today)
    out_dir = OUTPUTS / org_id
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{datetime.now():%Y%m%d-%H%M%S}_{form_id}_초안{ext}"

    preview = None
    if ext == ".docx":
        doc = Document(str(src))
        missing: set = set()
        used: set = set()
        for p in doc.paragraphs:
            _fill_paragraph(p, values, missing, used)
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    for p in cell.paragraphs:
                        _fill_paragraph(p, values, missing, used)
        preview = _docx_preview(doc)
        doc.save(str(out))
    else:
        missing, used = _fill_hwpx(src, out, values)

    return {"file": str(out.relative_to(ROOT)), "name": out.name,
            "filled": {k: values[k] for k in sorted(used - missing)},
            "missing": sorted(missing), "preview": preview}


def safe_output_path(rel: str) -> Path:
    p = (ROOT / rel).resolve()
    if OUTPUTS.resolve() not in p.parents or not p.is_file():
        raise ValueError("파일을 찾을 수 없습니다")
    return p
