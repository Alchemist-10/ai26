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
  "Show configured alerts today",
  "What's the busiest camera right now?",
]

export function NLQueryChat() {
  const [msgs, setMsgs] = useState<Msg[]>([
    {
      role: "bot",
      text: "Ask about plates, cameras, vehicle classes or alerts. Add today or a date to search retained history; otherwise the last five minutes are used.",
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
    <div className="flex h-full flex-col gap-3 font-sans text-white">
      {/* Messages area */}
      <div className="flex-1 space-y-3 overflow-y-auto pr-1">
        {msgs.map((m, i) => (
          <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
            <div
              className={`max-w-[85%] rounded-lg px-4 py-2.5 text-xs leading-relaxed ${
                m.role === "user"
                  ? "bg-white text-black font-semibold shadow-sm"
                  : "border border-zinc-800 bg-zinc-900/80 text-zinc-200"
              }`}
            >
              <div className="whitespace-pre-wrap">{m.text}</div>
              {m.sql && (
                <div className="mt-2 overflow-x-auto rounded border border-zinc-800 bg-black/60 p-2 text-[11px] text-zinc-400 font-sans">
                  <div className="mb-1 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-zinc-500">
                    <Database className="h-3 w-3" />
                    <span>Query explanation</span>
                  </div>
                  <div className="text-zinc-300 font-sans">{m.sql}</div>
                </div>
              )}
            </div>
          </div>
        ))}
        {busy && (
          <div className="flex justify-start">
            <div className="flex items-center gap-2 rounded-lg border border-zinc-800 bg-zinc-900/80 px-4 py-2.5 text-xs text-zinc-400 font-sans">
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-zinc-400" />
              <span>Querying grid index...</span>
            </div>
          </div>
        )}
        <div ref={chatEndRef} />
      </div>

      {/* Preset Queries and Info */}
      <div className="flex flex-col gap-2 pt-2 border-t border-zinc-900">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="inline-flex items-center gap-1.5 rounded border border-zinc-800 bg-zinc-900/80 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider text-zinc-400">
            <Terminal className="h-3 w-3" />
            Deterministic Query Engine / Not LLM
          </span>
          <span className="text-[11px] text-zinc-500">Quick inquiries:</span>
        </div>

        <div className="flex flex-wrap gap-1.5">
          {PRESETS.map((p) => (
            <button
              key={p}
              type="button"
              onClick={() => send(p)}
              disabled={busy}
              className="cursor-pointer rounded-full border border-zinc-800 bg-zinc-900/60 px-3 py-1 text-xs text-zinc-400 font-sans transition-colors hover:border-zinc-600 hover:bg-zinc-850 hover:text-white disabled:opacity-50"
            >
              {p}
            </button>
          ))}
        </div>
      </div>

      {/* Input bar */}
      <div className="flex gap-2">
        <input
          id="nl-query-input"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send(input)}
          aria-label="Question about camera observations"
          maxLength={500}
          placeholder="Plates at CAM-07 today"
          disabled={busy}
          className="flex-1 rounded-md border border-zinc-800 bg-zinc-900/70 px-3.5 py-2.5 text-base font-sans text-white placeholder:text-zinc-600 outline-none transition-colors focus:border-zinc-500 focus:ring-1 focus:ring-zinc-500"
        />
        <button
          type="button"
          onClick={() => send(input)}
          disabled={busy || !input.trim()}
          className="cursor-pointer inline-flex items-center gap-1.5 rounded-md bg-white px-4 py-2.5 text-xs font-semibold text-black transition-colors hover:bg-zinc-200 disabled:opacity-50 disabled:cursor-not-allowed shadow-sm font-sans"
        >
          <span>Ask</span>
          <CornerDownLeft className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  )
}
