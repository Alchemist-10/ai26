#import "style.typ": *
#set page(width: auto, height: auto, margin: 6pt, fill: white)
#set text(font: "Liberation Serif", size: 7.5pt)
#canvas(length: 1cm, {
  import draw: *
  node("in", (0, 0), 1.9, 1.3, [Plate crop\ grayscale,\ fixed size], bg: c-src)
  node("stem", (2.7, 0), 1.9, 1.3, [Conv stem +\ MobileNetV2\ blocks])
  node("mvit", (5.4, 0), 1.9, 1.3, [MobileViT-v2\ blocks])
  node("head", (8.1, 0), 1.9, 1.3, [Per-position\ classifier head])
  node("out", (10.8, 0), 1.9, 1.3, [Character\ sequence +\ confidences], bg: c-out)
  for p in (("in","stem"),("stem","mvit"),("mvit","head"),("head","out")) { arrow(p.at(0)+".east", p.at(1)+".west") }
  // expanded block
  rect((3.1, -4.9), (7.7, -1.9), stroke: (paint: ink, thickness: 0.8pt, dash: "dashed"), radius: 3pt)
  content((5.4, -2.15), text(size: 8pt, style: "italic")[inside a MobileViT-v2 block])
  node("u", (4.0, -3.5), 1.1, 1.2, [Local conv\ + unfold\ to patches], bg: c-proj)
  node("s", (5.4, -3.5), 1.1, 1.2, [Separable\ self-\ attention], bg: c-proj)
  node("f", (6.8, -3.5), 1.1, 1.2, [Fold +\ fuse with\ input], bg: c-proj)
  arrow("u.east", "s.west"); arrow("s.east", "f.west")
  line("mvit.south", (5.4, -1.9), stroke: (paint: ink, thickness: 0.6pt, dash: "dotted"))
})
