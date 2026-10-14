import { usePolling } from "@/hooks/usePolling"
import { useState } from "react"
import { getFlows, getStats, type Camera, type Stats } from "@/lib/api"
import { OsmMap } from "@/components/OsmMap"

export function AnalyticsPanel({ cameras }: { cameras: Camera[] }) {
  const [stats, setStats] = useState<Stats | null>(null)
  const [flows, setFlows] = useState<{from:string;to:string;count:number}[]>([])
  const [error, setError] = useState<string | null>(null)
  usePolling(async signal => {
    try {
      const [s, f] = await Promise.all([getStats(signal), getFlows(signal)])
      if (!signal.aborted) { setStats(s); setFlows(f); setError(null) }
    } catch (e) { if (!signal.aborted) setError(e instanceof Error ? e.message : "Activity unavailable") }
  }, 10000)
  const counts=Object.entries(stats?.per_camera_passages ?? {}).sort((a,b)=>b[1]-a[1])
  const processing=cameras.filter((c)=>c.health.last_frame_at && (c.health.frame_age_seconds ?? Infinity)<15 && ["processing","loading"].includes(c.health.status)).length
  const located=cameras.filter(c=>c.location_confirmed&&Number.isFinite(c.lat)&&Number.isFinite(c.lon))
  const unlocated=cameras.filter(c=>!c.location_confirmed||!Number.isFinite(c.lat)||!Number.isFinite(c.lon))
  return <div className="h-full overflow-y-auto bg-black p-4 text-white sm:p-6"><div className="mx-auto flex max-w-5xl flex-col gap-4">
    <div><h1 className="text-lg font-semibold">Traffic observation analytics</h1><p className="mt-2 text-sm text-zinc-400">Last five minutes of sampled recorded inputs. Track passages are camera-local; they do not measure globally unique vehicles or calibrated congestion.</p></div>
    {error && <p role="alert" className="rounded border border-red-400/40 p-3 text-red-200">{error}</p>}
    <div className="h-64 overflow-hidden rounded border border-zinc-800"><OsmMap points={located.map((c)=>({id:c.id,lat:c.lat,lon:c.lon,label:c.id,detail:c.source_available?`${stats?.per_camera_passages[c.id] ?? 0} sampled passages · ${c.location}`:`Source missing; passage count unknown · ${c.location}`,size:c.source_available?5+Math.min(20,stats?.per_camera_passages[c.id] ?? 0):5,color:c.source_available?"#38d1c2":"#84949d"}))} className="h-full w-full" /></div>
    <p className="text-xs text-zinc-400">Map shows {located.length} camera locations marked confirmed. Unconfirmed positions are omitted: {unlocated.length?unlocated.map(c=>c.id).join(", "):"none"}. Marker size reflects sampled passage count only while a source is available; missing-source activity is unknown.</p>
    <dl className="grid gap-3 sm:grid-cols-4">{[["Frame reads",stats?.total_events ?? "—","Repeated detections included"],["Vehicle track passages",stats?.vehicle_passages ?? "—","Baseline tracker; count accuracy unmeasured"],["Average confidence",stats?`${Math.round(stats.avg_confidence*100)}%`:"—","Model score, not accuracy"],["Recently processing",cameras.length ? `${processing}/${cameras.length}` : "—","Sources available: "+cameras.filter(c=>c.source_available).length]].map(([name,value,detail])=><div key={name} className="rounded border border-zinc-800 bg-zinc-950 p-4"><dt className="text-sm text-zinc-400">{name}</dt><dd className="my-2 text-2xl font-semibold tabular-nums">{value}</dd><p className="text-xs text-zinc-400">{detail}</p></div>)}</dl>
    <section className="rounded border border-zinc-800 p-4"><h2 className="font-semibold">Camera-local vehicle passages</h2>{!counts.length && <p className="mt-3 text-sm text-zinc-400">No tracked passages in this interval.</p>}{counts.map(([camera,count])=><div className="flex justify-between border-b border-zinc-800 py-3 text-sm" key={camera}><span>{camera}</span><span>{count}</span></div>)}</section>
    <section className="rounded border border-zinc-800 p-4"><h2 className="font-semibold">Origin / destination transitions</h2><p className="mt-2 text-sm text-zinc-400">Computed from deduplicated plate passages that pass the travel gate. Candidate identity remains unverified. Unsynchronized replay and unconfirmed coordinates do not create accepted flows.</p>{!flows.length && <p className="mt-3 text-sm text-zinc-400">No calibrated accepted transitions in this interval.</p>}{flows.map(f=><div className="flex justify-between border-b border-zinc-800 py-3 text-sm" key={`${f.from}-${f.to}`}><span>{f.from} → {f.to}</span><span>{f.count}</span></div>)}</section>
    <section><h2 className="font-semibold">Camera health</h2><div className="overflow-x-auto"><table className="mt-3 w-full text-left text-sm"><thead><tr><th className="py-2">Camera</th><th>Source</th><th>Processor</th><th>Inference branches</th><th>Processed FPS</th><th>Frame age</th></tr></thead><tbody>{cameras.map(c=>{const branches=c.health.inference_branches;const active=[branches.vehicle_detection_enabled?"vehicle":"vehicle off",...(c.kind==="plate"?[branches.plate_recognition_enabled?"plate OCR":"plate OCR off"]:[])];return <tr className="border-t border-zinc-800" key={c.id}><td className="py-3">{c.id}</td><td>{c.source_available?"available":"missing"}</td><td>{c.health.status}{c.health.error && <p className="max-w-64 text-xs text-red-200">{c.health.error}</p>}</td><td>{active.join(" · ")}</td><td>{c.health.processed_fps}</td><td>{c.health.frame_age_seconds === null ? "no frame" : `${c.health.frame_age_seconds}s`}</td></tr>})}</tbody></table></div></section>
  </div></div>
}
