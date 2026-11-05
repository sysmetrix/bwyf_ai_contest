"""서비 기본 서식: 업무별 서식(.docx)을 기관 결재선·용어에 맞춰 만들어 서식 보관함에 넣습니다.

서식 항목은 공공기관 공식 서식의 구성을 따릅니다(각 서식에 근거를 적어 둠).
기관이 쓰는 서식이 있으면 서식 보관함에서 바꿔 올리면 되고, 그 서식은 다시 덮어쓰지 않습니다.
"""
from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

from .engine import term
from .store import list_org_forms, load_profile, org_dir, save_profile

# 업무별 서식: 기관별 제목, 표 항목, 끝맺음 문구, 구성 근거
# 항목은 "이름" 또는 ("화면에 보일 이름", "채울 값 이름") — 값 이름이 {{자리표시}}가 됩니다.
FORMS = {
    "travel_request": {
        "title": {"default": "출장 신청서", "demo-city": "출장 명령 신청서"},
        "rows": ["소속", "직급", ("성명", "출장자"), "출장지", "출장 기간", "출장 일수", "출장 목적", "교통수단",
                 "동행자", "예상 일비", "결재선", "작성일"],
        "closing": "위와 같이 출장을 신청합니다.",
        "basis": "출장 명령 항목(출장자·출장지·기간·목적·교통수단) 기준",
    },
    "travel_settlement": {
        "title": {"term": "여비 정산서"},
        "rows": [("성명", "출장자"), "소속", "출장지", "출장 기간", "출장 일수", ("운임(교통비)", "교통비"), "일비",
                 "숙박비", "식비", ("합계", "여비 합계"), "법인카드 사용액", ("붙임(증빙)", "붙임"), "제출 기한",
                 "결재선", "작성일"],
        "closing": "위와 같이 여비를 정산(청구)합니다.",
        "basis": "「공무원 여비 규정」 제2조 여비의 종류(운임·일비·숙박비·식비) 기준",
    },
    "leave_request": {
        "title": {"default": "휴가 신청서(연가)"},
        "rows": ["소속", "직급", ("성명", "신청자"), "휴가 종류", "사용 기간", "사용 일수", "사유", "업무 대행자",
                 "비상 연락처", "신청 기한", "승인권자", "작성일"],
        "closing": "위와 같이 휴가를 신청합니다.",
        "basis": "공무원 휴가 제도(연가·병가·공가·특별휴가) 신청 항목 기준",
    },
    "sick_leave": {
        "title": {"default": "휴가 신청서(병가)"},
        "rows": ["소속", "직급", ("성명", "신청자"), "휴가 종류", "사용 기간", "사용 일수", "사유", "증빙 서류",
                 "업무 대행자", "비상 연락처", "승인권자", "작성일"],
        "closing": "위와 같이 휴가를 신청합니다.",
        "basis": "공무원 휴가 제도(연가·병가·공가·특별휴가) 신청 항목 기준",
    },
    "purchase_request": {
        "title": {"term": "구매 요청서"},
        "rows": [("요청 부서", "소속"), ("요청자", "요청자"), ("품명", "품목"), "규격", "수량", "추정 금액", "용도",
                 "납품 희망일", "예산 과목", "견적 기준", "전결권자", "결재선", "작성일"],
        "closing": "위와 같이 물품 구매를 요청합니다.",
        "basis": "물품 구매 요구 항목(품명·규격·수량·금액·용도·예산 과목) 기준",
    },
    "event_plan": {
        "title": {"default": "행사 계획서"},
        "rows": ["행사명", "목적", "행사 일시", "장소", ("참석 대상·인원", "참석 대상"), "세부 프로그램", "소요 예산",
                 "안전 관리", "계획 기안 기한", "결과보고 기한", "전결권자", "결재선", "작성일"],
        "closing": "위와 같이 행사를 계획하여 보고합니다.",
        "basis": "기관 행사 운영 지침의 행사 계획 기재 사항 기준",
    },
}

# 기안문은 표 서식이 아니라 공문서 구성(두문·본문·결문)을 따릅니다.
# 근거: 「행정업무의 운영 및 혁신에 관한 규정 시행규칙」 제4조(문서의 구성)
DRAFT_BASIS = "「행정업무의 운영 및 혁신에 관한 규정 시행규칙」 제4조 문서의 구성(두문·본문·결문) 기준"


HEAD = {"demo-agency": "가상 ○○출연기관장", "demo-city": "가상 ○○시장"}  # 예시 기관의 '○○ 귀하'


def _head(org_id: str, org_name: str, line: list) -> str:
    return HEAD.get(org_id) or f"{org_name} {line[-1] if line else '기관장'}"


def _title(spec: dict, org_id: str, profile: dict) -> str:
    t = spec["title"]
    if "term" in t:
        return term(profile, t["term"])
    return t.get(org_id) or t["default"]


def _note(example: bool, basis: str) -> str:
    return ("※ 모의 서식 (프로토타입 시연용·가상) · " if example else "※ 서비 기본 서식 — 기관 서식이 있으면 바꿔 올리세요 · ") + basis


def _shade(cell, hex_color: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_color)
    tc_pr.append(shd)


def _para(doc, text, size=11, bold=False, align=None, color=None, space_after=4):
    p = doc.add_paragraph()
    run = p.add_run(text)
    run.font.size = Pt(size)
    run.bold = bold
    if color:
        run.font.color.rgb = RGBColor.from_string(color)
    if align is not None:
        p.alignment = align
    p.paragraph_format.space_after = Pt(space_after)
    return p


