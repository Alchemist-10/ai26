import { usePolling } from "@/hooks/usePolling"
import { useMemo, useState } from "react"
import { FileText, Search } from "lucide-react"
import { createEvidenceReport, getTrajectory, scopedResourceUrl, type Camera, type EvidenceReport, type Trajectory } from "@/lib/api"
import { EvidenceTimeline } from "@/components/panels/EvidenceTimeline"
import { OsmMap, type MapLine } from "@/components/OsmMap"
import { DEMO_PLATE } from "@/lib/demo"

const button = "rounded-md border border-zinc-700 px-3 py-2 text-sm hover:bg-zinc-800 disabled:cursor-not-allowed disabled:opacity-50"
const field = "min-w-0 rounded-md border border-zinc-700 bg-zinc-900 px-3 py-2 text-base text-white"

type Investigation = { plate: string; since: string; until: string }

function Results({ query }: { query: Investigation }) {
  const [trajectory, setTrajectory] = useState<Trajectory | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [report, setReport] = useState<EvidenceReport | null>(null)
  const [exporting, setExporting] = useState(false)
  const interval = { since: query.since || "0", ...(query.until ? {until: query.until} : {}) }
  usePolling(async signal => {
    try {
      const result = await getTrajectory(query.plate, interval, signal)
      if (!signal.aborted) { setTrajectory(result); setError(null) }
    } catch (e) { if (!signal.aborted) setError(e instanceof Error ? e.message : "Investigation failed") }
  }, 3000)
  async function generate() {
    if (exporting) return
    setExporting(true)
    try { setReport(await createEvidenceReport(query.plate, interval)); setError(null) }
    catch (e) { setError(e instanceof Error ? e.message : "Report failed") }
    finally { setExporting(false) }
  }
  const hops = trajectory?.observations ?? []
  const topImageCandidates = useMemo(() => {
    const groups = report?.image_review_candidates?.groups ?? []
    const unique = new Map<string, (typeof groups)[number]["top_k"][number]>()
    for (const group of groups) for (const candidate of group.top_k) {
      const existing = unique.get(candidate.crop_sha256)
      if (!existing || candidate.score > existing.score) unique.set(candidate.crop_sha256, candidate)
    }
    return [...unique.values()].sort((a, b) => b.score - a.score).slice(0, 3)
  }, [report?.image_review_candidates])
  const lines: MapLine[] = []
  if (trajectory) {
    for (const [state, links] of [["accepted", trajectory.accepted_links], ["rejected", trajectory.rejected_links], ["candidate", trajectory.candidate_links]] as const) {
      for (const [i, link] of links.entries()) {
        const a = hops.find((h) => h.camera_id === link.from_camera_id && h.ts === link.from_ts)
        const b = hops.find((h) => h.camera_id === link.to_camera_id && h.ts === link.to_ts)
        if (a && b && a.location_confirmed && b.location_confirmed && [a.lat,a.lon,b.lat,b.lon].every(Number.isFinite)) lines.push({id:`${state}-${i}`,points:[[a.lat,a.lon],[b.lat,b.lon]],color:state === "accepted" ? "#38d1c2" : state === "rejected" ? "#ff5c72" : "#ffb545",dashed:state !== "accepted",width:3})
      }
    }
  }
  return <section className="flex min-h-0 flex-1 flex-col gap-4" aria-live="polite">
    {error && <p role="alert" className="rounded border border-red-400/40 p-3 text-red-200">{error}</p>}
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div><h2 className="text-lg font-semibold">{trajectory?.plate ?? query.plate}</h2><p className="text-sm text-zinc-400">{trajectory ? trajectory.status.replaceAll("_", " ") : "Loading observations…"} · automated links are candidates, not verified identity</p></div>
      <button type="button" className={button} disabled={!hops.length || !!error || exporting} onClick={generate}><FileText className="mr-2 inline h-4 w-4" />{exporting ? "Creating report…" : "Create report snapshot"}</button>
    </div>
    {trajectory && hops.length === 0 && <div className="rounded border border-zinc-700 p-6"><h3 className="font-semibold">No matching supported plate observations</h3><p className="mt-2 text-sm text-zinc-400">This plate has no supported reads in the selected interval. Check source availability or choose another interval. No route or evidence has been inferred.</p></div>}
    {report && <div className="rounded border border-zinc-700 p-3 text-sm"><p>Saved snapshot {report.report_id} · {report.trajectory.observations.length} observations</p><p className="my-2 break-all font-mono text-xs text-zinc-400">SHA-256 {report.package_hash}</p><div className="flex flex-wrap gap-4"><a className="underline underline-offset-4 hover:text-teal-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-teal-400" href={scopedResourceUrl(`/api/reports/${report.report_id}`)}>Download JSON</a><a className="underline underline-offset-4 hover:text-teal-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-teal-400" href={scopedResourceUrl(`/api/reports/${report.report_id}/package`)}>Download artifact package</a><a className="underline underline-offset-4 hover:text-teal-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-teal-400" target="_blank" rel="noreferrer" href={scopedResourceUrl(`/api/reports/${report.report_id}/print`)}>Open report / Save PDF</a></div><p className="mt-2 text-xs text-zinc-400">{report.retention}. This saved report remains separate from subsequent live updates.</p>
      {report.image_review_candidates && <div className="mt-4 border-t border-zinc-800 pt-3"><h3 className="font-medium">Image review shortlist</h3><p className="mt-1 text-xs text-zinc-400">Highest-scoring three crops · heuristic only, not OCR accuracy. All raw images remain in the report.</p>{topImageCandidates.length > 0 ? <ul className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-3">{topImageCandidates.map((candidate,index)=><li key={candidate.crop_sha256} className="min-w-0"><a className="block rounded-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-teal-400" href={scopedResourceUrl(`/api/artifacts/${candidate.crop_sha256}`)} target="_blank" rel="noreferrer" aria-label={`Open image review candidate ${index+1}`}><img src={scopedResourceUrl(`/api/artifacts/${candidate.crop_sha256}`)} alt={`Plate crop review candidate ${index+1}`} loading="lazy" decoding="async" width="240" height="96" className="h-24 w-full rounded-sm border border-zinc-800 bg-zinc-950 object-contain" /><span className="mt-1 block text-xs text-zinc-300">Candidate {index+1} · heuristic {candidate.score.toFixed(2)}</span><span className="block truncate font-mono text-[10px] text-zinc-500">{candidate.crop_sha256}</span></a></li>)}</ul> : <p className="mt-2 text-xs text-zinc-400">No current stored plate crops were available to rank.</p>}</div>}
    </div>}
    {!!hops.length && <div className="grid gap-4 lg:grid-cols-2">
      <div><div className="h-80 overflow-hidden rounded border border-zinc-700"><OsmMap points={hops.filter(h=>h.location_confirmed&&[h.lat,h.lon].every(Number.isFinite)).map((h,i)=>({id:`${h.camera_id}-${i}`,lat:h.lat,lon:h.lon,label:h.camera_id,detail:h.location}))} lines={lines} className="h-full w-full" /></div><p className="mt-2 text-xs text-zinc-400">Only confirmed locations and transitions are plotted. Unconfirmed observations remain listed with their camera IDs and timestamp.</p></div>
      <div className="space-y-3"><p className="text-sm text-zinc-400">Solid teal: travel-gated candidates. Dashed amber: unresolved calibration. Dashed red: rejected transitions.</p>
        {hops.map((h,i)=><div key={`${h.camera_id}-${h.ts}-${i}`} className="border-b border-zinc-800 pb-3"><p>{h.camera_id} · {new Date(h.ts*1000).toLocaleString()}</p><p className="text-sm text-zinc-400">{h.location_confirmed?h.location:"Location unconfirmed"} · OCR confidence {Math.round(h.confidence*100)}%</p><p className="text-sm">Raw: {h.plate_raw ?? "unavailable"} · canonical: {h.plate}</p><p className="text-xs text-zinc-400">{h.time_basis === "replay_clock" ? "Replay clock; original capture time unknown" : "Provided observation timestamp"}</p></div>)}
        {[...trajectory!.rejected_links,...trajectory!.candidate_links].map((l,i)=><p key={i} className="text-sm text-amber-200">{l.from_camera_id} → {l.to_camera_id}: {l.reason}</p>)}
      </div>
    </div>}
  </section>
}

export function TimelinePage({ cameras }: { cameras: Camera[] }) {
  const [mode, setMode] = useState<"log" | "investigate" | "demo">("log")
  const [camera, setCamera] = useState("")
  const [plate, setPlate] = useState("")
  const [from, setFrom] = useState("")
  const [to, setTo] = useState("")
  const [query, setQuery] = useState<Investigation | null>(null)
  const [formError, setFormError] = useState<string | null>(null)
  function search(e: React.FormEvent) {
    e.preventDefault()
    if (!plate.trim()) { setFormError("Enter a plate to investigate"); return }
    const since=from ? String(new Date(from).getTime()/1000) : "0"
    const until=to ? String(new Date(to).getTime()/1000) : ""
    if (until && Number(since)>Number(until)) { setFormError("Start must be before end"); return }
    setFormError(null); setQuery({plate:plate.trim().toUpperCase(),since,until})
  }
  return <div className="flex h-full flex-col gap-4 overflow-y-auto bg-black p-4 text-white">
    <div className="flex flex-wrap gap-2"><button className={button} onClick={()=>setMode("log")}>Live camera log</button><button className={button} onClick={()=>setMode("investigate")}>Plate trajectory</button><button className={button} onClick={()=>setMode(mode === "demo" ? "investigate" : "demo")}>{mode === "demo" ? "Exit walkthrough" : "Preview synthetic walkthrough"}</button></div>
    {mode === "log" && <><label className="flex flex-wrap items-center gap-3 text-sm">Camera<select aria-label="Camera log" className={field} value={camera || cameras[0]?.id || ""} onChange={(e)=>setCamera(e.target.value)}>{cameras.map((c)=><option key={c.id} value={c.id}>{c.id} · {c.source_available ? c.health.status : "source missing"}</option>)}</select></label><div className="min-h-64 flex-1"><EvidenceTimeline key={camera} cameras={cameras} focused={camera || cameras[0]?.id || ""} /></div></>}
    {mode === "demo" && <section className="rounded border border-amber-500/50 p-4"><h2 className="text-lg font-semibold">Synthetic walkthrough · {DEMO_PLATE.plate}</h2><p className="my-3 text-sm text-amber-200">Example only. These events are not observed, cannot be searched as live data, and cannot be exported as evidence.</p>{DEMO_PLATE.hops.map((h)=><p className="my-2" key={h.camera}>{h.camera} · {h.location} · synthetic time {h.time}</p>)}</section>}
    {mode === "investigate" && <><form onSubmit={search} className="flex flex-wrap items-end gap-3"><label className="flex min-w-0 flex-col gap-1 text-sm">Plate<input className={field} aria-label="Plate to investigate" value={plate} maxLength={24} placeholder="KL07AB1234" onChange={(e)=>setPlate(e.target.value.toUpperCase())} /></label><label className="flex min-w-0 flex-col gap-1 text-sm">From (local time)<input className={field} type="datetime-local" value={from} onChange={(e)=>setFrom(e.target.value)} /></label><label className="flex min-w-0 flex-col gap-1 text-sm">Until (local time)<input className={field} type="datetime-local" value={to} onChange={(e)=>setTo(e.target.value)} /></label><button className={button} type="submit"><Search className="mr-2 inline h-4 w-4" />Search</button></form><p className="text-sm text-zinc-400">Blank dates search retained history. Results refresh every three seconds; only submitting a search changes its filters.</p>{formError && <p role="alert" className="text-red-200">{formError}</p>}{query && <Results key={JSON.stringify(query)} query={query} />}</>}
  </div>
}
