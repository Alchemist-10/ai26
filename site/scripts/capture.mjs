// Capture real dashboard screenshots + clips for the site.
// Needs the app running (privacy mode recommended):
//   AI26_PRIVACY_ENABLED=1 AI26_PRIVACY_KEY_FILE=... uv run run.py --skip-install
// Usage: node scripts/capture.mjs [shots|clips|all]   (APP_URL, DEMO_URL env overrides)
import { chromium } from "@playwright/test"
import { execFileSync } from "node:child_process"
import { mkdirSync, mkdtempSync, readdirSync, rmSync, statSync, writeFileSync } from "node:fs"
import { tmpdir } from "node:os"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..")
const SHOTS = join(ROOT, "src/assets/screens")
const CLIPS = join(ROOT, "public/clips")
const APP = process.env.APP_URL ?? "http://127.0.0.1:5174"
const DEMO = process.env.DEMO_URL ?? "http://127.0.0.1:8765" // python3 -m http.server 8765 -d demo
const MAX_BYTES = 900 * 1024
const what = process.argv[2] ?? "all"
mkdirSync(SHOTS, { recursive: true })
mkdirSync(CLIPS, { recursive: true })

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

// Mask anything that looks like an Indian plate, keeping only the state code (privacy, best effort).
async function maskPlates(page) {
  await page.evaluate(() => {
    const re = /\b([A-Z]{2})[\s-]?\d{1,2}[\s-]?[A-Z]{0,3}[\s-]?\d{3,4}\b/g
    const mask = (t) => t.replace(re, "$1 •• •• ••••")
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT)
    for (let n = walker.nextNode(); n; n = walker.nextNode()) n.textContent = mask(n.textContent)
    // React may re-render controlled fields, so blur matching ones instead of editing their value.
    for (const el of document.querySelectorAll("input, textarea")) if (mask(el.value + el.placeholder) !== el.value + el.placeholder) el.style.filter = "blur(6px)"
  })
}

// Write PNG (stepping width down until < MAX_BYTES) plus a WebP alongside.
function save(buf, name) {
  const tmp = join(mkdtempSync(join(tmpdir(), "cap-")), "raw.png")
  writeFileSync(tmp, buf)
  const png = join(SHOTS, `${name}.png`)
  // Largest width that fits; truecolor first, then 256-colour palette.
  fit: for (const w of [2880, 2400, 2160, 1920, 1600, 1440]) {
    for (const out of [png, `PNG8:${png}`]) {
      execFileSync("magick", [tmp, "-resize", `${w}x>`, "-strip", "-define", "png:compression-level=9", out])
      if (statSync(png).size < MAX_BYTES) break fit
    }
  }
  execFileSync("magick", [tmp, "-resize", "2880x>", "-strip", "-quality", "82", join(SHOTS, `${name}.webp`)])
  rmSync(dirname(tmp), { recursive: true })
  console.log(`${name}: ${(statSync(png).size / 1024) | 0}KB png`)
}

async function shot(page, name, target) {
  await maskPlates(page)
  await sleep(300)
  const el = typeof target === "string" ? page.locator(target).first() : target
  save(await (el ? el.screenshot() : page.screenshot()), name)
}

// Focus the camera with the most recent detection, then wait until its streamed frame carries boxes.
async function focusDetection(page) {
  const health = async () => (await (await page.request.get(`${APP}/api/health`)).json()).cameras
  const cam = (await health()).filter((c) => c.last_event_at).sort((a, b) => b.last_event_at - a.last_event_at)[0]
  if (!cam) return
  await page.getByRole("button", { name: new RegExp(cam.camera_id) }).first().click()
  await sleep(500)
  await page.getByText("Waiting for the first sampled frame").waitFor({ state: "hidden", timeout: 20000 }).catch(() => {})
  for (let i = 0; i < 120; i++) {
    const c = (await health()).find((x) => x.camera_id === cam.camera_id)
    if (c.last_event_at === c.last_frame_at && Date.now() / 1000 - c.last_frame_at < 0.4) break
    await sleep(250)
  }
  await sleep(800)
}

async function nav(page, label) {
  await page.getByRole("button", { name: "Open navigation" }).click()
  await page.getByRole("button", { name: new RegExp(label) }).first().click()
  await sleep(2500)
}

async function ask(page, q, typeDelay = 0) {
  const box = page.getByPlaceholder("Plates at CAM-07 today")
  await box.click()
  await box.pressSequentially(q, { delay: typeDelay })
  await box.press("Enter")
  await page.waitForFunction(() => !document.body.innerText.includes("Thinking"), null, { timeout: 15000 }).catch(() => {})
  await sleep(2500)
}

