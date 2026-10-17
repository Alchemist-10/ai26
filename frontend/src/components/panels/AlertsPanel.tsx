import { useEffect, useState } from "react"
import { Bell, CheckCircle2 } from "lucide-react"
import { getAlerts, type Alert } from "@/lib/api"
import { DEMO_ALERTS } from "@/lib/demo"

export function AlertsPanel() {
  const [alerts, setAlerts] = useState<Alert[]>([])
  const [showDemo, setShowDemo] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    const tick = () =>
      getAlerts()
        .then((a) => alive && setAlerts(a))
        .catch((reason: Error) => alive && setError(reason.message))
    tick()
    const id = setInterval(tick, 3000)
    return () => {
      alive = false
      clearInterval(id)
    }
  }, [])

  const displayAlerts = [...alerts, ...(showDemo ? DEMO_ALERTS : [])]

  return (
    <div className="h-full overflow-y-auto bg-[#08090d] text-zinc-100 p-4 sm:p-6 select-none">
      <div className="mx-auto flex max-w-5xl flex-col gap-4">
        {/* Top Header Card */}
        <div className="flex flex-col gap-1 rounded-xl border border-white/[0.08] bg-[#0d1017]/90 p-4 backdrop-blur-md shadow-sm">
          <div className="flex items-center gap-2.5">
            <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-rose-500/10 text-rose-400 border border-rose-500/20">
              <Bell className="h-4 w-4" />
            </div>
            <div>
              <h1 className="text-sm font-semibold text-white tracking-tight">Automated Anomaly & Match Alerts</h1>
              <p className="text-[11px] text-zinc-400">
                Rule-based route-anomaly and cross-camera appearance matches computed continuously from the detection log.
              </p>
            </div>
          </div>
        </div>

        {error && (
          <div className="rounded-lg border border-rose-500/30 bg-rose-950/40 p-3 text-xs text-rose-200">
            Alert API unavailable: {error}
          </div>
        )}

        {/* Demo Controller Console */}
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-white/[0.08] bg-[#0d1017]/90 p-4 backdrop-blur-md">
          <div className="space-y-0.5">
            <div className="text-xs font-semibold text-white tracking-tight">Operator Escalation Review</div>
            <div className="text-[11px] text-zinc-400">
              Toggle labeled walkthrough scenario to inspect human-operator escalation flows.
            </div>
          </div>
          <button
            type="button"
            onClick={() => setShowDemo((value) => !value)}
            className={`cursor-pointer rounded-lg px-3.5 py-1.5 text-xs font-medium transition-all ${
              showDemo
                ? "bg-blue-600 text-white shadow-sm shadow-blue-500/20"
                : "border border-white/[0.08] bg-zinc-900/80 text-zinc-300 hover:bg-zinc-800 hover:text-white"
            }`}
          >
            {showDemo ? "Hide Demonstration Scenarios" : "Preview Demonstration Scenarios"}
          </button>
        </div>

        {showDemo && (
          <div className="flex items-center gap-2 px-1 text-[11px] font-mono uppercase tracking-wider text-amber-400">
            <span className="h-1.5 w-1.5 rounded-full bg-amber-400 animate-pulse" />
            Displaying simulated operator demonstration alerts — not live occurrences
          </div>
        )}

        {/* Alerts List */}
        {displayAlerts.length === 0 ? (
          <div className="flex flex-col items-center justify-center rounded-xl border border-white/[0.08] bg-[#0c0e15]/80 py-16 text-center">
            <CheckCircle2 className="mb-2 h-7 w-7 text-emerald-500/80" />
            <div className="text-sm font-semibold text-zinc-200">No active anomalies detected</div>
            <div className="mt-1 text-xs text-zinc-500 max-w-sm">
              Active detection rules: Cross-camera appearance match, perimeter loitering, and route deviations.
            </div>
          </div>
        ) : (
          <div className="flex flex-col gap-2.5">
            {displayAlerts.map((a, i) => (
              <div
                key={i}
                className="group flex gap-3.5 rounded-xl border border-white/[0.08] bg-[#0d1017]/90 p-4 transition-all hover:border-white/[0.14] backdrop-blur-md shadow-sm"
              >
                <div
                  className={`w-1 flex-none rounded-full ${
                    a.severity === "critical"
                      ? "bg-rose-500 shadow-[0_0_8px_rgba(244,63,94,0.5)]"
                      : a.severity === "warning"
                      ? "bg-amber-400 shadow-[0_0_8px_rgba(251,191,36,0.4)]"
                      : "bg-blue-400 shadow-[0_0_8px_rgba(96,165,250,0.4)]"
                  }`}
                />
                <div className="flex min-w-0 flex-1 flex-col gap-1.5">
                  <div className="flex flex-wrap items-center gap-2">
                    <span
                      className={`inline-flex items-center rounded-md px-2 py-0.5 text-[10px] font-mono font-bold uppercase tracking-wider ${
                        a.severity === "critical"
                          ? "border border-rose-500/30 bg-rose-950/40 text-rose-300"
                          : a.severity === "warning"
                          ? "border border-amber-500/30 bg-amber-950/40 text-amber-300"
                          : "border border-blue-500/30 bg-blue-950/40 text-blue-300"
                      }`}
                    >
                      {a.severity}
                    </span>
                    <span className="inline-flex items-center rounded-md border border-white/[0.08] bg-zinc-900/80 px-2 py-0.5 text-[10px] font-mono text-zinc-400 uppercase tracking-wider">
                      {a.type}
                    </span>
                  </div>
                  <div className="text-sm font-semibold text-white tracking-tight">{a.summary}</div>
                  <div className="text-xs text-zinc-400 leading-relaxed">{a.detail}</div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
