"""Sakshi explainer clips (Manim CE). Numbers come from backend/ code, not invented.

Render: ./render.sh  (see that file). Scenes import the stdlib-only backend modules
(tracking.py, fusion.py, plate_format.py) so costs, statuses and repairs are computed
by the real algorithms.
"""
import sys
from pathlib import Path

from manim import *

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
from fusion import PlateConsensus  # noqa: E402
from plate_format import normalize_plate  # noqa: E402
from tracking import CentroidTracker, _Track, _assignment, _center  # noqa: E402

PLATE_MIN_CONF = 0.35  # backend/inference.py (module imports torch, so mirrored here)
TOTAL_FPS = 2.0  # backend/processing.py AI26_TOTAL_INFERENCE_FPS default

BG, TEAL, TEXT, MUTED = "#080d12", "#38d1c2", "#e7eef0", "#7f95a0"
DANGER, WARN, OK = "#f2706a", "#f0b75a", "#6ee7a8"
PANEL, LINE = "#0e171f", "#1f2c36"
SANS, MONO = "Noto Sans", "JetBrains Mono"

config.background_color = BG


def txt(s, size=30, color=TEXT, mono=False, weight=NORMAL, **kw):
    # z_index 1: text stays above filled boxes even when a box is animated (re-added) later
    return Text(s, font=MONO if mono else SANS, font_size=size, color=color, weight=weight, **kw).set_z_index(1)


def eyebrow(s):
    return txt(s, 24, TEAL, weight=BOLD).to_corner(UL, buff=0.55)


def outro(scene, hold=1.4):
    scene.wait(hold)
    scene.play(*[FadeOut(m) for m in scene.mobjects], run_time=0.8)
    scene.wait(0.3)


# ---------------------------------------------------------------- 1. pipeline
class Pipeline(Scene):
    def construct(self):
        stages = [  # (title, subtitle, is_pretrained_model)
            ("Sources", "city cameras\nRTSP / MP4", False),
            ("Scheduler", "2 FPS total budget", False),
            ("YOLOv8n", "640×640 · vehicles", True),
            ("Tracker", "camera-local IDs", False),
            ("Plate + OCR", "YOLOv9-tiny\nMobileViT-v2", True),
            ("Consensus", "3 agreeing reads", False),
            ("SQLite", "observations, audit,\nprovenance", False),
            ("Dashboard", "reads cached output", False),
        ]
        w, h, gap = 2.75, 1.6, 0.55
        xs = [(-1.5 + i) * (w + gap) for i in range(4)]
        pos = [np.array([x, 1.3, 0]) for x in xs] + [np.array([x, -1.35, 0]) for x in reversed(xs)]
        cards = []
        for (title, sub, model), p in zip(stages, pos):
            col = WARN if model else TEAL
            box = RoundedRectangle(corner_radius=0.18, width=w, height=h, stroke_color=col,
                                   stroke_width=2.5, stroke_opacity=0.55, fill_color=PANEL, fill_opacity=1)
            t = txt(title, 30, TEXT, weight=BOLD)
            s = VGroup(*[txt(line, 20, MUTED) for line in sub.split("\n")]).arrange(DOWN, buff=0.06)
            body = VGroup(t, s).arrange(DOWN, buff=0.14)
            if body.width > w - 0.3:
                body.scale_to_fit_width(w - 0.3)
            cards.append(VGroup(box.move_to(p), body.move_to(p)))

        def link(a, b):
            ba, bb = cards[a][0], cards[b][0]
            if abs(ba.get_y() - bb.get_y()) > 0.1:
                return Arrow(ba.get_bottom(), bb.get_top(), buff=0.08, stroke_width=3, color=MUTED,
                             max_tip_length_to_length_ratio=0.25)
            d = RIGHT if bb.get_x() > ba.get_x() else LEFT
            return Arrow(ba.get_edge_center(d), bb.get_edge_center(-d), buff=0.06, stroke_width=3,
                         color=MUTED, max_tip_length_to_length_ratio=0.3)

        arrows = [link(i, i + 1) for i in range(7)]
        legend = VGroup(
            VGroup(RoundedRectangle(corner_radius=0.06, width=0.42, height=0.28, stroke_color=WARN, stroke_width=2.5,
                                    fill_color=WARN, fill_opacity=0.15), txt("pretrained model", 24, TEXT)).arrange(RIGHT, buff=0.18),
            VGroup(RoundedRectangle(corner_radius=0.06, width=0.42, height=0.28, stroke_color=TEAL, stroke_width=2.5,
                                    fill_color=TEAL, fill_opacity=0.15), txt("deterministic code", 24, TEXT)).arrange(RIGHT, buff=0.18),
        ).arrange(RIGHT, buff=0.6).move_to([0, -3.5, 0])
        head = eyebrow("ONE SAMPLED FRAME, END TO END")

        self.play(FadeIn(head, shift=DOWN * 0.2), FadeIn(legend, shift=DOWN * 0.2), run_time=0.6)
        self.play(LaggedStart(*[FadeIn(c, scale=0.94) for c in cards], lag_ratio=0.1, run_time=1.6),
                  LaggedStart(*[GrowArrow(a) for a in arrows], lag_ratio=0.1, run_time=1.6))

        # the frame token: a small thumbnail that gains detection boxes, then a plate chip
        token = VGroup(RoundedRectangle(corner_radius=0.06, width=0.86, height=0.52, stroke_color=TEXT,
                                        stroke_width=2.5, fill_color=BG, fill_opacity=1))
        lift = UP * 0.42
        token.move_to(cards[0][0].get_top() + lift)

        def lit(i):
            model = stages[i][2]
            col = WARN if model else TEAL
            box = cards[i][0]
            return AnimationGroup(box.animate.set_stroke(col, width=4, opacity=1).set_fill(col, opacity=0.12),
                                  cards[i][1][0].animate.set_color(col if model else TEXT))

        chip = txt("KA01AB1234", 22, WARN, mono=True, weight=BOLD)
        self.play(FadeIn(token, shift=DOWN * 0.2), lit(0), run_time=0.5)
        for i in range(1, 8):
            target = cards[i][0].get_top() + lift if i < 4 else cards[i][0].get_bottom() - lift
            if i == 4:  # row change: drop down the right side, ride under the bottom row
                target = target + LEFT * (chip.width + 0.08) / 2  # leave room so tag + chip stay centred
                path = VMobject().set_points_as_corners([token.get_center(), token.get_center() + RIGHT * 1.75,
                                                         target + RIGHT * 1.75, target])
                move = MoveAlongPath(token, path, rate_func=smooth)
            else:
                move = token.animate.move_to(target)
            self.play(move, run_time=0.55)
            extra = []
            if i == 2:  # detector adds vehicle boxes
                bx = VGroup(Rectangle(width=0.26, height=0.18, stroke_color=WARN, stroke_width=2.5),
                            Rectangle(width=0.2, height=0.14, stroke_color=WARN, stroke_width=2.5)).arrange(RIGHT, buff=0.1)
                extra.append(FadeIn(bx.move_to(token), scale=1.6))
                token.add(bx)
            if i == 3:
                tag = txt("#12", 22, TEAL, mono=True, weight=BOLD).next_to(token, LEFT, buff=0.08)
                extra.append(FadeIn(tag))
                token.add(tag)
            if i == 4:
                chip.next_to(token, RIGHT, buff=0.08)
                extra.append(FadeIn(chip))
                token.add(chip)
            if i == 5:
                extra.append(token[-1].animate.set_color(OK))
            self.play(lit(i), *extra, run_time=0.45)
        outro(self, 1.6)