async function shots(browser) {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2, colorScheme: "dark" })
  const page = await ctx.newPage()
  await page.goto(APP)
  await sleep(8000) // let sampled previews + overlays arrive
  await focusDetection(page)
  await shot(page, "dashboard-overview")
  await page.getByRole("button", { name: "vehicle", exact: true }).click()
  await sleep(1500)
  const wall = await page.getByLabel("Search cameras").locator("xpath=ancestor::div[contains(@class,'flex-col')][1]").boundingBox()
  const tile = await page.locator("img[alt$='sampled preview']").last().boundingBox()
  await maskPlates(page)
  save(await page.screenshot({ clip: { ...wall, height: tile.y + tile.height + 12 - wall.y } }), "camera-wall")
  await page.getByRole("button", { name: "all", exact: true }).click()

  await nav(page, "Evidence Timeline")
  await page.getByLabel("Camera log").selectOption("CAM-05") // usually the busiest sampled camera
  await sleep(2500)
  await shot(page, "timeline")

  await nav(page, "Ask the Grid")
  await ask(page, "What's the busiest camera right now?")
  await ask(page, "How many cars today?")
  await shot(page, "query")

  await nav(page, "Alerts")
  await page.getByText("Configure local rules").click()
  await sleep(800)
  await shot(page, "investigation")

  await nav(page, "Camera settings")
  await sleep(2000)
  await shot(page, "camera-settings")

  await nav(page, "Traffic activity")
  await sleep(2000)
  await shot(page, "congestion")
  await ctx.close()

  // Evidence report: no plate footage locally, so use the synthetic demo walkthrough.
  const dctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2, colorScheme: "dark" })
  const dpage = await dctx.newPage()
  await dpage.goto(`${DEMO}/evidence.html`)
  await sleep(1500)
  await dpage.locator("#evidence-chips > *").first().click()
  await sleep(1500)
  await shot(dpage, "evidence-report")
  await dctx.close()

  const mctx = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true, colorScheme: "dark" })
  const mpage = await mctx.newPage()
  await mpage.goto(APP)
  await sleep(8000)
  await focusDetection(mpage)
  await shot(mpage, "mobile-overview")
  await mctx.close()
}

// Record with Playwright, then transcode to VP9 webm + H.264 mp4 and grab a poster.
async function clip(browser, name, seconds, drive) {
  const dir = mkdtempSync(join(tmpdir(), "clip-"))
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 }, colorScheme: "dark", recordVideo: { dir, size: { width: 1280, height: 800 } } })
  const t0 = Date.now()
  const page = await ctx.newPage()
  const lead = Math.max(0, (await drive(page)) - t0) / 1000 // drive returns when the interesting part starts
  await ctx.close()
  const raw = join(dir, readdirSync(dir).find((f) => f.endsWith(".webm")))
  const base = join(CLIPS, name)
  const trim = ["-ss", String(lead), "-t", String(seconds)]
  execFileSync("ffmpeg", ["-y", "-loglevel", "error", ...trim, "-i", raw, "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "26", "-preset", "slow", "-movflags", "+faststart", `${base}.mp4`])
  execFileSync("ffmpeg", ["-y", "-loglevel", "error", ...trim, "-i", raw, "-an", "-c:v", "libvpx-vp9", "-b:v", "0", "-crf", "38", "-row-mt", "1", `${base}.webm`])
  execFileSync("ffmpeg", ["-y", "-loglevel", "error", "-sseof", "-0.5", "-i", `${base}.mp4`, "-frames:v", "1", `${base}.png`])
  rmSync(dir, { recursive: true })
  for (const ext of ["mp4", "webm", "png"]) console.log(`${name}.${ext}: ${(statSync(`${base}.${ext}`).size / 1024) | 0}KB`)
}

async function clips(browser) {
  await clip(browser, "app-live", 10, async (page) => {
    await page.goto(APP)
    await sleep(6000)
    await focusDetection(page)
    await maskPlates(page)
    const start = Date.now() - 500
    await sleep(10500)
    return start
  })
  await clip(browser, "app-query", 10, async (page) => {
    await page.goto(APP)
    await sleep(3000)
    await nav(page, "Ask the Grid")
    const start = Date.now() - 500
    const box = page.getByPlaceholder("Plates at CAM-07 today")
    await box.click()
    await box.pressSequentially("What's the busiest camera right now?", { delay: 70 })
    await box.press("Enter")
    await sleep(6500)
    return start
  })
}

const browser = await chromium.launch()
if (what === "shots" || what === "all") await shots(browser)
if (what === "clips" || what === "all") await clips(browser)
await browser.close()
