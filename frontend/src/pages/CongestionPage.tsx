import { usePolling } from "@/hooks/usePolling"
import { useState } from "react"
import { getStats, getTrafficBaselines, type Camera, type Stats, type TrafficBaseline } from "@/lib/api"
import { OsmMap } from "@/components/OsmMap"

export function CongestionPage({ cameras }: { cameras: Camera[] }) {
  const [stats,setStats]=useState<Stats|null>(null)
  const [baseline,setBaseline]=useState<TrafficBaseline|null>(null)
  const [error,setError]=useState<string|null>(null)
  usePolling(async signal => {
    try {
      const s = await getStats(signal)
      if (!signal.aborted) { setStats(s); setError(null) }
    } catch (e) { if (!signal.aborted) setError(e instanceof Error ? e.message : "Activity unavailable") }
  }, 10000)
  usePolling(async signal => {
    try {
      const result=await getTrafficBaselines(signal,28)
      if (!signal.aborted) setBaseline(result)
    } catch (e) { if (!signal.aborted) setError(e instanceof Error ? e.message : "Historical activity unavailable") }
  }, 60000)
  const total=stats?.vehicle_passages || 1
  const ranked=cameras.map(c=>({camera:c,count:stats?.per_camera_passages[c.id] ?? 0})).sort((a,b)=>b.count-a.count)
  const located=ranked.filter(({camera:c})=>c.location_confirmed&&Number.isFinite(c.lat)&&Number.isFinite(c.lon))
  const unlocated=ranked.filter(({camera:c})=>!c.location_confirmed||!Number.isFinite(c.lat)||!Number.isFinite(c.lon))
  return <div className="flex h-full flex-col gap-4 overflow-y-auto p-4">
    <div><h1 className="text-lg font-semibold">Sampled traffic activity</h1><p className="mt-2 text-sm text-muted-foreground">Camera-local track passages over five minutes. Relative activity does not establish congestion, physical speed, or a historical baseline. Missing feeds remain unobserved.</p></div>
    {error && <p role="alert" className="text-red-200">{error}</p>}
    <div className="grid min-h-0 flex-1 gap-4 md:grid-cols-[1fr_280px]">
      <div className="relative min-h-80 overflow-hidden rounded border border-border"><OsmMap points={located.map(({camera:c,count})=>({id:c.id,lat:c.lat,lon:c.lon,label:c.id,detail:c.source_available?`${count} sampled passages · ${c.location}`:`Source missing; passage count unknown · ${c.location}`,size:c.source_available?5+count/total*24:5,color:c.source_available?"#38d1c2":"#84949d"}))} className="h-full w-full" />{unlocated.length>0&&<div className="absolute left-3 top-3 max-w-[75%] rounded border border-border bg-background/90 px-3 py-2 text-xs text-muted-foreground">Unconfirmed camera positions are not plotted: {unlocated.map(({camera})=>camera.id).join(", ")}</div>}</div>
      <div><h2 className="font-semibold">Observed passages</h2>{ranked.map(({camera:c,count})=><div className="flex justify-between border-b border-border py-3 text-sm" key={c.id}><div>{c.id}<p className="text-xs text-muted-foreground">{c.source_available?c.health.status:"source missing"} · {c.location_confirmed?c.location:"location unconfirmed"}</p></div><span>{c.source_available?count:"unknown"}</span></div>)}</div>
    </div>
    <section className="rounded border border-border p-4">
      <h2 className="font-semibold">Historical hourly passage baseline</h2>
      <p className="mt-1 text-sm text-muted-foreground">Live-source samples only; replay footage is excluded. Counts are camera-local tracked passages, not road-segment traffic volume or physical speed. Timezone: {baseline?.timezone ?? "—"}; window: {baseline?.window_days ?? 28} days.</p>
      <div className="mt-3 overflow-x-auto"><table className="w-full min-w-[680px] text-left text-sm">
        <thead><tr className="border-b border-border text-muted-foreground"><th className="py-2 pr-3">Camera</th><th className="py-2 pr-3">Latest completed hour</th><th className="py-2 pr-3">Passages</th><th className="py-2 pr-3">Prior same weekday/hour median</th><th className="py-2 pr-3">Change</th><th className="py-2">Status</th></tr></thead>
        <tbody>{(baseline?.cameras ?? []).map(item=><tr className="border-b border-border/70" key={item.camera_id}>
          <td className="py-2 pr-3">{item.camera_id}</td>
          <td className="py-2 pr-3">{item.latest_complete_hour_local ? new Date(item.latest_complete_hour_local).toLocaleString("en-IN",{timeZone:baseline?.timezone}) : "—"}</td>
          <td className="py-2 pr-3">{item.latest_passages ?? "—"}</td>
          <td className="py-2 pr-3">{item.baseline_median === null ? "—" : `${item.baseline_median} (${item.baseline_comparable_hours} hours)`}</td>
          <td className="py-2 pr-3">{item.change_vs_median_percent === null ? "—" : `${item.change_vs_median_percent > 0 ? "+" : ""}${item.change_vs_median_percent}%`}</td>
          <td className="py-2">{item.status.replaceAll("_"," ")}</td>
        </tr>)}</tbody>
      </table></div>
      <p className="mt-2 text-xs text-muted-foreground">An hour counts as covered only with at least four processed frames across two quarter-hours. Speed remains unavailable until route distances and capture clocks are independently calibrated. A baseline appears after at least two prior same-weekday/hour buckets meet that coverage.</p>
    </section>
  </div>
}
