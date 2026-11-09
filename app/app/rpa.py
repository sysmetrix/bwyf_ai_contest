"""API 없는 그룹웨어 연결 — 사람과 똑같이 로그인해서 읽고 씁니다.

연동 API를 열어 주지 않는 기관이 많습니다. 그런 곳에서는 서무비서가 브라우저를
띄워 아이디·비밀번호로 들어간 뒤, 사람이 하는 것과 같은 순서로 화면을 눌러
규정·서식을 읽고 기안을 임시저장합니다.

**읽기와 쓰기를 다르게 다룹니다.**

  읽기(규정·서식·조직도)는 틀려도 아무것도 망가지지 않습니다. 못 읽을 뿐입니다.
  쓰기(기안)는 틀리면 엉뚱한 칸에 값이 들어갈 수 있으므로, 화면에 보이는 글자로만
  찾고(버튼 이름·칸 이름), 좌표 클릭과 해시된 클래스 이름은 쓰지 않습니다.
  그래야 그룹웨어가 새 판으로 바뀌어도 살아남습니다.

그리고 **상신은 하지 않습니다.** 임시저장까지만 하고 멈춥니다. 사람이 눈으로
확인하고 누릅니다.

비밀번호는 이 파일에 들어오지 않습니다. 운영체제의 자격 증명 저장소에서 읽어
옵니다(`credentials.py`). 윈도우에서는 자격 증명 관리자입니다.

필요한 것: `pip install playwright` 와 크롬(또는 엣지). 브라우저는 따로 내려받지
않고 PC에 깔린 것을 씁니다.
"""
from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

# 화면이 반응할 때까지 기다리는 한도(밀리초). 고정 대기 대신 조건을 기다립니다.
WAIT = 15_000
BROWSER_CHANNELS = ("chrome", "msedge")


@dataclass
class RpaResult:
    ok: bool
    error: str | None = None
    data: Any = None
    seconds: float = 0.0
    meta: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {"ok": self.ok, "error": self.error, "seconds": round(self.seconds, 2),
                **({"meta": self.meta} if self.meta else {})}


def available() -> tuple[bool, str]:
    """이 PC에서 쓸 수 있는지. 쓸 수 없으면 무엇을 해야 하는지 알려 줍니다."""
    try:
        import playwright  # noqa: F401
    except ImportError:
        return False, "playwright 가 설치되지 않았습니다 (pip install playwright)"
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        return False, f"playwright 를 불러오지 못했습니다: {exc}"
    try:
        with sync_playwright() as pw:
            for ch in BROWSER_CHANNELS:
                try:
                    b = pw.chromium.launch(channel=ch, headless=True)
                    b.close()
                    return True, ch
                except Exception:
                    continue
    except Exception as exc:
        return False, f"브라우저를 띄우지 못했습니다: {exc}"
    return False, "크롬 또는 엣지가 필요합니다. 둘 중 하나를 설치해 주세요"


@contextmanager
def session(base_url: str, user_id: str, password: str, *,
            company: str = "", org_id: str = "", headless: bool = True,
            timeout: int = WAIT) -> Iterator[Any]:
    """로그인한 페이지를 돌려줍니다. 끝나면 브라우저를 닫습니다."""
    from playwright.sync_api import sync_playwright

    base = base_url.rstrip("/")
    with sync_playwright() as pw:
        browser = None
        last = None
        for ch in BROWSER_CHANNELS:
            try:
                browser = pw.chromium.launch(channel=ch, headless=headless)
                break
            except Exception as exc:
                last = exc
        if browser is None:
            raise RuntimeError(f"크롬 또는 엣지를 띄우지 못했습니다: {last}")
        try:
            page = browser.new_page()
            page.set_default_timeout(timeout)
            _login(page, base, user_id, password, company,
                   steps=login_steps(org_id) if org_id else None)
            yield page
        finally:
            browser.close()


# 그룹웨어마다 로그인 주소가 다릅니다. 흔한 자리를 차례로 보고,
# 비밀번호 칸이 보이는 곳을 로그인 화면으로 봅니다.
LOGIN_PATHS = ("", "/login", "/Login", "/login.do", "/auth/login", "/sso/login",
               "/member/login", "/user/login", "#/login")


def _find_login_page(page, base: str) -> None:
    last = None
    for path in LOGIN_PATHS:
        url = base + path
        try:
            page.goto(url, wait_until="domcontentloaded")
            page.wait_for_timeout(400)
        except Exception as exc:
            last = exc
            continue
        # 비밀번호 칸이 있거나, 아이디 칸과 '로그인' 단추가 보이면 로그인 화면입니다.
        if page.locator("input[type='password']").count():
            return
        if _first_visible(page, [lambda: page.get_by_role("button", name="로그인")]):
            return
    if last:
        raise RuntimeError("로그인 화면을 찾지 못했습니다(주소를 확인해 주세요)")