# ---------------------------------------------------------------- 2. consensus
class Consensus(Scene):
    def construct(self):
        head = eyebrow("PLATE CONSENSUS · PER CAMERA, PER TRACK")
        cell_w = 0.62

        def plate_cells(s, color=TEXT):
            g = VGroup()
            for ch in s:
                box = RoundedRectangle(corner_radius=0.06, width=cell_w - 0.06, height=0.82, stroke_color=LINE,
                                       stroke_width=2, fill_color=PANEL, fill_opacity=1)
                g.add(VGroup(box, txt(ch, 40, color, mono=True, weight=BOLD).move_to(box)))
            return g.arrange(RIGHT, buff=0.06)

        # left column: OCR read + gates
        read_anchor = np.array([-3.3, 1.55, 0])
        read_label = txt("OCR read", 24, MUTED).move_to(read_anchor + UP * 1.2).align_to(read_anchor + LEFT * 3.1, LEFT)
        gate_specs = [f"confidence ≥ {PLATE_MIN_CONF:.2f}", "format valid", "track not ambiguous"]
        gates = VGroup(*[
            VGroup(RoundedRectangle(corner_radius=0.22, width=3.9, height=0.56, stroke_color=LINE, stroke_width=2,
                                    fill_color=PANEL, fill_opacity=1),
                   txt(g, 24, TEXT)) for g in gate_specs]).arrange(DOWN, buff=0.16)
        for g in gates:
            g[1].move_to(g[0]).align_to(g[0], LEFT).shift(RIGHT * 0.5)
        gates.move_to([-4.15, -1.2, 0])
        gate_label = txt("gates", 24, MUTED).next_to(gates, UP, buff=0.18).align_to(gates, LEFT)
        excluded = VGroup(
            RoundedRectangle(corner_radius=0.14, width=2.9, height=1.95, stroke_color=LINE, stroke_width=2),
            txt("history only", 22, MUTED).shift(UP * 0.62),
            txt("not queryable", 18, MUTED).shift(UP * 0.32),
        ).move_to([-0.3, -1.38, 0])

        # right column: window of last 8 reads
        slots = VGroup(*[RoundedRectangle(corner_radius=0.08, width=4.7, height=0.5, stroke_color=LINE, stroke_width=1.5,
                                          fill_color=PANEL, fill_opacity=1) for _ in range(8)]).arrange(DOWN, buff=0.08)
        slots.move_to([4.15, -0.55, 0])
        win_label = txt("window · last 8 reads", 24, MUTED).next_to(slots, UP, buff=0.18).align_to(slots, LEFT)
        status_box = RoundedRectangle(corner_radius=0.2, width=4.7, height=0.95, stroke_color=LINE, stroke_width=2,
                                      fill_color=PANEL, fill_opacity=1).next_to(win_label, UP, buff=0.25).align_to(slots, LEFT)
        status = txt("no reads yet", 26, MUTED).move_to(status_box)

        self.play(FadeIn(head, shift=DOWN * 0.2), FadeIn(read_label), FadeIn(gate_label), FadeIn(gates),
                  FadeIn(win_label), FadeIn(slots), FadeIn(status_box), FadeIn(status), FadeIn(excluded), run_time=0.8)

        consensus = PlateConsensus()  # real backend/fusion.py defaults: minimum_reads=3, window=8
        filled = 0
        marks = VGroup()

        def set_status(new_text, color, sub=None):
            nonlocal status
            g = VGroup(txt(new_text, 28, color, weight=BOLD))
            if sub:
                g.add(txt(sub, 20, MUTED))
            g.arrange(DOWN, buff=0.06)
            if g.width > status_box.width - 0.3:
                g.scale_to_fit_width(status_box.width - 0.3)
            g.move_to(status_box)
            anims = [ReplacementTransform(status, g), status_box.animate.set_stroke(color, opacity=1)]
            status = g
            return anims

        def clear(group):  # fade each member: members were added to the scene one by one
            anims = [FadeOut(m) for m in group]
            group.remove(*group)
            return anims

        def run_read(raw, conf, fast=False, show_tags=False, status_fn=None):
            nonlocal filled
            norm = normalize_plate(raw)
            canon = str(norm["plate_norm"])
            cells = plate_cells(raw).move_to(read_anchor)
            extra = VGroup(txt(f"conf {conf:.2f}", 24, MUTED, mono=True).next_to(cells, DOWN, buff=0.2).align_to(cells, RIGHT))
            self.play(FadeIn(cells, shift=RIGHT * 0.4), FadeIn(extra[0]), run_time=0.35 if fast else 0.5)
            if show_tags:  # Indian syntax: state LL, district DD, series L..LLL, number D..DDDD
                tags = VGroup()
                for i0, i1, name in [(0, 2, "state"), (2, 4, "district"), (4, 6, "series"), (6, 10, "number")]:
                    seg = cells[i0:i1]
                    br = Line(seg.get_corner(UL) + UP * 0.12 + RIGHT * 0.04, seg.get_corner(UR) + UP * 0.12 + LEFT * 0.04,
                              stroke_color=MUTED, stroke_width=2)
                    tags.add(br, txt(name, 18, MUTED).next_to(br, UP, buff=0.06))
                extra.add(*tags)
                self.play(*[FadeIn(m) for m in tags], run_time=0.4)
            changed = [i for i, (x, y) in enumerate(zip(raw, canon)) if x != y]
            if changed:
                log = txt(f"repair logged  {raw} → {canon}", 20, MUTED, mono=True).next_to(cells, DOWN, buff=0.2).align_to(cells, LEFT)
                if not fast:
                    self.play(*[cells[i][0].animate.set_stroke(WARN, width=3) for i in changed],
                              *[cells[i][1].animate.set_color(WARN) for i in changed], run_time=0.35)
                self.play(*[Transform(cells[i][1], txt(canon[i], 40, OK, mono=True, weight=BOLD).move_to(cells[i][0]))
                            for i in changed], *[cells[i][0].animate.set_stroke(OK, width=3) for i in changed],
                          FadeOut(extra[0]), FadeIn(log, shift=UP * 0.1), run_time=0.5 if fast else 0.6)
                extra.remove(extra[0])
                extra.add(log)
            # gates (same checks and order as inference.py)
            results = [conf >= PLATE_MIN_CONF, bool(norm["format_valid"]), True]
            gate_anims, ok_all = [], True
            for g, passed in zip(gates, results):
                if not ok_all:
                    break
                col = OK if passed else DANGER
                mark = txt("✓" if passed else "✗", 26, col, mono=True, weight=BOLD).move_to(g[0]).align_to(g[0], LEFT).shift(RIGHT * 0.18)
                marks.add(mark)
                gate_anims.append(AnimationGroup(g[0].animate.set_stroke(col, opacity=1), FadeIn(mark, scale=1.4)))
                ok_all = passed
            self.play(LaggedStart(*gate_anims, lag_ratio=0.35), run_time=0.4 if fast else 0.7)
            reset = [g[0].animate.set_stroke(LINE) for g in gates] + clear(marks) + clear(extra)
            if not ok_all:
                chip = VGroup(txt(canon, 22, MUTED, mono=True), txt(f"{conf:.2f}", 18, DANGER, mono=True)
                              ).arrange(DOWN, buff=0.06).move_to(excluded).shift(DOWN * 0.35)
                self.play(ReplacementTransform(cells, chip), *reset, run_time=0.6)
                return None
            result = consensus.read("CAM-07", 12, canon, "matched", confidence=conf)
            slot = slots[filled]
            row = VGroup(txt(canon, 26, TEXT, mono=True, weight=BOLD), txt(f"{conf:.2f}", 20, MUTED, mono=True)).arrange(RIGHT, buff=0.5)
            row.move_to(slot)
            filled += 1
            self.play(ReplacementTransform(cells, row), slot.animate.set_stroke(TEAL, opacity=0.7), *reset,
                      *(status_fn(result) if status_fn else []), run_time=0.5)
            return result, row

        tentative = lambda r: set_status(f"tentative · {r['supporting_reads']} of 3", MUTED)
        r, _ = run_read("KAO1A8I234", 0.81, show_tags=True, status_fn=tentative)
        assert r["identity_status"] == "tentative"
        r, _ = run_read("KA01AB1234", 0.74, fast=True, status_fn=tentative)
        assert run_read("KA01AB7234", 0.22, fast=True) is None  # below 0.35: kept, never queryable
        r, _ = run_read("KA01A81234", 0.66, fast=True,
                        status_fn=lambda r: set_status("supported plate · KA01AB1234", OK, "3 consistent reads, same track"))
        assert r["identity_status"] == "supported" and r["fused_plate"] == "KA01AB1234"
        self.wait(0.4)
        r, row = run_read("KA01AB1284", 0.58, fast=True)
        assert r["identity_status"] == "conflicting" and r["fused_plate"] is None
        diff = row[0][8]
        self.play(diff.animate.set_color(DANGER), slots[filled - 1].animate.set_stroke(DANGER, opacity=1),
                  *set_status("conflict → abstain", DANGER, "no plate asserted · reads kept for review"), run_time=0.6)
        outro(self, 1.6)


