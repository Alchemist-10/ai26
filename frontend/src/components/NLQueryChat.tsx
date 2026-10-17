import { useState, useRef, useEffect } from "react"
import { askNL } from "@/lib/api"
import { CornerDownLeft, Database, Terminal } from "lucide-react"

interface Msg {
  role: "user" | "bot"
  text: string
  sql?: string
}

const PRESETS = [
  "Which plates crossed Kathrikkadavu Junction today?",
  "Show all violations this session",
  "What's the busiest camera right now?",
]

export function NLQueryChat() {
  const [msgs, setMsgs] = useState<Msg[]>([
    {
      role: "bot",
      text: "Ask about plates, cameras, or alerts — answers come from the live detection log.",
    },
  ])
  const [input, setInput] = useState("")
  const [busy, setBusy] = useState(false)
  const chatEndRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [msgs, busy])

  async function send(q: string) {
    if (!q.trim() || busy) return
    setMsgs((m) => [...m, { role: "user", text: q }])
    setInput("")
    setBusy(true)
    try {
      const res = await askNL(q)
      setMsgs((m) => [...m, { role: "bot", text: res.text, sql: res.sql }])
    } catch (error) {
      setMsgs((m) => [
        ...m,
        {
          role: "bot",
          text: `Query unavailable: ${error instanceof Error ? error.message : "backend error"}`,
        },
      ])
    }
    setBusy(false)
  }

  return (
    <div className="flex h-full flex-col gap-3 text-zinc-100 select-none">
      {/* Messages area */}
      <div className="flex-1 space-y-3 overflow-y-auto pr-1">
        {msgs.map((m, i) => (
          <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
            <div
              className={`max-w-[85%] rounded-xl px-4 py-3 text-xs leading-relaxed ${
                m.role === "user"
                  ? "bg-blue-600 text-white font-medium shadow-md shadow-blue-500/20"
                  : "border border-white/[0.08] bg-[#11141e]/90 text-zinc-200 backdrop-blur-md"
              }`}
            >
              <div className="whitespace-pre-wrap">{m.text}</div>
              {m.sql && (
                <div className="mt-2.5 overflow-x-auto rounded-lg border border-white/[0.08] bg-black/60 p-2.5 text-[11px] font-mono text-zinc-300">
                  <div className="mb-1.5 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-blue-400">
                    <Database className="h-3 w-3" />
                    <span>Deterministic SQL</span>
                  </div>
                  <div className="text-zinc-300 font-mono text-[11px] leading-normal">{m.sql}</div>
                </div>
              )}
            </div>
          </div>
        ))}
        {busy && (
          <div className="flex justify-start">
            <div className="flex items-center gap-2 rounded-xl border border-white/[0.08] bg-[#11141e]/90 px-4 py-3 text-xs text-zinc-400">
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-blue-400" />
              <span>Querying grid index...</span>
            </div>
          </div>
        )}
        <div ref={chatEndRef} />
      </div>

      {/* Preset Queries and Info */}
      <div className="flex flex-col gap-2 pt-2.5 border-t border-white/[0.06]">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="inline-flex items-center gap-1.5 rounded-md border border-white/[0.08] bg-zinc-900/80 px-2 py-0.5 text-[10px] font-mono uppercase tracking-wider text-zinc-400">
            <Terminal className="h-3 w-3 text-blue-400" />
            Deterministic SQL Engine
          </span>
          <span className="text-[11px] text-zinc-500 font-mono">Suggested Inquiries:</span>
        </div>

        <div className="flex flex-wrap gap-1.5">
          {PRESETS.map((p) => (
            <button
              key={p}
              type="button"
              onClick={() => send(p)}
              disabled={busy}
              className="cursor-pointer rounded-lg border border-white/[0.08] bg-zinc-900/60 px-3 py-1 text-xs text-zinc-400 transition-colors hover:border-blue-500/40 hover:bg-zinc-800/80 hover:text-white disabled:opacity-50"
            >
              {p}
            </button>
          ))}
        </div>
      </div>

      {/* Input bar */}
      <div className="flex gap-2 pt-1">
        <input
          id="nl-query-input"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send(input)}
          placeholder="Ask about license plates, camera channels, or corridor congestion..."
          disabled={busy}
          className="flex-1 rounded-xl border border-white/[0.08] bg-zinc-900/90 px-3.5 py-2.5 text-xs text-white placeholder:text-zinc-500 outline-none transition-colors focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
        />
        <button
          type="button"
          onClick={() => send(input)}
          disabled={busy || !input.trim()}
          className="cursor-pointer inline-flex items-center gap-1.5 rounded-xl bg-blue-600 hover:bg-blue-500 px-4 py-2.5 text-xs font-semibold text-white transition-colors disabled:opacity-40 disabled:cursor-not-allowed shadow-sm shadow-blue-500/20"
        >
          <span>Query</span>
          <CornerDownLeft className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  )
}
