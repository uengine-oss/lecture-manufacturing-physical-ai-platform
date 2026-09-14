"""교재 빌드: textbooks/<반>/*.md → dist/docx, dist/html(자체 포함), dist/pdf + 목차 index.html

사용: python tools/build_textbooks.py [--pdf]
"""
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor

L = Path(__file__).resolve().parent.parent
TB = L / "textbooks"
DIST = TB / "dist"
FONT = "Pretendard"

CSS = """
body{font-family:Pretendard,"Apple SD Gothic Neo","Noto Sans KR",sans-serif;max-width:980px;margin:0 auto;padding:40px 28px 80px;color:#18212f;line-height:1.75;font-size:16px;background:#fcfcfb}
h1{font-size:30px;border-bottom:3px solid #2a78d6;padding-bottom:10px;margin-top:0}h2{font-size:23px;margin-top:44px;border-left:6px solid #2a78d6;padding-left:12px}
h3{font-size:18px;margin-top:28px;color:#1e3a8a}table{border-collapse:collapse;width:100%;margin:14px 0;font-size:14.5px;display:block;overflow-x:auto}
th,td{border:1px solid #e2e8f0;padding:7px 10px;vertical-align:top}th{background:#f1f5f9}img{max-width:100%;border:1px solid #e2e8f0;border-radius:10px;margin:10px 0;background:#fff}
figure{margin:18px 0}figcaption{color:#64748b;font-size:13.5px;text-align:center}
pre{background:#0f172a;color:#e2e8f0;padding:14px 16px;border-radius:10px;overflow-x:auto;font-size:13.5px;line-height:1.5}code{font-family:ui-monospace,Menlo,monospace;font-size:.92em}
p code,li code,td code{background:#eef2ff;color:#3730a3;padding:1px 5px;border-radius:5px}
blockquote{border-left:4px solid #f59e0b;background:#fffbeb;margin:14px 0;padding:10px 16px;border-radius:0 10px 10px 0}
nav#TOC{background:#f8fafc;border:1px solid #e2e8f0;border-radius:12px;padding:10px 20px;font-size:14px}nav#TOC ul{padding-left:18px}
.back{font-size:14px}
@media print{body{max-width:none;padding:0 8mm}pre{white-space:pre-wrap}h2{page-break-after:avoid}img{page-break-inside:avoid}}
"""


def reference_docx(path: Path) -> None:
    subprocess.run(f"pandoc -o '{path}' --print-default-data-file reference.docx", shell=True, check=True)
    d = Document(str(path))
    for name in ["Normal", "Body Text", "First Paragraph", "Compact", "Heading 1", "Heading 2", "Heading 3", "Title", "Table", "Source Code", "Block Text", "Image Caption", "Captioned Figure"]:
        try:
            st = d.styles[name]
        except KeyError:
            continue
        st.font.name = FONT
        rpr = st.element.get_or_add_rPr()
        rfonts = rpr.find(qn("w:rFonts"))
        if rfonts is None:
            rfonts = rpr.makeelement(qn("w:rFonts"), {})
            rpr.append(rfonts)
        for att in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
            rfonts.set(qn(att), FONT)
        if name.startswith("Heading") or name == "Title":
            st.font.color.rgb = RGBColor(0x1E, 0x3A, 0x8A)
        if name in ("Normal", "Body Text", "First Paragraph", "Compact"):
            st.font.size = Pt(10.5)
    d.styles["Heading 1"].font.size = Pt(20)
    d.styles["Heading 2"].font.size = Pt(15)
    d.styles["Heading 3"].font.size = Pt(12.5)
    d.save(str(path))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", action="store_true")
    a = ap.parse_args()
    for sub in ("docx", "html", "pdf"):
        (DIST / sub).mkdir(parents=True, exist_ok=True)
    ref = DIST / "reference.docx"
    reference_docx(ref)
    (DIST / "textbook.css").write_text(CSS)
    entries = []
    for cls in ("실전반", "통합반"):
        for md in sorted((TB / cls).glob("*.md")):
            title = next((l[2:].strip() for l in md.read_text().splitlines() if l.startswith("# ")), md.stem)
            base = f"{cls}_{md.stem}"
            # 첫 H1 은 문서 제목(title 메타데이터)으로 옮기고 본문에서는 뺀다 — 제목이 두 번 나오지 않게
            lines = md.read_text().splitlines()
            first = next(i for i, l in enumerate(lines) if l.startswith("# "))
            body = "\n".join(lines[:first] + lines[first + 1 :])
            common = ["pandoc", "-", "--from", "gfm+pipe_tables+implicit_figures", f"--resource-path={md.parent}", "--metadata", f"title={title}", "--metadata", "lang=ko"]
            subprocess.run(common + ["-o", str(DIST / "docx" / f"{base}.docx"), f"--reference-doc={ref}", "--toc", "--toc-depth=2"], input=body, text=True, check=True)
            subprocess.run(common + ["-s", "--toc", "--toc-depth=2", "--embed-resources", "--css", str(DIST / "textbook.css"), "-o", str(DIST / "html" / f"{base}.html"), "--variable", "pagetitle=" + title], input=body, text=True, check=True)
            entries.append((cls, title, base))
            print("built", base)
    rows = "".join(f'<tr><td>{c}</td><td><a href="html/{b}.html">{t}</a></td><td><a href="docx/{b}.docx">DOCX</a></td><td>{"<a href=pdf/"+b+".pdf>PDF</a>" if a.pdf else ""}</td></tr>' for c, t, b in entries)
    (DIST / "index.html").write_text(f"<!doctype html><meta charset=utf-8><title>차수별 교재</title><style>{CSS}</style><h1>제조 피지컬 AI 플랫폼 연계 — 차수별 교재</h1><table><tr><th>반</th><th>회차</th><th>DOCX</th><th>PDF</th></tr>{rows}</table>")
    if a.pdf:
        subprocess.run(["node", str(L / "video" / "print_pdf.mjs"), str(DIST)], check=True)


if __name__ == "__main__":
    main()
