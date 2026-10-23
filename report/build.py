#!/usr/bin/env python3
"""Build SAKSHI report: report.md -> report.typ (PDF via typst) and report.docx.

Run: uv run --with python-docx build.py
"""
import re
import subprocess
from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

ROOT = Path(__file__).parent
FIGS = ROOT / "figs"
FONT = "Times New Roman"

TITLE = "SAKSHI"
SUBTITLE = "Multi-Camera Vehicle Analytics and Evidence Review"
TAGLINE = "An AI system for vehicle detection, licence-plate review and auditable observations"
COURSE = "CSE311 Artificial Intelligence"
DEPT = "Department of Computer Science and Engineering"
INST = "Indian Institute of Information Technology Kottayam"
YEAR = "Third Year"
AY = "Academic Year 2026–2027"
GUIDE = "Dr. Sreeja M U"
TEAM = [
    ("A S Sri Dathan", "2024BCS0091"),
    ("Akshay V.S", "2024BCD0015"),
    ("Bharadwaj B Chand", "2024BCS0059"),
    ("Shivansh Neekhra", "2024BCS0023"),
    ("Srimoneyshankar Ajith", "2024BCS0055"),
]
ACK = [
    "We express our sincere gratitude to our course instructor, Dr. Sreeja M U, for guidance throughout this mini project, and to the Department of Computer Science and Engineering, IIIT Kottayam, for the facilities provided.",
    "We declare that this report describes work carried out by our team. Third-party resources are acknowledged below and in the References. The project uses pretrained detection and recognition models and demonstration footage; it does not claim that the team trained the detector or the OCR model from scratch. Each member has reviewed, run and understood the code, methodology, data and results reported here and is responsible for them.",
]
RESOURCES = [
    "Ultralytics YOLOv8n pretrained weights (yolov8n.pt) for vehicle and person detection.",
    "Fast-ALPR 0.4.0 with the Open Image Models plate detector (YOLOv9-tiny, 384 × 384) and the FastPlateOCR global MobileViT-v2 OCR model.",
    "PyTorch (CPU), ONNX Runtime, OpenCV, NumPy, FastAPI, SQLite, React, TypeScript, Vite and Tailwind CSS.",
    "Six short recorded traffic clips (CAM-01 to CAM-06) for local demonstration and benchmarks; CAM-07 to CAM-09 were supplied privately for plate-review experiments and are not redistributed.",
]

# ---------------------------------------------------------------- parse
def parse(path):
    """Return dict(abstract, keywords, blocks, refs). Blocks carry numbering."""
    lines = path.read_text().split("\n")
    blocks, abstract, keywords, refs = [], [], "", []
    mode, h1, h2, nfig, ntab = "abstract", 0, 0, 0, 0
    labels = {}
    i = 0
    appendix = False
    while i < len(lines):
        ln = lines[i]
        if not ln.strip():
            i += 1
            continue
        if ln.startswith("[[keywords]]"):
            keywords = ln[len("[[keywords]]"):].strip()
            mode = "body"
        elif ln.startswith("[[references]]"):
            mode = "refs"
        elif ln.startswith("[[appendix]]"):
            appendix = True
            mode = "body"
        elif mode == "abstract" and ln.startswith("[[abstract]]"):
            pass
        elif mode == "abstract":
            abstract.append(ln)
        elif mode == "refs":
            refs.append(ln)
        elif ln.startswith("# "):
            if appendix:
                blocks.append(("h1", None, ln[2:], None))
            else:
                h1 += 1; h2 = 0; nfig = 0; ntab = 0
                blocks.append(("h1", str(h1), ln[2:], None))
        elif ln.startswith("## "):
            if appendix:
                blocks.append(("h2", None, ln[3:], None))
            else:
                h2 += 1
                blocks.append(("h2", f"{h1}.{h2}", ln[3:], None))
        elif ln.startswith("[[fig|"):
            _, name, cap, src = ln.strip("[]").split("|", 3)
            nfig += 1
            num = f"{h1}.{nfig}"
            labels["fig:" + name] = f"Figure {num}"
            blocks.append(("fig", num, name, (cap, src)))
        elif ln.startswith("[[table|"):
            parts = ln.strip("[]").split("|")
            cap, lab = parts[1], (parts[2] if len(parts) > 2 else None)
            ntab += 1
            num = f"{h1}.{ntab}"
            if lab:
                labels["table:" + lab] = f"Table {num}"
            rows = []
            i += 1
            while i < len(lines) and lines[i].strip():
                rows.append([c.strip() for c in lines[i].split(" | ")])
                i += 1
            blocks.append(("table", num, cap, rows))
            continue
        elif ln.startswith("[[eq]]"):
            blocks.append(("eq", None, ln[6:], None))
        elif ln.startswith("- "):
            blocks.append(("li", None, ln[2:], None))
        else:
            blocks.append(("p", None, ln, None))
        i += 1
    return dict(abstract=abstract, keywords=keywords, blocks=blocks, refs=refs, labels=labels)