# ---------------------------------------------------------------- 3. tracking
class Tracking(Scene):
    def construct(self):
        head = eyebrow("CAMERA-LOCAL TRACKING")
        tracker = CentroidTracker()  # real defaults: max_distance=140, ambiguity_margin=0.04
        margin = tracker.ambiguity_margin
        UNMATCHED = 1.1  # dummy-column cost in tracking.update

        # camera view panel: a 600×338 px crop of the frame starting at (250, 230)
        view = RoundedRectangle(corner_radius=0.15, width=6.4, height=3.6, stroke_color=LINE, stroke_width=2,
                                fill_color=PANEL, fill_opacity=1).move_to([-3.45, -0.1, 0])
        s, ox, oy = 6.4 / 600, 250, 230

        def P(x, y):
            return view.get_corner(UL) + np.array([(x - ox) * s, -(y - oy) * s, 0])

        def box(b, color, dashed=False, label=None, width=3):
            r = Rectangle(width=(b[2] - b[0]) * s, height=(b[3] - b[1]) * s, stroke_color=color, stroke_width=width)
            r.move_to((P(b[0], b[1]) + P(b[2], b[3])) / 2)
            m = DashedVMobject(r, num_dashes=28) if dashed else r
            g = VGroup(m)
            if label:
                g.add(txt(label, 22, color, mono=True, weight=BOLD).next_to(r, UP, buff=0.06).align_to(r, LEFT))
            return g

        formula = VGroup(
            txt("cost =", 28, TEXT, mono=True),
            VGroup(txt("0.75", 28, TEAL, mono=True, weight=BOLD), txt("· predicted-centre distance", 24, TEXT)).arrange(RIGHT, buff=0.15),
            VGroup(txt("+ 0.20", 28, TEAL, mono=True, weight=BOLD), txt("· (1 − IoU)", 24, TEXT)).arrange(RIGHT, buff=0.15),
            VGroup(txt("+ 0.05", 28, TEAL, mono=True, weight=BOLD), txt("· area change", 24, TEXT)).arrange(RIGHT, buff=0.15),
        ).arrange(DOWN, aligned_edge=LEFT, buff=0.12)
        formula[1:].shift(RIGHT * 0.3)
        formula.move_to([3.6, 2.05, 0]).align_to(np.array([0.85, 0, 0]), LEFT)
        gate_note = txt("class, size and distance gates reject pairs", 20, MUTED).next_to(formula, DOWN, buff=0.2).align_to(formula, LEFT)
        view_label = txt("previous tracks (dashed) · new detections (solid)", 20, MUTED).next_to(view, DOWN, buff=0.18)

        self.play(FadeIn(head, shift=DOWN * 0.2), FadeIn(view), FadeIn(view_label), run_time=0.6)
        self.play(LaggedStart(*[FadeIn(m, shift=RIGHT * 0.2) for m in formula], lag_ratio=0.2), FadeIn(gate_note), run_time=1.0)

        def matrix(rows, cols, costs):
            cw, ch = 1.32, 0.64
            cells = VGroup()
            for r_i in range(len(rows)):
                for c_i in range(len(cols)):
                    v = costs[r_i][c_i]
                    label = "✕" if v >= 1e5 else f"{v:.3f}" if c_i < len(cols) - 1 else f"{v:.1f}"
                    col = MUTED if (v >= 1e5 or c_i == len(cols) - 1) else TEXT
                    rect = Rectangle(width=cw, height=ch, stroke_color=LINE, stroke_width=1.5, fill_color=PANEL, fill_opacity=1)
                    rect.move_to([c_i * cw, -r_i * ch, 0])
                    cells.add(VGroup(rect, txt(label, 24, col, mono=True).move_to(rect)))
            heads = VGroup(*[txt(c, 22, TEAL if c.startswith("#") else MUTED, mono=True).move_to([i * cw, ch * 0.85, 0])
                             for i, c in enumerate(cols)])
            rlabels = VGroup(*[txt(r, 22, TEXT, mono=True).move_to([-cw * 0.85, -i * ch, 0]) for i, r in enumerate(rows)])
            g = VGroup(cells, heads, rlabels)
            return g.move_to([3.6, -1.15, 0])

        def track(i, b):
            return _Track(i, "car", _center(b), b, 0.0)

        # ---- case A: two cars, clean assignment
        tA = [track(1, (300, 330, 460, 440)), track(2, (470, 380, 630, 490))]
        tA[0].velocity, tA[1].velocity = (70, 0), (-40, 0)
        dA = [{"label": "car", "bbox": (372, 332, 534, 444)}, {"label": "car", "bbox": (428, 384, 590, 496)}]
        cA = [[tracker._cost(t, d, 1.0) for t in tA] for d in dA]
        pick = _assignment([row + [UNMATCHED] * len(dA) for row in cA])
        assert pick == [0, 1]
        old = VGroup(box(tA[0].bbox, TEAL, True, "#1"), box(tA[1].bbox, TEAL, True, "#2"))
        old[1][1].next_to(old[1][0], DOWN, buff=0.06).align_to(old[1][0], LEFT)
        arrowsA = VGroup(*[Arrow(P(*t.center), P(t.center[0] + t.velocity[0], t.center[1]), buff=0, stroke_width=3,
                                 color=TEAL, max_tip_length_to_length_ratio=0.35) for t in tA])
        new = VGroup(box(dA[0]["bbox"], TEXT, label="D1"), box(dA[1]["bbox"], TEXT, label="D2"))
        new[0][1].align_to(new[0][0], RIGHT)
        new[1][1].next_to(new[1][0], DOWN, buff=0.06).align_to(new[1][0], RIGHT)
        mA = matrix(["D1", "D2"], ["#1", "#2", "new"], [row + [UNMATCHED] for row in cA])
        cap = txt("one global minimum-cost assignment per frame", 20, MUTED).next_to(mA, DOWN, buff=0.25)

        self.play(FadeIn(old), GrowArrow(arrowsA[0]), GrowArrow(arrowsA[1]), run_time=0.6)
        self.play(FadeIn(new, shift=RIGHT * 0.1), run_time=0.5)
        self.play(FadeIn(mA, shift=UP * 0.15), run_time=0.6)
        chosen = [mA[0][r * 3 + c][0] for r, c in enumerate(pick)]
        self.play(*[c.animate.set_stroke(OK, width=4).set_fill(OK, opacity=0.14) for c in chosen], FadeIn(cap), run_time=0.6)
        self.play(FadeOut(old), FadeOut(arrowsA),
                  Transform(new[0][1], txt("#1", 22, OK, mono=True, weight=BOLD).move_to(new[0][1]).align_to(new[0][1], LEFT)),
                  Transform(new[1][1], txt("#2", 22, OK, mono=True, weight=BOLD).move_to(new[1][1]).align_to(new[1][1], RIGHT)),
                  new[0][0].animate.set_stroke(OK), new[1][0].animate.set_stroke(OK), run_time=0.6)
        self.wait(0.9)
        self.play(FadeOut(new), FadeOut(mA), FadeOut(cap), run_time=0.5)

        # ---- case B: one detection between two parked tracks -> near tie
        tB = [track(3, (500, 300, 640, 400)), track(4, (664, 300, 804, 400))]
        dB = [{"label": "car", "bbox": (580, 302, 722, 404)}]
        cB = [[tracker._cost(t, d, 1.0) for t in tB] for d in dB]
        gap = abs(cB[0][0] - cB[0][1])
        assert gap <= margin
        # confirm with the real update loop: both old tracks retired, detection gets a fresh ID
        live = CentroidTracker()
        live.update([{"label": "car", "bbox": t.bbox} for t in tB], 0.0)
        out = live.update(dB, 1.0)
        assert out[0]["association_status"] == "ambiguous" and live.active_ids == {out[0]["track_id"]}
        new_id = max(t.track_id for t in tB) + 1  # live tracker numbered from 1; scene tracks are #3, #4

        oldB = VGroup(box(tB[0].bbox, TEAL, True, "#3"), box(tB[1].bbox, TEAL, True, "#4"))
        oldB[1][1].align_to(oldB[1][0], RIGHT)
        dBox = box(dB[0]["bbox"], TEXT, label="D1")
        dBox[1].next_to(dBox[0], DOWN, buff=0.06)
        mB = matrix(["D1"], ["#3", "#4", "new"], [cB[0] + [UNMATCHED]])
        tie = txt(f"|Δ| = {gap:.3f} ≤ margin {margin:.2f}", 24, WARN, mono=True).next_to(mB, DOWN, buff=0.3)
        verdict = VGroup(txt("near-tie → don't guess", 28, DANGER, weight=BOLD),
                         txt("#3 and #4 retired · detection starts a new ID", 20, MUTED)).arrange(DOWN, buff=0.08).next_to(tie, DOWN, buff=0.22)

        self.play(FadeIn(oldB), run_time=0.5)
        self.play(FadeIn(dBox, shift=DOWN * 0.1), run_time=0.4)
        self.play(FadeIn(mB, shift=UP * 0.15), run_time=0.5)
        self.play(*[mB[0][i][0].animate.set_stroke(WARN, width=4) for i in (0, 1)], FadeIn(tie), run_time=0.6)
        self.play(FadeIn(verdict, shift=UP * 0.1),
                  *[o.animate.set_opacity(0.2) for o in oldB],
                  Transform(dBox[1], txt(f"#{new_id} new", 22, WARN, mono=True, weight=BOLD).move_to(dBox[1])),
                  dBox[0].animate.set_stroke(WARN), run_time=0.7)
        outro(self, 1.8)


