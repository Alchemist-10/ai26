#!/usr/bin/env python3
"""Build SAKSHI_Presentation.pptx. Run: uv run --with python-pptx --with pillow deck.py"""
from pathlib import Path
from PIL import Image
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.util import Inches, Pt

F = Path(__file__).parent / "figs"
INK, ACC, MUTED = RGBColor(0x1F, 0x2D, 0x3D), RGBColor(0x1F, 0x4E, 0x8C), RGBColor(0x5A, 0x67, 0x75)
FONT = "Calibri"
prs = Presentation(); prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
blank = prs.slide_layouts[6]
TEAM = "A S Sri Dathan (2024BCS0091)  |  Akshay V.S (2024BCD0015)  |  Bharadwaj B Chand (2024BCS0059)  |  Shivansh Neekhra (2024BCS0023)  |  Srimoneyshankar Ajith (2024BCS0055)"


def text(sl, x, y, w, h, s, size=18, bold=False, color=INK, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, italic=False):
    tb = sl.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h)); tf = tb.text_frame; tf.word_wrap = True
    tf.vertical_anchor = anchor
    for i, line in enumerate(s.split("\n")):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align; r = p.add_run(); r.text = line
        r.font.size = Pt(size); r.font.bold = bold; r.font.italic = italic; r.font.color.rgb = color; r.font.name = FONT
    return tb


def bullets(sl, x, y, w, h, items, size=18, gap=8):
    tb = sl.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h)); tf = tb.text_frame; tf.word_wrap = True
    for i, it in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.space_after = Pt(gap); r = p.add_run(); r.text = "•  " + it
        r.font.size = Pt(size); r.font.color.rgb = INK; r.font.name = FONT


def card(sl, x, y, w, h, big, small, fill=RGBColor(0xEE,0xF3,0xF9), bigsize=34):
    b = sl.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h)); b.fill.solid(); b.fill.fore_color.rgb = fill; b.line.color.rgb = ACC; b.line.width = Pt(1)
    text(sl, x, y + 0.1, w, h * 0.55, big, size=bigsize, bold=True, color=ACC, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
    text(sl, x + 0.1, y + h * 0.55, w - 0.2, h * 0.45, small, size=13, color=MUTED, align=PP_ALIGN.CENTER)


def notes(sl, s):
    sl.notes_slide.notes_text_frame.text = s


def flow(sl, y, labels, fills):
    n = len(labels); w = 2.6; gap = (11.9 - n * w) / (n - 1)
    for i, (l, f) in enumerate(zip(labels, fills)):
        x = 0.7 + i * (w + gap)
        b = sl.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(1.2)); b.fill.solid(); b.fill.fore_color.rgb = f; b.line.color.rgb = ACC
        text(sl, x, y, w, 1.2, l, size=16, bold=True, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
        if i < n - 1:
            a = sl.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW, Inches(x + w + 0.08), Inches(y + 0.4), Inches(gap - 0.16), Inches(0.4)); a.fill.solid(); a.fill.fore_color.rgb = ACC; a.line.fill.background()


def slide(title, n):
    sl = prs.slides.add_slide(blank)
    bar = sl.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, Inches(0.25), prs.slide_height); bar.fill.solid(); bar.fill.fore_color.rgb = ACC; bar.line.fill.background()
    text(sl, 0.7, 0.35, 12, 0.8, title, size=30, bold=True, color=ACC)
    ln = sl.shapes.add_connector(1, Inches(0.7), Inches(1.15), Inches(12.6), Inches(1.15)); ln.line.color.rgb = ACC; ln.line.width = Pt(1.2)
    text(sl, 0.7, 7.05, 8, 0.3, "SAKSHI  |  CSE311 Artificial Intelligence  |  IIIT Kottayam", size=10, color=MUTED)
    text(sl, 12.0, 7.05, 0.8, 0.3, str(n), size=10, color=MUTED, align=PP_ALIGN.RIGHT)
    return sl


def pic(sl, name, x, y, maxw, maxh):
    w, h = Image.open(F / f"{name}.png").size
    s = min(maxw / w, maxh / h)
    sl.shapes.add_picture(str(F / f"{name}.png"), Inches(x + (maxw - w * s) / 2), Inches(y), Inches(w * s), Inches(h * s))


