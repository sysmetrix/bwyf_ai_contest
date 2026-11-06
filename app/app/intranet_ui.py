"""인트라넷 화면에 넣어 줄 자료 — 규정·서식 읽기와 공문서 화면 만들기.

연동약속 v0.2에 따라 인트라넷은 따로 서버를 두지 않고 서무비서가
`/intranet/` 으로 함께 내줍니다. 결재 문서도 서무비서의 가상 결재함
한 곳에만 둡니다. 이 파일은 그 화면에 넣어 줄 자료를 만듭니다.

규정·서식은 레포 루트의 `data/`(지은)를 그대로 읽습니다.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

from . import approval, store

def _find(*names: str) -> Path:
    """레포에서 돌 때와 설치판에서 돌 때 둘 다 찾습니다.

    레포에서는 app/ 바깥에 data/ 와 intranet/ 이 있고, 윈도우 설치판에서는
    app 폴더 안 bundled/ 에 같은 것이 들어갑니다.
    """
    for base in (store.ROOT.parent, store.ROOT / "bundled"):
        p = base.joinpath(*names)
        if p.exists():
            return p
    return store.ROOT.parent.joinpath(*names)


DATA = _find("data")
INDEX = _find("intranet", "index.html")

ORG = {"id": "bwyf", "name": "재단법인 부천여성청소년재단", "short": "재단"}

# 기관설정서의 직급·직위 체계를 따른 가상 구성원입니다. 실명은 쓰지 않습니다.
MEMBERS = [
    {"id": "u-choi", "name": "최센터장", "dept": "청소년센터", "rank": 1,
     "title": "센터장", "grade": "전문계약직 1급"},
    {"id": "u-lee", "name": "이팀장", "dept": "총무팀", "rank": 2,
     "title": "부장(팀장)", "grade": "일반직(가) 2급"},
    {"id": "u-park", "name": "박차장", "dept": "총무팀", "rank": 3,
     "title": "차장", "grade": "일반직(가) 3급"},
    {"id": "u-kim", "name": "김서무", "dept": "총무팀", "rank": 5,
     "title": "직원", "grade": "일반직(가) 5급"},
    {"id": "u-ceo", "name": "대표이사", "dept": "경영진", "rank": 0,
     "title": "대표이사", "grade": "임원"},
]


def _ui_user(m: dict) -> dict:
    """화면이 쓰는 모양. 결재라인 지정은 '직급'을 글자로 치므로 rank 에 직위를 넣습니다."""
    return {**m, "username": m.get("login") or m["id"],
            "rank": m.get("title") or str(m.get("rank", "")),
            "rank_no": m.get("rank"), "department": m.get("dept")}


def _frontmatter(text: str) -> tuple[dict, str]:
    """맨 위 --- 사이의 YAML 메타데이터를 꺼냅니다. 간단한 형태만 다룹니다."""
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end < 0:
        return {}, text
    head, body = text[3:end], text[end + 4:]
    meta: dict[str, Any] = {}
    for line in head.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        k, v = line.split(":", 1)
        v = v.strip()
        if v.startswith("[") and v.endswith("]"):
            meta[k.strip()] = [x.strip() for x in v[1:-1].split(",") if x.strip()]
        else:
            meta[k.strip()] = v
    return meta, body.lstrip("\n")


def _layer_of(rel: Path) -> str:
    p = str(rel)
    if p.startswith("1_공통"):
        return "공통"
    if "4_서식" in p:
        return "서식"
    if "3_매뉴얼" in p:
        return "매뉴얼"
    if "2_세칙지침" in p:
        return "세칙지침"
    if "1_규정" in p:
        return "규정"
    return "기준"


def _category(meta: dict, layer: str) -> str:
    """서비 쪽 분류와 맞추기 위한 거친 분류입니다."""
    tasks = meta.get("관련업무") or []
    joined = " ".join(tasks) if isinstance(tasks, list) else str(tasks)
    table = [("출장", "travel"), ("여비", "travel"), ("복무", "hr"), ("휴가", "hr"),
             ("구매", "procurement"), ("지출", "finance"), ("회계", "finance"),
             ("물품", "procurement"), ("행사", "event"), ("강의", "lecture"),
             ("기안", "general"), ("결재", "general")]
    for word, cat in table:
        if word in joined:
            return cat
    return "general"


def _load_documents() -> tuple[list[dict], list[dict]]:
    """규정류와 서식을 나눠 읽습니다. (규정, 서식)"""
    if not DATA.exists():
        return [], []
    regs: list[dict] = []
    forms: list[dict] = []
    seen: set[str] = set()

    for path in sorted(DATA.rglob("*.md")):
        rel = path.relative_to(DATA)
        if rel.name == "README.md":
            continue
        text = path.read_text(encoding="utf-8")
        meta, body = _frontmatter(text)
        layer = _layer_of(rel)
        is_form = layer == "서식"

        code = str(meta.get("서식코드") or meta.get("문서코드") or path.stem)
        code = re.sub(r"[^0-9A-Za-z가-힣._-]", "_", code) or path.stem
        base, n = code, 2
        while code in seen:
            code, n = f"{base}-{n}", n + 1
        seen.add(code)

        title = str(meta.get("서식명") or meta.get("문서명") or path.stem)
        item = {
            "id": code,
            "title": title,
            "category": _category(meta, layer),
            "org_id": ORG["id"],
            "updated_at": str(meta.get("기준일") or meta.get("개정") or meta.get("제정") or ""),
            "version": "1.0",
            "layer": layer,
            "metadata": {k: v for k, v in meta.items() if k != "비고"},
            "_path": str(path),
            "_name": path.name,
            "_body": body,
        }
        (forms if is_form else regs).append(item)
    return regs, forms


REGULATIONS, FORMS = _load_documents()
BY_ID = {f"reg:{d['id']}": d for d in REGULATIONS} | {f"form:{d['id']}": d for d in FORMS}


# ---------- 서버가 쌓는 자료(기안·첨부) ----------

# 결재 문서는 서무비서의 가상 결재함 한 곳에만 둡니다(약속 v0.2).
# 이 파일은 그것을 화면 모양으로 바꿔 주기만 합니다.

def _summary(doc: dict, limit: int = 700) -> str:
    lines = [ln for ln in doc["_body"].splitlines() if ln.strip()]
    text = "\n".join(lines[:14])
    if len(text) > limit:
        text = text[:limit].rstrip() + " …"
    meta = doc.get("metadata") or {}
    head = []
    for k in ("종류", "층", "제정", "개정", "기준일", "근거", "작성시점", "관련업무"):
        if meta.get(k):
            v = meta[k]
            head.append(f"{k}: {', '.join(v) if isinstance(v, list) else v}")
    tail = "\n\n전문은 아래 첨부를 내려받아 보세요."
    return ("　|　".join(head) + "\n\n" if head else "") + text + tail


def _library_rows() -> list[dict]:
    """규정·서식을 게시판 자료실에 올려 둡니다."""
    today = f"{date.today():%Y-%m-%d}"
    rows = []
    for kind, items in (("규정", REGULATIONS), ("서식", FORMS)):
        for d in items:
            fid = f"{'reg' if kind == '규정' else 'form'}:{d['id']}"
            rows.append({
                "id": f"lib-{fid}",
                "type": "게시판",
                "folder": "자료실",
                "kind": "생산문서",
                "title": f"[{kind}] {d['id']} {d['title']}",
                "body": _summary(d),
                "status": "공개",
                "date": d["updated_at"][:10] or today,
                "details": {"attachments": [{"id": fid, "name": d["_name"]}],
                            "documentType": "자료실"},
            })
    return rows


def _folder_of(state: str) -> tuple[str, str]:
    """가상 결재함의 상태를 화면의 함·상태 글자로 옮깁니다."""
    return {
        "draft": ("임시보관문서", "임시저장"),
        "submitted": ("상신문서", "결재중"),
        "in_progress": ("결재대기문서", "결재중"),
        "approved": ("결재완료문서", "결재완료"),
        "rejected": ("반려/회수문서", "반려"),
    }.get(state or "draft", ("임시보관문서", "임시저장"))


def _line_labels(doc: dict) -> list[str]:
    out = []
    for a in doc.get("approval_line") or []:
        if isinstance(a, dict):
            out.append(str(a.get("label") or a.get("user_id") or ""))
        else:
            out.append(str(a))
    return [x for x in out if x]


def _approval_rows() -> list[dict]:
    rows = []
    for doc in approval.mock_documents(limit=200):
        folder, status = _folder_of(doc.get("state"))
        line = _line_labels(doc)
        rows.append({
            "id": doc["doc_no"],
            "type": "전자결재",
            "kind": "생산문서",
            "template": doc.get("form_title") or doc.get("task") or "일반기안문",
            "folder": folder,
            "title": doc.get("title") or "제목 없음",
            "body": doc.get("contents") or "",
            "party": ", ".join(line),
            "status": status,
            "date": (doc.get("created") or "")[:10],
            "details": {
                "documentType": "내부결재",
                "sender": doc.get("drafter_name") or doc.get("drafter") or "서무비서",
                "attachments": _attachment_items(doc),
                "approvalLine": doc.get("approval_line") or [],
                "sheetHTML": _sheet_html(doc, BY_ID.get(f"form:{doc.get('form_code')}")),
                "sheetFields": doc.get("fields") or {},
                "출처": "서무비서가 올림",
            },
        })
    rows.sort(key=lambda r: r["id"], reverse=True)
    return rows


def _attachment_items(doc: dict) -> list[dict]:
    """붙임은 결재 패키지 폴더 안에 있습니다. 화면이 내려받을 id 를 붙여 줍니다."""
    out = []
    pkg = doc.get("package_id")
    org = doc.get("org_id") or ""
    for a in doc.get("attachments") or []:
        name = a if isinstance(a, str) else str(a.get("name") or "")
        if not name:
            continue
        out.append({"id": f"att:{org}:{pkg}:{name}", "name": name})
    return out


def attachment_path(file_id: str) -> Path | None:
    """att:<기관>:<패키지>:<파일명> 을 실제 경로로 바꿉니다. 폴더 밖은 막습니다."""
    try:
        _, org, pkg, name = file_id.split(":", 3)
    except ValueError:
        return None
    base = (store.org_dir(org) / "packages" / pkg).resolve()
    for cand in (base / "붙임" / Path(name).name, base / Path(name).name):
        c = cand.resolve()
        if c.is_file() and str(c).startswith(str(base)):
            return c
    return None


def _bootstrap_state() -> dict:
    today = f"{date.today():%Y-%m-%d}"
    seeded = [
        {"id": "seed-0", "type": "알림", "folder": "알림", "title": "규정·서식이 자료실에 올라왔습니다",
         "body": f"규정류 {len(REGULATIONS)}건, 서식 {len(FORMS)}건", "status": "새글", "date": today},
        {"id": "seed-1", "type": "게시판", "folder": "공지사항", "title": "서무비서 연동 시연 안내",
         "body": "서무비서가 자료실의 규정·서식을 읽고 기안을 전자결재함에 올립니다.",
         "status": "공지", "date": today},
    ]
    return {
        "rows": _approval_rows() + _library_rows() + seeded,
        "recent": ["출장신청서", "여비", "지출결의서"],
        "time": {},
        "modulesSeeded": True,
    }


# ---------- 공문서 화면(한글 문서처럼 보이는 결재 화면) ----------
# 인트라넷 화면은 details.sheetHTML 이 있으면 그걸 공문서 모양으로 그려 줍니다.
# 서식(F01~F23)의 항목을 읽어 표로 만들고, 서무비서가 보낸 값으로 채웁니다.
# 화면 쪽 정화기가 class/colspan/rowspan 외의 속성과 input 을 지우므로 글자만 씁니다.

_SKIP_HEADS = {"결재", "기안자", "검토자", "결재권자", "전결일자", "담당", "팀장", "실장"}


def _md_tables(body: str) -> list[list[list[str]]]:
    """마크다운 표를 행·칸 목록으로 뽑습니다."""
    tables, cur = [], []
    for line in body.splitlines():
        t = line.strip()
        if t.startswith("|") and t.endswith("|"):
            cells = [c.strip() for c in t.strip("|").split("|")]
            if all(set(c) <= set("-: ") for c in cells):   # |---|---| 구분줄
                continue
            cur.append(cells)
        elif cur:
            tables.append(cur); cur = []
    if cur:
        tables.append(cur)
    return tables


def _form_fields(form: dict | None) -> list[str]:
    """서식에서 채워야 할 항목 이름을 뽑습니다.

    두 가지 모양을 다룹니다.
      세로형: | 항목 | 내용 | 작성 안내 |  → 각 행의 첫 칸이 항목
      가로형: | 대상자 | 유형 | 시작일 | …  → 머리글 칸이 항목
    """
    if not form:
        return []
    names: list[str] = []
    for tb in _md_tables(form["_body"]):
        if not tb:
            continue
        head = tb[0]
        if head and head[0] in ("항목", "구분"):
            for row in tb[1:]:
                if row and row[0] and row[0] not in _SKIP_HEADS:
                    names.append(row[0])
        elif len(head) >= 2 and not any(h in _SKIP_HEADS for h in head[:2]):
            names.extend(h for h in head if h and h not in _SKIP_HEADS)
    out, seen = [], set()
    for n in names:
        key = re.sub(r"\s+", "", n)
        if key and key not in seen:
            seen.add(key); out.append(n)
    return out[:16]


def _skeleton(form: dict | None) -> str | None:
    """서식 안에 기안문 본문 틀(```코드블록```)이 있으면 그것을 씁니다."""
    if not form:
        return None
    m = re.search(r"```\n(.*?)```", form["_body"], re.S)
    return m.group(1).rstrip() if m else None


def _match_value(field: str, fields: dict) -> str:
    """서식 항목 이름에 맞는 값을 찾아 줍니다. 없으면 빈칸으로 둡니다."""
    key = re.sub(r"[\s()（）/·]", "", field)
    table = [
        (("일시", "기간", "시작일", "출장일"), ("시작일",)),
        (("종료일", "복귀"), ("종료일",)),
        (("장소", "목적지", "출장지", "방문"), ("장소",)),
        (("품명", "품목", "물품"), ("품목",)),
        (("금액", "예산", "소요", "단가"), ("금액",)),
        (("일수", "신청일수"), ("일수",)),
        (("목적", "사유", "내용", "건명"), ("업무",)),
        (("직무대행", "동행", "협조"), ()),          # 사람이 직접 적을 칸
        (("대상자", "신청인", "기안자", "작성자", "보고자"), ("기안자",)),
        (("직위", "직급"), ("직위",)),
        (("부서", "소속부서"), ("부서",)),
        (("기관명", "소속", "부서명"), ("기관명",)),
        (("기한", "제출"), ("기한",)),
    ]
    for words, keys in table:
        if not any(w in key for w in words):
            continue
        # 한 항목은 한 규칙만 씁니다. 값이 없으면 빈칸으로 두고 다음 규칙으로
        # 넘어가지 않습니다(넘어가면 엉뚱한 값이 들어갑니다).
        for k in keys:
            v = fields.get(k)
            if v is None:
                continue
            if k == "금액":
                try:
                    return f"{int(v):,}원"
                except (TypeError, ValueError):
                    return str(v)
            if k == "시작일" and fields.get("종료일"):
                return f"{v} ~ {fields['종료일']}"
            return str(v)
        return ""
    return ""


def _esc(v) -> str:
    return (str(v if v is not None else "")
            .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _sheet_html(doc: dict, form: dict | None) -> str:
    """전자결재함에서 한글 공문서처럼 보이는 화면을 만듭니다."""
    f = doc.get("fields") or {}
    line = f.get("결재선") or _line_labels(doc)
    org = f.get("기관명") or ORG["name"]

    sign = ("<table class=\"sheet-signbox\"><tbody><tr>"
            + "".join(f"<th>{_esc(r)}</th>" for r in (list(line)[:4] or ["기안", "검토", "결재"]))
            + "</tr><tr>" + "<td></td>" * len(list(line)[:4] or [1, 2, 3])
            + "</tr></tbody></table>")

    rows = []
    for name in _form_fields(form):
        rows.append(f"<tr><th>{_esc(name)}</th><td>{_esc(_match_value(name, f))}</td></tr>")
    table = ("<table><tbody>" + "".join(rows) + "</tbody></table>") if rows else ""

    skel = _skeleton(form)
    body_src = skel if (skel and not rows) else (doc.get("contents") or "")
    body = "".join(f"<p>{_esc(ln) or '&#160;'}</p>" for ln in str(body_src).splitlines())

    attach = ""
    names = [a["name"] for a in _attachment_items(doc)]
    if names:
        attach = ("<p>붙　임　" + ",　".join(f"{_esc(n)} 1부." for n in names) + "　끝.</p>")

    basis = f.get("근거조문") or []
    basis_html = ("<p class=\"sheet-basis\">근거　" + " / ".join(_esc(b) for b in basis) + "</p>") if basis else ""

    form_name = f"（{form['id']} {form['title']}）" if form else ""

    return (
        "<section class=\"official-sheet\">"
        + sign
        + "<p class=\"sheet-motto\">모두가 성장하는 지역 파트너</p>"
        + f"<h2>{_esc(org)}</h2>"
        + "<p>수신자　내부결재</p><p>（경유）</p>"
        + f"<p>제　목　<strong>{_esc(doc.get('title'))}</strong>　<span>{_esc(form_name)}</span></p>"
        + "<hr>"
        + f"<div>{table}{body}{attach}{basis_html}</div>"
        + "<div class=\"official-footer\">"
        + f"<p>협조자　{_esc('、'.join(str(x) for x in list(line)[1:]))}</p>"
        + f"<p>시행　{_esc(doc.get('doc_no'))} （{_esc(doc.get('date'))}）　접수　</p>"
        + "</div>"
        + f"<p class=\"sheet-issuer\">{_esc(org)}</p>"
        + "</section>"
    )


def bootstrap_state() -> dict:
    return _bootstrap_state()


def page_html(user: dict | None = None) -> str:
    """인트라넷 화면. 서무비서가 /intranet/ 으로 함께 내줍니다."""
    if not INDEX.exists():
        raise FileNotFoundError("intranet/index.html 이 없습니다")
    html = INDEX.read_text(encoding="utf-8")
    me = user or MEMBERS[-2]            # 기본은 담당자(김서무)
    boot = ("<script>window.__serverBootstrap="
            + json.dumps({"state": _bootstrap_state(),
                          "user": _ui_user(me),
                          "users": [_ui_user(m) for m in MEMBERS]},
                         ensure_ascii=False)
            + ";</script>")
    # ?doc=문서번호 로 들어오면 그 문서를 바로 펼칩니다.
    # 준호의 index.html 은 손대지 않고, 뒤에 작은 스크립트만 덧붙입니다.
    jump = """<script>
(function(){
  var m = new URLSearchParams(location.search).get('doc');
  if (!m) return;
  var tries = 0;
  var timer = setInterval(function(){
    if (++tries > 40) { clearInterval(timer); return; }
    var go = document.querySelector('[data-page="전자결재"]');
    if (go && !document.querySelector('[data-item]')) { go.click(); return; }
    var row = document.querySelector('[data-item="' + CSS.escape(m) + '"]');
    if (row) { clearInterval(timer); row.click(); return; }
    var folders = ['임시보관문서','상신문서','결재대기문서','결재완료문서'];
    var f = folders[tries % folders.length];
    var btn = document.querySelector('[data-folder="' + f + '"]');
    if (btn) btn.click();
  }, 250);
})();
</script>"""
    html = html.replace("<head>", "<head>" + boot, 1) if "<head>" in html else boot + html
    return html.replace("</body>", jump + "</body>", 1) if "</body>" in html else html + jump


def members() -> list[dict]:
    return [_ui_user(m) for m in MEMBERS]


def member(user_id: str) -> dict | None:
    for m in MEMBERS:
        if m["id"] == user_id:
            return m
    return None
