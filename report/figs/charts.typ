#import "style.typ": *
#set page(width: auto, height: auto, margin: 6pt, fill: white)
#set text(font: "Liberation Serif", size: 8pt)
#import "@preview/cetz:0.3.4": canvas, draw
// generic horizontal/vertical bar helper not needed: each chart drawn directly
#let cams = ("CAM-01","CAM-02","CAM-03","CAM-04","CAM-05","CAM-06","CAM-07","CAM-08","CAM-09")
#let frames = (39,39,39,39,39,39,38,38,39)
#let over = (2,2,4,3,7,1,36,37,39)
#canvas(length: 1cm, {
  import draw: *
  let bw = 0.55
  // axes
  line((0,0),(0,5.2), stroke: 0.7pt); line((0,0),(10.4,0), stroke: 0.7pt)
  for t in (0,10,20,30,40) { let y = t*0.12; line((-0.08,y),(0,y)); content((-0.35,y), text(size: 7pt)[#t]); if t>0 { line((0,y),(10.4,y), stroke: 0.3pt + luma(220)) } }
  content((-1.1, 2.6), angle: 90deg, text(size: 7.5pt)[count per camera])
  for (i, c) in cams.enumerate() {
    let x = 0.3 + i*1.1
    rect((x, 0), (x+bw, frames.at(i)*0.12), fill: rgb("#7fa6cf"), stroke: 0.5pt + ink)
    rect((x+bw, 0), (x+2*bw, over.at(i)*0.12), fill: rgb("#d9822b"), stroke: 0.5pt + ink)
    content((x+bw, -0.4), text(size: 7pt)[#c])
  }
  rect((0.5, 5.6), (0.8, 5.85), fill: rgb("#7fa6cf"), stroke: 0.5pt+ink); content((2.4, 5.72), text(size: 7.5pt)[sampled frames completed])
  rect((4.6, 5.6), (4.9, 5.85), fill: rgb("#d9822b"), stroke: 0.5pt+ink); content((7.3, 5.72), text(size: 7.5pt)[attempts over 500 ms target])
})
