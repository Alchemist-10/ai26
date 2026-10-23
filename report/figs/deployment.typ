#import "style.typ": *
#set page(width: auto, height: auto, margin: 6pt, fill: white)
#set text(font: "Liberation Serif", size: 7.5pt)
#canvas(length: 1cm, {
  import draw: *
  // left: measured
  rect((-0.2, -4.6), (4.6, 1.0), stroke: 0.9pt + ink, radius: 4pt, fill: rgb("#fafafa"))
  content((2.2, 0.65), text(weight: "bold")[Measured (local CPU host)])
  node("m1", (2.2, -0.5), 3.8, 1.0, [Single processor\ 12-thread laptop CPU], bg: c-ai)
  node("m2", (2.2, -1.9), 3.8, 1.0, [PyTorch FP32 detector\ + ONNX plate stack], bg: c-ai)
  node("m3", (2.2, -3.3), 3.8, 1.0, [SQLite + FastAPI + React\ 9 replay sources], bg: c-store)
  arrow("m1.south", "m2.north"); arrow("m2.south", "m3.north")
  // right: projected
  rect((5.6, -4.6), (14.6, 1.0), stroke: (paint: rgb("#7a4a9a"), thickness: 0.9pt, dash: "dashed"), radius: 4pt, fill: rgb("#fcf9fe"))
  content((10.1, 0.65), text(weight: "bold", fill: rgb("#5a2d7a"))[Projected (not tested)])
  node("p1", (7.4, -1.0), 2.8, 1.0, [Edge gateways\ decode + sample], bg: c-proj)
  node("p2", (7.4, -2.6), 2.8, 1.0, [Frame queue\ per-site], bg: c-proj)
  node("p3", (11.0, -1.0), 2.8, 1.0, [GPU / INT8 inference\ workers (scaled out)], bg: c-proj)
  node("p4", (11.0, -2.6), 2.8, 1.0, [PostgreSQL / object\ store for evidence], bg: c-proj)
  node("p5", (13.5, -3.9), 2.2, 0.9, [Dashboard +\ audit service], bg: c-proj)
  arrow("p1.south", "p2.north"); arrow("p2.east", "p3.south", ); arrow("p3.south", "p4.north"); arrow("p4.east", (13.5, -2.6)); line((13.5,-2.6),"p5.north", mark: (end: ">", fill: ink, size: 0.18), stroke: 0.9pt+ink)
  arrow("m3.east", (5.6, -3.3))
})
