import { useEffect, useState } from "react"
import { ArrowRight, BarChart3, Activity, Video } from "lucide-react"
import { getCameras, getStats, type Camera, type Stats } from "@/lib/api"
import { OsmMap } from "@/components/OsmMap"
import { DEMO_FLOWS } from "@/lib/demo"

export function AnalyticsPanel() {
  const [stats, setStats] = useState<Stats | null>(null)
  const [cameras, setCameras] = useState<Camera[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getCameras().then(setCameras).catch((reason: Error) => setError(reason.message))
  }, [])

  useEffect(() => {
    let alive = true
    const tick = () =>
      getStats()
        .then((s) => alive && setStats(s))
        .catch((reason: Error) => alive && setError(reason.message))
    tick()
    const id = setInterval(tick, 2000)
    return () => {
      alive = false
      clearInterval(id)
    }
  }, [])

  const perCam = stats ? Object.entries(stats.per_camera).sort((a, b) => b[1] - a[1]) : []
  const max = perCam.length ? perCam[0][1] : 1
  const total = stats?.total_events || 1
  const mapColor = (share: number) => (share > 0.35 ? "#ff5c72" : share > 0.18 ? "#ffb545" : "#22d3c8")

  return (
    <div className="h-full overflow-y-auto bg-[#08090d] text-zinc-100 p-4 sm:p-6 select-none">
      <div className="mx-auto flex max-w-5xl flex-col gap-4">
        {/* Top Header Card */}
        <div className="flex flex-col gap-1 rounded-xl border border-white/[0.08] bg-[#0d1017]/90 p-4 backdrop-blur-md shadow-sm">
          <div className="flex items-center gap-2.5">
            <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-blue-600/20 text-blue-400 border border-blue-500/30">
              <BarChart3 className="h-4 w-4" />
            </div>
            <div>
              <h1 className="text-sm font-semibold text-white tracking-tight">Traffic & Detection Analytics</h1>
              <p className="text-[11px] text-zinc-400">
                Rolling 5-minute detection window. Real event counts normalized to prevent looping demo artifacts.
              </p>
            </div>
          </div>
        </div>

        {error && (
          <div className="rounded-lg border border-rose-500/30 bg-rose-950/40 p-3 text-xs text-rose-200">
            Analytics API unavailable: {error}
          </div>
        )}

        {/* Map Overview Section */}
        <div className="relative h-64 overflow-hidden rounded-xl border border-white/[0.08] bg-[#0c0e15]">
          <OsmMap
            points={cameras.map((cam) => {
              const share = (stats?.per_camera[cam.id] ?? 0) / total
              return { id: cam.id, lat: cam.lat, lon: cam.lon, label: cam.id, color: mapColor(share), size: 5 + share * 16 }
            })}
            className="h-full w-full"
            ariaLabel="OpenStreetMap congestion overview of Kochi"
          />
          <div className="absolute bottom-2.5 left-2.5 z-10 flex items-center gap-4 rounded-lg border border-white/[0.08] bg-black/85 px-3 py-1.5 text-[11px] font-mono text-zinc-300 backdrop-blur-md shadow-lg">
            <span className="flex items-center gap-1.5">
              <span className="h-2 w-2 rounded-full bg-[#22d3c8]" /> Baseline
            </span>
            <span className="flex items-center gap-1.5">
              <span className="h-2 w-2 rounded-full bg-[#ffb545]" /> Elevated
            </span>
            <span className="flex items-center gap-1.5">
              <span className="h-2 w-2 rounded-full bg-[#ff5c72]" /> Peak Load
            </span>
          </div>
        </div>

        {/* Metric Summary Cards */}
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <div className="rounded-xl border border-white/[0.08] bg-[#0d1017]/90 p-4 backdrop-blur-md shadow-sm">
            <div className="flex items-center justify-between text-zinc-400">
              <span className="text-[11px] font-mono font-medium uppercase tracking-wider text-zinc-400">Detections (5 min)</span>
              <Activity className="h-3.5 w-3.5 text-blue-400" />
            </div>
            <div className="mt-2 text-2xl font-bold tracking-tight text-white tabular-nums font-mono">
              {stats?.total_events ?? "—"}
            </div>
            <div className="mt-1 text-[11px] text-zinc-500">Verified vehicle & plate inferences</div>
          </div>

          <div className="rounded-xl border border-white/[0.08] bg-[#0d1017]/90 p-4 backdrop-blur-md shadow-sm">
            <div className="flex items-center justify-between text-zinc-400">
              <span className="text-[11px] font-mono font-medium uppercase tracking-wider text-zinc-400">Confidence Score</span>
              <Activity className="h-3.5 w-3.5 text-emerald-400" />
            </div>
            <div className="mt-2 text-2xl font-bold tracking-tight text-white tabular-nums font-mono">
              {stats ? `${Math.round(stats.avg_confidence * 100)}%` : "—"}
            </div>
            <div className="mt-1 text-[11px] text-zinc-500">Average model detection certainty</div>
          </div>

          <div className="rounded-xl border border-white/[0.08] bg-[#0d1017]/90 p-4 backdrop-blur-md shadow-sm">
            <div className="flex items-center justify-between text-zinc-400">
              <span className="text-[11px] font-mono font-medium uppercase tracking-wider text-zinc-400">Active Sensor Channels</span>
              <Video className="h-3.5 w-3.5 text-blue-400" />
            </div>
            <div className="mt-2 flex items-baseline gap-2 text-2xl font-bold tracking-tight text-white tabular-nums font-mono">
              {cameras.length || "—"}
              <span className="text-xs font-semibold text-emerald-400 font-mono">online</span>
            </div>
            <div className="mt-1 text-[11px] text-zinc-500">Continuous RTSP/MJPEG pipelines</div>
          </div>
        </div>

        {/* Detections per camera breakdown */}
        <div className="rounded-xl border border-white/[0.08] bg-[#0d1017]/90 p-4 backdrop-blur-md shadow-sm">
          <div className="mb-3.5 flex items-center justify-between">
            <div className="text-xs font-semibold uppercase tracking-wider text-zinc-400 font-mono">
              Channel Volume Distribution
            </div>
            <span className="text-[11px] text-zinc-500 font-mono">Rolling window</span>
          </div>
          <div className="flex flex-col gap-2.5">
            {perCam.map(([cam, count]) => (
              <div key={cam} className="flex items-center gap-3">
                <span className="w-20 text-xs font-mono font-semibold text-zinc-300">{cam}</span>
                <div className="h-2 flex-1 overflow-hidden rounded-full bg-white/[0.06] border border-white/[0.04]">
                  <div
                    className="h-full rounded-full bg-blue-500 transition-all duration-300"
                    style={{ width: `${Math.max(2, (count / max) * 100)}%` }}
                  />
                </div>
                <span className="w-12 text-right text-xs font-mono font-semibold tabular-nums text-white">
                  {count}
                </span>
              </div>
            ))}
            {perCam.length === 0 && <div className="text-xs text-zinc-500 py-2">No detection records yet.</div>}
          </div>
        </div>

        {/* Origin / destination flow */}
        <div className="rounded-xl border border-white/[0.08] bg-[#0d1017]/90 p-4 backdrop-blur-md shadow-sm">
          <div className="mb-3 flex items-center justify-between">
            <div className="text-xs font-semibold uppercase tracking-wider text-zinc-400 font-mono">
              Corridor Flow Trajectories
            </div>
            <span className="inline-flex items-center rounded-md border border-white/[0.08] bg-zinc-900/80 px-2 py-0.5 text-[10px] font-mono uppercase tracking-wider text-zinc-400">
              Walkthrough Scenario
            </span>
          </div>
          <div className="divide-y divide-white/[0.04]">
            {DEMO_FLOWS.map((flow) => (
              <div key={`${flow.from}-${flow.to}`} className="flex items-center gap-3 py-2.5 text-xs">
                <span className="min-w-0 flex-1 truncate text-zinc-300 font-medium">{flow.from}</span>
                <ArrowRight className="h-3.5 w-3.5 flex-none text-zinc-600" />
                <span className="min-w-0 flex-1 truncate text-zinc-300 font-medium">{flow.to}</span>
                <span className="w-10 text-right font-mono font-semibold tabular-nums text-white">{flow.count}</span>
              </div>
            ))}
          </div>
          <div className="mt-3 text-[11px] text-zinc-500">
            Flow reconstruction illustrates multi-junction vehicle journey mapping between sensor nodes.
          </div>
        </div>
      </div>
    </div>
  )
}