# 로그인 칸을 알아보는 말들. 라벨·안내문구·name 속성을 두루 봅니다.
# 그룹웨어마다 쓰는 말이 달라 한 가지로 정하지 않습니다.
FIELD_WORDS = {
    "회사": ("회사코드", "회사 코드", "기관코드", "기관 코드", "업체코드", "고객코드",
             "도메인", "company", "corp", "domain", "tenant", "site"),
    "아이디": ("아이디", "사번", "사용자", "아이디를", "id", "user", "login",
               "email", "메일", "계정"),
}
# 다음 단계로 넘어가는 단추. 앞의 것부터 찾습니다.
FORWARD_WORDS = ("로그인", "다음", "확인", "계속", "접속", "들어가기",
                 "sign in", "log in", "login", "next", "continue", "submit")
MAX_LOGIN_STEPS = 5          # 화면이 몇 번 바뀌어도 따라갑니다


def choose_fields(descs: list[str], *, has_company: bool) -> dict[str, int]:
    """글자 칸 설명들을 보고 어느 칸이 무엇인지 고릅니다 (몇 번째 칸인지로 답합니다).

    브라우저 없이도 확인할 수 있게 판단만 떼어 두었습니다.
    `descs` 는 칸마다 라벨·안내문구·name 을 이어 붙인 글입니다(소문자).
    """
    low = [d.lower() for d in descs]
    out: dict[str, int] = {}
    taken: set[int] = set()

    def pick(kind: str) -> None:
        for i, d in enumerate(low):
            if i in taken:
                continue
            if any(w in d for w in FIELD_WORDS[kind]):
                out[kind] = i
                taken.add(i)
                return

    if has_company:
        pick("회사")
    pick("아이디")

    # 아마란스처럼 '회사코드' 와 '아이디' 가 나란히 있는데 라벨이 없는 화면.
    # 글자 칸이 둘이고 회사코드를 받아 두었다면, 앞이 회사코드입니다.
    if has_company and "회사" not in out and len(low) >= 2:
        first = next((i for i in range(len(low)) if i not in taken), None)
        if first is not None and out.get("아이디") != first:
            out["회사"] = first
            taken.add(first)
    if "아이디" not in out:
        nxt = next((i for i in range(len(low)) if i not in taken), None)
        if nxt is not None:
            out["아이디"] = nxt
    return out


def _describe(box) -> str:
    """칸 하나를 설명하는 글 모으기 — 라벨·안내문구·name·id·aria-label."""
    bits = []
    for attr in ("placeholder", "name", "id", "aria-label", "autocomplete", "title"):
        try:
            v = box.get_attribute(attr)
            if v:
                bits.append(v)
        except Exception:
            pass
    for how in ("xpath=ancestor::label[1]", "xpath=preceding::label[1]"):
        try:
            lab = box.locator(how).first
            if lab.count():
                bits.append((lab.inner_text() or "")[:40])
                break
        except Exception:
            pass
    return " ".join(bits)


def _text_boxes(page) -> list:
    """지금 화면에 보이는 글자 칸들 (비밀번호·숨은 칸 제외)."""
    out = []
    try:
        loc = page.locator("input:not([type='password']):not([type='hidden'])"
                           ":not([type='checkbox']):not([type='radio'])"
                           ":not([type='submit']):not([type='button'])")
        for i in range(min(loc.count(), 12)):
            b = loc.nth(i)
            try:
                if b.is_visible() and b.is_enabled():
                    out.append(b)
            except Exception:
                continue
    except Exception:
        pass
    return out


def _password_box(page):
    return _first_visible(page, [lambda: page.locator("input[type='password']")])


def _forward_button(page, *, prefer_login: bool):
    """다음 단계로 넘기는 단추. 비밀번호를 넣었으면 '로그인' 을 먼저 봅니다."""
    words = list(FORWARD_WORDS)
    if not prefer_login:
        words = [w for w in words if w not in ("로그인", "sign in", "log in", "login")] + \
                ["로그인", "sign in", "log in", "login"]
    tries = []
    for w in words:
        tries.append(lambda w=w: page.get_by_role("button", name=w))
        tries.append(lambda w=w: page.get_by_role("link", name=w))
        tries.append(lambda w=w: page.locator(f"input[type='submit'][value*='{w}' i]"))
    tries.append(lambda: page.locator("button[type='submit']"))
    return _first_visible(page, tries)


def _fill(box, value: str) -> bool:
    """비어 있을 때만 채웁니다. 단계가 바뀌며 같은 칸이 다시 나와도 덮지 않습니다."""
    try:
        if (box.input_value() or "").strip():
            return False
        box.fill(value)
        return True
    except Exception:
        return False


def _logged_in(page) -> bool:
    try:
        if page.locator("input[type='password']").count():
            return False
    except Exception:
        return False
    return _first_visible(page, [lambda: page.get_by_role("button", name="로그인")]) is None