def table(sl, x, y, w, rows, colw, size=13):
    t = sl.shapes.add_table(len(rows), len(rows[0]), Inches(x), Inches(y), Inches(w), Inches(0.4 * len(rows))).table
    for c, cw in enumerate(colw): t.columns[c].width = Inches(cw)
    for r, row in enumerate(rows):
        for c, v in enumerate(row):
            cell = t.cell(r, c); cell.text = ""; p = cell.text_frame.paragraphs[0]; run = p.add_run(); run.text = v
            run.font.size = Pt(size); run.font.name = FONT; run.font.bold = (r == 0)
            run.font.color.rgb = INK
            cell.fill.solid(); cell.fill.fore_color.rgb = RGBColor(0xDC, 0xE7, 0xF3) if r == 0 else (RGBColor(0xFF, 0xFF, 0xFF) if r % 2 else RGBColor(0xF4, 0xF6, 0xF8))



BL, GR, OR = RGBColor(0xDC,0xE7,0xF3), RGBColor(0xE1,0xF0,0xDC), RGBColor(0xFB,0xE6,0xD8)
# 1 title
sl = prs.slides.add_slide(blank)
bg = sl.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, prs.slide_width, Inches(0.35)); bg.fill.solid(); bg.fill.fore_color.rgb = ACC; bg.line.fill.background()
text(sl, 0.8, 0.9, 11.7, 0.5, "CSE311 ARTIFICIAL INTELLIGENCE  |  MINI PROJECT", size=16, bold=True, color=MUTED)
text(sl, 0.8, 1.5, 11.7, 1.5, "SAKSHI", size=88, bold=True, color=ACC)
text(sl, 0.8, 3.1, 11.7, 0.8, "Multi-Camera Vehicle Analytics and Evidence Review", size=32, bold=True)
text(sl, 0.8, 3.9, 11.7, 0.6, "Vehicle detection, licence-plate review and auditable observations", size=18, italic=True, color=MUTED)
pic(sl, "architecture", 8.6, 4.3, 4.4, 2.6)
text(sl, 0.8, 4.9, 7.6, 1.0, "A S Sri Dathan (2024BCS0091)\nAkshay V.S (2024BCD0015)\nBharadwaj B Chand (2024BCS0059)\nShivansh Neekhra (2024BCS0023)\nSrimoneyshankar Ajith (2024BCS0055)", size=13)
text(sl, 0.8, 6.55, 11.7, 0.6, "Guide: Dr. Sreeja M U  |  Department of CSE, IIIT Kottayam  |  Third Year  |  2026\u20132027", size=13, color=MUTED)
notes(sl, "SAKSHI turns multi-camera traffic video into reviewable, auditable vehicle and plate observations. Pretrained models do the perception; our contribution is the pipeline that keeps uncertainty visible.")

# 2 problem
sl = slide("The Problem: Too Much Video, Too Little Trust", 2)
flow(sl, 1.5, ["Hours of CCTV from many cameras", "Candidate vehicles and plate reads", "Reviewed, auditable evidence"], [BL, GR, OR])
card(sl, 0.7, 3.2, 3.8, 1.7, "OCR can be wrong", "Small, blurred plates get misread", bigsize=22)
card(sl, 4.75, 3.2, 3.8, 1.7, "Replay \u2260 capture time", "A file timestamp is not when it happened", bigsize=20)
card(sl, 8.8, 3.2, 3.8, 1.7, "Wrong ID is costly", "So uncertain reads must abstain", bigsize=22)
text(sl, 0.7, 5.3, 11.9, 1.5, "Example: a reviewer asks which cameras saw a blue truck last night. SAKSHI returns a short list of candidate frames with raw evidence and an uncertainty label, instead of a confident but unsupported plate.", size=18, color=INK)
notes(sl, "Problem: reviewing video by hand does not scale, and a naive ALPR demo can implicate the wrong vehicle. We use AI for detection and OCR because fixed rules fail on varied scenes, and we wrap it in review controls.")

