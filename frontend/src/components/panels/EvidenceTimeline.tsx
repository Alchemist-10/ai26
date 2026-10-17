import { useEffect, useState } from "react"
import { getEvents, type Camera, type DetectionEvent } from "@/lib/api"

export function EvidenceTimeline({ cameras, focused }: { cameras: Camera[]; focused: string }) {
  const [events, setEvents] = useState<DetectionEvent[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    const tick = () => getEvents({ camera: focused }).then((e) => alive && setEvents(e.slice(-40).reverse())).catch((reason: Error) => alive && setError(reason.message))
    tick()
    const id = setInterval(tick, 2000)
    return () => {
      alive = false
      clearInterval(id)
    }
  }, [focused])

  const cam = cameras.find((c) => c.id === focused)

  return (
    <div className="flex h-full flex-col gap-2.5 overflow-hidden bg-[#08090d] p-4 text-zinc-100 select-none">
      <div className="flex items-center justify-between border-b border-white/[0.06] pb-2.5">
        <div className="text-xs text-zinc-400">
          Live stream events for <span className="font-mono font-semibold text-white">{cam?.id ?? focused}</span>
          <span className="text-zinc-500 ml-1">
            ({cam && (cam.location_confirmed ? cam.location : "Location unconfirmed")})
          </span>
        </div>
        <span className="rounded border border-white/[0.08] bg-zinc-900/80 px-2 py-0.5 text-[10px] font-mono text-zinc-400">
          {cam?.kind === "plate" ? "Fast-ALPR OCR" : "YOLOv8 + Centroid Tracking"}
        </span>
      </div>

      {error && (
        <div className="rounded-lg border border-rose-500/30 bg-rose-950/40 p-2.5 text-xs text-rose-200">
          Evidence API unavailable: {error}
        </div>
      )}

      <div className="flex-1 overflow-y-auto rounded-xl border border-white/[0.08] bg-[#0c0e15]/80">
        {events.length === 0 && (
          <div className="p-8 text-center text-xs text-zinc-500 font-mono">
            No inference detections logged yet for this channel.
          </div>
        )}
        {events.map((e, i) => (
          <div
            key={i}
            className="flex items-center justify-between gap-3 border-b border-white/[0.04] px-4 py-2.5 transition-colors hover:bg-white/[0.02] last:border-0"
          >
            <div className="flex items-center gap-3 min-w-0">
              <span
                className={`h-2 w-2 rounded-full ${
                  e.kind === "plate" ? "bg-blue-400" : "bg-emerald-400"
                }`}
              />
              <div className="flex flex-col min-w-0">
                <span className="font-mono text-xs font-semibold text-white truncate">
                  {e.kind === "plate" ? e.plate : e.label}
                </span>
                <span className="font-mono text-[10px] text-zinc-500">
                  {new Date(e.ts * 1000).toLocaleTimeString()}
                </span>
              </div>
            </div>

            <span className="inline-flex items-center rounded-md border border-white/[0.08] bg-zinc-900 px-2 py-0.5 font-mono text-[10px] font-semibold text-zinc-300">
              {Math.round(e.confidence * 100)}%
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

