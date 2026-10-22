// Product tour: tabs that switch app screenshots, with a sliding indicator and
// an auto-advance progress bar (after shadcn Tabs + Magic UI feature tabs).
import { useEffect, useRef, useState } from "react";
import { AnimatePresence, MotionConfig, motion, useInView, useReducedMotion } from "motion/react";

export interface Shot {
  id: string;
  label: string;
  caption: string;
  path: string;
  img: { src: string; avif: string; webp: string; width: number; height: number; alt: string };
}

const DWELL = 7000;

export default function ScreenTabs({ shots }: { shots: Shot[] }) {
  const [active, setActive] = useState(0);
  const [auto, setAuto] = useState(true);
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { amount: 0.4 });
  const reduce = useReducedMotion();
  const running = auto && inView && !reduce;

  useEffect(() => {
    if (!running) return;
    const t = setTimeout(() => setActive((a) => (a + 1) % shots.length), DWELL);
    return () => clearTimeout(t);
  }, [running, active, shots.length]);

  const pick = (i: number) => { setAuto(false); setActive(i); };
  const onKey = (e: React.KeyboardEvent) => {
    const d = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
    if (!d) return;
    e.preventDefault();
    const next = (active + d + shots.length) % shots.length;
    pick(next);
    document.getElementById(`tab-${shots[next].id}`)?.focus();
  };
  const s = shots[active];

  return (
    <MotionConfig reducedMotion="user">
      <div ref={ref}>
        <div role="tablist" aria-label="App screens" onKeyDown={onKey} className="-mx-4 flex gap-1 overflow-x-auto px-4 pb-1 [scrollbar-width:none] sm:mx-0 sm:flex-wrap sm:justify-center sm:px-0">
          {shots.map((t, i) => (
            <button
              key={t.id}
              id={`tab-${t.id}`}
              role="tab"
              type="button"
              aria-selected={i === active}
              aria-controls="tour-panel"
              tabIndex={i === active ? 0 : -1}
              onClick={() => pick(i)}
              className={`relative shrink-0 cursor-pointer rounded-full border-0 bg-transparent px-4 py-2 text-sm font-medium transition-colors ${i === active ? "text-fg" : "text-muted-fg hover:text-fg"}`}
            >
              {i === active && (
                <motion.span layoutId="tour-pill" className="absolute inset-0 overflow-hidden rounded-full border border-line bg-card shadow-[var(--shadow-card)]" transition={{ type: "spring", bounce: 0.18, duration: 0.5 }}>
                  {running && (
                    <motion.span key={active} className="absolute bottom-0 left-0 h-[2px] bg-primary" initial={{ width: "0%" }} animate={{ width: "100%" }} transition={{ duration: DWELL / 1000, ease: "linear" }} />
                  )}
                </motion.span>
              )}
              <span className="relative">{t.label}</span>
            </button>
          ))}
        </div>

        <div id="tour-panel" role="tabpanel" aria-labelledby={`tab-${s.id}`} className="mt-6">
          <div className="relative overflow-hidden rounded-xl border border-line bg-[#07090b] shadow-[0_30px_80px_-30px_rgb(0_0_0/0.6)]">
            <div className="flex h-9 items-center gap-2 border-b border-white/10 bg-[#0e1215] px-3.5">
              <span className="size-2.5 rounded-full bg-white/15" /><span className="size-2.5 rounded-full bg-white/15" /><span className="size-2.5 rounded-full bg-white/15" />
              <span className="mx-auto truncate rounded-md bg-white/5 px-3 py-0.5 font-mono text-[11px] text-white/45">localhost:5174{s.path}</span>
              <span className="w-[42px]" />
            </div>
            <div className="relative aspect-[16/10] bg-black">
              <AnimatePresence initial={false}>
                <motion.picture
                  key={s.id}
                  className="absolute inset-0"
                  initial={{ opacity: 0, scale: 1.015 }}
                  animate={{ opacity: 1, scale: 1 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
                >
                  <source type="image/avif" srcSet={s.img.avif} sizes="(min-width: 1152px) 1100px, 100vw" />
                  <source type="image/webp" srcSet={s.img.webp} sizes="(min-width: 1152px) 1100px, 100vw" />
                  <img src={s.img.src} width={s.img.width} height={s.img.height} alt={s.img.alt} loading="lazy" decoding="async" className="h-full w-full object-contain object-top" />
                </motion.picture>
              </AnimatePresence>
            </div>
          </div>
          <p className="mx-auto mt-4 min-h-[3em] max-w-2xl text-center text-sm text-muted-fg" aria-live="polite">{s.caption}</p>
        </div>
      </div>
    </MotionConfig>
  );
}