# ---------------------------------------------------------------- 4. scaling
class Scaling(Scene):
    def construct(self):
        head = eyebrow("PROJECTED AGGREGATE THROUGHPUT")
        data = [  # report.md section "Projected scaling of the architecture"
            ("A", "prototype", "measured", 1.17, "1.17", True),
            ("B", "INT8 detector", "latency delta", 1.22, "~1.22", False),
            ("C", "multi-worker", "4 workers assumed", 4.9, "~4.9", False),
            ("D", "accelerated", "10× assumed", 11.7, "~11.7", False),
        ]
        ax = Axes(x_range=[0, 4, 1], y_range=[0, 12, 3], x_length=10.4, y_length=4.2, tips=False,
                  axis_config={"color": LINE, "stroke_width": 2},
                  y_axis_config={"include_ticks": False}).move_to([0.45, -0.3, 0])
        grid = VGroup(*[DashedLine(ax.c2p(0, y), ax.c2p(4, y), stroke_color=LINE, stroke_width=1.2, dash_length=0.08)
                        for y in (3, 6, 9, 12)])
        ylabels = VGroup(*[txt(str(y), 22, MUTED, mono=True).next_to(ax.c2p(0, y), LEFT, buff=0.18) for y in (0, 3, 6, 9, 12)])
        ytitle = txt("sampled FPS, all cameras", 22, MUTED)
        ytitle.move_to(ax.c2p(0, 11.2)).align_to(ax.c2p(0.08, 0), LEFT)

        bars, labels, values = VGroup(), VGroup(), VGroup()
        bw = 1.5
        for i, (k, l1, l2, v, vs, measured) in enumerate(data):
            x = i + 0.5
            base, top = ax.c2p(x, 0), ax.c2p(x, v)
            hgt = top[1] - base[1]
            col = TEAL if measured else WARN
            rect = Rectangle(width=bw, height=hgt, stroke_width=0).move_to((base + top) / 2)
            if measured:
                bar = VGroup(rect.set_fill(TEAL, 0.85))
            else:  # hatched fill + dashed outline = estimate
                hatch = VGroup()
                x0, x1, y0, y1 = rect.get_left()[0], rect.get_right()[0], rect.get_bottom()[1], rect.get_top()[1]
                step = 0.22
                c = y0 - (x1 - x0)
                while c < y1:  # lines y = x - x0 + c, clipped to the bar
                    pts = []
                    for xx in (x0, x1):
                        yy = xx - x0 + c
                        if y0 <= yy <= y1:
                            pts.append([xx, yy, 0])
                    for yy in (y0, y1):
                        xx = yy - c + x0
                        if x0 < xx < x1:
                            pts.append([xx, yy, 0])
                    if len(pts) == 2:
                        hatch.add(Line(pts[0], pts[1], stroke_color=WARN, stroke_width=2, stroke_opacity=0.55))
                    c += step
                outline = DashedVMobject(Rectangle(width=bw, height=max(hgt, 0.01), stroke_color=WARN, stroke_width=2.5).move_to(rect),
                                         num_dashes=max(8, int(hgt * 5)))
                bar = VGroup(rect.set_fill(WARN, 0.06), hatch, outline)
            bars.add(bar)
            lab = VGroup(txt(k, 28, col, weight=BOLD), txt(l1, 22, TEXT), txt(l2, 20, MUTED)).arrange(DOWN, buff=0.06)
            labels.add(lab.next_to(ax.c2p(x, 0), DOWN, buff=0.22))
            values.add(txt(vs, 30, col, mono=True, weight=BOLD).next_to(top, UP, buff=0.14))

        by = values[3].get_top()[1] + 0.22
        brace_l, brace_r = np.array([ax.c2p(1.12, 0)[0], by, 0]), np.array([ax.c2p(3.88, 0)[0], by, 0])
        bracket = VGroup(Line(brace_l, brace_r, stroke_color=WARN, stroke_width=2),
                         Line(brace_l, brace_l + DOWN * 0.15, stroke_color=WARN, stroke_width=2),
                         Line(brace_r, brace_r + DOWN * 0.15, stroke_color=WARN, stroke_width=2))
        badge = txt("projection, not tested", 26, WARN, weight=BOLD).next_to(bracket, UP, buff=0.12)
        legend = VGroup(
            VGroup(Square(0.28, fill_color=TEAL, fill_opacity=0.85, stroke_width=0), txt("measured", 22, TEXT)).arrange(RIGHT, buff=0.14),
            VGroup(DashedVMobject(Square(0.28, stroke_color=WARN, stroke_width=2.5), num_dashes=8), txt("estimate", 22, TEXT)).arrange(RIGHT, buff=0.14),
        ).arrange(RIGHT, buff=0.45).to_corner(UR, buff=0.55)

        self.play(FadeIn(head, shift=DOWN * 0.2), FadeIn(legend, shift=DOWN * 0.2), run_time=0.5)
        self.play(Create(ax), FadeIn(grid), FadeIn(ylabels), FadeIn(ytitle), run_time=0.8)
        self.play(GrowFromEdge(bars[0], DOWN), FadeIn(labels[0], shift=UP * 0.1), run_time=0.8)
        self.play(FadeIn(values[0], shift=UP * 0.1), run_time=0.3)
        self.wait(0.4)
        for i in (1, 2, 3):
            self.play(GrowFromEdge(bars[i], DOWN), FadeIn(labels[i], shift=UP * 0.1), run_time=0.75, rate_func=smooth)
            self.play(FadeIn(values[i], shift=UP * 0.1), run_time=0.25)
        self.play(Create(bracket), FadeIn(badge, shift=DOWN * 0.1), run_time=0.6)
        outro(self, 2.2)


