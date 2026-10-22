// Pipeline diagram with light packets travelling along curved beams
// (after Magic UI AnimatedBeam). Paths are measured from the DOM, so the same
// markup works as a left-to-right graph on desktop and top-to-bottom on phones.
import { useLayoutEffect, useRef, useState } from "react";
import { icons, type IconName } from "../lib/icons";

interface Node { id: string; icon: IconName; title: string; sub: string; accent?: boolean }

const columns: Node[][] = [
  [
    { id: "rtsp", icon: "radio", title: "Live cameras", sub: "RTSP, any number" },
    { id: "rec", icon: "video", title: "Recordings", sub: "MP4, hash-checked" },
  ],
  [{ id: "sched", icon: "clock", title: "Scheduler", sub: "global frame budget", accent: true }],
  [
    { id: "yolo", icon: "scan", title: "YOLOv8n", sub: "vehicles and people" },
    { id: "plate", icon: "type", title: "Plate OCR", sub: "detector + MobileViT-v2" },
  ],
  [
    { id: "track", icon: "route", title: "Tracker", sub: "per-camera motion + box" },
    { id: "cons", icon: "checks", title: "Consensus", sub: "3 reads or abstain", accent: true },
  ],
  [{ id: "db", icon: "database", title: "Observation store", sub: "reads, audit, hashes" }],
  [
    { id: "ui", icon: "dashboard", title: "Dashboard", sub: "wall and review" },
    { id: "q", icon: "search", title: "Query", sub: "bounded grammar" },
    { id: "jr", icon: "map", title: "Journeys", sub: "cross-camera links" },
    { id: "ev", icon: "file", title: "Evidence", sub: "hash-verified export" },
  ],
];

const edges: [string, string][] = [
  ["rtsp", "sched"], ["rec", "sched"], ["sched", "yolo"], ["sched", "plate"],
  ["yolo", "track"], ["plate", "cons"], ["track", "db"], ["cons", "db"],
  ["db", "ui"], ["db", "q"], ["db", "jr"], ["db", "ev"],
];

export default function PipelineBeam() {
  const box = useRef<HTMLDivElement>(null);
  const nodes = useRef(new Map<string, HTMLElement>());
  const [paths, setPaths] = useState<{ d: string; key: string }[]>([]);
  const [size, setSize] = useState({ w: 0, h: 0 });

  useLayoutEffect(() => {
    const el = box.current!;
    const measure = () => {
      const c = el.getBoundingClientRect();
      const wide = matchMedia("(min-width: 1024px)").matches;
      setSize({ w: c.width, h: c.height });
      setPaths(edges.map(([a, b]) => {
        const r1 = nodes.current.get(a)!.getBoundingClientRect();
        const r2 = nodes.current.get(b)!.getBoundingClientRect();
        if (wide) {
          const sx = r1.right - c.left, sy = r1.top + r1.height / 2 - c.top;
          const ex = r2.left - c.left, ey = r2.top + r2.height / 2 - c.top;
          const mx = (sx + ex) / 2;
          return { key: a + b, d: `M${sx},${sy} C${mx},${sy} ${mx},${ey} ${ex},${ey}` };
        }
        const sx = r1.left + r1.width / 2 - c.left, sy = r1.bottom - c.top;
        const ex = r2.left + r2.width / 2 - c.left, ey = r2.top - c.top;
        const my = (sy + ey) / 2;
        return { key: a + b, d: `M${sx},${sy} C${sx},${my} ${ex},${my} ${ex},${ey}` };
      }));
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  return (
    <div ref={box} className="relative">
      <svg className="pointer-events-none absolute inset-0 overflow-visible" width={size.w} height={size.h} viewBox={`0 0 ${size.w || 1} ${size.h || 1}`} fill="none" aria-hidden="true">
        {paths.map((p, i) => (
          <g key={p.key}>
            <path d={p.d} stroke="var(--border-strong)" strokeWidth="1.5" />
            <path d={p.d} pathLength={1} className="beam-packet" stroke="var(--primary)" strokeWidth="2" strokeLinecap="round" style={{ animationDelay: `${(i % 4) * 0.55}s` }} />
          </g>
        ))}
      </svg>
      <ol className="relative m-0 flex list-none flex-col gap-9 p-0 lg:flex-row lg:justify-between lg:gap-5">
        {columns.map((col, ci) => (
          <li key={ci} className="flex flex-wrap justify-center gap-2.5 lg:min-w-0 lg:flex-1 lg:flex-col lg:flex-nowrap lg:gap-4">
            {col.map((n) => (
              <div
                key={n.id}
                ref={(el) => { if (el) nodes.current.set(n.id, el); }}
                className={`flex min-w-0 basis-[46%] items-center gap-2.5 rounded-xl border bg-card p-2.5 shadow-[var(--shadow-card)] sm:basis-[30%] lg:basis-auto ${n.accent ? "border-primary/50 shadow-[0_0_24px_-6px_var(--glow)]" : "border-line"}`}
              >
                <span className={`grid size-8 shrink-0 place-items-center rounded-lg ${n.accent ? "bg-primary text-primary-fg" : "bg-muted text-primary"}`}>
                  <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" dangerouslySetInnerHTML={{ __html: icons[n.icon] }} />
                </span>
                <span className="min-w-0">
                  <span className="block text-[13px] font-medium leading-tight">{n.title}</span>
                  <span className="mt-0.5 block text-[11px] leading-tight text-muted-fg">{n.sub}</span>
                </span>
              </div>
            ))}
          </li>
        ))}
      </ol>
    </div>
  );
}