def _login(page, base: str, user_id: str, password: str, company: str = "",
           *, steps: list[dict] | None = None) -> None:
    """로그인. 특정 사이트에 맞추지 않고, 화면에 보이는 것으로 찾습니다.

    한 화면에 다 있는 곳도 있고, 아마란스처럼 **회사코드·아이디 → 다음 →
    비밀번호** 로 화면이 나뉘는 곳도 있습니다. 그래서 한 번에 끝내려 하지 않고,
    화면이 바뀔 때마다 다시 읽어 채울 수 있는 것을 채우고 넘깁니다.
    """
    _find_login_page(page, base)

    # 전에 사람이 보여 준 순서가 있으면 그것부터. 화면이 바뀌어 안 맞으면
    # 아래 '화면 읽고 채우기' 로 되돌아갑니다.
    if steps:
        try:
            if _login_by_steps(page, steps,
                               {"회사": company, "아이디": user_id, "비밀번호": password}):
                return
        except Exception:
            pass
        _find_login_page(page, base)

    put = {"회사": not company, "아이디": False, "비밀번호": False}
    for _ in range(MAX_LOGIN_STEPS):
        boxes = _text_boxes(page)
        if boxes:
            where = choose_fields([_describe(b) for b in boxes], has_company=bool(company))
            if company and "회사" in where and _fill(boxes[where["회사"]], company):
                put["회사"] = True
            if "아이디" in where and _fill(boxes[where["아이디"]], user_id):
                put["아이디"] = True

        pw = _password_box(page)
        if pw is not None and _fill(pw, password):
            put["비밀번호"] = True

        btn = _forward_button(page, prefer_login=put["비밀번호"])
        if btn is None:
            break
        try:
            btn.click()
        except Exception:
            break
        try:
            page.wait_for_load_state("networkidle", timeout=12_000)
        except Exception:
            pass
        page.wait_for_timeout(600)

        if put["비밀번호"] and _logged_in(page):
            return

    if not put["아이디"]:
        raise RuntimeError("로그인 화면에서 아이디 칸을 찾지 못했습니다")
    if not put["비밀번호"]:
        raise RuntimeError(
            "로그인 화면에서 비밀번호 칸을 찾지 못했습니다. "
            "회사코드를 먼저 넣어야 하는 그룹웨어라면 설정에서 회사코드를 적어 주세요. "
            "그래도 안 되면 설정의 '로그인 한 번 보여주기' 로 알려 주시면 그대로 따라 합니다")

    msg = ""
    for sel in (".err", "[role=alert]", ".error", ".alert"):
        try:
            loc = page.locator(sel).first
            if loc.count():
                msg = (loc.inner_text() or "").strip()[:80]
                break
        except Exception:
            pass
    raise RuntimeError("로그인이 되지 않았습니다"
                       + (f": {msg}" if msg else "(아이디·비밀번호를 확인해 주세요)"))


def _first_visible(page, candidates):
    """후보를 차례로 보고 처음 보이는 것을 돌려줍니다."""
    for make in candidates:
        try:
            loc = make().first
            if loc.count() and loc.is_visible():
                return loc
        except Exception:
            continue
    return None


def _open_menu(page, *names: str) -> None:
    """차례로 눌러 들어갑니다. 글자가 보이는 것만 누릅니다."""
    for name in names:
        target = _first_visible(page, [
            lambda n=name: page.get_by_role("button", name=n, exact=True),
            lambda n=name: page.get_by_text(n, exact=True),
        ])
        if target is None:
            raise RuntimeError(f"'{name}' 메뉴를 찾지 못했습니다")
        target.click()
        page.wait_for_timeout(250)


# ---------- 읽기 ----------

def _list_rows(page):
    """목록의 각 줄. 사이트마다 표·목록·링크 중 무엇을 쓰는지 달라 차례로 봅니다."""
    for sel in ("button.row", "table tbody tr", "[role=row]", "ul li a", "ul li", ".list-item"):
        try:
            loc = page.locator(sel)
            if loc.count() >= 2:        # 머리글 한 줄만 있는 표는 거릅니다
                return loc
        except Exception:
            continue
    return None



def read_library(base_url: str, user_id: str, password: str, *,
        company: str = "", org_id: str = "",
                 menu: tuple[str, str] = ("게시판", "자료실"),
                 limit: int = 100, headless: bool = True) -> RpaResult:
    """자료실에 올라온 규정·서식의 제목과 본문을 읽어 옵니다."""
    t0 = time.perf_counter()
    try:
        with session(base_url, user_id, password, company=company,
                     org_id=org_id, headless=headless) as page:
            _open_menu(page, *menu)
            page.wait_for_timeout(400)
            rows = _list_rows(page)
            n = min(rows.count(), limit) if rows else 0
            items = []
            for i in range(n):
                row = rows.nth(i)
                title = (row.inner_text() or "").strip().splitlines()[0]
                row.click()
                page.wait_for_timeout(300)
                body = ""
                try:
                    body = page.locator("#modal").inner_text()
                except Exception:
                    pass
                items.append({"title": title, "body": body})
                close = _first_visible(page, [
                    lambda: page.get_by_role("button", name="닫기"),
                ])
                if close is not None:
                    close.click()
                    page.wait_for_timeout(150)
            return RpaResult(ok=True, data=items, seconds=time.perf_counter() - t0,
                             meta={"count": len(items)})
    except Exception as exc:
        return RpaResult(ok=False, error=_friendly(exc), seconds=time.perf_counter() - t0)


