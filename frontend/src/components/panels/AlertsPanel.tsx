import { usePolling } from "@/hooks/usePolling"
import { useEffect, useState } from "react"
import { getAlerts, getCameras, getEscalations, getRules, reviewAlert, saveRules, type Alert, type Camera, type EscalationCursor, type RuleConfig } from "@/lib/api"
import { DEMO_ALERTS } from "@/lib/demo"

const button="rounded border border-zinc-700 px-3 py-2 text-sm hover:bg-zinc-800 disabled:opacity-50"
const field="min-w-0 rounded border border-zinc-700 bg-zinc-900 px-3 py-2 text-base"
type ReviewState = "acknowledged" | "reviewed" | "dismissed" | "escalated"

function Rules() {
  const [rules,setRules]=useState<RuleConfig|null>(null)
  const [cameras,setCameras]=useState<Camera[]>([])
  const [watch,setWatch]=useState("")
  const [message,setMessage]=useState("")
  const [busy,setBusy]=useState(false)
  const [camera,setCamera]=useState("CAM-01")
  const [zone,setZone]=useState<[number,number,number,number]>([0,0,1,1])
  const [seconds,setSeconds]=useState(30)
  const [conditionPlate,setConditionPlate]=useState("")
  const [minimumSightings,setMinimumSightings]=useState(1)
  const [historyWindow,setHistoryWindow]=useState(0)
  const [activeFrom,setActiveFrom]=useState("")
  const [activeUntil,setActiveUntil]=useState("")
  const [permitId,setPermitId]=useState("")
  const [permitPlate,setPermitPlate]=useState("")
  const [permitCamera,setPermitCamera]=useState("CAM-01")
  const [permitFrom,setPermitFrom]=useState("")
  const [permitUntil,setPermitUntil]=useState("")
  const [permitReason,setPermitReason]=useState("")
  useEffect(()=>{
    let alive=true
    Promise.all([getRules(),getCameras()]).then(([r,c])=>{
      if(alive){
        const complete={...r,watchlist_conditions:r.watchlist_conditions??{},zone_permits:r.zone_permits??[]}
        setRules(complete);setCameras(c)
        setWatch(Object.entries(complete.watchlist).map(([plate,reason])=>`${plate} | ${reason}`).join("\n"))
        if(c.length){setCamera(c[0].id);setPermitCamera(c[0].id)}
      }
    }).catch(e=>alive&&setMessage(e.message))
    return()=>{alive=false}
  },[])
  function chooseConditionPlate(plate:string){
    setConditionPlate(plate)
    const condition=rules?.watchlist_conditions[plate]
    setMinimumSightings(condition?.minimum_sightings??1)
    setHistoryWindow(condition?.history_window_seconds??0)
    setActiveFrom(condition?.active_from!=null?toLocalDateTime(condition.active_from):"")
    setActiveUntil(condition?.active_until!=null?toLocalDateTime(condition.active_until):"")
  }
  function addCondition(){
    if(!rules||!conditionPlate)return
    const from=activeFrom?localDateTimeToEpoch(activeFrom):undefined
    const until=activeUntil?localDateTimeToEpoch(activeUntil):undefined
    setRules({...rules,watchlist_conditions:{...rules.watchlist_conditions,[conditionPlate]:{
      minimum_sightings:minimumSightings,history_window_seconds:historyWindow,active_from:from,active_until:until,
    }}})
    setMessage("Condition staged. Save local rules to apply it.")
  }
  function addPermit(){
    if(!rules||!permitId.trim()||!permitPlate.trim()||!permitFrom||!permitUntil||!permitReason.trim())return
    const validFrom=localDateTimeToEpoch(permitFrom),validUntil=localDateTimeToEpoch(permitUntil)
    if(validFrom>=validUntil){setMessage("Permit end time must be after its start time.");return}
    setRules({...rules,zone_permits:[...rules.zone_permits,{permit_id:permitId.trim(),plate:permitPlate.trim().toUpperCase(),camera_ids:[permitCamera],valid_from:validFrom,valid_until:validUntil,reason:permitReason.trim()}]})
    setPermitId("");setPermitPlate("");setPermitFrom("");setPermitUntil("");setPermitReason("")
    setMessage("Permit staged. Save local rules to apply it.")
  }
  async function save() {
    if(!rules||busy)return
    setBusy(true)
    try{
      const watchlist:Record<string,string>={}
      for(const line of watch.split("\n").filter(l=>l.trim())){
        const [plate,...reason]=line.split("|")
        if(!reason.join("|").trim())throw new Error("Each watchlist entry needs a plate and reason, separated by |")
        watchlist[plate.trim().toUpperCase()]=reason.join("|").trim()
      }
      const conditions=Object.fromEntries(Object.entries(rules.watchlist_conditions).filter(([plate])=>plate in watchlist))
      const result=await saveRules({...rules,watchlist,watchlist_conditions:conditions})
      setRules(result);setMessage("Rules saved and audited. They apply to subsequent evaluations.")
    }catch(e){setMessage(e instanceof Error?e.message:"Rules could not be saved")}
    finally{setBusy(false)}
  }
  return <details className="rounded border border-zinc-800 p-4"><summary className="cursor-pointer font-semibold">Configure local rules</summary><p className="my-3 text-sm text-zinc-400">Local course configuration. Permit records are operator-entered hints only; they are not checked against an external authority and do not establish compliance or a violation.</p>
    {message && <p className="my-3 text-sm" role="status">{message}</p>}
    {rules && <div className="flex flex-col gap-5">
      <label className="flex flex-col gap-2 text-sm">Watchlist — one plate | reason per line<textarea className={field} rows={3} value={watch} onChange={e=>setWatch(e.target.value)} /></label>
      <fieldset className="space-y-3"><legend className="font-medium">Watchlist history and effective dates</legend><p className="text-sm text-zinc-400">A match can require a minimum number of supported sightings (including the current one) inside a lookback window and can be active only during a time range. With no condition, one current sighting is enough.</p>
        {Object.entries(rules.watchlist_conditions).map(([plate,condition])=><div key={plate} className="flex flex-wrap items-center gap-3 rounded border border-zinc-800 p-3 text-sm"><span className="font-mono">{plate}</span><span>{condition.minimum_sightings} sightings / {condition.history_window_seconds}s</span><span>{condition.active_from!=null?new Date(condition.active_from*1000).toLocaleString():"no start"} → {condition.active_until!=null?new Date(condition.active_until*1000).toLocaleString():"no expiry"}</span><button type="button" className={button} onClick={()=>{const next={...rules.watchlist_conditions};delete next[plate];setRules({...rules,watchlist_conditions:next})}}>Remove condition</button></div>)}
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3"><label className="text-sm">Watchlist plate<select className={`${field} mt-1 w-full`} value={conditionPlate} onChange={e=>chooseConditionPlate(e.target.value)}><option value="">Select a saved plate</option>{Object.keys(rules.watchlist).map(plate=><option key={plate}>{plate}</option>)}</select></label><label className="text-sm">Minimum sightings<input className={`${field} mt-1 w-full`} type="number" min="1" max="1000" value={minimumSightings} onChange={e=>setMinimumSightings(Number(e.target.value))} /></label><label className="text-sm">Lookback seconds<input className={`${field} mt-1 w-full`} type="number" min="0" max={7*86400} value={historyWindow} onChange={e=>setHistoryWindow(Number(e.target.value))} /></label><label className="text-sm">Active from (local time)<input className={`${field} mt-1 w-full`} type="datetime-local" value={activeFrom} onChange={e=>setActiveFrom(e.target.value)} /></label><label className="text-sm">Active until (local time)<input className={`${field} mt-1 w-full`} type="datetime-local" value={activeUntil} onChange={e=>setActiveUntil(e.target.value)} /></label><button type="button" className={`${button} self-end`} disabled={!conditionPlate} onClick={addCondition}>Add / update condition</button></div>
      </fieldset>
      <fieldset><legend className="mb-2 font-medium">Zone-sighting cameras</legend><div className="flex flex-wrap gap-4">{cameras.map(c=><label key={c.id} className="flex gap-2 text-sm"><input type="checkbox" checked={rules.restricted_cameras.includes(c.id)} onChange={e=>setRules({...rules,restricted_cameras:e.target.checked?[...rules.restricted_cameras,c.id]:rules.restricted_cameras.filter(id=>id!==c.id)})} />{c.id}</label>)}</div></fieldset>
      <fieldset className="space-y-3"><legend className="font-medium">Local zone permits</legend><p className="text-sm text-zinc-400">A matching record changes a restricted-camera warning into an informational permitted-visit record. Sakshi does not verify the permit or issuer.</p>
        {rules.zone_permits.map(permit=><div key={permit.permit_id} className="flex flex-wrap items-center gap-3 rounded border border-zinc-800 p-3 text-sm"><span>{permit.plate} · {permit.camera_ids.join(", ")} · {permit.permit_id}</span><span>{new Date(permit.valid_from*1000).toLocaleString()} → {new Date(permit.valid_until*1000).toLocaleString()}</span><button type="button" className={button} onClick={()=>setRules({...rules,zone_permits:rules.zone_permits.filter(item=>item.permit_id!==permit.permit_id)})}>Remove permit</button></div>)}
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3"><label className="text-sm">Permit ID<input className={`${field} mt-1 w-full`} maxLength={64} value={permitId} onChange={e=>setPermitId(e.target.value)} /></label><label className="text-sm">Plate<input className={`${field} mt-1 w-full font-mono`} value={permitPlate} onChange={e=>setPermitPlate(e.target.value)} /></label><label className="text-sm">Camera<select className={`${field} mt-1 w-full`} value={permitCamera} onChange={e=>setPermitCamera(e.target.value)}>{cameras.map(c=><option key={c.id}>{c.id}</option>)}</select></label><label className="text-sm">Valid from (local time)<input className={`${field} mt-1 w-full`} type="datetime-local" value={permitFrom} onChange={e=>setPermitFrom(e.target.value)} /></label><label className="text-sm">Valid until (local time)<input className={`${field} mt-1 w-full`} type="datetime-local" value={permitUntil} onChange={e=>setPermitUntil(e.target.value)} /></label><label className="text-sm">Reason<input className={`${field} mt-1 w-full`} maxLength={500} value={permitReason} onChange={e=>setPermitReason(e.target.value)} /></label><button type="button" className={`${button} justify-self-start`} onClick={addPermit}>Add permit</button></div>
      </fieldset>
      <div><h3 className="font-semibold">Dwell zones</h3><p className="my-2 text-sm text-zinc-400">Configure an image region before enabling dwell rules. Coordinates are fractions of frame width/height from 0 to 1. This detects time inside a zone, not malicious intent.</p>{rules.dwell_zones.map((z,i)=><div className="my-2 flex flex-wrap items-center gap-3 text-sm" key={i}><span>{z.camera_id} · [{z.zone.join(", ")}] · {z.dwell_seconds}s</span><button className={button} onClick={()=>setRules({...rules,dwell_zones:rules.dwell_zones.filter((_,j)=>i!==j)})}>Remove zone</button></div>)}<div className="flex flex-wrap items-end gap-3"><label className="flex flex-col text-sm">Camera<select className={field} value={camera} onChange={e=>setCamera(e.target.value)}>{cameras.map(c=><option key={c.id}>{c.id}</option>)}</select></label>{["Left","Top","Right","Bottom"].map((name,i)=><label className="flex w-24 flex-col text-sm" key={name}>{name}<input className={field} type="number" min="0" max="1" step=".05" value={zone[i]} onChange={e=>setZone(zone.map((v,j)=>i===j?Number(e.target.value):v) as typeof zone)} /></label>)}<label className="flex w-28 flex-col text-sm">Dwell seconds<input className={field} type="number" min="10" max="3600" value={seconds} onChange={e=>setSeconds(Number(e.target.value))} /></label><button className={button} onClick={()=>setRules({...rules,dwell_zones:[...rules.dwell_zones,{camera_id:camera,zone:[...zone],dwell_seconds:seconds,max_gap_seconds:5}]})}>Add zone</button></div></div>
      <button className={`${button} self-start`} disabled={busy} onClick={save}>{busy?"Saving…":"Save local rules"}</button></div>}
  </details>
}

