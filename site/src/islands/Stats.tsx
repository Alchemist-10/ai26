// Stat strip with count-up numbers (after Magic UI NumberTicker, built on motion).
// Server HTML already holds the final values, so no-JS visitors see them too.
import { useEffect, useRef } from "react";
import { useInView, useMotionValue, useReducedMotion, useSpring } from "motion/react";

export interface Stat { value: number; decimals?: number; prefix?: string; suffix?: string; label: string; note: string }

function Ticker({ value, decimals = 0 }: { value: number; decimals?: number }) {
  const ref = useRef<HTMLSpanElement>(null);
  const mv = useMotionValue(0);
  const spring = useSpring(mv, { damping: 40, stiffness: 90 });
  const inView = useInView(ref, { once: true, margin: "0px 0px -10% 0px" });
  const reduce = useReducedMotion();
  const fmt = (n: number) => n.toLocaleString("en-IN", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });

  useEffect(() => {
    if (reduce || !inView) return;
    const off = spring.on("change", (v) => { if (ref.current) ref.current.textContent = fmt(v); });
    mv.set(value);
    return off;
  }, [inView, reduce]);

  return <span ref={ref}>{fmt(value)}</span>;
}

export default function Stats({ stats }: { stats: Stat[] }) {
  return (
    <dl className="grid grid-cols-2 gap-px overflow-hidden rounded-2xl border border-line bg-line lg:grid-cols-5">
      {stats.map((s, i) => (
        <div key={s.label} className={`bg-bg p-5 sm:p-6 ${i === stats.length - 1 ? "col-span-2 lg:col-span-1" : ""}`}>
          <dt className="sr-only">{s.label}</dt>
          <dd className="m-0">
            <span className="block font-mono text-3xl font-medium tracking-tight tabular-nums sm:text-4xl">
              {s.prefix}<Ticker value={s.value} decimals={s.decimals} />{s.suffix && <span className="text-primary">{s.suffix}</span>}
            </span>
            <span className="mt-2 block text-sm font-medium">{s.label}</span>
            <span className="mt-1 block text-xs text-muted-fg">{s.note}</span>
          </dd>
        </div>
      ))}
    </dl>
  );
}