def read_pending(base_url: str, user_id: str, password: str, *,
        company: str = "", org_id: str = "",
                 headless: bool = True) -> RpaResult:
    """결재를 기다리는 문서 목록을 읽습니다(결재자 브리핑용)."""
    t0 = time.perf_counter()
    try:
        with session(base_url, user_id, password, company=company,
                     org_id=org_id, headless=headless) as page:
            _open_menu(page, "전자결재", "결재대기문서")
            page.wait_for_timeout(400)
            rows = _list_rows(page)
            items = [(rows.nth(i).inner_text() or "").strip().splitlines()[0]
                     for i in range(rows.count())] if rows else []
            return RpaResult(ok=True, data=items, seconds=time.perf_counter() - t0,
                             meta={"count": len(items)})
    except Exception as exc:
        return RpaResult(ok=False, error=_friendly(exc), seconds=time.perf_counter() - t0)


# ---------- 쓰기 (임시저장까지만) ----------

def save_draft(base_url: str, user_id: str, password: str, *,
               company: str = "",
               title: str, body: str, recipient: str = "내부결재",
               form_name: str = "일반기안문", attachments: list[Path] | None = None,
               org_id: str | None = None, headless: bool = True) -> RpaResult:
    """기안을 임시저장합니다. **상신하지 않습니다.**

    익혀 둔 길(지도)이 있으면 그 길로 갑니다. 없으면 흔한 이름으로 찾아봅니다.
    """
    site = load_map(org_id) if org_id else {}
    menu = tuple(site.get("draft") or ()) or ("전자결재", "결재작성")
    forms = site.get("forms") or []
    if forms and form_name not in forms:
        # 익힌 양식 중에 비슷한 이름이 있으면 그걸 씁니다.
        form_name = next((f for f in forms if form_name[:3] in f), forms[0])

    t0 = time.perf_counter()
    try:
        with session(base_url, user_id, password, company=company,
                     org_id=org_id, headless=headless) as page:
            _open_menu(page, *menu)
            page.wait_for_timeout(400)

            form = _first_visible(page, [
                lambda: page.get_by_role("button", name=form_name),
                lambda: page.get_by_text(form_name, exact=True),
            ])
            if form is None:
                raise RuntimeError(f"'{form_name}' 양식을 찾지 못했습니다")
            form.click()
            page.wait_for_timeout(700)

            rec = _first_visible(page, [lambda: page.get_by_label("수신자")])
            if rec is not None:
                rec.fill(recipient)

            ttl = _first_visible(page, [
                lambda: page.get_by_label("제목"),
                lambda: page.locator("#modal input[name='title']"),
            ])
            if ttl is None:
                raise RuntimeError("제목 칸을 찾지 못했습니다")
            ttl.fill(title)

            rich = page.locator("#modal [data-rich]").first
            if rich.count():
                rich.click()
                rich.fill(body)
            else:
                ta = _first_visible(page, [lambda: page.locator("#modal textarea")])
                if ta is None:
                    raise RuntimeError("본문 칸을 찾지 못했습니다")
                ta.fill(body)

            for f in attachments or []:
                picker = page.locator("#modal input[type='file']").first
                if picker.count():
                    picker.set_input_files(str(f))
                    page.wait_for_timeout(300)

            save = _first_visible(page, [
                lambda: page.get_by_role("button", name="임시저장"),
            ])
            if save is None:
                raise RuntimeError("임시저장 단추를 찾지 못했습니다")
            save.click()
            page.wait_for_timeout(900)

            return RpaResult(ok=True, seconds=time.perf_counter() - t0,
                             meta={"state": "draft", "title": title,
                                   "note": "임시저장했습니다. 상신은 사람이 합니다."})
    except Exception as exc:
        return RpaResult(ok=False, error=_friendly(exc), seconds=time.perf_counter() - t0)


def _friendly(exc: Exception) -> str:
    text = str(exc)
    if "Timeout" in text or "timeout" in text:
        return ("화면이 제때 뜨지 않았습니다. 그룹웨어가 느리거나 화면 구성이 "
                "바뀌었을 수 있습니다")
    if "ERR_CONNECTION" in text or "net::" in text:
        return "그룹웨어 주소에 연결하지 못했습니다"
    if "executable doesn't exist" in text or "Executable doesn" in text:
        return "크롬 또는 엣지가 필요합니다. 둘 중 하나를 설치해 주세요"
    return text.splitlines()[0][:180] if text else "알 수 없는 오류"