def _new_doc() -> Document:
    doc = Document()
    normal = doc.styles["Normal"]
    normal.font.name = "맑은 고딕"
    normal.element.rPr.rFonts.set(qn("w:eastAsia"), "맑은 고딕")
    normal.font.size = Pt(11)
    for s in doc.sections:
        s.left_margin = s.right_margin = Cm(2.2)
        s.top_margin = Cm(2)
    return doc


def _label_table(doc, rows: list) -> None:
    table = doc.add_table(rows=0, cols=2)
    table.style = "Table Grid"
    for row in rows:
        label, key = row if isinstance(row, tuple) else (row, row)
        cells = table.add_row().cells
        cells[0].text = label
        cells[1].text = "{{" + key + "}}"
        cells[0].width = Cm(4.2)
        cells[1].width = Cm(12.4)
        cells[0].paragraphs[0].runs[0].bold = True
        _shade(cells[0], "F3F4F1")


def make_draft_document(org_id: str, org_name: str, out_dir: Path, head: str, example: bool) -> str:
    """기안문: 두문(행정기관명·수신·경유) → 본문(제목·내용·붙임) → 결문(발신명의·결재·시행·연락처)."""
    doc = _new_doc()
    _para(doc, _note(example, DRAFT_BASIS), size=8, color="999999",
          align=WD_ALIGN_PARAGRAPH.CENTER, space_after=8)
    _para(doc, org_name, size=18, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, space_after=12)  # 행정기관명
    _label_table(doc, [("수신", "수신"), ("(경유)", "경유"), ("제목", "제목"), ("내용", "주요 내용"),
                       ("소요 금액", "소요 금액"), ("붙임", "붙임")])
    _para(doc, "끝.", align=WD_ALIGN_PARAGRAPH.RIGHT, space_after=16)
    _para(doc, head, size=16, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, space_after=14)
    _label_table(doc, [("기안자", "기안자"), ("검토자", "검토자"), ("결재권자", "전결권자"), ("결재선", "결재선"),
                       ("협조자", "협조자"),
                       ("시행", "시행번호"), ("시행일", "작성일"), ("접수", "접수"),
                       ("주소", "주소"), ("전화·전송", "전화"), ("전자우편", "전자우편"), ("공개 구분", "공개 구분")])
    path = out_dir / "draft_document.docx"
    doc.save(path)
    return path.name


def generate(org_id: str, only_missing: bool = True) -> list[str]:
    """기관 결재선·용어로 기본 서식을 만들어 서식 보관함에 연결합니다.
    only_missing=True면 이미 올려 둔 서식은 건드리지 않고 빈 칸만 채웁니다."""
    profile = load_profile(org_id)
    org_name = (profile.get("org") or {}).get("name") or org_id
    example = bool((profile.get("org") or {}).get("example"))
    line = (profile.get("approval") or {}).get("line") or ["담당", "팀장"]
    head = _head(org_id, org_name, line)
    have = {f["id"] for f in list_org_forms(org_id) if f["exists"]} if only_missing else set()
    out_dir = org_dir(org_id) / "forms"
    out_dir.mkdir(parents=True, exist_ok=True)
    made = []
    if "draft_document" not in have:
        make_draft_document(org_id, org_name, out_dir, head, example)
        made.append("draft_document")
    for form_id, spec in FORMS.items():
        if form_id in have:
            continue
        doc = _new_doc()

        _para(doc, org_name, size=10, color="666666", align=WD_ALIGN_PARAGRAPH.LEFT, space_after=2)
        _para(doc, _title(spec, org_id, profile), size=20, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, space_after=2)
        _para(doc, _note(example, spec["basis"]), size=8, color="999999",
              align=WD_ALIGN_PARAGRAPH.CENTER, space_after=10)

        # 결재란: 기관 결재선 그대로
        sign = doc.add_table(rows=2, cols=len(line) + 1)
        sign.style = "Table Grid"
        sign.alignment = WD_TABLE_ALIGNMENT.RIGHT
        cells = sign.rows[0].cells
        cells[0].text = "결재"
        cells[0].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
        _shade(cells[0], "F3F4F1")
        for i, role in enumerate(line, start=1):
            cells[i].text = role
            cells[i].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
            _shade(cells[i], "F3F4F1")
        sign.rows[1].height = Cm(1.4)
        for c in sign.columns:
            for cell in c.cells:
                cell.width = Cm(2.0)
        _para(doc, "", space_after=6)

        _label_table(doc, spec["rows"])  # 왼쪽 항목 / 오른쪽 {{값}}

        _para(doc, "", space_after=10)
        _para(doc, spec["closing"], align=WD_ALIGN_PARAGRAPH.CENTER, space_after=14)
        _para(doc, "{{작성일}}", align=WD_ALIGN_PARAGRAPH.CENTER, space_after=10)
        _para(doc, "작성자:                         (서명)", align=WD_ALIGN_PARAGRAPH.RIGHT, space_after=18)
        _para(doc, f"{head} 귀하", size=12, bold=True, align=WD_ALIGN_PARAGRAPH.LEFT)
        doc.save(out_dir / f"{form_id}.docx")
        made.append(form_id)

    if made:
        profile = load_profile(org_id)
        forms = profile.setdefault("forms", {})
        for form_id in made:
            forms[form_id] = f"forms/{form_id}.docx"
        save_profile(org_id, profile)
    return made