# ---------------------------------------------------------------- 5. scheduler
class Scheduler(Scene):
    def construct(self):
        head = eyebrow("CITYWIDE SOURCES, ONE GLOBAL FRAME BUDGET")
        cols, rows = 6, 4
        offline = {9, 20}  # missing / retrying sources: skipped, consume no slot
        tiles = VGroup()
        for i in range(cols * rows):
            off = i in offline
            r = RoundedRectangle(corner_radius=0.1, width=0.86, height=0.56, stroke_color=LINE if off else MUTED,
                                 stroke_width=2, fill_color=PANEL, fill_opacity=1)
            lab = txt(f"{i + 1:02d}", 20, DANGER if off else TEXT, mono=True, weight=BOLD).move_to(r)
            tiles.add(VGroup(DashedVMobject(r, num_dashes=18) if off else r, lab))
        tiles.arrange_in_grid(rows, cols, buff=0.12).move_to([-3.6, 0.3, 0])
        # faint street grid behind the tiles
        streets = VGroup(*[Line(tiles.get_left() + LEFT * 0.25 + UP * y, tiles.get_right() + RIGHT * 0.25 + UP * y,
                                stroke_color=LINE, stroke_width=6) for y in np.linspace(-1.0, 1.0, 3)],
                         *[Line(tiles.get_bottom() + DOWN * 0.2 + RIGHT * x, tiles.get_top() + UP * 0.2 + RIGHT * x,
                                stroke_color=LINE, stroke_width=6) for x in np.linspace(-1.96, 1.96, 3)]
                         ).move_to(tiles).set_z_index(-1)
        cams_label = txt("city cameras · 24 shown of N", 22, MUTED).next_to(tiles, UP, buff=0.25).align_to(tiles, LEFT)
        off_note = txt("offline sources skipped, no slot used", 20, MUTED).next_to(tiles, DOWN, buff=0.22).align_to(tiles, LEFT)

        def worker_box(title, w=3.3, h=1.2):
            t = txt(title, 24, TEXT, weight=BOLD)
            if t.width > w - 0.3:
                t.scale_to_fit_width(w - 0.3)
            return VGroup(RoundedRectangle(corner_radius=0.16, width=w, height=h, stroke_color=WARN, stroke_width=3,
                                           fill_color=WARN, fill_opacity=0.08), t)

        worker = worker_box("inference worker").move_to([3.3, 1.5, 0])
        worker[1].move_to(worker[0])
        budget = VGroup(txt(f"{TOTAL_FPS:.0f} FPS total, shared", 24, TEAL, weight=BOLD),
                        txt(f"one {1000 / TOTAL_FPS:.0f} ms slot at a time, round robin", 18, MUTED)
                        ).arrange(DOWN, buff=0.06).next_to(worker, DOWN, buff=0.2)
        cache = VGroup(RoundedRectangle(corner_radius=0.16, width=2.9, height=0.9, stroke_color=TEAL, stroke_width=2.5,
                                        fill_color=PANEL, fill_opacity=1), txt("cached output", 22, TEXT)).move_to([2.75, -1.35, 0])
        cache[1].move_to(cache[0])
        a1 = Arrow(budget.get_bottom() + LEFT * 0.55, cache[0].get_top(), buff=0.1, stroke_width=3, color=MUTED, max_tip_length_to_length_ratio=0.25)

        def viewer():
            r = RoundedRectangle(corner_radius=0.08, width=0.95, height=0.62, stroke_color=MUTED, stroke_width=2,
                                 fill_color=PANEL, fill_opacity=1)
            return VGroup(r, Line(r.get_corner(UL) + DOWN * 0.14 + RIGHT * 0.05, r.get_corner(UR) + DOWN * 0.14 + LEFT * 0.05,
                                  stroke_color=MUTED, stroke_width=1.5))
        viewers = VGroup(*[viewer() for _ in range(3)]).arrange(DOWN, buff=0.14).move_to([5.85, -1.35, 0])
        vlabel = txt("viewers", 20, MUTED).next_to(viewers, UP, buff=0.15)
        vlinks = VGroup(*[Line(cache[0].get_right(), v.get_left(), stroke_color=TEAL, stroke_width=1.5, stroke_opacity=0.6) for v in viewers])
        vnote = txt("viewers add no workers", 20, MUTED).next_to(viewers, DOWN, buff=0.18).align_to(viewers, RIGHT)

        self.play(FadeIn(head, shift=DOWN * 0.2), FadeIn(streets), FadeIn(cams_label),
                  LaggedStart(*[FadeIn(t, scale=0.8) for t in tiles], lag_ratio=0.03), run_time=1.1)
        self.play(FadeIn(worker, scale=0.95), FadeIn(budget), GrowArrow(a1), FadeIn(cache), run_time=0.6)

        # beat 1 (implemented): one worker walks the sources in order
        live = [i for i in range(cols * rows) if i not in offline]
        order = live[6:15]
        for n, i in enumerate(order):
            t = tiles[i]
            dot = Dot(t.get_center(), radius=0.08, color=TEAL).set_z_index(2)
            anims = [t[0].animate.set_stroke(TEAL, width=3), dot.animate.move_to(worker[0].get_left() + RIGHT * 0.15)]
            if i == 10:  # first slot after the offline source 10
                anims += [Indicate(tiles[9], color=DANGER, scale_factor=1.12), FadeIn(off_note)]
            if n in (2, 4, 6):
                k = (n - 2) // 2
                anims += [FadeIn(viewers[k], shift=LEFT * 0.2), Create(vlinks[k])] + ([FadeIn(vlabel)] if k == 0 else [])
            if n == 7:
                anims.append(FadeIn(vnote))
            self.play(*anims, run_time=0.32, rate_func=smooth)
            self.play(t[0].animate.set_stroke(MUTED, width=2), FadeOut(dot, scale=0.3), run_time=0.14)

        # beat 2 (projected): partition cameras by column across workers
        part_cols = [TEAL, OK, TEXT]
        parts = [[i for i in range(cols * rows) if (i % cols) // 2 == p] for p in range(3)]
        workers = VGroup(*[worker_box(f"worker {p + 1}", w=1.6, h=0.85) for p in range(3)]).arrange(RIGHT, buff=0.15)
        for p, wb in enumerate(workers):
            wb[1].move_to(wb[0])
            wb[0].set_stroke(part_cols[p])
            wb[0].set_fill(part_cols[p], 0.08)
        workers.move_to([3.75, worker.get_y(), 0])
        badge = txt("projected scale-out · not tested", 22, WARN, weight=BOLD).next_to(workers, UP, buff=0.22)
        boxes = VGroup(*[SurroundingRectangle(VGroup(*[tiles[i] for i in idx]), buff=0.06, corner_radius=0.12,
                                              stroke_color=part_cols[p], stroke_width=2.5) for p, idx in enumerate(parts)])
        self.play(ReplacementTransform(worker, workers), FadeIn(badge, shift=DOWN * 0.1), Create(boxes),
                  budget[0].animate.become(txt("aggregate ≈ workers × rate", 24, TEAL, weight=BOLD).move_to(budget[0])),
                  budget[1].animate.become(txt("each worker cycles its own cameras", 18, MUTED).move_to(budget[1])),
                  run_time=0.8)
        for step in range(3):
            dots, anims = [], []
            for p, idx in enumerate(parts):
                cand = [i for i in idx if i not in offline]
                i = cand[(step * 3 + p) % len(cand)]
                d = Dot(tiles[i].get_center(), radius=0.08, color=part_cols[p]).set_z_index(2)
                dots.append(d)
                anims += [d.animate.move_to(workers[p][0].get_bottom() + UP * 0.12), tiles[i][0].animate.set_stroke(part_cols[p], width=3)]
            self.add(*dots)
            self.play(*anims, run_time=0.5, rate_func=smooth)
            self.play(*[FadeOut(d, scale=0.3) for d in dots], *[t[0].animate.set_stroke(MUTED, width=2) for t in tiles if not isinstance(t[0], DashedVMobject)],
                      run_time=0.18)
        outro(self, 1.4)