# 3 objectives
sl = slide("Objectives", 3)
obj = [("Shared sampling", "One processor, global 2 FPS budget"), ("Detect vehicles", "Pretrained YOLOv8n; people for masking"), ("Read plates", "Detector + OCR; keep raw and ambiguous reads"),
       ("Track per camera", "Motion + box cost, ambiguity abstention"), ("Persist evidence", "SQLite, model hashes, audit chain"), ("Review dashboard", "Queries, rules, signed reports")]
for i, (a, b) in enumerate(obj):
    card(sl, 0.7 + (i % 3) * 4.05, 1.5 + (i // 3) * 2.6, 3.8, 2.3, a, b, bigsize=24)
text(sl, 0.7, 6.55, 12, 0.4, "Plus: reproducible evaluation tools that state what is and is not measured.", size=15, italic=True, color=MUTED)
notes(sl, "Six objectives map to the six pipeline stages. The last line matters: we say clearly what we did not measure.")

# 4 literature
sl = slide("Existing Work and Literature", 4)
table(sl, 0.7, 1.5, 11.9, [
    ["Work", "Idea", "Role in SAKSHI"],
    ["YOLO [Redmon 2016], YOLOv8", "Single-stage real-time detection", "Pretrained vehicle and person detector"],
    ["SORT / DeepSORT", "Motion + Hungarian assignment; learned appearance", "Inspires global-assignment tracker; no appearance model"],
    ["YOLO-based ALPR [Laroca 2018]", "Detect plate, then read characters", "Two-stage plate detector + OCR structure"],
    ["MobileViT / v2 [Mehta 2022]", "Convolution + separable self-attention for mobile", "Backbone of the plate OCR model"],
    ["Integer quantisation [Jacob 2018]", "Lower precision for speed and size", "INT8 detector comparison"],
], [3.6, 4.2, 4.1], size=15)
text(sl, 0.7, 5.3, 11.9, 1.2, "Gap addressed: an integrated review workflow around uncertain predictions (provenance, audit, abstention), not a new detector.", size=18, italic=True, color=ACC)
notes(sl, "We combine established methods. Five or more works inform detection, tracking, plate OCR, efficient inference and evaluation. The report covers all of them in section 3.")

# 5 architecture
sl = slide("Proposed System: Architecture", 5)
pic(sl, "architecture", 0.7, 1.3, 8.4, 5.6)
card(sl, 9.4, 1.5, 3.4, 1.4, "1 processor", "Viewers read cached output; no extra workers", bigsize=26)
card(sl, 9.4, 3.1, 3.4, 1.4, "MP4 / RTSP", "Input sources, 9 cameras in the demo", bigsize=26)
card(sl, 9.4, 4.7, 3.4, 1.4, "Signed reports", "SHA-256 hashes, optional Ed25519", bigsize=26)
notes(sl, "Walk the figure left to right: sources, scheduler, detector, plate branch, tracker and gate, database, then rules, journeys, reports and queries behind one API and dashboard.")

# 6 dataset
sl = slide("Dataset and Input", 6)
card(sl, 0.7, 1.5, 2.8, 1.8, "9", "cameras: 6 bundled, 3 managed originals")
card(sl, 3.7, 1.5, 2.8, 1.8, "45", "prediction-blind review frames")
card(sl, 6.7, 1.5, 2.8, 1.8, "21", "plate crops reviewed by a person")
card(sl, 9.7, 1.5, 2.8, 1.8, "0", "labelled held-out samples")
bullets(sl, 0.7, 3.8, 12, 3.0, [
    "CAM-01 to CAM-06: bundled clips for replay and detector calibration. CAM-07 to CAM-09: higher-resolution originals for plate review.",
    "Models are pretrained, so no training set was collected; there is no labelled test set, so no accuracy is claimed.",
    "Privacy mode pixelates people and plates before output is shared.",
], size=17)
notes(sl, "Be explicit that the data supports runtime measurement and a small review, not an accuracy claim. Input sources: MP4 or RTSP. Output: observations, alerts, signed reports.")

# 7 OCR model
sl = slide("AI Technique: Transformer-Style Plate OCR", 7)
pic(sl, "mobilevit", 0.7, 1.3, 12, 3.3)
bullets(sl, 0.7, 4.9, 12, 2.0, [
    "MobileViT-v2 mixes convolution (local detail) with separable self-attention (global layout) at linear cost, so it runs on CPU.",
    "Plate detector: YOLOv9-tiny at 384 \u00d7 384; OCR model: global-plates-mobile-vit-v2; both via ONNX Runtime.",
], size=17)
notes(sl, "Why this model: small, CPU-capable, available pretrained. Separable self-attention avoids quadratic cost over patches. We did not train it; its accuracy on Indian plates is unmeasured.")

# 8 plate gates
sl = slide("Plate Reading: Abstain Unless Evidence Agrees", 8)
pic(sl, "plate_path", 0.7, 1.3, 12, 3.6)
card(sl, 0.7, 5.2, 3.8, 1.5, "\u2265 0.35", "OCR confidence threshold", bigsize=28)
card(sl, 4.75, 5.2, 3.8, 1.5, "3 of last 8", "reads must agree on one string", bigsize=28)
card(sl, 8.8, 5.2, 3.8, 1.5, "Else: raw only", "kept for review, never an identity", bigsize=28)
notes(sl, "This is the core safety idea. A wrong plate is worse than no plate, so a plate becomes queryable only after passing confidence, format, track and consensus checks.")

# 9 tracking
sl = slide("Camera-Local Tracking", 9)
text(sl, 0.7, 1.4, 12, 0.5, "Association cost between a track and a detection", size=20, bold=True)
for i, (w, lab, col) in enumerate([(0.75, "distance 0.75", ACC), (0.20, "1 \u2212 IoU 0.20", RGBColor(0x4F,0x9A,0x6B)), (0.05, "area change 0.05", RGBColor(0xD9,0x82,0x2B))]):
    y = 2.1 + i * 0.9
    b = sl.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.7), Inches(y), Inches(10 * w), Inches(0.6)); b.fill.solid(); b.fill.fore_color.rgb = col; b.line.fill.background()
    text(sl, 0.8 + 10 * w, y, 3, 0.6, lab, size=16, anchor=MSO_ANCHOR.MIDDLE)