# ---------- 조직도 탐색 ----------
# 역할을 판정하려면 '내 직급'을 알아야 합니다. API 가 없는 그룹웨어에서는
# 사람이 보는 화면을 뒤져 찾습니다. 그룹웨어마다 메뉴 이름이 달라서
# 흔히 쓰는 이름을 차례로 눌러 봅니다.

ORG_MENUS = (
    ("조직도",), ("임직원업무관리", "조직도"), ("연락처", "전체 연락처"),
    ("인사", "조직도"), ("조직", "구성원"),
)

# 화면에서 직위를 알아보는 말. 앞쪽일수록 높은 자리입니다.
TITLE_RANKS = [
    (0, ("대표이사", "이사장", "원장")),
    (1, ("실장", "관장", "센터장", "본부장")),
    (2, ("부장", "팀장")),
    (3, ("차장",)),
    (4, ("대리", "과장")),
    (5, ("주임", "사원", "직원")),
]


def rank_of(title: str) -> int | None:
    """직위 글자에서 직급을 읽어 냅니다. 전결표와 맞추는 데 씁니다."""
    t = (title or "").strip()
    if not t:
        return None
    for rank, words in TITLE_RANKS:
        if any(w in t for w in words):
            return rank
    return None


def read_members(base_url: str, user_id: str, password: str, *,
        company: str = "", org_id: str = "",
                 headless: bool = True) -> RpaResult:
    """조직도를 뒤져 사람·부서·직위를 모으고, 직위에서 직급을 읽어 냅니다.

    이 결과가 있어야 서무비서가 '나는 몇 급이고, 무엇을 전결할 수 있는지'를
    기관 전결표와 맞춰 볼 수 있습니다.
    """
    t0 = time.perf_counter()
    try:
        with session(base_url, user_id, password, company=company,
                     org_id=org_id, headless=headless) as page:
            rows, used = [], None
            for menu in ORG_MENUS:
                try:
                    _open_menu(page, *menu)
                except Exception:
                    continue
                page.wait_for_timeout(500)
                found = _scrape_people(page)
                if found:
                    rows, used = found, " › ".join(menu)
                    break

            # 조직도를 못 찾으면 최소한 '나'는 알아냅니다. 그것만으로도
            # 역할 판정이 됩니다.
            me = _scrape_me(page, user_id)
            if me and not any(m.get("id") == me.get("id") for m in rows):
                rows.insert(0, me)

            if not rows:
                return RpaResult(ok=False, seconds=time.perf_counter() - t0,
                                 error="조직도를 찾지 못했습니다. 메뉴 이름을 알려 주시면 맞추겠습니다")
            return RpaResult(ok=True, data=rows, seconds=time.perf_counter() - t0,
                             meta={"메뉴": used or "(내 정보만)", "인원": len(rows)})
    except Exception as exc:
        return RpaResult(ok=False, error=_friendly(exc), seconds=time.perf_counter() - t0)


def _scrape_people(page) -> list[dict]:
    """표나 목록에서 이름·부서·직위로 보이는 줄을 모읍니다."""
    import re
    out, seen = [], set()
    text_blocks = []
    for sel in ("table tr", "li", "button.row", "[role=row]"):
        try:
            loc = page.locator(sel)
            for i in range(min(loc.count(), 200)):
                t = (loc.nth(i).inner_text() or "").strip()
                if t:
                    text_blocks.append(t)
        except Exception:
            continue

    for t in text_blocks:
        parts = [x.strip() for x in re.split(r"[\t\n·|/,]+", t) if x.strip()]
        if not (2 <= len(parts) <= 6):
            continue
        title = next((x for x in parts if rank_of(x) is not None), None)
        if not title:
            continue
        name = next((x for x in parts
                     if x != title and 2 <= len(x) <= 5 and re.fullmatch(r"[가-힣]+", x)), None)
        if not name or name in seen:
            continue
        seen.add(name)
        dept = next((x for x in parts if x not in (name, title) and len(x) <= 20), "")
        out.append({"id": name, "name": name, "dept": dept,
                    "title": title, "rank": rank_of(title), "source": "rpa"})
    return out


def _scrape_me(page, user_id: str) -> dict | None:
    """화면 어딘가에 있는 '내 정보'에서 이름과 직위를 찾습니다."""
    import re
    try:
        body = page.locator("body").inner_text()
    except Exception:
        return None
    for line in (body or "").splitlines():
        line = line.strip()
        if len(line) > 40 or rank_of(line) is None:
            continue
        name = next((w for w in re.split(r"[\s·|/,]+", line)
                     if 2 <= len(w) <= 5 and re.fullmatch(r"[가-힣]+", w)
                     and rank_of(w) is None), None)
        if name:
            title = next(w for w in re.split(r"[\s·|/,]+", line) if rank_of(w) is not None)
            return {"id": user_id or name, "name": name, "dept": "",
                    "title": title, "rank": rank_of(title), "source": "rpa-me"}
    return None

