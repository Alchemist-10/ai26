#import "style.typ": *
#set page(width: auto, height: auto, margin: 6pt, fill: white)
#set text(font: "Liberation Serif", size: 8pt)
#canvas(length: 1cm, {
  import draw: *
  let names = ("PyTorch FP32", "ONNX Runtime FP32", "ONNX Runtime INT8")
  let med = (92.834, 95.309, 55.782)
  let p95 = (98.743, 101.240, 58.306)
  let cols = (rgb("#7fa6cf"), rgb("#7fa6cf"), rgb("#4f9a6b"))
  let s = 0.055
  line((0,0),(0,4.4), stroke: 0.7pt); line((0,0),(6.2,0), stroke: 0.7pt)
  for t in (0,20,40,60,80,100) { let x = t*s; line((x,0),(x,-0.08)); content((x,-0.3), text(size: 7pt)[#t]); if t>0 { line((x,0),(x,4.4), stroke: 0.3pt + luma(220)) } }
  content((3.0,-0.75), text(size: 7.5pt)[median model-forward latency (ms, lower is faster)])
  for (i, n) in names.enumerate() {
    let y = 3.4 - i*1.4
    rect((0, y - 0.4), (med.at(i)*s, y+0.4), fill: cols.at(i), stroke: 0.5pt + ink)
    line((p95.at(i)*s, y - 0.25), (p95.at(i)*s, y+0.25), stroke: 0.8pt)
    content((med.at(i)*s/2, y), text(fill: white, weight: "bold", size: 8pt)[#med.at(i)])
    content((-0.2, y), anchor: "east", text(size: 7.5pt)[#n])
  }
  content((5.5, 4.2), text(size: 7pt)[| = p95])
})
