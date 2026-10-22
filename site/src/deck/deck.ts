// Deck runtime: builds, effects, presenter tools, print mode.
const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;
const root = document.documentElement;
const slides = [...document.querySelectorAll<HTMLElement>(".stage > .slide")];
const stage = $("stage");
const viewport = $("viewport");
const hud = document.querySelector<HTMLElement>(".hud")!;
const total = slides.length;
const builds = slides.map((s) => Number(s.dataset.builds || 0));
const titles = slides.map((s) => s.querySelector("h1, h2")?.textContent?.trim() || s.getAttribute("aria-label") || "");
const isPrint = root.classList.contains("print");
const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;

slides.forEach((s, k) => s.style.setProperty("--n", `"${String(k + 1).padStart(2, "0")}"`));

let i = 0;
let b = 0;
let gen = 0; // bumps on every slide change so running effects stop

/* ---------- effects ---------- */
const SETS: Record<string, string> = {
  plate: "ABCDEFGHJKLMNPRSTUVWXYZ0123456789",
  ch: "ABCDEFGHJKLMNPRSTUVWXYZ0123456789",
  hex: "0123456789abcdef",
  title: "ABCDEFGHIJKLMNOPQRSTUVWXYZ#%&@$/",
};
const finalText = (el: HTMLElement) => (el.dataset.final ??= el.textContent || "");

const scramble = (el: HTMLElement, delay: number) => {
  const final = finalText(el);
  const set = SETS[el.dataset.scramble || "plate"] || SETS.plate;
  const g = gen;
  const dur = 500 + final.length * 45;
  const t0 = performance.now() + delay;
  const rnd = () => set[Math.floor(Math.random() * set.length)];
  const step = (t: number) => {
    if (g !== gen) { el.textContent = final; return; }
    const k = Math.max(0, (t - t0) / dur);
    const n = Math.floor(k * final.length);
    el.textContent = final.slice(0, n) + [...final.slice(n)].map((c) => (/[\s…·?]/.test(c) ? c : rnd())).join("");
    if (k < 1) requestAnimationFrame(step);
    else el.textContent = final;
  };
  requestAnimationFrame(step);
};