def resolve(text, labels):
    return re.sub(r"\{((?:fig|table):\w+)\}", lambda m: labels[m.group(1)], text)


# ---------------------------------------------------------------- typst
def tesc(s):
    return re.sub(r"([\\#$*_@<`~])", r"\\\1", s)


def tinline(s):
    out = []
    for tok in re.split(r"(`[^`]+`)", s):
        if tok.startswith("`"):
            out.append("#raw(" + '"' + tok[1:-1].replace('"', '\\"') + '"' + ")")
        else:
            out.append(tesc(tok))
    return "".join(out)


TYPST_HEAD = r'''#set document(title: "SAKSHI: Multi-Camera Vehicle Analytics and Evidence Review", author: "SAKSHI project team")
#set page(paper: "a4", margin: (x: 2.5cm, y: 2.5cm))
#set text(font: "Liberation Serif", size: 11pt, lang: "en")
#set par(justify: true, leading: 0.72em, spacing: 1.05em)
#show raw: set text(font: ("DejaVu Sans Mono"), size: 9pt)
#show link: set text(fill: rgb("#1f4e8c"))
#let ink = rgb("#1f2d3d")
#let accent = rgb("#1f4e8c")
#set heading(numbering: "1.1")
#show heading.where(level: 1): it => {
  pagebreak(weak: true)
  v(0.6em)
  block(width: 100%, below: 0.9em)[
    #set text(size: 17pt, weight: "bold", fill: accent)
    #if it.numbering != none [#counter(heading).display(it.numbering)#h(0.6em)]#it.body
    #v(-0.2em)
    #line(length: 100%, stroke: 0.8pt + accent)
  ]
}
#show heading.where(level: 2): it => block(above: 1.3em, below: 0.7em)[
  #set text(size: 13pt, weight: "bold", fill: ink)
  #if it.numbering != none [#counter(heading).display(it.numbering)#h(0.5em)]#it.body
]
#show figure: set block(breakable: false)
#show figure.where(kind: "tbl"): set figure.caption(position: top)
#show figure.caption: it => align(center)[#set text(size: 10pt); #it.body]
#show figure.where(kind: "fig"): set figure.caption(position: bottom)
'''


def typst_table(rows):
    n = len(rows[0])
    w = [max(8, min(40, sum(len(r[c]) for r in rows) / len(rows))) for c in range(n)]
    cols = ", ".join(f"{x:.0f}fr" for x in w)
    cells = []
    for ri, r in enumerate(rows):
        for c in r:
            if ri == 0:
                cells.append(f"[*{tinline(c)}*]")
            else:
                cells.append(f"[{tinline(c)}]")
    return (
        f"#table(columns: ({cols}), inset: 5pt, align: left + horizon,\n"
        f"  stroke: 0.5pt + luma(160),\n"
        f"  fill: (_, y) => if y == 0 {{ rgb(\"#dce7f3\") }} else if calc.odd(y) {{ white }} else {{ luma(247) }},\n"
        f"  table.header({', '.join(cells[:n])}),\n  " + ", ".join(cells[n:]) + ")"
    )


