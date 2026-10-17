import { useEffect, useState } from "react"
import { FileText, Route, Search } from "lucide-react"
import type { Camera, EvidenceReport, Trajectory } from "@/lib/api"
import { createEvidenceReport, getTrajectory } from "@/lib/api"
import { cn } from "@/lib/utils"
import { EvidenceTimeline } from "@/components/panels/EvidenceTimeline"
import { OsmMap } from "@/components/OsmMap"
import { DEMO_PLATE } from "@/lib/demo"

function formatTime(ts: number) {
  return new Date(ts * 1000).toLocaleTimeString()
}

export function TimelinePage({ cameras }: { cameras: Camera[] }) {
  const [camId, setCamId] = useState("")
  const [mode, setMode] = useState<"live" | "trajectory">("live")
  const [plate, setPlate] = useState(DEMO_PLATE.plate)
  const [trajectory, setTrajectory] = useState<Trajectory | null>(null)
  const [trajectoryPlate, setTrajectoryPlate] = useState("")
  const [trajectoryError, setTrajectoryError] = useState<string | null>(null)
  const [evidence, setEvidence] = useState<EvidenceReport | null>(null)
  const [evidenceError, setEvidenceError] = useState<string | null>(null)
  const active = camId || cameras[0]?.id || ""

  useEffect(() => {
    if (mode !== "trajectory" || !plate.trim()) return
    let alive = true
    getTrajectory(plate.trim())
      .then((result) => {
        if (!alive) return
        setTrajectory(result)
        setTrajectoryPlate(plate.trim())
        setTrajectoryError(null)
      })
      .catch((error: Error) => alive && setTrajectoryError(error.message))
    return () => {
      alive = false
    }
  }, [mode, plate])

  async function printEvidence() {
    setEvidenceError(null)
    try {
      const result = await createEvidenceReport(plate.trim())
      setEvidence(result)
      window.setTimeout(() => window.print(), 0)
    } catch (error) {
      setEvidenceError(error instanceof Error ? error.message : "Evidence export failed")
    }
  }

  if (mode === "trajectory") {
    const live = Boolean(trajectory?.observations.length && trajectoryPlate === plate.trim())
    const hops = live
      ? trajectory!.observations
      : DEMO_PLATE.hops.map((hop) => ({
        camera_id: hop.camera,
        location: hop.location,
        location_confirmed: false,
        lat: cameras.find((camera) => camera.id === hop.camera)?.lat ?? 0,
        lon: cameras.find((camera) => camera.id === hop.camera)?.lon ?? 0,
        ts: 0,
        confidence: hop.confidence,
        repairs: [],
      }))
    const points = hops.map((hop) => ({ id: hop.camera_id, lat: hop.lat, lon: hop.lon, label: hop.camera_id, active: true }))
    const rejected = live
      ? trajectory!.rejected_links.map((link) => link.reason).join("; ") || "None"
      : DEMO_PLATE.rejected
    const status = live ? trajectory!.status.replace("_", " ") : DEMO_PLATE.status

    return (
      <div className="flex h-full flex-col gap-3 overflow-y-auto bg-[#08090d] p-4 text-zinc-100">
        {/* Mode Toggle + Status */}
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/[0.06] pb-3">
          <div className="flex items-center rounded-lg bg-zinc-900/90 p-0.5 border border-white/[0.08]">
            <button
              type="button"
              onClick={() => setMode("live")}
              className="rounded-md px-3 py-1.5 text-xs font-medium text-zinc-400 hover:text-white transition-colors cursor-pointer"
            >
              Live Camera Log
            </button>
            <button
              type="button"
              onClick={() => setMode("trajectory")}
              className="rounded-md bg-blue-600 px-3 py-1.5 text-xs font-semibold text-white shadow-sm shadow-blue-500/20 cursor-pointer"
            >
              Plate Trajectory
            </button>
          </div>

          <div className="flex items-center gap-2">
            <span
              className={cn(
                "inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-mono font-medium border",
                live
                  ? "border-emerald-500/30 bg-emerald-950/30 text-emerald-300"
                  : "border-white/[0.08] bg-zinc-900/80 text-zinc-400"
              )}
            >
              <span className={cn("h-1.5 w-1.5 rounded-full", live ? "bg-emerald-400 animate-pulse" : "bg-zinc-500")} />
              {live ? "Live Event Trajectory" : "Demonstration Mode"}
            </span>
          </div>
        </div>

        {/* Plate Input Bar */}
        <div className="flex flex-wrap items-center gap-3 rounded-xl border border-white/[0.08] bg-[#0d1017]/90 p-3.5 backdrop-blur-md shadow-sm">
          <Route className="h-4 w-4 text-blue-400" />
          <div className="flex items-center gap-2">
            <input
              type="text"
              aria-label="Plate to investigate"
              value={plate}
              onChange={(event) => setPlate(event.target.value.toUpperCase())}
              placeholder="e.g. KL-07-CB-1234"
              className="h-8 w-48 rounded-lg border border-white/[0.1] bg-black/50 px-3 font-mono text-xs font-bold tracking-wider text-white placeholder:text-zinc-600 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
            <span className="rounded-md border border-white/[0.06] bg-zinc-900/80 px-2.5 py-1 text-[11px] text-zinc-400 font-mono">
              HSRP / KERALA REGISTRY
            </span>
          </div>

          <button
            type="button"
            className="ml-auto inline-flex items-center gap-2 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-100 hover:text-white px-3.5 py-1.5 text-xs font-medium border border-white/10 shadow-sm transition-all cursor-pointer"
            onClick={printEvidence}
          >
            <FileText className="h-3.5 w-3.5 text-zinc-400" />
            <span>Generate Evidence Dossier</span>
          </button>
        </div>

        {/* Error / Success States */}
        {trajectoryError && (
          <div className="rounded-lg border border-rose-500/30 bg-rose-950/40 p-2.5 text-xs text-rose-200">
            Trajectory unavailable: {trajectoryError}
          </div>
        )}
        {evidenceError && (
          <div className="rounded-lg border border-rose-500/30 bg-rose-950/40 p-2.5 text-xs text-rose-200">
            Evidence export unavailable: {evidenceError}
          </div>
        )}
        {evidence && (
          <div className="rounded-lg border border-blue-500/30 bg-blue-950/30 p-2.5 text-xs font-mono text-blue-200 flex items-center justify-between">
            <span>Report ID: {evidence.report_id}</span>
            <span>SHA-256: {evidence.package_hash.slice(0, 16)}…</span>
            <span>Retention: {evidence.retention}</span>
          </div>
        )}

        {/* Map + Detail Card */}
        <div className="grid min-h-0 flex-1 gap-3.5 lg:grid-cols-[1.3fr_0.7fr]">
          <div className="min-h-[380px] overflow-hidden rounded-xl border border-white/[0.08] bg-[#0b0d13]">
            <OsmMap
              points={points}
              lines={[
                {
                  id: "trajectory",
                  points: points.map((point) => [point.lat, point.lon] as [number, number]),
                  color: "#3b82f6",
                  width: 4,
                },
              ]}
              className="h-full w-full"
              ariaLabel={`Evidence trajectory for ${plate}`}
            />
          </div>

          <div className="flex flex-col rounded-xl border border-white/[0.08] bg-[#0d1017]/90 p-4 backdrop-blur-md">
            <div className="flex items-center justify-between border-b border-white/[0.06] pb-3">
              <div>
                <div className="font-mono text-lg font-bold tracking-wider text-white">
                  {plate || DEMO_PLATE.plate}
                </div>
                <div className="text-xs text-zinc-400 mt-0.5">
                  {live ? "Confirmed Vehicle Sightings" : DEMO_PLATE.vehicle}
                </div>
              </div>
              <span
                className={cn(
                  "inline-flex items-center rounded-md border px-2.5 py-1 text-[11px] font-mono font-medium capitalize",
                  live
                    ? "border-emerald-500/30 bg-emerald-950/30 text-emerald-300"
                    : "border-white/[0.08] bg-zinc-900 text-zinc-400"
                )}
              >
                {status}
              </span>
            </div>

            <div className="mt-4 flex-1 space-y-3 overflow-y-auto pr-1">
              {hops.map((hop, index) => (
                <div key={`${hop.camera_id}-${hop.ts}-${index}`} className="flex gap-3">
                  <div className="flex flex-col items-center">
                    <span className="mt-1 h-2.5 w-2.5 rounded-full bg-blue-500 ring-4 ring-blue-500/20" />
                    {index < hops.length - 1 && <span className="w-px flex-1 bg-white/[0.1] my-1" />}
                  </div>
                  <div className="pb-2 flex-1">
                    <div className="flex items-center justify-between">
                      <span className="font-mono text-xs font-semibold text-white">
                        {hop.camera_id}
                      </span>
                      <span className="font-mono text-[11px] text-zinc-400">
                        {hop.ts ? formatTime(hop.ts) : DEMO_PLATE.hops[index]?.time}
                      </span>
                    </div>
                    <div className="text-xs text-zinc-400 mt-0.5">{hop.location}</div>
                    <div className="mt-1.5 flex items-center gap-2">
                      <span className="inline-flex items-center rounded bg-zinc-900 px-2 py-0.5 text-[10px] font-mono text-zinc-300 border border-white/[0.06]">
                        {Math.round(hop.confidence * 100)}% match
                      </span>
                      {hop.repairs.length > 0 && (
                        <span className="text-[10px] text-amber-400 font-mono">
                          OCR repaired: {hop.repairs.join(", ")}
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>

            {rejected && rejected !== "None" && (
              <div className="mt-3 rounded-lg border border-white/[0.06] bg-black/40 p-2.5 text-xs text-zinc-400">
                <span className="text-zinc-300 font-semibold">Rejected candidate:</span> {rejected}
              </div>
            )}
            {!live && (
              <div className="mt-2 text-[11px] text-zinc-500">
                Five-minute log has no live matches for this query. Displaying labeled demonstration route.
              </div>
            )}
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col bg-[#08090d] text-zinc-100 select-none">
      {/* Top Toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/[0.08] bg-[#0c0e14] px-4 py-2.5">
        <div className="flex items-center rounded-lg bg-zinc-900/90 p-0.5 border border-white/[0.08]">
          <button
            type="button"
            onClick={() => setMode("live")}
            className="rounded-md bg-blue-600 px-3 py-1.5 text-xs font-semibold text-white shadow-sm shadow-blue-500/20 cursor-pointer"
          >
            Live Camera Log
          </button>
          <button
            type="button"
            onClick={() => setMode("trajectory")}
            className="flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium text-zinc-400 hover:text-white transition-colors cursor-pointer"
          >
            <Search className="h-3.5 w-3.5" />
            <span>Plate Trajectory</span>
          </button>
        </div>

        <div className="text-xs text-zinc-400">
          Select a channel to inspect chronological detection events.
        </div>
      </div>

      {/* Camera Sidebar + Timeline */}
      <div className="grid min-h-0 flex-1 grid-cols-[240px_1fr]">
        <div className="flex flex-col gap-1 overflow-y-auto border-r border-white/[0.08] bg-[#0a0c12] p-2.5">
          {cameras.map((camera) => {
            const isSelected = camera.id === active
            return (
              <button
                key={camera.id}
                type="button"
                onClick={() => setCamId(camera.id)}
                className={cn(
                  "rounded-lg px-3 py-2.5 text-left text-xs transition-all cursor-pointer border",
                  isSelected
                    ? "bg-zinc-800/90 border-blue-500/50 text-white shadow-sm ring-1 ring-blue-500/30"
                    : "border-transparent text-zinc-400 hover:bg-white/[0.04] hover:text-zinc-200"
                )}
              >
                <div className="flex items-center justify-between">
                  <span className="font-mono font-semibold tracking-wide text-white">
                    {camera.id}
                  </span>
                  <span className="text-[10px] font-mono text-zinc-400">
                    {camera.kind === "plate" ? "ANPR" : "CAM"}
                  </span>
                </div>
                <div className="truncate text-[11px] text-zinc-400 mt-0.5">
                  {camera.location_confirmed ? camera.location : "Location unconfirmed"}
                </div>
              </button>
            )
          })}
        </div>
        <div className="min-h-0 bg-[#08090d]">
          <EvidenceTimeline cameras={cameras} focused={active} />
        </div>
      </div>
    </div>
  )
}