function localDateTimeToEpoch(value:string){return new Date(value).getTime()/1000}
function toLocalDateTime(epoch:number){const d=new Date(epoch*1000);return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}-${String(d.getDate()).padStart(2,"0")}T${String(d.getHours()).padStart(2,"0")}:${String(d.getMinutes()).padStart(2,"0")}`}

export function AlertsPanel() {
  const [alerts,setAlerts]=useState<Alert[]>([])
  const [escalations,setEscalations]=useState<Alert[]>([])
  const [escalationPages,setEscalationPages]=useState<Array<EscalationCursor|null>>([null])
  const [nextEscalationCursor,setNextEscalationCursor]=useState<EscalationCursor|null>(null)
  const [loadingOlder,setLoadingOlder]=useState(false)
  const [demo,setDemo]=useState(false)
  const [reviewer,setReviewer]=useState("")
  const [note,setNote]=useState("")
  const [escalationTarget,setEscalationTarget]=useState("")
  const [busy,setBusy]=useState<string|null>(null)
  const [error,setError]=useState<string|null>(null)
  usePolling(async signal => {
    try {
      const [recent,...pages] = await Promise.all([getAlerts(signal),...escalationPages.map(cursor=>getEscalations(cursor,signal))])
      if (!signal.aborted) {
        setAlerts(recent)
        const unique = new Map(pages.flatMap(page=>page.items).map(alert=>[alert.alert_id,alert]).filter(([id])=>Boolean(id)) as [string,Alert][])
        setEscalations([...unique.values()])
        setNextEscalationCursor(pages.at(-1)?.next_cursor ?? null)
        setError(null)
      }
    } catch (e) { if (!signal.aborted) setError(e instanceof Error ? e.message : "Alerts failed") }
  }, 5000, !demo)
  async function loadOlderEscalations(){
    if(!nextEscalationCursor||loadingOlder)return
    setLoadingOlder(true)
    try{
      const page=await getEscalations(nextEscalationCursor)
      setEscalations(current=>[...new Map([...current,...page.items].filter(alert=>alert.alert_id).map(alert=>[alert.alert_id!,alert])).values()])
      setEscalationPages(current=>[...current,nextEscalationCursor])
      setNextEscalationCursor(page.next_cursor)
      setError(null)
    }catch(e){setError(e instanceof Error?e.message:"Older escalations could not be loaded")}
    finally{setLoadingOlder(false)}
  }
  async function review(alert:Alert,state:ReviewState){
    if(!alert.alert_id||busy)return
    if(!reviewer.trim()){setError("Enter your reviewer name before recording a decision");return}
    if(state==="escalated"&&!escalationTarget.trim()){setError("Enter the reviewer or team receiving this escalation");return}
    setBusy(alert.alert_id)
    try{await reviewAlert(alert.alert_id,state,reviewer,note,state==="escalated"?escalationTarget.trim():undefined);setAlerts(await getAlerts());setEscalations(current=>state==="escalated"?current:current.filter(item=>item.alert_id!==alert.alert_id));setError(null)}
    catch(e){setError(e instanceof Error?e.message:"Review could not be saved")}
    finally{setBusy(null)}
  }
  const queued=demo?[]:escalations
  const shown=demo?DEMO_ALERTS:alerts.filter(a=>a.state!=="escalated")
  const renderAlert=(a:Alert,i:number)=>(
    <article key={a.alert_id ?? i} className="rounded border border-zinc-800 p-4">
      <p className={`text-sm ${a.severity==="critical"?"text-red-200":a.severity==="warning"?"text-amber-200":"text-zinc-400"}`}>
        {a.severity} · {a.type} · {a.state ?? "synthetic"}
      </p>
      <h2 className="my-2 font-semibold">{a.summary}</h2>
      <p className="text-sm text-zinc-400">{a.detail}</p>
      <p className="mt-2 text-xs text-zinc-400">{new Date(a.ts*1000).toLocaleString()}</p>
      {a.escalation_target&&<p className="mt-2 text-sm">Escalated to <span className="font-medium">{a.escalation_target}</span></p>}
      {a.review?.map((r,j)=><p key={j} className="mt-2 break-words text-sm">
        {r.reviewer}{r.reviewer_authenticated?" (signed-in account)":" (local name claim)"} · {r.state}{r.escalation_target?` → ${r.escalation_target}`:""}{r.note?` · ${r.note}`:""}
      </p>)}
      {a.alert_id&&<div className="mt-3 flex flex-wrap gap-2">
        {(["acknowledged","reviewed","dismissed","escalated"] as const).map(state=><button
          key={state}
          className={button}
          disabled={!!busy}
          onClick={()=>review(a,state)}
        >{busy===a.alert_id?"Saving…":state==="acknowledged"?"Acknowledge":state==="reviewed"?"Mark reviewed":state==="dismissed"?"Dismiss":"Escalate / reassign"}</button>)}
      </div>}
    </article>
  )
  return <div className="h-full overflow-y-auto bg-black p-4 text-white sm:p-6"><div className="mx-auto flex max-w-5xl flex-col gap-4">
    <div><h1 className="text-lg font-semibold">Rule alerts and review</h1><p className="mt-2 max-w-[70ch] text-sm leading-relaxed text-zinc-400">Review plate watchlist, zone-sighting, camera-transition, and per-track dwell alerts. Escalations stay in the queue beyond the recent-alert window. Signed-in reviews use the account name; local mode records a reviewer name claim. Recipients are local claims and this app sends no external notifications.</p></div>
    <button className={`${button} self-start`} onClick={()=>setDemo(!demo)}>{demo?"Return to real rule alerts":"Preview synthetic alerts"}</button>
    {demo?<p className="text-sm text-amber-200">Synthetic examples only. Review and escalation actions are unavailable for these fixtures.</p>:<><Rules /><div className="grid gap-3 sm:grid-cols-2"><label className="flex min-w-0 flex-col gap-1 text-sm">Reviewer name (local mode)<input className={field} maxLength={100} value={reviewer} onChange={e=>setReviewer(e.target.value)} /></label><label className="flex min-w-0 flex-col gap-1 text-sm">Escalation recipient<input className={field} maxLength={100} value={escalationTarget} onChange={e=>setEscalationTarget(e.target.value)} placeholder="Reviewer or team" /></label><label className="flex min-w-0 flex-col gap-1 text-sm sm:col-span-2">Review or handoff note<input className={field} maxLength={1000} value={note} onChange={e=>setNote(e.target.value)} /></label></div></>}
    {error && <p role="alert" className="rounded border border-red-400/40 p-3 text-red-200">{error}</p>}
    {!demo&&<section aria-labelledby="escalations-heading" className="flex flex-col gap-3"><div><h2 id="escalations-heading" className="font-semibold">Escalation queue <span className="text-sm font-normal text-zinc-400">{queued.length}{nextEscalationCursor?"+":""}</span></h2><p className="mt-1 text-sm text-zinc-400">Open handoffs remain visible here until a reviewer records the next decision.</p></div>{queued.length===0?<p className="rounded border border-zinc-800 p-4 text-sm text-zinc-400">No active escalations.</p>:queued.map(renderAlert)}{nextEscalationCursor&&<button type="button" className={`${button} self-start`} disabled={loadingOlder} onClick={loadOlderEscalations}>{loadingOlder?"Loading…":"Load older handoffs"}</button>}</section>}
    <section aria-labelledby="recent-alerts-heading" className="flex flex-col gap-3"><div><h2 id="recent-alerts-heading" className="font-semibold">{demo?"Synthetic examples":"Recent alerts"}</h2>{!demo&&<p className="mt-1 text-sm text-zinc-400">Recent rule alerts, including unresolved items. Empty results do not prove every camera is processing.</p>}</div>{shown.length===0?<p className="rounded border border-zinc-800 p-4 text-sm text-zinc-400">No recent configured rule alerts.</p>:shown.map(renderAlert)}</section>
  </div></div>
}
