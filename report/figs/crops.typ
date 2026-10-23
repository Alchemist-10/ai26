#import "style.typ": *
#set page(width: auto, height: auto, margin: 6pt, fill: white)
#set text(font: "Liberation Serif", size: 8pt)
#canvas(length: 1cm, {
  import draw: *
  let parts = ((16, "Unreadable", rgb("#b9c2cc")), (4, "Readable", rgb("#7fa6cf")), (1, "Uncertain", rgb("#e7c46a")))
  let x = 0
  let s = 0.4
  for p in parts {
    rect((x, 0), (x + p.at(0)*s, 0.9), fill: p.at(2), stroke: 0.6pt + ink)
    content((x + p.at(0)*s/2, 0.45), text(size: 8pt, weight: "bold")[#p.at(0)])
    content((x + p.at(0)*s/2 + if p.at(1) == "Uncertain" { 0.5 } else { 0 }, -0.4), text(size: 7.5pt)[#p.at(1)])
    x += p.at(0)*s
  }
  content((x/2, 1.35), text(size: 8pt)[21 selected plate crops, reviewer judgement])
  // second bar: outcomes of 4 readable
  let y = -3.1
  rect((0, y), (4*1.0, y+0.9), fill: rgb("#d9822b"), stroke: 0.6pt + ink)
  content((2.0, y+0.45), text(size: 8pt, weight: "bold", fill: white)[4 mismatched])
  rect((4.0, y), (8.0, y+0.9), fill: rgb("#4f9a6b"), stroke: 0.6pt + ink)
  content((6.0, y+0.45), text(size: 8pt, weight: "bold", fill: white)[4 rejected by gates])
  content((4.0, y+1.35), text(size: 8pt)[Four readable crops: OCR outcome (left) and gate decision (right)])
  content((4.0, y - 0.45), text(size: 7.5pt)[none became a supported plate identity])
})
