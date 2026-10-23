#import "@preview/cetz:0.3.4": canvas, draw
#set page(width: auto, height: auto, margin: 6pt, fill: white)
#set text(font: "Liberation Serif", size: 9pt)
#let ink = rgb("#1f2d3d")
#let c-src = rgb("#eceff3")
#let c-ai = rgb("#dce7f3")
#let c-store = rgb("#e1f0dc")
#let c-out = rgb("#fbe6d8")
#let c-ui = rgb("#fff1cc")
#let c-proj = rgb("#efe3f6")
#let node(name, pos, w, h, body, bg: c-ai, sk: 0.9pt + ink) = {
  import draw: *
  rect((pos.at(0) - w/2, pos.at(1) - h/2), (pos.at(0) + w/2, pos.at(1) + h/2), fill: bg, stroke: sk, radius: 3pt, name: name)
  content(name, align(center, body))
}
#let arrow(a, b, ..args) = draw.line(a, b, mark: (end: ">", fill: ink, size: 0.18), stroke: 0.9pt + ink, ..args)
