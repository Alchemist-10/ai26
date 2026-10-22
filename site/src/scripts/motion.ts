// Motion for the story. Progressive enhancement: the page is complete and
// readable before this runs; motion only adds. Under reduced motion every
// function here leaves the static page alone.
import { gsap } from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

gsap.registerPlugin(ScrollTrigger);

export const reducedMotion = () => matchMedia("(prefers-reduced-motion: reduce)").matches;

/* ---------- Spine: one scan line, a detection bracket per chapter, drawn by scroll ---------- */

function spinePath(x: number, height: number, beats: number[]): string {
  // At each chapter the line steps out into a small box, like a detection
  // snapping onto a frame, then returns to the scan line.
  const parts = [`M ${x} 0`];
  for (const y of beats) {
    if (y < 40 || y > height - 60) continue;
    parts.push(
      `L ${x} ${y - 22}`,
      `L ${x + 14} ${y - 22}`,
      `L ${x + 14} ${y + 22}`,
      `L ${x} ${y + 22}`,
    );
  }
  parts.push(`L ${x} ${height}`);
  return parts.join(" ");
}

export function initSpine() {
  const host = document.querySelector<HTMLElement>(".spine");
  const track = document.querySelector<SVGPathElement>("[data-spine-track]");
  const ink = document.querySelector<SVGPathElement>("[data-spine-ink]");
  if (!host || !track || !ink) return;
  const container = host.parentElement as HTMLElement;

  let trigger: ScrollTrigger | undefined;
  let previousWidth = -1;
  let previousHeight = -1;

  const layout = (force = false) => {
    const width = container.clientWidth;
    const height = container.offsetHeight;
    if (!force && width === previousWidth && height === previousHeight) return false;
    previousWidth = width;
    previousHeight = height;
    const x = parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--spine-x")) || 20;
    const top = container.getBoundingClientRect().top + scrollY;
    const beats = [...container.querySelectorAll<HTMLElement>("[data-beat] .chapter__marker")].map(
      (m) => m.getBoundingClientRect().top + scrollY - top + 7,
    );
    const d = spinePath(x, height, beats);
    track.setAttribute("d", d);
    ink.setAttribute("d", d);
    host.classList.add("is-drawn");

    const len = ink.getTotalLength();
    ink.style.strokeDasharray = `${len}`;
    trigger?.kill();
    if (reducedMotion()) {
      ink.style.strokeDashoffset = "0";
      return true;
    }
    // Ink follows the reader: the drawn tip sits ~60% down the viewport.
    trigger = ScrollTrigger.create({
      trigger: container,
      start: "top 60%",
      end: "bottom 60%",
      scrub: 0.6,
      onUpdate: (self) => {
        ink.style.strokeDashoffset = `${len * (1 - self.progress)}`;
      },
    });
    ink.style.strokeDashoffset = `${len * (1 - trigger.progress)}`;
    return true;
  };

  let raf = 0;
  let forceLayout = false;
  const schedule = (force = false) => {
    forceLayout ||= force;
    cancelAnimationFrame(raf);
    raf = requestAnimationFrame(() => {
      const changed = layout(forceLayout);
      forceLayout = false;
      if (changed) ScrollTrigger.refresh();
    });
  };
  const start = () => {
    new ResizeObserver(() => schedule()).observe(container);
    document.fonts?.ready.then(() => schedule(true));
    document.addEventListener("toggle", () => schedule(true), true);
    layout();
  };
  // The story is below the opening viewport. Its static fallback stays visible
  // until the reader approaches it; avoid measuring every chapter during load.
  if (!reducedMotion() && container.getBoundingClientRect().top > innerHeight) {
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) {
        observer.disconnect();
        start();
      }
    });
    observer.observe(container);
  } else start();
}

/* ---------- Reveal: SVG strokes draw, groups stagger in, once ---------- */

export function initReveals(root: ParentNode = document) {
  if (reducedMotion()) return;
  const onceVisible = (target: Element, run: () => void) => {
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) {
        observer.disconnect();
        if (!reducedMotion()) run();
      }
    }, { rootMargin: "0px 0px -20% 0px" });
    observer.observe(target);
  };
  root.querySelectorAll<SVGGeometryElement>("[data-draw]").forEach((el) => {
    onceVisible(el.closest("[data-draw-root]") ?? el, () => {
    const len = el.getTotalLength();
    gsap.fromTo(
      el,
      { strokeDasharray: len, strokeDashoffset: len },
      {
        strokeDashoffset: 0,
        duration: Number(el.dataset.draw) || 1.2,
        ease: "power2.inOut",
      },
    );
    });
  });
  root.querySelectorAll<HTMLElement>("[data-stagger]").forEach((group) => {
    onceVisible(group, () => {
    gsap.from(group.children, {
      opacity: 0,
      y: 18,
      duration: 0.7,
      ease: "power3.out",
      stagger: Number(group.dataset.stagger) || 0.08,
    });
    });
  });
}

/* ---------- Steps: sticky visual + scrolling text, native sticky + IO ---------- */

export function initSteps(root: ParentNode = document) {
  root.querySelectorAll<HTMLElement>("[data-steps]").forEach((el) => {
    const steps = [...el.querySelectorAll<HTMLElement>("[data-step]")];
    const set = (i: number) => {
      el.dataset.active = String(i);
      steps.forEach((s, j) => s.toggleAttribute("data-current", i === j));
    };
    set(0);
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) if (e.isIntersecting) set(steps.indexOf(e.target as HTMLElement));
      },
      { rootMargin: "-45% 0px -45% 0px" },
    );
    steps.forEach((s) => io.observe(s));
  });
}

/* ---------- Count: numbers tick up once when seen ---------- */

export function initCounts(root: ParentNode = document) {
  if (reducedMotion()) return;
  const fmt = new Intl.NumberFormat("en-IN");
  root.querySelectorAll<HTMLElement>("[data-count]").forEach((el) => {
    const end = Number(el.dataset.count);
    const state = { v: 0 };
    gsap.to(state, {
      v: end,
      duration: 1.4,
      ease: "power2.out",
      scrollTrigger: { trigger: el, start: "top 85%", once: true },
      onUpdate: () => (el.textContent = fmt.format(Math.round(state.v))),
    });
  });
}

export { gsap, ScrollTrigger };
