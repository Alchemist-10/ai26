#import "style.typ": *
#set page(width: auto, height: auto, margin: 6pt, fill: white)
#set text(font: "Liberation Serif", size: 8pt)
// projected cameras servable at 1 FPS each, derived from per-frame cost
// measured: 1.171 FPS total (both branches) => ~854 ms/frame-slot on host
// projected: INT8 detector (55.8 ms vs 92.8 ms) removes ~37 ms of ~854 ms; GPU/multi-worker scenarios are assumptions
#canvas(length: 1cm, {
  import draw: *
  let names = ("A. Measured\nCPU, FP32", "B. INT8 detector\nsame host", "C. 4 CPU workers\nINT8 (4 hosts)", "D. 1 GPU worker\n(assumed 10x)")
  let fps = (1.17, 1.22, 4.9, 11.7)
  let cols = (rgb("#4f7fb0"), rgb("#8d6cb0"), rgb("#8d6cb0"), rgb("#8d6cb0"))
  let s = 0.38
  line((0,0),(0,5.0), stroke: 0.7pt); line((0,0),(9.2,0), stroke: 0.7pt)
  for t in (0,2,4,6,8,10,12) { let y = t*0.4; line((-0.08,y),(0,y)); content((-0.35,y), text(size: 7pt)[#t]); if t>0 { line((0,y),(9.2,y), stroke: 0.3pt + luma(220)) } }
  content((-1.0, 2.4), angle: 90deg, text(size: 7.5pt)[total sampled FPS])
  for (i, n) in names.enumerate() {
    let x = 0.6 + i*2.2
    rect((x, 0), (x+1.3, fps.at(i)*0.4), fill: cols.at(i), stroke: 0.5pt + ink)
    content((x+0.65, fps.at(i)*0.4+0.3), text(size: 8pt, weight: "bold")[#fps.at(i)])
    content((x+0.65, -0.65), text(size: 7pt)[#n])
  }
})
