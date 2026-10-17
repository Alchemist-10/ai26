import { useEffect, useState } from "react"
import { getCameras, getStats, type Camera, type Stats } from "@/lib/api"
import { OsmMap, type MapLine } from "@/components/OsmMap"
import { cn } from "@/lib/utils"

const CORRIDORS = [
  ["CAM-01", "CAM-02", "CAM-03"],
  ["CAM-04", "CAM-01", "CAM-05"],
  ["CAM-06", "CAM-07", "CAM-08", "CAM-09"],
]

export function CongestionPage() {
  const [cameras, setCameras] = useState<Camera[]>([])
  const [stats, setStats] = useState<Stats | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getCameras().then(setCameras).catch((reason: Error) => setError(reason.message))
  }, [])

  useEffect(() => {
    let alive = true
    const tick = () => getStats().then((s) => alive && setStats(s)).catch((reason: Error) => alive && setError(reason.message))
    tick()
    const id = setInterval(tick, 2000)
    return () => {
      alive = false
      clearInterval(id)
    }
  }, [])

  const total = stats?.total_events || 1
  const ranked = cameras
    .map((c) => ({ cam: c, count: stats?.per_camera[c.id] ?? 0 }))
    .sort((a, b) => b.count - a.count)
  const load = (cameraId: string) => {
    const count = stats?.per_camera[cameraId] ?? 0
    return count / total
  }
  const congestionColor = (share: number) => (share > 0.35 ? "#ff5c72" : share > 0.18 ? "#ffb545" : "#22d3c8")
  const byId = Object.fromEntries(cameras.map((camera) => [camera.id, camera]))
  const lines: MapLine[] = CORRIDORS.map((corridor, index) => ({
    id: `corridor-${index}`,
    points: corridor
      .map((id) => byId[id])
      .filter(Boolean)
      .map((camera) => [camera.lat, camera.lon] as [number, number]),
    color: congestionColor(corridor.reduce((sum, id) => sum + load(id), 0) / corridor.length),
    width: 8,
  })).filter((line) => line.points.length > 1)

  return (
    <div className="grid h-full grid-cols-[1fr_340px] gap-0 bg-[#08090d] text-zinc-100 select-none">
      {error && (
        <div className="absolute left-4 top-4 z-20 rounded-lg border border-rose-500/30 bg-rose-950/90 p-2.5 text-xs text-rose-200">
          Congestion API unavailable: {error}
        </div>
      )}

      <div className="relative min-h-0 border-r border-white/[0.08] p-4 flex flex-col">
        <div className="mb-3 flex items-center justify-between gap-3 text-xs text-zinc-400">
          <span>Real-time corridor throughput (rolling 5-minute detection window).</span>
          <span className="rounded-md border border-white/[0.08] bg-zinc-900/80 px-2 py-0.5 font-mono text-[10px] text-zinc-400">
            COMPUTED CORRIDOR VECTORS
          </span>
        </div>

        <div className="relative flex-1 overflow-hidden rounded-xl border border-white/[0.08] bg-[#0c0e15]">
          <OsmMap
            lines={lines}
            points={cameras.map((cam) => ({
              id: cam.id,
              lat: cam.lat,
              lon: cam.lon,
              label: cam.id,
              detail: `${stats?.per_camera[cam.id] ?? 0} detections / 5 min`,
              color: congestionColor(load(cam.id)),
              size: 5 + load(cam.id) * 24,
            }))}
            className="h-full w-full"
            ariaLabel="OpenStreetMap live congestion map of Kochi"
          />

          <div className="absolute bottom-3 left-3 flex items-center gap-4 rounded-lg border border-white/[0.08] bg-black/85 px-3 py-1.5 text-xs text-zinc-300 backdrop-blur-md shadow-lg">
            <span className="flex items-center gap-1.5 font-mono text-[11px]">
              <span className="h-2 w-2 rounded-full bg-[#22d3c8]" /> Baseline
            </span>
            <span className="flex items-center gap-1.5 font-mono text-[11px]">
              <span className="h-2 w-2 rounded-full bg-[#ffb545]" /> Elevated
            </span>
            <span className="flex items-center gap-1.5 font-mono text-[11px]">
              <span className="h-2 w-2 rounded-full bg-[#ff5c72]" /> Peak Load
            </span>
          </div>
        </div>
      </div>

      <div className="flex min-h-0 flex-col overflow-y-auto bg-[#0a0c12] p-4 border-l border-white/[0.04]">
        <div className="mb-3 flex items-center justify-between">
          <span className="text-xs font-semibold uppercase tracking-wider text-zinc-400 font-mono">
            Corridor Density Rank
          </span>
          <span className="text-[10px] font-mono text-zinc-500">
            {total} Total Events
          </span>
        </div>

        <div className="flex flex-col gap-2">
          {ranked.map(({ cam, count }, i) => {
            const share = count / total
            const pct = Math.round(share * 100)
            return (
              <div
                key={cam.id}
                className="group flex flex-col gap-1.5 rounded-lg border border-white/[0.06] bg-[#0d1017] p-2.5 transition-colors hover:border-white/[0.12]"
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="w-4 text-center font-mono text-[11px] font-bold text-zinc-500">
                      {i + 1}
                    </span>
                    <span className="font-mono text-xs font-semibold text-white">
                      {cam.id}
                    </span>
                  </div>

                  <span
                    className={cn(
                      "font-mono text-[11px] font-semibold px-2 py-0.5 rounded border",
                      share > 0.35
                        ? "border-rose-500/30 bg-rose-950/40 text-rose-300"
                        : share > 0.18
                        ? "border-amber-500/30 bg-amber-950/40 text-amber-300"
                        : "border-emerald-500/30 bg-emerald-950/30 text-emerald-300"
                    )}
                  >
                    {count} events ({pct}%)
                  </span>
                </div>

                <div className="truncate text-[10px] text-zinc-400 pl-6">
                  {cam.location_confirmed ? cam.location : "Location unconfirmed"}
                </div>

                <div className="mt-1 h-1 w-full overflow-hidden rounded-full bg-white/[0.06]">
                  <div
                    className="h-full rounded-full transition-all duration-500"
                    style={{
                      width: `${Math.min(pct * 2.5, 100)}%`,
                      backgroundColor: congestionColor(share),
                    }}
                  />
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}

