#import "style.typ": *
#set page(width: auto, height: auto, margin: 6pt, fill: white)
#set text(font: "Liberation Serif", size: 7.5pt)
#canvas(length: 1cm, {
  import draw: *
  // row 1
  node("src", (1.3, 0), 2.3, 1.2, [Video sources\ CAM-01 to CAM-09\ MP4 / RTSP], bg: c-src)
  node("sch", (4.3, 0), 2.3, 1.2, [Round-robin\ scheduler\ 2 FPS total budget], bg: c-ai)
  node("det", (7.3, 0), 2.3, 1.2, [YOLOv8n\ vehicle and person\ detection], bg: c-ai)
  node("alpr", (10.3, 0), 2.3, 1.2, [Plate detector +\ MobileViT-v2 OCR], bg: c-ai)
  arrow("src.east", "sch.west"); arrow("sch.east", "det.west"); arrow("det.east", "alpr.west")
  // row 2
  node("trk", (4.3, -2.6), 2.3, 1.2, [Camera-local tracker\ global assignment], bg: c-ai)
  node("gate", (7.3, -2.6), 2.3, 1.2, [Plate normalisation\ and 3-read consensus], bg: c-ai)
  node("db", (10.3, -2.6), 2.3, 1.2, [SQLite (WAL)\ reads, passages,\ audit chain], bg: c-store)
  arrow("det.south", "trk.north"); arrow("alpr.south", "gate.north", ); arrow("trk.east", "gate.west"); arrow("gate.east", "db.west")
  // row 3
  node("r1", (1.3, -5.2), 2.3, 1.2, [Rules, alerts,\ watchlists], bg: c-out)
  node("r2", (4.3, -5.2), 2.3, 1.2, [Journey candidates\ (review only)], bg: c-out)
  node("r3", (7.3, -5.2), 2.3, 1.2, [Evidence reports\ SHA-256 / Ed25519], bg: c-out)
  node("r4", (10.3, -5.2), 2.3, 1.2, [Deterministic\ query grammar], bg: c-out)
  for r in ("r1","r2","r3","r4") { arrow("db.south", r + ".north") }
  node("api", (5.8, -7.4), 9.4, 1.0, [FastAPI service #sym.arrow.r React / TypeScript investigation dashboard], bg: c-ui)
  for r in ("r1","r2","r3","r4") { arrow(r + ".south", (rel: (0, -0.001), to: "api.north")) }
})
