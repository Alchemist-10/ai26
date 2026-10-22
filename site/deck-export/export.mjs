// Export the deck to public/Sakshi-presentation.{pdf,pptx}.
// Usage (from site/): npm run build && node deck-export/export.mjs && npm run build
// The second build copies the fresh files into dist. THEME=light exports the light theme.
// PDF: Chromium print of /present/?print (every slide fully built, one 1280x720 page each).
// PPTX: one 1920x1080 screenshot per slide, speaker notes from each slide's <aside class="notes">.
import fs from "node:fs";
import http from "node:http";
import path from "node:path";
import { chromium } from "@playwright/test";
import PptxGenJS from "pptxgenjs";

const site = path.resolve(import.meta.dirname, "..");
const dist = path.join(site, "dist");
const out = path.join(site, "public");
const BASE = "/ai26";
const theme = process.env.THEME === "light" ? "light" : "dark";
const types = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg", ".webp": "image/webp", ".woff2": "font/woff2", ".woff": "font/woff", ".webm": "video/webm", ".mp4": "video/mp4", ".pdf": "application/pdf" };

if (!fs.existsSync(path.join(dist, "present", "index.html"))) {
  console.error("dist/present/index.html missing: run `npm run build` first");
  process.exit(1);
}

// Minimal static server for dist under the /ai26 base path (avoids clashing with other preview servers).
const server = http.createServer((req, res) => {
  const url = decodeURIComponent(new URL(req.url, "http://x").pathname);
  let file = path.join(dist, url.slice(BASE.length));
  if (!url.startsWith(BASE) || !file.startsWith(dist)) return res.writeHead(404).end();
  if (fs.existsSync(file) && fs.statSync(file).isDirectory()) file = path.join(file, "index.html");
  if (!fs.existsSync(file)) return res.writeHead(404).end();
  res.writeHead(200, { "content-type": types[path.extname(file)] || "application/octet-stream" });
  fs.createReadStream(file).pipe(res);
});
await new Promise((r) => server.listen(0, "127.0.0.1", r));
const origin = `http://127.0.0.1:${server.address().port}`;

const browser = await chromium.launch();
try {
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 720 }, deviceScaleFactor: 1.5, colorScheme: theme });
  const page = await ctx.newPage();
  page.on("pageerror", (e) => console.error("page error:", e.message));
  await page.goto(`${origin}${BASE}/present/?print`, { waitUntil: "load" });
  await page.evaluate(async (t) => {
    document.documentElement.dataset.theme = t; // print would otherwise fall back to the light scheme
    await document.fonts.ready;
    await Promise.all([...document.images].map((i) => (i.complete ? null : new Promise((r) => { i.onload = i.onerror = r; }))));
  }, theme);
  await page.waitForTimeout(500);

  const slides = page.locator(".stage > .slide");
  const n = await slides.count();
  const notes = await slides.evaluateAll((els) =>
    els.map((s) => [...(s.querySelector(".notes")?.querySelectorAll("p") ?? [])].map((p) => p.textContent.replace(/\s+/g, " ").trim()).join("\n\n")),
  );

  const pptx = new PptxGenJS();
  pptx.layout = "LAYOUT_WIDE";
  pptx.title = "Sakshi";
  pptx.author = "Sakshi team, IIIT Kottayam";
  for (let k = 0; k < n; k++) {
    const jpg = await slides.nth(k).screenshot({ type: "jpeg", quality: 88 });
    const slide = pptx.addSlide();
    slide.addImage({ data: `image/jpeg;base64,${jpg.toString("base64")}`, x: 0, y: 0, w: 13.333, h: 7.5 });
    if (notes[k]) slide.addNotes(notes[k]);
  }
  await pptx.writeFile({ fileName: path.join(out, "Sakshi-presentation.pptx"), compression: true });

  await page.pdf({ path: path.join(out, "Sakshi-presentation.pdf"), width: "1280px", height: "720px", printBackground: true, preferCSSPageSize: true });
  console.log(`exported ${n} slides (${theme}) to public/Sakshi-presentation.pdf and .pptx`);
} finally {
  await browser.close();
  server.close();
}
