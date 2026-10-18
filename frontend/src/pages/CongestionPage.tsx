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
  return <div className="h-full overflow-y-auto">
    <div className="mx-auto w-full max-w-[1600px] space-y-8 px-5 py-6 sm:px-7 sm:py-8">
    <header className="space-y-3">
      <h1 className="text-2xl font-semibold tracking-tight">Sampled traffic activity</h1>
      <p className="max-w-4xl text-sm leading-6 text-muted-foreground">Camera-local track passages over five minutes. These counts show observed activity only; they do not establish congestion, physical speed, or a historical baseline. Missing feeds remain unobserved.</p>
    </header>
    {error && <p role="alert" className="rounded border border-red-400/30 bg-red-950/30 px-4 py-3 text-sm leading-6 text-red-200">{error}</p>}
    <section className="grid gap-x-8 gap-y-6 rounded border border-border bg-zinc-950/60 p-5 text-sm sm:grid-cols-3 sm:p-6" aria-label="Unmeasured traffic metrics">
      <div><p className="text-muted-foreground">Globally unique vehicles</p><p className="mt-2 font-medium">{stats?.metrics.globally_unique_vehicles.value ?? "Not measured"}</p></div>
      <div><p className="text-muted-foreground">Occupancy and density</p><p className="mt-2 font-medium">Not measured</p><p className="mt-2 max-w-[38ch] text-sm leading-6 text-muted-foreground">Requires calibrated road and lane geometry.</p></div>
      <div><p className="text-muted-foreground">Physical speed</p><p className="mt-2 font-medium">{stats?.metrics.physical_speed_kmh.value ?? "Unavailable"}</p><p className="mt-2 max-w-[38ch] text-sm leading-6 text-muted-foreground">Requires verified route distance and synchronized capture clocks.</p></div>
    </section>
    <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_minmax(18rem,22rem)] lg:items-start">
      <figure className="relative h-[360px] overflow-hidden rounded border border-border bg-zinc-950 sm:h-[420px] lg:h-[560px]">
        <OsmMap points={located.map(({camera:c,count})=>({id:c.id,lat:c.lat,lon:c.lon,label:c.id,detail:c.source_available?`${count} sampled passages · ${c.location}`:`Source missing; passage count unknown · ${c.location}`,size:c.source_available?5+count/total*24:5,color:c.source_available?"#38d1c2":"#84949d"}))} className="h-full w-full" />
        {unlocated.length>0&&<figcaption className="absolute left-4 top-4 max-w-[min(28rem,calc(100%-2rem))] rounded border border-border bg-background/95 px-4 py-3 text-sm leading-6 text-muted-foreground">{located.length===0?"No confirmed camera positions are plotted yet.":`Unconfirmed positions are hidden for ${unlocated.length} camera${unlocated.length===1?"":"s"}.`} Add verified coordinates in camera settings to place them on the map.</figcaption>}
      </figure>
      <section aria-labelledby="observed-passages-heading" className="min-w-0">
        <div className="mb-2 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
          <h2 id="observed-passages-heading" className="text-xl font-semibold tracking-tight">Observed passages</h2>
          <span className="text-sm text-muted-foreground">Last five minutes</span>
        </div>
        <ul className="divide-y divide-border" aria-label="Vehicle passages by camera">
          {ranked.length===0?<li className="py-6 text-sm leading-6 text-muted-foreground">No cameras are assigned to this case.</li>:ranked.map(({camera:c,count})=><li className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-4 py-4" key={c.id}>
            <div className="min-w-0"><p className="font-medium">{c.id}</p><p className="mt-1 truncate text-sm leading-5 text-muted-foreground">{c.source_available?c.health.status:"Source missing"} · {c.location_confirmed?c.location:"Location unconfirmed"}</p></div>
            <span className="tabular-nums text-lg font-semibold">{c.source_available?count:"Unknown"}</span>
          </li>)}
        </ul>
      </section>
    </div>
    <section aria-labelledby="baseline-heading" className="space-y-4 rounded border border-border bg-zinc-950/40 p-5 sm:p-6">
      <header className="space-y-2">
        <h2 id="baseline-heading" className="text-xl font-semibold tracking-tight">Historical hourly passage baseline</h2>
        <p className="max-w-5xl text-sm leading-6 text-muted-foreground">Live-source samples only; replay footage is excluded. Counts are camera-local tracked passages, not road-segment traffic volume or physical speed. Timezone: {baseline?.timezone ?? "—"}; window: {baseline?.window_days ?? 28} days.</p>
      </header>
      {!baseline?<p role="status" className="py-2 text-sm text-muted-foreground">Loading historical coverage…</p>:baseline.cameras.length===0?<p className="rounded border border-border/70 px-4 py-5 text-sm leading-6 text-muted-foreground">No historical baseline is available yet. It appears after at least two prior same-weekday/hour periods meet the coverage requirement.</p>:<div className="overflow-x-auto rounded border border-border/70"><table className="w-full min-w-[680px] text-left text-sm">
        <thead><tr className="border-b border-border bg-zinc-950/70 text-muted-foreground"><th className="px-3 py-3">Camera</th><th className="px-3 py-3">Latest completed hour</th><th className="px-3 py-3">Passages</th><th className="px-3 py-3">Prior same weekday/hour median</th><th className="px-3 py-3">Change</th><th className="px-3 py-3">Status</th></tr></thead>
        <tbody>{baseline.cameras.map(item=><tr className="border-b border-border/70 last:border-0" key={item.camera_id}>
          <td className="px-3 py-3">{item.camera_id}</td>
          <td className="px-3 py-3">{item.latest_complete_hour_local ? new Date(item.latest_complete_hour_local).toLocaleString("en-IN",{timeZone:baseline.timezone}) : "—"}</td>
          <td className="px-3 py-3 tabular-nums">{item.latest_passages ?? "—"}</td>
          <td className="px-3 py-3">{item.baseline_median === null ? "—" : `${item.baseline_median} (${item.baseline_comparable_hours} hours)`}</td>
          <td className="px-3 py-3 tabular-nums">{item.change_vs_median_percent === null ? "—" : `${item.change_vs_median_percent > 0 ? "+" : ""}${item.change_vs_median_percent}%`}</td>
          <td className="px-3 py-3">{item.status.replaceAll("_"," ")}</td>
        </tr>)}</tbody>
      </table></div>}
      <p className="max-w-5xl text-sm leading-6 text-muted-foreground">An hour counts as covered only with at least four processed frames across two quarter-hours. Speed remains unavailable until route distances and capture clocks are independently calibrated. A baseline appears after at least two prior same-weekday/hour buckets meet that coverage.</p>
    </section>
    </div>
  </div>
}
