import { usePolling } from "@/hooks/usePolling"
import { useState } from "react"
import { getEvents, type Camera, type DetectionEvent } from "@/lib/api"

export function EvidenceTimeline({ cameras, focused }: { cameras: Camera[]; focused: string }) {
  const [events, setEvents] = useState<DetectionEvent[]>([])
  const [error, setError] = useState<string | null>(null)

  usePolling(async signal => {
    try {
      const result = await getEvents({ camera: focused, limit: 40 }, signal)
      if (!signal.aborted) { setEvents(result.reverse()); setError(null) }
    } catch (reason) { if (!signal.aborted) setError(reason instanceof Error ? reason.message : "Evidence unavailable") }
  }, 5000)

  const cam = cameras.find((c) => c.id === focused)

  return (
    <div className="flex h-full flex-col gap-2 overflow-hidden bg-black p-3 font-sans text-white">
      <div className="text-xs text-zinc-400 font-sans">
        Live detections for <span className="font-semibold text-white">{cam?.id ?? focused}</span>
        {cam && (cam.location_confirmed ? ` (${cam.location})` : " (location unconfirmed)")} — real
        {cam?.kind === "plate" ? " Fast-ALPR OCR reads" : " YOLOv8 vehicle detections"}, last five minutes
      </div>
      {error && <div className="rounded-md border border-red-500/30 bg-red-950/40 p-2 text-xs text-red-200 font-sans">Evidence API unavailable: {error}</div>}
      <div className="flex-1 overflow-y-auto rounded-md border border-zinc-800 bg-zinc-950">
        {events.length === 0 && (
          <div className="p-6 text-center text-xs text-zinc-500 font-sans">
            No detections in this interval. Check camera health and source availability.
          </div>
        )}
        {events.map((e, i) => (
          <div key={e.event_id || i} className="flex items-center justify-between gap-3 border-b border-zinc-800/80 px-3.5 py-2.5 transition-colors hover:bg-zinc-900/50 last:border-0">
            <div className="flex flex-col">
              <span className="text-xs font-semibold text-white tracking-tight font-sans">
                {e.kind === "plate" ? e.plate || "Unreadable plate region" : e.label}
              </span>
              <span className="text-[11px] text-zinc-500 font-sans">
                {`${new Date(e.ts * 1000).toLocaleTimeString()} · track ${e.track_id ?? "unknown"} · ${e.identity_status ?? "vehicle"}`}
              </span>
            </div>
            <span className="inline-flex items-center rounded border border-zinc-800 bg-zinc-900 px-2 py-0.5 text-[11px] font-sans font-medium text-zinc-300">
              {Math.round(e.confidence * 100)}%
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}