bullets(sl, 0.7, 5.0, 12, 1.9, [
    "Minimum-cost assignment per frame; near-equal competing matches are marked ambiguous and those tracks are retired.",
    "Track IDs are local to one camera: no appearance model, so no cross-camera identity is claimed.",
], size=17)
notes(sl, "Weights are from backend/tracking.py. Costs are heuristic scores, not probabilities.")

# 10 results replay
sl = slide("Results: Nine-Camera Replay", 10)
pic(sl, "charts", 0.7, 1.3, 8.0, 4.6)
card(sl, 9.0, 1.4, 3.7, 1.4, "1.17 FPS", "349 frames in 298 s (target 2.0)", bigsize=28)
card(sl, 9.0, 3.0, 3.7, 1.4, "0 failures", "no failed inference attempts", bigsize=28)
card(sl, 9.0, 4.6, 3.7, 1.4, "830 MiB", "median memory; 163% median CPU", bigsize=28)
text(sl, 0.7, 6.1, 12, 0.8, "Almost every 500 ms overrun comes from CAM-07 to CAM-09: full-resolution plate inference is the bottleneck.", size=17, italic=True, color=MUTED)
notes(sl, "Stable, no failures, but below the 2 FPS budget on a single 12-thread laptop CPU. These are execution measurements, not accuracy.")

# 11 latency
sl = slide("Results: INT8 Quantisation Speed-Up", 11)
pic(sl, "latency", 0.7, 1.4, 7.0, 4.6)
card(sl, 8.2, 1.5, 4.5, 1.5, "55.8 vs 92.8 ms", "INT8 ONNX vs PyTorch FP32 median", bigsize=26)
card(sl, 8.2, 3.2, 4.5, 1.5, "3.6 MB", "INT8 model vs 12.8 MB FP32 ONNX", bigsize=28)
card(sl, 8.2, 4.8, 4.5, 1.3, "15 of 16", "detections matched FP32 (unlabelled)", bigsize=28)
text(sl, 0.7, 6.45, 12, 0.5, "Detector-only, 10 runs after 2 warm-ups. Agreement with FP32 is not accuracy. INT8 is not yet in live inference.", size=15, italic=True, color=MUTED)
notes(sl, "About 41 percent faster than FP32 ONNX. Quantisation is a promising speed lever pending held-out validation.")