def build_typst(d):
    L = d["labels"]
    o = [TYPST_HEAD]
    # title page (no numbering)
    o.append("#set page(numbering: none, footer: none)")
    o.append(f'''#align(center)[
  #v(1.2cm)
  #text(size: 12pt, tracking: 2pt, weight: "bold")[{COURSE.upper()}]\\
  #v(2pt)
  #text(size: 11pt)[Mini Project Report]
  #v(1.8cm)
  #text(size: 54pt, weight: "bold", fill: accent, tracking: 6pt)[{TITLE}]
  #v(4pt)
  #line(length: 40%, stroke: 1.2pt + accent)
  #v(6pt)
  #text(size: 18pt, weight: "bold")[{tesc(SUBTITLE)}]
  #v(4pt)
  #text(size: 12pt, style: "italic")[{tesc(TAGLINE)}]
  #v(1.8cm)
  #text(size: 12pt, weight: "bold")[Submitted by]
  #v(6pt)
  #table(columns: (7cm, 4.5cm), inset: 6pt, align: (left, left), stroke: (x, y) => (bottom: 0.4pt + luma(170)),
    table.header([*Student name*], [*Roll number*]),
    {", ".join(f"[{tesc(n)}], [{r}]" for n, r in TEAM)})
  #v(1.2cm)
  #text(size: 12pt)[Under the guidance of]\\
  #text(size: 13pt, weight: "bold")[{GUIDE}]
  #v(1.4cm)
  #text(size: 12pt, weight: "bold")[{DEPT}]\\
  #text(size: 12pt)[{INST}]\\
  #text(size: 11pt)[{YEAR} \\u{{2022}} {AY}]
]''')
    # front matter
    o.append('#set page(numbering: "i", footer: context align(center, text(size: 9pt)[#counter(page).display("i")]))')
    o.append("#counter(page).update(1)")
    o.append("#pagebreak()")
    o.append('#heading(numbering: none, outlined: false)[Acknowledgement and Declaration]')
    for p in ACK:
        o.append(tinline(p) + "\n")
    o.append("#heading(level: 2, numbering: none, outlined: false)[Third-party resources used]")
    for r in RESOURCES:
        o.append("- " + tinline(r))
    o.append("#pagebreak()")
    o.append('#heading(numbering: none, outlined: false)[Table of Contents]')
    o.append('#outline(title: none, depth: 2, indent: 1.2em)')
    o.append("#pagebreak()")
    o.append('#heading(numbering: none, outlined: false)[List of Figures]')
    o.append('#outline(title: none, target: figure.where(kind: "fig"))')
    o.append('#v(1.5em)')
    o.append('#heading(numbering: none, outlined: false)[List of Tables]')
    o.append('#outline(title: none, target: figure.where(kind: "tbl"))')
    o.append("#pagebreak()")
    o.append('#heading(numbering: none, outlined: true)[Abstract]')
    for p in d["abstract"]:
        o.append(tinline(p) + "\n")
    o.append(f"*Keywords:* {tinline(d['keywords'])}")
    # body
    o.append('#set page(numbering: "1", footer: context [#line(length: 100%, stroke: 0.4pt + luma(170)) #v(-4pt) #text(size: 9pt)[SAKSHI #h(1fr) #counter(page).display("1")]])')
    o.append('#counter(page).update(1)')
    first = True
    refs_done = False
    for kind, num, a, b in d["blocks"]:
        if kind == "h1":
            o.append("#heading(level: 1" + (", numbering: none" if num is None else "") + f")[{tinline(a)}]")
        elif kind == "h2":
            o.append("#heading(level: 2" + (", numbering: none" if num is None else "") + f")[{tinline(a)}]")
        elif kind == "p":
            o.append(tinline(resolve(a, L)) + "\n")
        elif kind == "li":
            o.append("- " + tinline(resolve(a, L)))
        elif kind == "eq":
            o.append(f'#align(center)[#box(inset: 6pt, stroke: 0.5pt + luma(160), radius: 2pt)[#text(style: "italic")[{tinline(a)}]]]')
        elif kind == "fig":
            cap, src = b
            o.append(
                f'#figure([#image("figs/{a}.svg", width: 94%)#v(2pt)#text(size: 8.5pt, style: "italic")[{tinline(src)}]], kind: "fig", supplement: none, numbering: none,\n'
                f'  caption: [*Figure {num}* {tinline(cap)}])'
            )
        elif kind == "table":
            o.append(
                f'#figure({typst_table(b)[1:]}, kind: "tbl", supplement: none, numbering: none,\n'
                f'  caption: [*Table {num}* {tinline(a)}])'
            )
    # references (inserted before appendix heading => handle by order)
    return o


def assemble_typst(d):
    parts = build_typst(d)
    # insert references before first unnumbered appendix h1
    idx = next(i for i, p in enumerate(parts) if p.startswith("#heading(level: 1, numbering: none)[Appendix"))
    refs = ["#heading(level: 1, numbering: none)[References]", '#set par(justify: false, hanging-indent: 1.6em, spacing: 0.7em)']
    for r in d["refs"]:
        refs.append(tinline(r) + "\n")
    refs.append("#set par(justify: true, hanging-indent: 0pt, spacing: 1.05em)")
    return "\n".join(parts[:idx] + refs + parts[idx:])


