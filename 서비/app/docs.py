"""여러 형식의 규정 파일에서 글자를 읽어 옵니다. 원본 파일은 읽기만 합니다.

지원: .md .txt .docx .hwpx .pdf(pypdf 설치 시)
HWP(구 형식 .hwp)는 한글에서 '다른 이름으로 저장 → HWPX 또는 PDF'로 바꿔 넣어 주세요.
"""
from __future__ import annotations

import re
import zipfile
from pathlib import Path

SUPPORTED = {".md", ".txt", ".docx", ".hwpx", ".pdf"}


def read_text(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in {".md", ".txt"}:
        return path.read_text(encoding="utf-8", errors="replace")
    if ext == ".docx":
        return _read_docx(path)
    if ext == ".hwpx":
        return _read_hwpx(path)
    if ext == ".pdf":
        return _read_pdf(path)
    return ""


def _read_docx(path: Path) -> str:
    from docx import Document

    doc = Document(str(path))
    parts = [p.text for p in doc.paragraphs]
    for table in doc.tables:
        for row in table.rows:
            parts.append(" | ".join(c.text for c in row.cells))
    return "\n".join(parts)


def _read_hwpx(path: Path) -> str:
    parts: list[str] = []
    with zipfile.ZipFile(path) as z:
        sections = sorted(n for n in z.namelist() if re.match(r"Contents/section\d+\.xml", n))
        for name in sections:
            xml = z.read(name).decode("utf-8", errors="replace")
            # 문단(<hp:p>) 단위로 줄바꿈, 글자(<hp:t>)만 꺼냄
            for para in re.findall(r"<hp:p[ >].*?</hp:p>", xml, re.S):
                text = "".join(re.findall(r"<hp:t[^>]*>(.*?)</hp:t>", para, re.S))
                text = re.sub(r"<[^>]+>", "", text)
                parts.append(_unescape(text))
    return "\n".join(parts)


def _read_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        return ""
    reader = PdfReader(str(path))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def _unescape(s: str) -> str:
    return (s.replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"')
             .replace("&apos;", "'").replace("&amp;", "&"))
