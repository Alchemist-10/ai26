// Quickstart terminal that types its commands when scrolled into view
// (after Magic UI Terminal / TypingAnimation). Comments describe what happens;
// they are not captured log output.
import { useEffect, useRef, useState } from "react";
import { useInView, useReducedMotion } from "motion/react";

const lines: { cmd?: string; note?: string }[] = [
  { cmd: "git clone https://github.com/moneytosms/ai26 && cd ai26" },
  { note: "# needs Python 3.12, Node.js 22.12+ and uv" },
  { cmd: "uv run run.py" },
  { note: "# dashboard  http://localhost:5174" },
  { note: "# api        http://127.0.0.1:8001" },
  { cmd: "uv run run.py --skip-install" },
  { note: "# fast restart after the first install" },
];
const total = lines.reduce((n, l) => n + (l.cmd ? l.cmd.length : 1), 0);

export default function Terminal() {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { once: true, amount: 0.6 });
  const reduce = useReducedMotion();
  const [typed, setTyped] = useState(total);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!inView || reduce) return;
    setTyped(0);
    let n = 0;
    const id = setInterval(() => { n += 1; setTyped(n); if (n >= total) clearInterval(id); }, 24);
    return () => clearInterval(id);
  }, [inView, reduce]);

  let budget = typed;
  const copy = () => {
    navigator.clipboard?.writeText(lines.filter((l) => l.cmd).slice(0, 2).map((l) => l.cmd).join("\n")).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    }).catch(() => {});
  };

  return (
    <div ref={ref} className="overflow-hidden rounded-xl border border-line bg-[#090c0e] text-left shadow-[0_30px_80px_-30px_rgb(0_0_0/0.6)]">
      <div className="flex h-9 items-center gap-2 border-b border-white/10 px-3.5">
        <span className="size-2.5 rounded-full bg-white/15" /><span className="size-2.5 rounded-full bg-white/15" /><span className="size-2.5 rounded-full bg-white/15" />
        <span className="mx-auto font-mono text-[11px] text-white/40">zsh · ai26</span>
        <button type="button" onClick={copy} className="cursor-pointer rounded border border-white/10 bg-white/5 px-2 py-0.5 font-mono text-[11px] text-white/60 hover:text-white">
          {copied ? "copied" : "copy"}
        </button>
      </div>
      <pre className="m-0 overflow-x-auto border-0 bg-transparent p-5 font-mono text-[13px] leading-7 text-white/85" aria-label="Quickstart commands">
        {lines.map((l, i) => {
          const len = l.cmd ? l.cmd.length : 1;
          const show = Math.max(0, Math.min(len, budget));
          budget -= len;
          if (show === 0) return <div key={i} className="h-7" />;
          return l.cmd ? (
            <div key={i}><span className="text-[oklch(0.79_0.13_182)] select-none">$ </span>{l.cmd.slice(0, show)}{show < len && <span className="ml-px inline-block h-4 w-2 translate-y-0.5 bg-white/70" />}</div>
          ) : (
            <div key={i} className="text-white/40">{l.note}</div>
          );
        })}
      </pre>
    </div>
  );
}