# ---------------------------------------------------------------- docx
def set_cell_bg(cell, color):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear"); shd.set(qn("w:color"), "auto"); shd.set(qn("w:fill"), color)
    tcPr.append(shd)


def set_repeat_header(row):
    trPr = row._tr.get_or_add_trPr()
    el = OxmlElement("w:tblHeader"); el.set(qn("w:val"), "true"); trPr.append(el)


def run_fmt(run, size=None, bold=None, italic=None, color=None, font=FONT):
    run.font.name = font
    run._element.rPr.rFonts.set(qn("w:eastAsia"), font)
    if size: run.font.size = Pt(size)
    if bold is not None: run.bold = bold
    if italic is not None: run.italic = italic
    if color: run.font.color.rgb = RGBColor.from_string(color)


def add_inline(p, text, size=None, bold=None, italic=None, color=None):
    for tok in re.split(r"(`[^`]+`)", text):
        if tok.startswith("`"):
            r = p.add_run(tok[1:-1]); run_fmt(r, size=(size or 11) - 1.5, font="DejaVu Sans Mono", bold=bold, italic=italic, color=color)
        elif tok:
            r = p.add_run(tok); run_fmt(r, size=size, bold=bold, italic=italic, color=color)


def add_field(p, instr, placeholder="", size=None):
    def fc(t):
        r = p.add_run(); run_fmt(r, size=size)
        e = OxmlElement("w:fldChar"); e.set(qn("w:fldCharType"), t); r._r.append(e); return r
    fc("begin")
    r = p.add_run(); run_fmt(r, size=size)
    it = OxmlElement("w:instrText"); it.set(qn("xml:space"), "preserve"); it.text = instr; r._r.append(it)
    fc("separate")
    r = p.add_run(placeholder); run_fmt(r, size=size)
    fc("end")


def add_bookmark_free_toc(doc, instr, placeholder):
    p = doc.add_paragraph()
    add_field(p, instr, placeholder)
    return p


def set_pgnum(section, fmt, start):
    sectPr = section._sectPr
    for e in sectPr.findall(qn("w:pgNumType")):
        sectPr.remove(e)
    e = OxmlElement("w:pgNumType"); e.set(qn("w:fmt"), fmt); e.set(qn("w:start"), str(start)); sectPr.append(e)


def footer_page(section, left_text=None):
    section.footer.is_linked_to_previous = False
    p = section.footer.paragraphs[0]
    for r in list(p.runs):
        r._r.getparent().remove(r._r)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    if left_text:
        r = p.add_run(left_text + "    |    "); run_fmt(r, size=9)
    add_field(p, "PAGE", "1", size=9)


def style_setup(doc):
    st = doc.styles
    n = st["Normal"]
    n.font.name = FONT; n.font.size = Pt(11)
    n.element.rPr.rFonts.set(qn("w:eastAsia"), FONT)
    pf = n.paragraph_format; pf.line_spacing = 1.15; pf.space_after = Pt(6)
    for name, size, before, after in (("Heading 1", 17, 18, 10), ("Heading 2", 13, 12, 6)):
        h = st[name]
        h.font.name = FONT; h.font.size = Pt(size); h.font.bold = True
        h.font.color.rgb = RGBColor.from_string("1F4E8C" if name == "Heading 1" else "1F2D3D")
        h.element.rPr.rFonts.set(qn("w:ascii"), FONT); h.element.rPr.rFonts.set(qn("w:hAnsi"), FONT)
        h.paragraph_format.space_before = Pt(before); h.paragraph_format.space_after = Pt(after)
        h.paragraph_format.keep_with_next = True
    h1 = st["Heading 1"]; h1.paragraph_format.page_break_before = True
    from docx.enum.style import WD_STYLE_TYPE
    for nm in ("FigCaption", "TabCaption"):
        s = st.add_style(nm, WD_STYLE_TYPE.PARAGRAPH)
        s.base_style = st["Normal"]; s.font.size = Pt(10); s.font.name = FONT
        s.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
        s.paragraph_format.space_after = Pt(8); s.paragraph_format.space_before = Pt(4)
        s.paragraph_format.keep_with_next = (nm == "TabCaption")
    for lv in (1, 2):
        t = st[f"TOC {lv}"] if f"TOC {lv}" in [x.name for x in st] else st.add_style(f"TOC {lv}", WD_STYLE_TYPE.PARAGRAPH)
        t.font.name = FONT; t.font.size = Pt(11); t.paragraph_format.left_indent = Cm(0.6 * (lv - 1)); t.paragraph_format.space_after = Pt(2)


