// Live mini-visual: per-track plate consensus. Reads arrive one at a time; three
// consistent reads support a plate, a conflict abstains, a weak read is history only.
// Plate strings are synthetic.
import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion, useInView, useReducedMotion } from "motion/react";

type Read = { text: string; conf: number; bad?: number };
const scenarios: { reads: Read[]; verdict: string; tone: "ok" | "bad" | "warn" }[] = [
  { reads: [{ text: "KA01AB1234", conf: 0.81 }, { text: "KA01AB1234", conf: 0.74 }, { text: "KA01AB1234", conf: 0.66 }], verdict: "Supported: 3 consistent reads", tone: "ok" },
  { reads: [{ text: "KA01AB1234", conf: 0.79 }, { text: "KA01AB1234", conf: 0.71 }, { text: "KA01AB1284", conf: 0.58, bad: 8 }], verdict: "Abstained: conflicting reads", tone: "bad" },
  { reads: [{ text: "KA01AB7234", conf: 0.22 }], verdict: "History only: below 0.35 gate", tone: "warn" },
];
const toneClass = { ok: "border-ok/40 bg-ok-surface text-ok", bad: "border-critical/40 bg-critical-surface text-critical", warn: "border-warn/40 bg-warn-surface text-warn" };

export default function ConsensusDemo() {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { amount: 0.5 });
  const reduce = useReducedMotion();
  const [scene, setScene] = useState(1);
  const [step, setStep] = useState(99);

  useEffect(() => {
    if (!inView || reduce) return;
    const n = scenarios[scene].reads.length;
    const t = setTimeout(() => {
      if (step < n) setStep(step + 1);
      else { setScene((scene + 1) % scenarios.length); setStep(0); }
    }, step < n ? 750 : 2600);
    return () => clearTimeout(t);
  }, [inView, reduce, scene, step]);

  const sc = scenarios[scene];
  const shown = sc.reads.slice(0, step);
  const done = step >= sc.reads.length;

  return (
    <div ref={ref} className="flex h-full flex-col gap-2 font-mono text-[13px]">
      <div className="flex items-center justify-between text-[11px] text-muted-fg">
        <span>CAM-03 · track 12</span><span>window ≤ 8 reads</span>
      </div>
      <ul className="m-0 flex min-h-[118px] list-none flex-col gap-1.5 p-0">
        <AnimatePresence mode="popLayout" initial={false}>
          {shown.map((r, i) => (
            <motion.li
              key={`${scene}-${i}`}
              layout
              initial={{ opacity: 0, x: -10 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0 }}
              className={`flex items-center justify-between rounded-md border px-2.5 py-1.5 ${r.bad ? "border-critical/40" : r.conf < 0.35 ? "border-warn/40" : "border-line"} bg-bg`}
            >
              <span className="tracking-wider">
                {r.bad ? <>{r.text.slice(0, 8)}<span className="text-critical">{r.text[8]}</span>{r.text.slice(9)}</> : r.text}
              </span>
              <span className={r.conf < 0.35 ? "text-warn" : "text-muted-fg"}>{r.conf.toFixed(2)}</span>
            </motion.li>
          ))}
        </AnimatePresence>
      </ul>
      <div className="mt-auto h-8">
        <AnimatePresence mode="wait">
          {done && (
            <motion.p key={scene} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} className={`m-0 rounded-md border px-2.5 py-1.5 font-sans text-xs font-medium ${toneClass[sc.tone]}`}>
              {sc.verdict}
            </motion.p>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
