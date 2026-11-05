"""구동안내서(.md)를 한글이 깨지지 않는 PDF로 변환하는 1회성 스크립트."""
import re
import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                 TableStyle, Preformatted, HRFlowable)

pdfmetrics.registerFont(TTFont("Malgun", r"C:\Windows\Fonts\malgun.ttf"))
pdfmetrics.registerFont(TTFont("MalgunBold", r"C:\Windows\Fonts\malgunbd.ttf"))

H1 = ParagraphStyle("H1", fontName="MalgunBold", fontSize=18, leading=24, spaceAfter=10, textColor=colors.HexColor("#172e27"))
H2 = ParagraphStyle("H2", fontName="MalgunBold", fontSize=14, leading=20, spaceBefore=14, spaceAfter=8, textColor=colors.HexColor("#245344"))
H3 = ParagraphStyle("H3", fontName="MalgunBold", fontSize=11.5, leading=16, spaceBefore=10, spaceAfter=4, textColor=colors.HexColor("#245344"))
BODY = ParagraphStyle("Body", fontName="Malgun", fontSize=9.5, leading=14, spaceAfter=6)
QUOTE = ParagraphStyle("Quote", fontName="Malgun", fontSize=9, leading=13, spaceAfter=6, textColor=colors.HexColor("#6b6b6b"), leftIndent=10)
LI = ParagraphStyle("LI", fontName="Malgun", fontSize=9.5, leading=14, spaceAfter=3, leftIndent=12, bulletIndent=2)
CODE = ParagraphStyle("Code", fontName="Malgun", fontSize=8.8, leading=12,
                       backColor=colors.HexColor("#fafbfa"), borderColor=colors.HexColor("#e3e6e4"),
                       borderWidth=0.5, borderPadding=6)


def code_repl(m: re.Match) -> str:
    content = m.group(1)
    font = "Courier" if content.isascii() else "Malgun"
    return f'<font face="{font}" size="8.5" color="#a84a2f">{content}</font>'


def inline(s: str) -> str:
    s = s.replace("✕", "X")
    s = re.sub(r"`(.+?)`", lambda m: "\x00" + m.group(1) + "\x01", s)
    s = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"\x00(.+?)\x01", code_repl, s)
    return s


def build(md_path: Path, pdf_path: Path) -> None:
    text = md_path.read_text(encoding="utf-8")
    lines = text.split("\n")
    story = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if stripped.startswith("```"):
            i += 1
            code_lines = []
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            story.append(Preformatted("\n".join(code_lines), CODE))
            story.append(Spacer(1, 6))
            i += 1
            continue

        if stripped.startswith("|"):
            table_lines = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                table_lines.append(lines[i].strip())
                i += 1
            rows = [[c.strip() for c in r.strip("|").split("|")] for r in table_lines
                    if not re.match(r"^\|?\s*-+\s*(\|\s*-+\s*)*\|?$", r)]
            data = [[Paragraph(inline(c), BODY) for c in row] for row in rows]
            ncols = max(len(r) for r in data)
            col_w = (170 * mm) / ncols
            t = Table(data, colWidths=[col_w] * ncols, repeatRows=1)
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#edf3f0")),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#dfe3e0")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ]))
            story.append(t)
            story.append(Spacer(1, 8))
            continue

        if stripped.startswith("# "):
            story.append(Paragraph(inline(stripped[2:]), H1)); i += 1; continue
        if stripped.startswith("## "):
            story.append(Paragraph(inline(stripped[3:]), H2)); i += 1; continue
        if stripped.startswith("### "):
            story.append(Paragraph(inline(stripped[4:]), H3)); i += 1; continue
        if stripped == "---":
            story.append(HRFlowable(width="100%", color=colors.HexColor("#dfe3e0"), spaceAfter=8)); i += 1; continue
        if stripped.startswith("> "):
            story.append(Paragraph(inline(stripped[2:]), QUOTE)); i += 1; continue
        if re.match(r"^\d+\.\s", stripped):
            story.append(Paragraph(inline(stripped), LI)); i += 1; continue
        if stripped.startswith("- "):
            story.append(Paragraph("• " + inline(stripped[2:]), LI)); i += 1; continue
        if not stripped:
            story.append(Spacer(1, 4)); i += 1; continue
        story.append(Paragraph(inline(stripped), BODY)); i += 1

    doc = SimpleDocTemplate(str(pdf_path), pagesize=A4,
                             topMargin=18 * mm, bottomMargin=16 * mm,
                             leftMargin=18 * mm, rightMargin=18 * mm)
    doc.build(story)


if __name__ == "__main__":
    src = Path(sys.argv[1])
    dst = src.with_suffix(".pdf")
    build(src, dst)
    print(f"생성됨: {dst}")