# ---------- 결재시스템 사용법 익히기 ----------
# 규정을 읽는 것만으로는 기안을 올릴 수 없습니다. 그 시스템에서 **어디를 눌러**
# 기안을 쓰는지, 양식이 무엇무엇이 있는지, 칸 이름이 무엇인지까지 알아야 합니다.
# 한 번 돌아보며 길을 적어 두면(지도) 다음부터는 바로 그 길로 갑니다.

DRAFT_MENUS = (
    ("전자결재", "결재작성"), ("전자결재", "기안작성"), ("결재", "기안"),
    ("전자결재",), ("기안",), ("결재문서", "기안"),
)
LIBRARY_MENUS = (
    ("게시판", "자료실"), ("자료실",), ("문서함",), ("규정",),
    ("게시판", "규정"), ("업무자료", "규정"),
)


def explore(base_url: str, user_id: str, password: str, *,
        company: str = "", org_id: str = "",
            headless: bool = True) -> RpaResult:
    """그 시스템을 한 바퀴 돌아보고 '쓰는 법'을 적어 옵니다.

    적어 오는 것:
      메뉴 목록, 규정·서식이 있는 자리, 기안을 쓰는 자리,
      쓸 수 있는 양식 이름들, 양식의 입력 칸 이름과 단추 이름.
    이 지도가 있으면 다음부터 헤매지 않고 바로 그 자리로 갑니다.
    """
    t0 = time.perf_counter()
    try:
        with session(base_url, user_id, password, company=company,
                     org_id=org_id, headless=headless) as page:
            site = {"base_url": base_url.rstrip("/"),
                    "menus": _top_menus(page),
                    "library": None, "draft": None,
                    "forms": [], "fields": {}, "buttons": []}

            # 1) 규정·서식이 어디에 있나
            for path in LIBRARY_MENUS:
                if _try_path(page, path) and _list_rows(page):
                    site["library"] = list(path)
                    break

            # 2) 기안은 어디서 쓰나
            for path in DRAFT_MENUS:
                if not _try_path(page, path):
                    continue
                forms = _form_names(page)
                if forms:
                    site["draft"] = list(path)
                    site["forms"] = forms[:30]
                    break

            # 3) 양식 하나를 열어 칸 이름과 단추를 적어 둡니다
            if site["draft"] and site["forms"]:
                opened = _open_form(page, site["forms"][0])
                if opened:
                    site["fields"] = _form_fields(page)
                    site["buttons"] = _dialog_buttons(page)

            ok = bool(site["library"] or site["draft"])
            return RpaResult(ok=ok, data=site, seconds=time.perf_counter() - t0,
                             error=None if ok else "자료실도 결재작성도 찾지 못했습니다",
                             meta={"양식": len(site["forms"]), "칸": len(site["fields"])})
    except Exception as exc:
        return RpaResult(ok=False, error=_friendly(exc), seconds=time.perf_counter() - t0)


def _top_menus(page) -> list[str]:
    """맨 위·옆에 보이는 메뉴 이름을 모읍니다."""
    out, seen = [], set()
    for sel in ("nav button", "nav a", "header button", "[role=navigation] button",
                "aside button", "ul li button"):
        try:
            loc = page.locator(sel)
            for i in range(min(loc.count(), 40)):
                t = (loc.nth(i).inner_text() or "").strip()
                t = t.splitlines()[0] if t else ""
                if 1 < len(t) <= 12 and t not in seen:
                    seen.add(t); out.append(t)
        except Exception:
            continue
    return out[:30]


def _try_path(page, path) -> bool:
    try:
        _open_menu(page, *path)
        page.wait_for_timeout(450)
        return True
    except Exception:
        return False


def _form_names(page) -> list[str]:
    """고를 수 있는 결재 양식 이름들."""
    out, seen = [], set()
    for sel in ("button", "a", "li"):
        try:
            loc = page.locator(sel)
            for i in range(min(loc.count(), 120)):
                t = (loc.nth(i).inner_text() or "").strip()
                t = t.splitlines()[0].strip() if t else ""
                if not (3 <= len(t) <= 30) or t in seen:
                    continue
                if any(w in t for w in ("기안문", "품의", "요구서", "보고서", "신청서",
                                        "결의서", "명령서", "회의록", "계획서", "사유서")):
                    seen.add(t); out.append(t)
        except Exception:
            continue
    return out


def _open_form(page, name: str) -> bool:
    el = _first_visible(page, [
        lambda: page.get_by_role("button", name=name),
        lambda: page.get_by_text(name, exact=True),
    ])
    if not el:
        return False
    el.click()
    page.wait_for_timeout(900)
    return True


