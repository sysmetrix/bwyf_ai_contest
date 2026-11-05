"""규정 저장소: 규정 파일을 조문 단위로 나누고, 층(공통 → 기관 → 부서)별로 검색합니다.

검색은 외부 모델 없이 동작하는 '글자 두 개 묶음(바이그램)' 방식입니다.
한국어 형태소 분석기가 없어도 조사·어미 변화에 덜 흔들립니다.
"""
from __future__ import annotations

import hashlib
import math
import re
import threading
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from .docs import SUPPORTED, read_text
from .store import COMMON, ROOT, org_dir

LAYER_LABEL = {"common": "공통 규정", "org": "기관 규정", "dept": "부서 보충"}
LAYER_WEIGHT = {"common": 1.0, "org": 1.15, "dept": 1.25}  # 가까운 층을 우선

ARTICLE_RE = re.compile(r"^\s*(제\s*\d+\s*조(?:의\s*\d+)?)\s*(?:\(([^)]*)\))?")
ANNEX_RE = re.compile(r"^\s*(별표\s*\d*|부칙)\s*(?:\(([^)]*)\))?")


@dataclass
class Article:
    layer: str
    file: str          # 프로젝트 기준 상대 경로
    title: str         # 규정 이름
    ref: str           # 제12조, 별표 1 등
    heading: str       # (여비 정산)
    text: str

    @property
    def label(self) -> str:
        head = f"({self.heading})" if self.heading else ""
        return f"{self.title} {self.ref}{head}".strip()

    def as_dict(self, score: float | None = None) -> dict:
        d = {"layer": self.layer, "layer_label": LAYER_LABEL[self.layer], "file": self.file,
             "title": self.title, "ref": self.ref, "heading": self.heading,
             "label": self.label, "text": self.text}
        if score is not None:
            d["score"] = round(score, 3)
        return d


def split_articles(text: str, layer: str, file: str, fallback_title: str) -> list[Article]:
    lines = text.splitlines()
    title = fallback_title
    for line in lines:
        if line.strip():
            title = line.strip().lstrip("#").strip()
            break
    if len(title) > 30:  # 첫 줄이 제목이 아니라 긴 문장이면(매뉴얼 PDF 등) 파일 이름을 씁니다
        title = fallback_title.replace("_", " ").strip()
    articles: list[Article] = []
    cur_ref, cur_head, buf = "", "", []

    def flush():
        body = "\n".join(buf).strip()
        if body and cur_ref:
            articles.append(Article(layer, file, title, cur_ref, cur_head, body))

    for line in lines:
        m = ARTICLE_RE.match(line) or ANNEX_RE.match(line)
        if m:
            flush()
            cur_ref = re.sub(r"\s+", "", m.group(1)).replace("별표", "별표 ").strip()
            cur_head = (m.group(2) or "").strip()
            buf = [line.strip()]
        elif cur_ref:
            buf.append(line.strip())
    flush()
    no_articles = not articles
    if no_articles and text.strip():  # 조문 구조가 없는 문서는 통째로 하나(길면 아래에서 나눔)
        articles.append(Article(layer, file, title, "본문", "", text.strip()))
    if (no_articles and len(text) > PART_SIZE * 1.4) or (len(text) > 20000 and len(text) / len(articles) > 3000):
        # 규정집이 아니라 업무 매뉴얼: '제○조'는 본문에 인용된 다른 법 조문일 때가 많아 믿을 수 없으므로
        # 목차 제목(1-1. 출장과 국내여비 등)을 따라 나눕니다.
        return _manual_passages(text, layer, file, title)
    return [part for art in articles for part in _split_long(art)]


SECTION_RE = re.compile(r"^\s*((?:[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+\.|\d{1,2}-\d{1,2}(?:-\d{1,2})?\.?)\s*[가-힣A-Za-z(][^·❙]{1,28}"
                        r"|\d{1,2}\.\s*[가-힣][^·❙.\d~]{1,16})\s*$")  # '4. 정기인사 인원은 5~10명' 같은 문장 제외
PAGE_RE = re.compile(r"❙\s*(\d{1,4})\s*$")  # 쪽 머리글 'Ⅱ. 인사ㆍ노무 ❙ 25'


def _manual_passages(text: str, layer: str, file: str, title: str) -> list[Article]:
    parts: list[Article] = []
    section, page, buf = "앞부분", None, ""
    start_page = None

    def push():
        if buf.strip():
            parts.append(Article(layer, file, title, section, f"{start_page}쪽" if start_page else "", buf.strip()))

    for line in text.splitlines():
        if "· · ·" in line:  # 목차 줄은 내용이 아니라서 건너뜁니다
            continue
        pm = PAGE_RE.search(line)
        if pm:
            page = int(pm.group(1))
            if start_page is None:
                start_page = page
            continue
        m = SECTION_RE.match(line)
        if m and "· ·" not in line and not line.rstrip().endswith("다."):
            push()
            section, buf, start_page = re.sub(r"\s+", " ", m.group(1)).strip(), line + chr(10), page
            continue
        if len(buf) + len(line) > PART_SIZE:
            push()
            buf, start_page = "", page
        buf += line + chr(10)
    push()
    return parts