def build_docx(d, out):
    L = d["labels"]
    doc = Document()
    style_setup(doc)
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Cm(21.0), Cm(29.7)
    for s in ("left_margin", "right_margin", "top_margin", "bottom_margin"):
        setattr(sec, s, Cm(2.5))
    ACC = "1F4E8C"

    def centered(text, size, bold=False, italic=False, color=None, before=0, after=6):
        p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_before = Pt(before); p.paragraph_format.space_after = Pt(after)
        r = p.add_run(text); run_fmt(r, size=size, bold=bold, italic=italic, color=color)
        return p

    # title page
    centered(COURSE.upper(), 12, bold=True, before=30, after=2)
    centered("Mini Project Report", 11, after=50)
    centered(TITLE, 54, bold=True, color=ACC, after=4)
    centered(SUBTITLE, 18, bold=True, before=6, after=4)
    centered(TAGLINE, 12, italic=True, after=40)
    centered("Submitted by", 12, bold=True, after=6)
    t = doc.add_table(rows=1, cols=2); t.alignment = WD_TABLE_ALIGNMENT.CENTER; t.style = "Table Grid"
    for c, txt in zip(t.rows[0].cells, ("Student name", "Roll number")):
        c.text = ""; r = c.paragraphs[0].add_run(txt); run_fmt(r, size=11, bold=True); set_cell_bg(c, "DCE7F3")
    for n, rno in TEAM:
        cells = t.add_row().cells
        for c, txt in zip(cells, (n, rno)):
            c.text = ""; r = c.paragraphs[0].add_run(txt); run_fmt(r, size=11)
    for row in t.rows:
        row.cells[0].width = Cm(7); row.cells[1].width = Cm(4.5)
    centered("Under the guidance of", 12, before=26, after=2)
    centered(GUIDE, 13, bold=True, after=26)
    centered(DEPT, 12, bold=True, after=2)
    centered(INST, 12, after=2)
    centered(f"{YEAR} • {AY}", 11)

    # front matter section
    fs = doc.add_section(WD_SECTION.NEW_PAGE)
    set_pgnum(fs, "lowerRoman", 1)
    footer_page(fs)

    def unnumbered_h1(text, outline=True, page_break=False):
        p = doc.add_paragraph(style="Heading 1" if outline else "Normal")
        if not outline:
            p.paragraph_format.keep_with_next = True
            p.paragraph_format.space_before = Pt(10)
            r = p.add_run(text); run_fmt(r, size=17, bold=True, color=ACC)
        else:
            r = p.add_run(text)
        if not page_break and outline:
            pass
        return p

    p = unnumbered_h1("Acknowledgement and Declaration", outline=False)
    p.paragraph_format.page_break_before = False
    for t_ in ACK:
        p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY; add_inline(p, t_)
    p = doc.add_paragraph(); add_inline(p, "Third-party resources used", size=13, bold=True)
    for r_ in RESOURCES:
        p = doc.add_paragraph(style="List Bullet"); add_inline(p, r_)

    p = unnumbered_h1("Table of Contents", outline=False)
    p.paragraph_format.page_break_before = True
    add_bookmark_free_toc(doc, 'TOC \\o "1-2" \\h \\z \\u', "Right-click and choose Update Field to build the table of contents.")

    p = unnumbered_h1("List of Figures", outline=False); p.paragraph_format.page_break_before = True
    add_bookmark_free_toc(doc, 'TOC \\h \\z \\t "FigCaption,1"', "Update field to list figures.")
    p = unnumbered_h1("List of Tables", outline=False); p.paragraph_format.space_before = Pt(20)
    add_bookmark_free_toc(doc, 'TOC \\h \\z \\t "TabCaption,1"', "Update field to list tables.")

    p = doc.add_paragraph(style="Heading 1"); p.add_run("Abstract")
    for t_ in d["abstract"]:
        p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY; add_inline(p, t_)
    p = doc.add_paragraph(); add_inline(p, "Keywords: ", bold=True); add_inline(p, d["keywords"])

    # body section
    bs = doc.add_section(WD_SECTION.NEW_PAGE)
    set_pgnum(bs, "decimal", 1)
    footer_page(bs, "SAKSHI")

    first_body = True
    refs_inserted = False

    def insert_refs():
        p = doc.add_paragraph(style="Heading 1"); p.add_run("References")
        for r_ in d["refs"]:
            q = doc.add_paragraph(); q.paragraph_format.left_indent = Cm(1.0); q.paragraph_format.first_line_indent = Cm(-1.0)
            q.paragraph_format.space_after = Pt(4); add_inline(q, r_, size=10.5)

    for kind, num, a, b in d["blocks"]:
        if kind == "h1":
            if num is None and not refs_inserted:
                insert_refs(); refs_inserted = True
            p = doc.add_paragraph(style="Heading 1")
            p.add_run(f"{num}  {a}" if num else a)
            if first_body:
                p.paragraph_format.page_break_before = False; first_body = False
        elif kind == "h2":
            p = doc.add_paragraph(style="Heading 2"); p.add_run(f"{num}  {a}" if num else a)
        elif kind == "p":
            p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY; add_inline(p, resolve(a, L))
        elif kind == "li":
            p = doc.add_paragraph(style="List Bullet"); p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY; add_inline(p, resolve(a, L))
        elif kind == "eq":
            t = doc.add_table(rows=1, cols=1); t.style = "Table Grid"; t.alignment = WD_TABLE_ALIGNMENT.CENTER
            c = t.rows[0].cells[0]; c.text = ""; pp = c.paragraphs[0]; pp.alignment = WD_ALIGN_PARAGRAPH.CENTER
            add_inline(pp, a, italic=True)
            doc.add_paragraph().paragraph_format.space_after = Pt(2)
        elif kind == "fig":
            cap, src = b
            p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER; p.paragraph_format.keep_with_next = True
            p.paragraph_format.space_before = Pt(6)
            from PIL import Image
            w, h = Image.open(FIGS / f"{a}.png").size
            width = min(15.0, w / 200 * 2.54 * 1.35)
            p.add_run().add_picture(str(FIGS / f"{a}.png"), width=Cm(width))
            q = doc.add_paragraph(style="FigCaption"); add_inline(q, f"Figure {num}", bold=True, size=10); add_inline(q, " " + cap, size=10)
            q2 = doc.add_paragraph(); q2.alignment = WD_ALIGN_PARAGRAPH.CENTER; add_inline(q2, src, size=8.5, italic=True)
        elif kind == "table":
            q = doc.add_paragraph(style="TabCaption"); add_inline(q, f"Table {num}", bold=True, size=10); add_inline(q, " " + a, size=10)
            rows = b; ncol = len(rows[0])
            t = doc.add_table(rows=len(rows), cols=ncol); t.style = "Table Grid"; t.alignment = WD_TABLE_ALIGNMENT.CENTER
            wts = [max(8, min(40, sum(len(r[c]) for r in rows) / len(rows))) for c in range(ncol)]
            tot = sum(wts)
            for ri, r in enumerate(rows):
                for ci, txt in enumerate(r):
                    c = t.rows[ri].cells[ci]; c.width = Cm(16.0 * wts[ci] / tot); c.text = ""
                    pp = c.paragraphs[0]; pp.paragraph_format.space_after = Pt(1); pp.paragraph_format.line_spacing = 1.0
                    add_inline(pp, txt, size=9.5, bold=(ri == 0))
                    if ri == 0: set_cell_bg(c, "DCE7F3")
                    elif ri % 2 == 0: set_cell_bg(c, "F7F7F7")
            set_repeat_header(t.rows[0])
            doc.add_paragraph().paragraph_format.space_after = Pt(2)
    if not refs_inserted:
        insert_refs()
    doc.core_properties.title = "SAKSHI: Multi-Camera Vehicle Analytics and Evidence Review"
    doc.core_properties.author = "SAKSHI project team"
    # ask Word to refresh TOC / lists on open
    s = doc.settings.element
    u = OxmlElement("w:updateFields"); u.set(qn("w:val"), "true"); s.append(u)
    doc.save(out)


if __name__ == "__main__":
    d = parse(ROOT / "report.md")
    (ROOT / "report.typ").write_text(assemble_typst(d))
    subprocess.run(["typst", "compile", "report.typ", "SAKSHI_Project_Report.pdf"], cwd=ROOT, check=True)
    build_docx(d, ROOT / "SAKSHI_Project_Report.docx")
    print("ok")