const count = (el: HTMLElement) => {
  const target = Number(el.dataset.count);
  const dec = Number(el.dataset.dec || 0);
  const fmt = (v: number) => v.toLocaleString("en-IN", { minimumFractionDigits: dec, maximumFractionDigits: dec });
  const g = gen;
  const t0 = performance.now();
  const step = (t: number) => {
    const k = g !== gen ? 1 : Math.min(1, (t - t0) / 1300);
    el.textContent = fmt(target * (1 - Math.pow(1 - k, 3)));
    if (k < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
};

const race = (box: HTMLElement) => {
  const lanes = [...box.querySelectorAll<HTMLElement>(".lane")];
  const clock = box.querySelector<HTMLElement>(".race__t")!;
  const g = gen;
  const t0 = performance.now() + 400;
  const set = (t: number) => {
    lanes.forEach((l) => {
      const rel = Number(l.dataset.rel);
      l.style.setProperty("--p", String(Math.min(1, t / rel)));
      l.classList.toggle("done", t >= rel);
    });
    clock.textContent = Math.min(t, 1).toFixed(2);
  };
  set(0);
  const step = (now: number) => {
    const t = g !== gen ? 1 : Math.max(0, (now - t0) / 3200);
    set(t);
    if (t < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
};

const runEffects = (el: Element) => {
  if (isPrint || reduced || el.closest(".static")) return;
  const host = el as HTMLElement;
  const baseDelay = (parseFloat(getComputedStyle(host).transitionDelay) || 0) * 1000;
  const scr = [...(host.matches("[data-scramble]") ? [host] : []), ...host.querySelectorAll<HTMLElement>("[data-scramble]")];
  scr.forEach((s, k) => scramble(s, baseDelay + (s.dataset.scramble === "ch" ? k * 90 : 0)));
  const cnt = [...(host.matches("[data-count]") ? [host] : []), ...host.querySelectorAll<HTMLElement>("[data-count]")];
  cnt.forEach(count);
  if (host.matches("[data-race]")) race(host);
};

/* ---------- builds ---------- */
const applyBuild = (slide: HTMLElement, upTo: number, effects = true) => {
  slide.dataset.b = String(upTo);
  slide.querySelectorAll<HTMLElement>("[data-at]").forEach((el) => {
    const on = Number(el.getAttribute("data-at")) <= upTo;
    const was = el.classList.contains("on");
    el.classList.toggle("on", on);
    if (on && !was && effects) runEffects(el);
  });
};

/* ---------- layout ---------- */
const fit = () => {
  if (isPrint) return;
  const s = Math.min(viewport.clientWidth / 1280, viewport.clientHeight / 720);
  root.style.setProperty("--s", String(s));
  viewport.style.setProperty("--s", String(s));
};

/* ---------- media ---------- */
const syncMedia = () => {
  slides.forEach((s, k) =>
    s.querySelectorAll("video").forEach((v) => {
      if (k === i && !isPrint) void v.play().catch(() => {});
      else { v.pause(); v.currentTime = 0; }
    }),
  );
};

/* ---------- show ---------- */
const sweep = document.createElement("span");
sweep.className = "sweep";
stage.append(sweep);
const bar = $("bar");
const countEl = $("count");

const show = (nextI: number, nextB: number) => {
  const changed = nextI !== i;
  i = nextI;
  b = nextB;
  if (changed) gen++;
  slides.forEach((s, k) => {
    s.classList.toggle("is-active", k === i);
    s.classList.toggle("is-past", k < i);
    s.classList.toggle("is-future", k > i);
    if (k !== i) { s.querySelectorAll(".on").forEach((el) => el.classList.remove("on")); s.dataset.b = "0"; }
  });
  if (changed) {
    const s = slides[i];
    s.querySelectorAll(".on").forEach((el) => el.classList.remove("on"));
    void s.offsetWidth;
    requestAnimationFrame(() => applyBuild(s, b));
    if (!reduced) { sweep.classList.remove("go"); void sweep.offsetWidth; sweep.classList.add("go"); }
    syncMedia();
  } else {
    applyBuild(slides[i], b);
  }
  countEl.textContent = `${i + 1} / ${total}`;
  bar.style.setProperty("--p", String((i + (builds[i] ? b / (builds[i] + 1) : 0)) / Math.max(1, total - 1)));
  history.replaceState(null, "", `${location.search}#${i + 1}`);
  renderNotes();
  ovItems.forEach((el, k) => el.classList.toggle("cur", k === i));
};

const next = () => {
  if (b < builds[i]) show(i, b + 1);
  else if (i < total - 1) show(i + 1, 0);
};
const prev = () => {
  if (b > 0) show(i, b - 1);
  else if (i > 0) show(i - 1, builds[i - 1]);
};

/* ---------- notes ---------- */
const notesEl = $("notes");
const t0 = Date.now();
const clock = (ms: number) => {
  const s = Math.floor(ms / 1000);
  return [Math.floor(s / 3600), Math.floor(s / 60) % 60, s % 60].map((n) => String(n).padStart(2, "0")).join(":");
};
function renderNotes() {
  if (notesEl.hidden) return;
  $("np-n").textContent = `${i + 1} / ${total}`;
  $("np-title").textContent = titles[i];
  $("np-next").textContent = i < total - 1 ? titles[i + 1] : "end";
  $("np-body").innerHTML = slides[i].querySelector(".notes")?.innerHTML || "<p>No notes.</p>";
}
const setNotes = (open: boolean) => {
  notesEl.hidden = !open;
  document.body.style.setProperty("--notes-h", open ? `${Math.round(innerHeight * 0.3)}px` : "0px");
  $("b-notes").setAttribute("aria-pressed", String(open));
  fit();
  renderNotes();
};
setInterval(() => {
  const t = clock(Date.now() - t0);
  $("tc").textContent = t;
  if (!notesEl.hidden) $("np-time").textContent = t;
}, 1000);

/* ---------- overview ---------- */
const ov = $("overview");
const grid = $("ov-grid");
const ovItems: HTMLElement[] = [];
const staticClone = (s: HTMLElement, k: number) => {
  const c = s.cloneNode(true) as HTMLElement;
  c.classList.remove("is-past", "is-future");
  c.classList.add("is-active", "static");
  c.removeAttribute("aria-label");
  c.querySelector(".notes")?.remove();
  c.querySelectorAll("img").forEach((img) => { img.decoding = "sync"; });
  c.querySelectorAll("video").forEach((v) => { v.preload = "none"; v.removeAttribute("src"); });
  applyBuild(c, builds[k], false);
  return c;
};
const sizeThumbs = () => ovItems.forEach((el) => el.style.setProperty("--k", String(el.clientWidth / 1280)));
const setOverview = (open: boolean) => {
  if (open && !ovItems.length) {
    slides.forEach((s, k) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "ov__item";
      btn.dataset.n = String(k + 1);
      btn.setAttribute("aria-label", `Slide ${k + 1}: ${titles[k]}`);
      btn.append(staticClone(s, k));
      btn.addEventListener("click", () => { setOverview(false); show(k, 0); });
      grid.append(btn);
      ovItems.push(btn);
    });
  }
  ov.hidden = !open;
  $("b-ov").setAttribute("aria-pressed", String(open));
  if (open) {
    sizeThumbs();
    ovItems.forEach((el, k) => el.classList.toggle("cur", k === i));
    ovItems[i]?.focus();
    ovItems[i]?.scrollIntoView({ block: "center" });
  }
};

/* ---------- help, theme, fullscreen ---------- */
const help = $("help");
const setHelp = (open: boolean) => { help.hidden = !open; };
help.addEventListener("click", () => setHelp(false));
const toggleTheme = () => {
  const dark = root.dataset.theme ? root.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
  root.dataset.theme = dark ? "light" : "dark";
  try { localStorage.setItem("sakshi-theme", root.dataset.theme); } catch {}
};
const toggleFs = () => {
  if (document.fullscreenElement) void document.exitFullscreen();
  else void document.documentElement.requestFullscreen?.();
};

/* ---------- print ---------- */
const buildAll = () => slides.forEach((s, k) => {
  s.classList.remove("is-past", "is-future");
  s.classList.add("is-active", "static");
  applyBuild(s, builds[k], false);
});

if (isPrint) {
  buildAll();
  // Chromium can leave async-decoded cropped images unpainted in this long static layout.
  document.querySelectorAll("img").forEach((img) => { img.decoding = "sync"; });
} else {
  addEventListener("beforeprint", () => { root.classList.add("print"); buildAll(); });
  addEventListener("afterprint", () => {
    root.classList.remove("print");
    slides.forEach((s) => s.classList.remove("static"));
    const k = i;
    i = -1;
    show(k, b);
  });

  addEventListener("keydown", (e) => {
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    const k = e.key;
    if (k === "Escape") { setOverview(false); setHelp(false); return; }
    if (k === "?") { setHelp(!!help.hidden); return; }
    if (!ov.hidden) { if (k.toLowerCase() === "o") setOverview(false); return; }
    if (["ArrowRight", "ArrowDown", "PageDown", " ", "Enter"].includes(k)) { e.preventDefault(); next(); }
    else if (["ArrowLeft", "ArrowUp", "PageUp", "Backspace"].includes(k)) { e.preventDefault(); prev(); }
    else if (k === "Home") show(0, 0);
    else if (k === "End") show(total - 1, builds[total - 1]);
    else if (k.toLowerCase() === "f") toggleFs();
    else if (k.toLowerCase() === "n") setNotes(!!notesEl.hidden);
    else if (k.toLowerCase() === "o") setOverview(true);
    else if (k.toLowerCase() === "t") toggleTheme();
  });

  stage.addEventListener("click", (e) => {
    if ((e.target as HTMLElement).closest("a, button, video")) return;
    next();
  });

  let x0: number | null = null;
  stage.addEventListener("pointerdown", (e) => { x0 = e.clientX; });
  addEventListener("pointerup", (e) => {
    if (x0 === null) return;
    const dx = e.clientX - x0;
    x0 = null;
    if (Math.abs(dx) > 60) (dx < 0 ? next : prev)();
  });

  $("next").addEventListener("click", next);
  $("prev").addEventListener("click", prev);
  $("fs").addEventListener("click", toggleFs);
  $("b-notes").addEventListener("click", () => setNotes(!!notesEl.hidden));
  $("b-ov").addEventListener("click", () => setOverview(!!ov.hidden));
  $("b-help").addEventListener("click", () => setHelp(!!help.hidden));

  let idle: number | undefined;
  const wake = () => {
    hud.classList.remove("idle");
    clearTimeout(idle);
    idle = window.setTimeout(() => hud.classList.add("idle"), 2800);
  };
  addEventListener("mousemove", wake);
  addEventListener("keydown", wake);
  wake();

  addEventListener("resize", () => {
    if (!notesEl.hidden) document.body.style.setProperty("--notes-h", `${Math.round(innerHeight * 0.3)}px`);
    fit();
    if (!ov.hidden) sizeThumbs();
  });
  addEventListener("hashchange", () => {
    const n = Number(location.hash.slice(1)) - 1;
    if (n >= 0 && n < total && n !== i) show(n, 0);
  });

  fit();
  const start = Number(location.hash.slice(1)) - 1;
  i = -1;
  show(start >= 0 && start < total ? start : 0, 0);
}
