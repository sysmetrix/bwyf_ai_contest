"""가상 인트라넷 서버 — 경연 시연용.

하는 일 세 가지입니다.

  1. 지은이 정리한 data/ 의 규정·서식을 인트라넷 자료실에 올려 둡니다.
  2. 서무비서(app/)가 그 규정·서식을 읽어 갈 수 있게 연동 API를 엽니다.
  3. 서무비서가 만든 기안을 받아 전자결재함에 넣습니다.

화면은 준호가 만든 index.html 을 그대로 씁니다. 그 화면은 서버가 있으면
window.__serverBootstrap 의 상태를 쓰도록 이미 만들어져 있어서, 서버가
상태를 넣어 주면 브라우저 저장소 대신 이 서버의 자료를 보여 줍니다.

실행:  python server.py        (기본 8100번)
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import (HTMLResponse, JSONResponse, RedirectResponse,
                               Response)

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
DATA = REPO / "data"
INDEX = HERE / "index.html"
STORE = HERE / "운영자료"          # 서버가 쌓는 것(기안·첨부). data/ 는 읽기만 합니다.
PORT = 8100

ORG = {"id": "bwyf", "name": "재단법인 부천여성청소년재단", "short": "재단"}


# ---------- 지은의 data/ 읽기 ----------

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

def _state_path() -> Path:
    return STORE / "state.json"


def _load_state() -> dict:
    try:
        return json.loads(_state_path().read_text(encoding="utf-8"))
    except Exception:
        return {"documents": {}, "files": {}, "seq": 0}


def _save_state(s: dict) -> None:
    STORE.mkdir(parents=True, exist_ok=True)
    _state_path().write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")


SERVER = _load_state()


def _next_doc_no() -> str:
    SERVER["seq"] = int(SERVER.get("seq", 0)) + 1
    return f"BWYF-{date.today():%Y%m%d}-{SERVER['seq']:04d}"


# ---------- 화면에 넣어 줄 상태 ----------

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


def _approval_rows() -> list[dict]:
    rows = []
    for doc in SERVER.get("documents", {}).values():
        rows.append({
            "id": doc["doc_no"],
            "type": "전자결재",
            "kind": "생산문서",
            "template": doc.get("template") or "일반기안문",
            "folder": doc["folder"],
            "title": doc["title"],
            "body": doc["body"],
            "party": doc.get("party", ""),
            "status": doc["status"],
            "date": doc["date"],
            "details": {
                "documentType": "내부결재",
                "sender": doc.get("sender") or "서무비서",
                "attachments": doc.get("attachments") or [],
                "approvalLine": doc.get("approvers") or [],
                "sheetHTML": doc.get("sheet_html") or "",
                "sheetFields": doc.get("fields") or {},
                "출처": "서무비서가 올림",
            },
        })
    rows.sort(key=lambda r: r["id"], reverse=True)
    return rows


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
    line = f.get("결재선") or doc.get("approvers") or []
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
    body_src = skel if (skel and not rows) else doc.get("body", "")
    body = "".join(f"<p>{_esc(ln) or '&#160;'}</p>" for ln in str(body_src).splitlines())

    attach = ""
    names = [a.get("name") for a in (doc.get("attachments") or []) if a.get("name")]
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


# ---------- 앱 ----------

app = FastAPI(title="가상 인트라넷", docs_url="/api/docs")


# ---------- 로그인 ----------
# 실제 그룹웨어처럼 아이디·비밀번호로 들어가게 합니다. API 키가 없는 기관에서는
# 서무비서가 사람과 똑같이 로그인해서 읽고 쓰기 때문에, 그 길을 시연하려면
# 로그인 화면이 있어야 합니다. 시연용 비밀번호는 아래 DEMO_PW 하나뿐입니다.
DEMO_PW = "demo1234"
SESSIONS: dict[str, str] = {}          # 세션값 → 사용자 id


def _member(user_id: str) -> dict | None:
    for m in MEMBERS:
        if m["id"] == user_id or m.get("login") == user_id:
            return m
    return None


def _current_user(request: Request) -> dict | None:
    sid = request.cookies.get("intranet_session")
    if not sid:
        return None
    return _member(SESSIONS.get(sid, ""))


def _ui_user(m: dict) -> dict:
    """화면이 쓰는 모양으로 바꿉니다.

    화면의 결재라인 지정은 사람이 '직급'을 글자로 칩니다(예: 센터장). 그래서
    rank 자리에는 직위 글자를 넣고, 숫자 직급은 rank_no 로 따로 둡니다.
    숫자 직급은 서무비서가 전결표와 맞출 때 쓰는 값이라 API 쪽은 그대로입니다.
    """
    return {**m, "username": m.get("login") or m["id"],
            "rank": m.get("title") or str(m.get("rank", "")),
            "rank_no": m.get("rank"), "department": m.get("dept")}


LOGIN_HTML = """<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>인트라넷 로그인</title>
<style>
 *{box-sizing:border-box} body{margin:0;font-family:"Malgun Gothic","Apple SD Gothic Neo",sans-serif;
  background:#eef2f7;display:grid;place-items:center;min-height:100vh;color:#24323f}
 .box{width:min(380px,92vw);background:#fff;padding:34px 30px;border-radius:10px;
  box-shadow:0 6px 22px #0d2b4a1a}
 h1{margin:0 0 4px;font-size:21px;letter-spacing:-.3px}
 p.sub{margin:0 0 22px;font-size:13px;color:#6b7b8c}
 label{display:block;font-size:13px;margin:12px 0 5px;color:#44586b}
 input{width:100%;padding:11px 12px;border:1px solid #ccd6e0;border-radius:6px;font-size:14px}
 input:focus{outline:2px solid #1687d3;border-color:transparent}
 button{width:100%;margin-top:20px;padding:12px;border:0;border-radius:6px;background:#1667b5;
  color:#fff;font-size:15px;cursor:pointer}
 button:hover{background:#12589c}
 .err{margin-top:14px;padding:9px 11px;background:#fdeaea;color:#a32626;border-radius:6px;font-size:13px}
 .hint{margin-top:20px;padding:11px;background:#f4f7fa;border-radius:6px;font-size:12px;color:#5d6e7e;line-height:1.6}
 .hint b{color:#24323f}
</style></head><body>
<form class="box" method="post" action="/login">
 <h1>인트라넷</h1>
 <p class="sub">재단법인 부천여성청소년재단 (시연용 가상 시스템)</p>
 <label for="uid">아이디</label>
 <input id="uid" name="user_id" autocomplete="username" autofocus required>
 <label for="pw">비밀번호</label>
 <input id="pw" name="password" type="password" autocomplete="current-password" required>
 <button type="submit">로그인</button>
 __ERROR__
 <div class="hint">시연용 계정입니다. 아이디 <b>u-kim</b>(직원) · <b>u-choi</b>(센터장) ·
  <b>u-lee</b>(팀장), 비밀번호는 모두 <b>demo1234</b> 입니다.</div>
</form></body></html>"""


@app.get("/login", response_class=HTMLResponse)
def login_page(error: str = "") -> HTMLResponse:
    html = LOGIN_HTML.replace("__ERROR__",
                              f'<div class="err">{_esc(error)}</div>' if error else "")
    return HTMLResponse(html)


@app.post("/login")
async def login(request: Request):
    form = await request.form()
    uid = str(form.get("user_id") or "").strip()
    pw = str(form.get("password") or "")
    member = _member(uid)
    if not member or pw != DEMO_PW:
        return RedirectResponse("/login?error=아이디 또는 비밀번호가 맞지 않습니다",
                                status_code=303)
    sid = uuid.uuid4().hex
    SESSIONS[sid] = member["id"]
    resp = RedirectResponse("/", status_code=303)
    resp.set_cookie("intranet_session", sid, httponly=True, samesite="lax")
    return resp


@app.get("/logout")
def logout(request: Request):
    sid = request.cookies.get("intranet_session")
    SESSIONS.pop(sid or "", None)
    resp = RedirectResponse("/login", status_code=303)
    resp.delete_cookie("intranet_session")
    return resp


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    me = _current_user(request)
    if not me:
        return RedirectResponse("/login", status_code=303)
    if not INDEX.exists():
        raise HTTPException(404, "index.html 이 없습니다")
    html = INDEX.read_text(encoding="utf-8")
    boot = ("<script>window.__serverBootstrap="
            + json.dumps({"state": _bootstrap_state(),
                          # 화면이 기대하는 모양: user.username(메일 계정), user.name,
                          # 그리고 결재라인 지정에 쓰는 users 목록.
                          "user": _ui_user(me),
                          "users": [_ui_user(m) for m in MEMBERS]},
                         ensure_ascii=False)
            + ";</script>")
    # 화면 스크립트가 돌기 전에 상태를 넣어야 합니다.
    if "<head>" in html:
        html = html.replace("<head>", "<head>" + boot, 1)
    else:
        html = boot + html
    return HTMLResponse(html)


@app.get("/api/state")
def api_state() -> dict:
    return {"ok": True, "state": _bootstrap_state()}


# --- 규정·서식 ---

def _public(d: dict) -> dict:
    return {k: v for k, v in d.items() if not k.startswith("_")}


@app.get("/api/v1/regulations")
def list_regulations(org_id: str | None = None, category: str = "all") -> dict:
    items = [d for d in REGULATIONS
             if (org_id in (None, "", d["org_id"]))
             and (category in ("all", "", d["category"]))]
    return {"ok": True, "data": [_public(d) for d in items], "count": len(items)}


@app.get("/api/v1/templates/forms")
def list_forms(org_id: str | None = None, category: str = "all") -> dict:
    items = [d for d in FORMS
             if (org_id in (None, "", d["org_id"]))
             and (category in ("all", "", d["category"]))]
    return {"ok": True, "data": [_public(d) for d in items], "count": len(items)}


def _disposition(name: str) -> str:
    """한글 파일명은 퍼센트 인코딩해야 HTTP 헤더에 넣을 수 있습니다."""
    return f"attachment; filename*=UTF-8''{quote(name)}"


def _file_response(doc: dict) -> Response:
    body = Path(doc["_path"]).read_bytes()
    return Response(body, media_type="text/markdown; charset=utf-8",
                    headers={"Content-Disposition": _disposition(doc["_name"])})


@app.get("/api/v1/regulations/{doc_id}/file")
def regulation_file(doc_id: str) -> Response:
    doc = BY_ID.get(f"reg:{doc_id}")
    if not doc:
        raise HTTPException(404, "그 규정을 찾지 못했습니다")
    return _file_response(doc)


@app.get("/api/v1/templates/{doc_id}/file")
def form_file(doc_id: str) -> Response:
    doc = BY_ID.get(f"form:{doc_id}") or BY_ID.get(f"reg:{doc_id}")
    if not doc:
        raise HTTPException(404, "그 서식을 찾지 못했습니다")
    return _file_response(doc)


# --- 기안 ---

def _store_file(name: str, data: bytes) -> dict:
    fid = "att:" + uuid.uuid4().hex[:12]
    folder = STORE / "첨부"
    folder.mkdir(parents=True, exist_ok=True)
    safe = Path(name or "첨부").name
    (folder / f"{fid.split(':')[1]}_{safe}").write_bytes(data)
    SERVER.setdefault("files", {})[fid] = {"name": safe, "bytes": len(data),
                                           "file": f"{fid.split(':')[1]}_{safe}"}
    return {"id": fid, "name": safe}


def _create_doc(payload: dict, attachments: list[dict]) -> dict:
    submitted = str(payload.get("state") or "draft") == "submitted"
    doc_no = _next_doc_no()
    doc = {
        "doc_no": doc_no,
        "title": str(payload.get("title") or "제목 없음"),
        "body": str(payload.get("content") or ""),
        "category": str(payload.get("category") or ""),
        "template": str(payload.get("category") or "") or "일반기안문",
        "org_id": str(payload.get("org_id") or ORG["id"]),
        "approvers": payload.get("approvers") or [],
        "fields": payload.get("fields") or {},
        "party": ", ".join(str(a) for a in (payload.get("approvers") or [])),
        "sender": "서무비서",
        "attachments": attachments,
        "date": f"{date.today():%Y-%m-%d}",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        # 서비는 임시저장까지만 합니다. 상신은 사람이 누릅니다.
        "folder": "상신문서" if submitted else "임시보관문서",
        "status": "결재중" if submitted else "임시저장",
        "history": [{"at": datetime.now().isoformat(timespec="seconds"),
                     "note": "서무비서가 올림(임시저장)" if not submitted else "상신"}],
    }
    form = BY_ID.get(f"form:{doc['category']}")
    doc["form_id"] = form["id"] if form else None
    doc["form_title"] = form["title"] if form else None
    doc["template"] = form["title"] if form else (doc.get("template") or "일반기안문")
    doc["sheet_html"] = _sheet_html(doc, form)

    SERVER.setdefault("documents", {})[doc_no] = doc
    _save_state(SERVER)
    return doc


@app.post("/api/v1/documents/draft")
async def create_draft(request: Request) -> JSONResponse:
    ctype = request.headers.get("content-type", "")
    attachments: list[dict] = []

    if ctype.startswith("multipart/form-data"):
        form = await request.form()
        raw = form.get("metadata")
        payload: dict = {}
        if raw is not None:
            text = raw if isinstance(raw, str) else (await raw.read()).decode("utf-8")
            try:
                payload = json.loads(text)
            except Exception:
                # 파이썬 dict 를 그대로 문자열로 보낸 경우까지 받아 줍니다.
                import ast
                try:
                    payload = ast.literal_eval(text)
                except Exception:
                    payload = {}
        for key, value in form.multi_items():
            if key == "metadata" or not hasattr(value, "read"):
                continue
            attachments.append(_store_file(
                getattr(value, "filename", None) or key, await value.read()))
    else:
        try:
            payload = await request.json()
        except Exception:
            payload = {}

    if not payload.get("title"):
        raise HTTPException(400, "기안 제목이 없습니다")

    doc = _create_doc(payload, attachments)
    return JSONResponse({"ok": True, "data": {
        "doc_no": doc["doc_no"], "state": "submitted" if doc["status"] == "결재중" else "draft",
        "url": f"/?doc={doc['doc_no']}", "created_at": doc["created_at"],
        "folder": doc["folder"], "attachments": doc["attachments"]}})


@app.post("/api/v1/documents/{doc_no}/submit")
def submit_draft(doc_no: str) -> dict:
    doc = SERVER.get("documents", {}).get(doc_no)
    if not doc:
        raise HTTPException(404, "그 기안을 찾지 못했습니다")
    doc["folder"], doc["status"] = "상신문서", "결재중"
    doc.setdefault("history", []).append(
        {"at": datetime.now().isoformat(timespec="seconds"), "note": "사람이 상신"})
    _save_state(SERVER)
    return {"ok": True, "data": {"doc_no": doc_no, "state": "submitted"}}


@app.get("/api/v1/documents/{doc_no}/status")
def draft_status(doc_no: str) -> dict:
    doc = SERVER.get("documents", {}).get(doc_no)
    if not doc:
        raise HTTPException(404, "그 기안을 찾지 못했습니다")
    return {"ok": True, "data": {"doc_no": doc_no, "status": doc["status"],
                                 "folder": doc["folder"], "title": doc["title"],
                                 "history": doc.get("history") or []}}


@app.get("/api/v1/documents")
def list_documents() -> dict:
    docs = sorted(SERVER.get("documents", {}).values(),
                  key=lambda d: d["doc_no"], reverse=True)
    return {"ok": True, "data": docs, "count": len(docs)}


@app.get("/api/v1/approvals/pending")
def pending_approvals(approver: str | None = None) -> dict:
    """결재를 기다리는 문서. 결재자에게 브리핑할 거리입니다."""
    waiting = []
    for doc in SERVER.get("documents", {}).values():
        if doc.get("folder") not in ("상신문서", "결재대기문서"):
            continue
        line = [str(x) for x in (doc.get("approvers") or [])]
        if approver and approver not in line:
            continue
        f = doc.get("fields") or {}
        waiting.append({
            "doc_no": doc["doc_no"], "title": doc["title"], "date": doc["date"],
            "status": doc["status"], "folder": doc["folder"],
            "drafter": doc.get("sender"), "approvers": line,
            "form_id": doc.get("form_id"), "form_title": doc.get("form_title"),
            "task": f.get("업무"), "amount": f.get("금액"),
            "deadline": f.get("기한"), "attachments": len(doc.get("attachments") or []),
        })
    waiting.sort(key=lambda d: d["doc_no"])
    return {"ok": True, "data": waiting, "count": len(waiting)}


# --- 기관·사용자 ---

@app.get("/api/v1/orgs")
def list_orgs() -> dict:
    return {"ok": True, "data": [ORG]}


@app.get("/api/v1/orgs/{org_id}")
def org_profile(org_id: str) -> dict:
    if org_id != ORG["id"]:
        raise HTTPException(404, "그 기관을 찾지 못했습니다")
    return {"ok": True, "data": {**ORG, "regulations": len(REGULATIONS), "forms": len(FORMS)}}


# ---------- 조직도 ----------
# 기관설정서의 직급·직위 체계를 따른 가상 구성원입니다. 실명은 쓰지 않습니다.
# 서무비서는 이 목록에서 '내 직급·직위'를 읽어 역할을 스스로 판정합니다.
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


@app.get("/api/v1/orgs/{org_id}/members")
def org_members(org_id: str) -> dict:
    """조직 구성원과 직급. 서무비서가 역할을 판정하는 근거입니다."""
    if org_id != ORG["id"]:
        raise HTTPException(404, "그 기관을 찾지 못했습니다")
    return {"ok": True, "data": MEMBERS, "count": len(MEMBERS),
            "note": "기관설정서 직급 체계를 따른 가상 구성원"}


@app.get("/api/v1/users/{user_id}")
def user_profile(user_id: str) -> dict:
    for m in MEMBERS:
        if m["id"] == user_id:
            return {"ok": True, "data": m}
    raise HTTPException(404, "그 사용자를 찾지 못했습니다")


# --- 첨부 내려받기 (화면이 /api/files/{id} 를 씁니다) ---

@app.get("/api/files/{file_id:path}")
def download(file_id: str) -> Response:
    doc = BY_ID.get(file_id)
    if doc:
        return _file_response(doc)
    rec = SERVER.get("files", {}).get(file_id)
    if rec:
        p = STORE / "첨부" / rec["file"]
        if p.is_file():
            return Response(p.read_bytes(), media_type="application/octet-stream",
                            headers={"Content-Disposition": _disposition(rec["name"])})
    raise HTTPException(404, "그 파일을 찾지 못했습니다")


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "regulations": len(REGULATIONS), "forms": len(FORMS),
            "documents": len(SERVER.get("documents", {}))}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="가상 인트라넷")
    ap.add_argument("--port", type=int, default=PORT)
    ap.add_argument("--host", default="127.0.0.1",
                    help="같은 사무실 PC에서도 열어 보게 하려면 0.0.0.0")
    args = ap.parse_args()

    print(f"\n  가상 인트라넷  http://127.0.0.1:{args.port}")
    if args.host == "0.0.0.0":
        import socket
        try:
            sk = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sk.connect(("8.8.8.8", 80))
            print(f"  같은 망에서는  http://{sk.getsockname()[0]}:{args.port}")
            sk.close()
        except Exception:
            pass
        print("  ※ 같은 망의 다른 PC에서도 열립니다. 시연이 끝나면 꺼 주세요.")
    print(f"  자료실에 올려 둔 규정류 {len(REGULATIONS)}건, 서식 {len(FORMS)}건")
    print(f"  전자결재함에 들어온 기안 {len(SERVER.get('documents', {}))}건\n")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