def _form_fields(page) -> dict:
    """열린 양식의 입력 칸 이름과 종류."""
    out = {}
    for sel in ("#modal input, #modal textarea, #modal select",
                "dialog input, dialog textarea, dialog select",
                "form input, form textarea, form select"):
        try:
            loc = page.locator(sel)
            for i in range(min(loc.count(), 60)):
                el = loc.nth(i)
                name = (el.get_attribute("name") or el.get_attribute("aria-label")
                        or el.get_attribute("placeholder") or "")
                if not name:
                    continue
                out[name] = (el.get_attribute("type")
                             or el.evaluate("e => e.tagName.toLowerCase()"))
            if out:
                break
        except Exception:
            continue
    return out


def _dialog_buttons(page) -> list[str]:
    out, seen = [], set()
    for sel in ("#modal button", "dialog button", "form button"):
        try:
            loc = page.locator(sel)
            for i in range(min(loc.count(), 30)):
                t = (loc.nth(i).inner_text() or "").strip()
                if t and len(t) <= 12 and t not in seen:
                    seen.add(t); out.append(t)
            if out:
                break
        except Exception:
            continue
    return out

# ---------- 익힌 길을 적어 두기 ----------
MAP_FILE = "결재시스템지도.json"


def map_path(org_id: str):
    from . import store
    return store.org_dir(org_id) / MAP_FILE


def save_map(org_id: str, site: dict) -> None:
    import json
    from datetime import datetime
    site = {**site, "익힌때": datetime.now().isoformat(timespec="seconds")}
    map_path(org_id).write_text(json.dumps(site, ensure_ascii=False, indent=2),
                                encoding="utf-8")


def load_map(org_id: str) -> dict:
    import json
    try:
        return json.loads(map_path(org_id).read_text(encoding="utf-8"))
    except Exception:
        return {}


def login_steps(org_id: str) -> list[dict]:
    """전에 사람이 보여 준 로그인 순서. 없으면 빈 목록."""
    return (load_map(org_id) or {}).get("로그인순서") or []


# 사람이 로그인하는 것을 보고 그대로 적어 두는 쪽지. 화면이 넘어가도 계속 적도록
# 페이지가 열릴 때마다 다시 붙입니다.
_WATCH_JS = """
(() => {
  const desc = (el) => ({
    name: el.getAttribute('name') || '',
    id: el.getAttribute('id') || '',
    placeholder: el.getAttribute('placeholder') || '',
    aria: el.getAttribute('aria-label') || '',
    type: (el.getAttribute('type') || 'text').toLowerCase(),
  });
  const send = (o) => { try { window.__seobi(o); } catch (e) {} };
  document.addEventListener('change', (e) => {
    const el = e.target;
    if (!el || el.tagName !== 'INPUT') return;
    const d = desc(el);
    if (['checkbox', 'radio', 'hidden', 'submit', 'button'].includes(d.type)) return;
    send({ 무엇: '채우기', 설명: d, 값: d.type === 'password' ? null : (el.value || '') });
  }, true);
  document.addEventListener('click', (e) => {
    const el = e.target && e.target.closest('button, a, input[type=submit]');
    if (!el) return;
    const text = (el.innerText || el.value || '').trim().slice(0, 30);
    if (text) send({ 무엇: '누르기', 글자: text });
  }, true);
})();
"""


def watch_login(org_id: str, base_url: str, *, user_id: str = "", company: str = "",
                wait_sec: int = 300) -> RpaResult:
    """사람이 직접 로그인하는 것을 보고 순서를 적어 둡니다.

    서비가 스스로 못 들어가는 그룹웨어(단계가 특이하거나, 화면에 아무 단서가 없는
    곳)를 위한 길입니다. 창이 뜨면 평소처럼 로그인하시면 됩니다.

    **비밀번호는 적지 않습니다.** 어느 칸이 비밀번호 칸인지만 적습니다.
    값은 윈도우 자격 증명 관리자에서 꺼내 씁니다.
    """
    from playwright.sync_api import sync_playwright

    base = base_url.rstrip("/")
    seen: list[dict] = []
    started = time.time()

    with sync_playwright() as pw:
        browser = None
        last = None
        for ch in BROWSER_CHANNELS:
            try:
                browser = pw.chromium.launch(channel=ch, headless=False)
                break
            except Exception as exc:
                last = exc
        if browser is None:
            return RpaResult(False, f"크롬 또는 엣지를 띄우지 못했습니다: {last}")
        try:
            ctx = browser.new_context()
            ctx.expose_binding("__seobi", lambda _src, o: seen.append(o))
            ctx.add_init_script(_WATCH_JS)
            page = ctx.new_page()
            page.goto(base, wait_until="domcontentloaded")

            # 로그인이 끝날 때까지(비밀번호 칸이 사라질 때까지) 기다립니다.
            done = False
            while time.time() - started < wait_sec:
                page.wait_for_timeout(1000)
                try:
                    if page.is_closed():
                        break
                    typed_pw = any(s.get("무엇") == "채우기"
                                   and (s.get("설명") or {}).get("type") == "password"
                                   for s in seen)
                    if typed_pw and page.locator("input[type='password']").count() == 0:
                        done = True
                        break
                except Exception:
                    break
        finally:
            browser.close()

    steps = _tidy_steps(seen, user_id=user_id, company=company)
    if not steps:
        return RpaResult(False, "보고 배운 것이 없습니다. 창에서 로그인을 끝까지 해 주세요",
                         seconds=time.time() - started)
    site = {**(load_map(org_id) or {}), "로그인순서": steps}
    save_map(org_id, site)
    return RpaResult(True, None, {"로그인순서": steps, "끝까지 봄": done},
                     seconds=time.time() - started)


