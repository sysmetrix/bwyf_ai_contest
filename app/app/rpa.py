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
            headless: bool = True, timeout: int = WAIT) -> Iterator[Any]:
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
            _login(page, base, user_id, password)
            yield page
        finally:
            browser.close()


def _login(page, base: str, user_id: str, password: str) -> None:
    """로그인. 칸은 화면에 보이는 이름으로 찾습니다."""
    page.goto(f"{base}/login", wait_until="domcontentloaded")

    # 아이디 칸: '아이디' 라벨을 먼저 보고, 없으면 흔한 이름들을 차례로 봅니다.
    ident = _first_visible(page, [
        lambda: page.get_by_label("아이디"),
        lambda: page.get_by_placeholder("아이디"),
        lambda: page.locator("input[name='user_id']"),
        lambda: page.locator("input[name='userId'], input[name='id']"),
    ])
    if ident is None:
        raise RuntimeError("로그인 화면에서 아이디 칸을 찾지 못했습니다")
    ident.fill(user_id)

    pw_box = _first_visible(page, [
        lambda: page.get_by_label("비밀번호"),
        lambda: page.locator("input[type='password']"),
    ])
    if pw_box is None:
        # 아이디를 먼저 넣고 '다음'을 눌러야 비밀번호 칸이 나오는 그룹웨어가 있습니다.
        nxt = _first_visible(page, [lambda: page.get_by_role("button", name="다음")])
        if nxt is not None:
            nxt.click()
            pw_box = _first_visible(page, [lambda: page.locator("input[type='password']")])
    if pw_box is None:
        raise RuntimeError("로그인 화면에서 비밀번호 칸을 찾지 못했습니다")
    pw_box.fill(password)

    btn = _first_visible(page, [
        lambda: page.get_by_role("button", name="로그인"),
        lambda: page.locator("button[type='submit']"),
    ])
    if btn is None:
        raise RuntimeError("로그인 단추를 찾지 못했습니다")
    btn.click()

    page.wait_for_load_state("networkidle")
    if "/login" in page.url:
        raise RuntimeError("로그인이 되지 않았습니다(아이디·비밀번호를 확인해 주세요)")


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

def read_library(base_url: str, user_id: str, password: str, *,
                 menu: tuple[str, str] = ("게시판", "자료실"),
                 limit: int = 100, headless: bool = True) -> RpaResult:
    """자료실에 올라온 규정·서식의 제목과 본문을 읽어 옵니다."""
    t0 = time.perf_counter()
    try:
        with session(base_url, user_id, password, headless=headless) as page:
            _open_menu(page, *menu)
            page.wait_for_timeout(400)
            rows = page.locator("button.row")
            n = min(rows.count(), limit)
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
                 headless: bool = True) -> RpaResult:
    """결재를 기다리는 문서 목록을 읽습니다(결재자 브리핑용)."""
    t0 = time.perf_counter()
    try:
        with session(base_url, user_id, password, headless=headless) as page:
            _open_menu(page, "전자결재", "결재대기문서")
            page.wait_for_timeout(400)
            rows = page.locator("button.row")
            items = [(rows.nth(i).inner_text() or "").strip().splitlines()[0]
                     for i in range(rows.count())]
            return RpaResult(ok=True, data=items, seconds=time.perf_counter() - t0,
                             meta={"count": len(items)})
    except Exception as exc:
        return RpaResult(ok=False, error=_friendly(exc), seconds=time.perf_counter() - t0)


# ---------- 쓰기 (임시저장까지만) ----------

def save_draft(base_url: str, user_id: str, password: str, *,
               title: str, body: str, recipient: str = "내부결재",
               form_name: str = "일반기안문", attachments: list[Path] | None = None,
               headless: bool = True) -> RpaResult:
    """기안을 임시저장합니다. **상신하지 않습니다.**"""
    t0 = time.perf_counter()
    try:
        with session(base_url, user_id, password, headless=headless) as page:
            _open_menu(page, "전자결재", "결재작성")
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
                 headless: bool = True) -> RpaResult:
    """조직도를 뒤져 사람·부서·직위를 모으고, 직위에서 직급을 읽어 냅니다.

    이 결과가 있어야 서무비서가 '나는 몇 급이고, 무엇을 전결할 수 있는지'를
    기관 전결표와 맞춰 볼 수 있습니다.
    """
    t0 = time.perf_counter()
    try:
        with session(base_url, user_id, password, headless=headless) as page:
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