# 12 crops
sl = slide("Results: Plate Gates on Real Crops", 12)
pic(sl, "crops", 0.7, 1.4, 7.4, 4.2)
bullets(sl, 8.4, 1.6, 4.4, 4.5, [
    "21 selected crops: 16 unreadable, 4 readable, 1 uncertain.",
    "All 4 readable crops were misread, and all 4 were rejected by the gates.",
    "None became a supported plate identity.",
    "Offline probe: 68 crop variants, 1 exact match, 5 passed gates.",
], size=16)
text(sl, 0.7, 6.1, 12, 0.7, "Selected sample, not representative: shows abstention behaviour, not OCR accuracy.", size=16, italic=True, color=MUTED)
notes(sl, "The honest takeaway: the system declined to name a plate rather than name a wrong one. We do not claim an accuracy or false-accept rate.")

# 13 projection
sl = slide("Projection: Scaling the Architecture (Estimate)", 13)
pic(sl, "projection", 0.7, 1.4, 5.6, 4.2)
pic(sl, "deployment", 6.5, 1.5, 6.4, 3.6)
bullets(sl, 0.7, 5.8, 12, 1.2, [
    "Not tested: full hardware and budget were unavailable. B is derived from measured INT8 latency; C assumes linear scaling by camera; D assumes 10\u00d7 (illustrative).",
], size=15)
notes(sl, "Proof of concept framing: decode, inference and storage are separate, so they can be scaled independently. All projected numbers are labelled estimates.")

# 14 conclusion
sl = slide("Conclusion and Future Scope", 14)
text(sl, 0.7, 1.4, 5.8, 0.5, "What we built", size=22, bold=True)
bullets(sl, 0.7, 1.95, 5.8, 4.8, [
    "End-to-end AI pipeline: detect, read, track, store, review.",
    "Zero failures over a nine-camera replay.",
    "Uncertainty controls that abstain instead of guessing.",
    "Honest scope: runtime measured, accuracy not claimed.",
], size=17)
text(sl, 6.9, 1.4, 5.8, 0.5, "Next", size=22, bold=True)
bullets(sl, 6.9, 1.95, 5.8, 4.8, [
    "Authorised labelled dataset and held-out evaluation.",
    "Fine-tune OCR on regional plates.",
    "GPU and edge profiling; INT8 in live inference.",
    "Verified clocks and locations for cross-camera journeys.",
    "Privacy, legal and security review.",
], size=17)
notes(sl, "Limitations: no held-out labels, single host, replay timestamps. Questions to expect are in Appendix A of the report.")

# 15 references
sl = slide("References and Demo", 15)
bullets(sl, 0.7, 1.4, 12, 4.2, [
    "J. Redmon et al., You Only Look Once, CVPR 2016.",
    "A. Bewley et al., SORT, ICIP 2016; N. Wojke et al., DeepSORT, ICIP 2017.",
    "R. Laroca et al., Robust Real-Time ALPR Based on YOLO, IJCNN 2018.",
    "S. Mehta, M. Rastegari, MobileViT, ICLR 2022; Separable Self-Attention, TMLR 2023.",
    "B. Jacob et al., Integer-Arithmetic-Only Inference, CVPR 2018.",
    "Ultralytics YOLOv8, Fast-ALPR, FastPlateOCR, Open Image Models documentation.",
], size=16, gap=6)
text(sl, 0.7, 5.7, 12, 0.8, "Demo: uv run run.py, then open http://localhost:5174", size=20, bold=True, color=ACC)
notes(sl, "Full reference list is in the report.")
prs.save(Path(__file__).parent / "SAKSHI_Presentation.pptx")
print("ok")