def _tidy_steps(seen: list[dict], *, user_id: str, company: str) -> list[dict]:
    """본 것을 다시 쓸 수 있는 순서로 정리합니다. 값은 남기지 않습니다."""
    out: list[dict] = []
    for s in seen:
        if s.get("무엇") == "누르기":
            if out and out[-1].get("무엇") == "누르기" and out[-1].get("글자") == s.get("글자"):
                continue
            out.append({"무엇": "누르기", "글자": s["글자"]})
            continue
        d = s.get("설명") or {}
        value = (s.get("값") or "").strip()
        if d.get("type") == "password":
            role = "비밀번호"
        elif user_id and value == user_id.strip():
            role = "아이디"
        elif company and value == company.strip():
            role = "회사"
        else:
            # 무엇인지 모르는 칸. 값은 적지 않고 사람에게 되묻습니다.
            role = "그밖에"
        find = {k: d[k] for k in ("name", "id", "placeholder", "aria") if d.get(k)}
        if not find:
            find = {"type": d.get("type") or "text"}
        out.append({"무엇": "채우기", "역할": role, "찾기": find})
    return out


def _by_find(page, find: dict):
    """적어 둔 단서로 칸을 다시 찾습니다."""
    tries = []
    if find.get("name"):
        tries.append(lambda: page.locator(f"input[name={find['name']!r}]"))
    if find.get("id"):
        tries.append(lambda: page.locator(f"#{find['id']}"))
    if find.get("placeholder"):
        tries.append(lambda: page.get_by_placeholder(find["placeholder"]))
    if find.get("aria"):
        tries.append(lambda: page.get_by_label(find["aria"]))
    if find.get("type"):
        tries.append(lambda: page.locator(f"input[type={find['type']!r}]"))
    return _first_visible(page, tries)


def _login_by_steps(page, steps: list[dict], values: dict[str, str]) -> bool:
    """보고 배운 순서 그대로 따라 합니다. 하나라도 못 찾으면 False."""
    for s in steps:
        if s.get("무엇") == "누르기":
            btn = _first_visible(page, [
                lambda: page.get_by_role("button", name=s["글자"]),
                lambda: page.get_by_role("link", name=s["글자"]),
                lambda: page.get_by_text(s["글자"], exact=True),
            ])
            if btn is None:
                return False
            btn.click()
            try:
                page.wait_for_load_state("networkidle", timeout=12_000)
            except Exception:
                pass
            page.wait_for_timeout(500)
            continue

        role = s.get("역할")
        value = values.get(role, "")
        if not value:
            if role == "그밖에":
                continue              # 모르는 칸은 건드리지 않습니다
            return False
        box = _by_find(page, s.get("찾기") or {})
        if box is None:
            return False
        _fill(box, value)
    return _logged_in(page)


def learn(org_id: str, base_url: str, user_id: str, password: str,
          *, company: str = "", headless: bool = True) -> RpaResult:
    """한 바퀴 돌아보고 길을 적어 둡니다. 연결할 때 한 번 부르면 됩니다."""
    res = explore(base_url, user_id, password, company=company,
                  org_id=org_id, headless=headless)
    if res.ok and res.data:
        save_map(org_id, res.data)
    return res


def describe(org_id: str) -> dict:
    """무엇을 익혔는지 사람이 볼 수 있게."""
    m = load_map(org_id)
    if not m:
        return {"익힘": False, "말": "아직 이 시스템을 돌아보지 않았습니다"}
    return {
        "익힘": True,
        "주소": m.get("base_url"),
        "익힌때": m.get("익힌때"),
        "메뉴": m.get("menus") or [],
        "규정·서식 자리": " › ".join(m.get("library") or []) or "못 찾음",
        "기안 쓰는 자리": " › ".join(m.get("draft") or []) or "못 찾음",
        "쓸 수 있는 양식": m.get("forms") or [],
        "양식 입력 칸": list((m.get("fields") or {}).keys()),
        "단추": m.get("buttons") or [],
    }