PART_SIZE = 1500


def _split_long(art: Article) -> list[Article]:
    """업무 매뉴얼처럼 '제○조' 하나에 수만 자가 뭉친 문서는 1,500자 안팎으로 나눠 읽습니다.
    그래야 검색이 정확한 부분을 찾고, 근거로 보여 줄 때도 어디인지 알 수 있어요."""
    if len(art.text) <= PART_SIZE * 1.4:
        return [art]
    parts, buf = [], ""
    for line in art.text.splitlines():
        if buf and len(buf) + len(line) > PART_SIZE:
            parts.append(buf)
            buf = ""
        buf += line + "\n"
    if buf.strip():
        parts.append(buf)
    n = len(parts)
    head = art.heading
    return [Article(art.layer, art.file, art.title, art.ref, f"{head} {i}/{n}".strip(), p.strip())
            for i, p in enumerate(parts, 1)]


def _bigrams(text: str) -> list[str]:
    grams = []
    for word in re.findall(r"[가-힣A-Za-z0-9]+", text.lower()):
        if len(word) == 1:
            grams.append(word)
        grams.extend(word[i:i + 2] for i in range(len(word) - 1))
    return grams


class RuleIndex:
    def __init__(self, articles: list[Article]):
        self.articles = articles
        # 장·조 제목(ref·heading)에 들어간 말은 세 번 세어서, 제목이 맞는 부분이 위로 오게 합니다
        self.grams = [Counter(_bigrams(" ".join([a.title, a.ref, a.ref, a.ref, a.heading, a.heading, a.text]))) for a in articles]
        df: Counter = Counter()
        for g in self.grams:
            df.update(g.keys())
        n = max(len(articles), 1)
        self.idf = {t: math.log(1 + n / c) for t, c in df.items()}

    def search(self, query: str, k: int = 3, layers: set[str] | None = None) -> list[tuple[Article, float]]:
        q = set(_bigrams(query))
        scored = []
        for art, grams in zip(self.articles, self.grams):
            if layers and art.layer not in layers:
                continue
            s = sum(self.idf.get(t, 0) * min(grams[t], 3) for t in q if t in grams)
            if s > 0:
                length_norm = 1 / math.sqrt(1 + len(art.text) / 400)
                scored.append((art, s * LAYER_WEIGHT[art.layer] * length_norm))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:k]


def _layer_files(org_id: str) -> list[tuple[str, Path]]:
    files: list[tuple[str, Path]] = []
    for f in sorted((COMMON / "rules").rglob("*")):
        files.append(("common", f))
    rules = org_dir(org_id) / "rules"
    if rules.exists():
        for f in sorted(rules.rglob("*")):
            layer = "dept" if "dept" in f.relative_to(rules).parts[:1] else "org"
            files.append((layer, f))
    return [(l, f) for l, f in files if f.is_file() and f.suffix.lower() in SUPPORTED]


TEXT_CACHE = ROOT / ".cache" / "rule_text"


def text_cache_path(f: Path) -> Path:
    # 파일 내용으로 이름을 정해서, 다른 PC로 옮겨도(경로가 달라도) 그대로 다시 쓸 수 있습니다
    return TEXT_CACHE / f"{hashlib.sha1(f.read_bytes()).hexdigest()}.txt"


def _cached_text(f: Path) -> str:
    """큰 PDF는 글자 뽑는 데 1분 넘게 걸려서, 한 번 뽑은 글자를 디스크에 저장해 두고 다시 씁니다.
    파일 내용이 바뀌면 새로 뽑습니다."""
    cached = text_cache_path(f)
    if cached.exists():
        return cached.read_text(encoding="utf-8")
    text = read_text(f)
    TEXT_CACHE.mkdir(parents=True, exist_ok=True)
    cached.write_text(text, encoding="utf-8")
    return text


_cache: dict[str, tuple[tuple, RuleIndex]] = {}
_lock = threading.Lock()


def get_index(org_id: str) -> RuleIndex:
    files = _layer_files(org_id)
    key = tuple((str(f), f.stat().st_mtime) for _, f in files)
    hit = _cache.get(org_id)
    if hit and hit[0] == key:
        return hit[1]
    with _lock:  # 시작할 때 미리 읽는 중이면 그게 끝나길 기다렸다가 결과를 같이 씁니다
        hit = _cache.get(org_id)
        if hit and hit[0] == key:
            return hit[1]
        articles: list[Article] = []
        for layer, f in files:
            rel = str(f.relative_to(ROOT))
            articles.extend(split_articles(_cached_text(f), layer, rel, f.stem))
        idx = RuleIndex(articles)
        _cache[org_id] = (key, idx)
        return idx


def warm_all(org_ids: list[str]) -> None:
    for org_id in org_ids:
        try:
            get_index(org_id)
        except Exception:
            pass


def list_rule_files(org_id: str) -> list[dict]:
    out = []
    for layer, f in _layer_files(org_id):
        out.append({"layer": layer, "layer_label": LAYER_LABEL[layer],
                    "file": str(f.relative_to(ROOT)), "ext": f.suffix.lower(),
                    "mtime": f.stat().st_mtime})
    return out
