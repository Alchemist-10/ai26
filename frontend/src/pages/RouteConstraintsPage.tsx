import { useEffect, useMemo, useState, type FormEvent } from "react"
import { ApiError, getCameraPairConstraints, saveCameraPairConstraint, type Camera, type CameraPairConstraint } from "@/lib/api"

const field = "mt-1 block min-h-11 w-full rounded border border-zinc-700 bg-zinc-950 px-3 py-2 text-base text-white"
const button = "min-h-11 rounded border border-zinc-600 px-4 py-2 text-sm text-white hover:bg-zinc-800 disabled:cursor-wait disabled:opacity-50"

export default function RouteConstraintsPage({ cameras }: { cameras: Camera[] }) {
  const [constraints, setConstraints] = useState<CameraPairConstraint[]>([])
  const [from, setFrom] = useState(cameras[0]?.id ?? "")
  const [to, setTo] = useState(cameras.find(camera => camera.id !== cameras[0]?.id)?.id ?? "")
  const [minimum, setMinimum] = useState("0")
  const [maximum, setMaximum] = useState("3600")
  const [enabled, setEnabled] = useState(true)
  const [reviewer, setReviewer] = useState("")
  const [reason, setReason] = useState("")
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")
  const [notice, setNotice] = useState("")
  const key = `${from}>${to}`
  const existing = useMemo(() => constraints.find(item => `${item.from_camera}>${item.to_camera}` === key), [constraints, key])
  const locationConfirmed = new Map(cameras.map(camera => [camera.id, camera.location_confirmed]))

  useEffect(() => {
    const controller = new AbortController()
    void getCameraPairConstraints(controller.signal).then(result => {
      if (!controller.signal.aborted) setConstraints(result)
    }).catch(cause => {
      if (!controller.signal.aborted) setError(message(cause))
    }).finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [])

  useEffect(() => {
    // Selection changes load the saved form values from the external route list.
    // oxlint-disable-next-line react/set-state-in-effect
    if (!existing) { setMinimum("0"); setMaximum("3600"); setEnabled(true); setReviewer(""); setReason(""); return }
    setMinimum(String(existing.min_travel_seconds)); setMaximum(String(existing.max_travel_seconds))
    setEnabled(existing.enabled); setReviewer(existing.reviewer); setReason(existing.reason)
  }, [existing])

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError(""); setNotice("")
    try {
      const saved = await saveCameraPairConstraint({
        from_camera_id: from, to_camera_id: to,
        min_travel_seconds: Number(minimum), max_travel_seconds: Number(maximum),
        enabled, reviewer: reviewer.trim(), reason: reason.trim(),
      })
      setConstraints(previous => [...previous.filter(item => `${item.from_camera}>${item.to_camera}` !== key), saved])
      setNotice(`${from} → ${to} travel constraint saved. New trajectory decisions will include this configuration snapshot.`)
    } catch (cause) { setError(message(cause)) }
    finally { setBusy(false) }
  }

  const ready = locationConfirmed.get(from) && locationConfirmed.get(to)

  return <section className="h-full overflow-y-auto bg-background px-4 py-6 text-foreground sm:px-6">
    <div className="mx-auto max-w-4xl">
      <h1 className="text-2xl font-semibold text-white">Camera-pair travel constraints</h1>
      <p className="mt-2 max-w-3xl text-sm leading-6 text-zinc-300">Configure directed travel-time windows only after confirming both camera locations. Windows are local operator inputs, not independently validated road travel times. Sakshi keeps matches unresolved when a pair has no constraint.</p>
      {error && <p role="alert" className="mt-4 rounded border border-red-400/30 bg-red-950/40 px-3 py-2 text-sm text-red-100">{error}</p>}
      {notice && <p role="status" className="mt-4 rounded border border-teal-400/30 bg-teal-950/30 px-3 py-2 text-sm text-teal-100">{notice}</p>}
      {loading ? <p role="status" className="mt-6 text-sm text-zinc-400">Loading configured camera pairs…</p> : <form onSubmit={submit} className="mt-6 space-y-5 border-y border-zinc-800 py-5">
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="text-sm text-zinc-300">From camera<select value={from} onChange={event => setFrom(event.target.value)} className={field}>{cameras.map(camera => <option key={camera.id} value={camera.id}>{camera.id} · {camera.location}{camera.location_confirmed ? " · confirmed" : " · unconfirmed"}</option>)}</select></label>
          <label className="text-sm text-zinc-300">To camera<select value={to} onChange={event => setTo(event.target.value)} className={field}>{cameras.filter(camera => camera.id !== from).map(camera => <option key={camera.id} value={camera.id}>{camera.id} · {camera.location}{camera.location_confirmed ? " · confirmed" : " · unconfirmed"}</option>)}</select></label>
        </div>
        <p className="text-sm text-zinc-400">{ready ? `Both locations are marked confirmed. ${existing ? existing.current_locations_valid ? "This pair has a current constraint." : "The saved constraint references older camera-location revisions; save again to review and update it." : "No constraint exists yet, so matching observations stay unresolved."}` : "Confirm both camera locations in Camera settings before saving a pair constraint."}</p>
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="text-sm text-zinc-300">Minimum travel time (seconds)<input required type="number" min="0" max="86400" step="any" value={minimum} onChange={event => setMinimum(event.target.value)} className={field} /></label>
          <label className="text-sm text-zinc-300">Maximum travel time (seconds)<input required type="number" min="0.001" max="86400" step="any" value={maximum} onChange={event => setMaximum(event.target.value)} className={field} /></label>
        </div>
        <label className="flex min-h-11 items-center gap-3 text-sm text-zinc-200"><input type="checkbox" checked={enabled} onChange={event => setEnabled(event.target.checked)} />This camera pair is a connected route</label>
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="text-sm text-zinc-300">Reviewer<input required maxLength={100} value={reviewer} onChange={event => setReviewer(event.target.value)} className={field} /></label>
          <label className="text-sm text-zinc-300">Reason<input required maxLength={1000} value={reason} onChange={event => setReason(event.target.value)} className={field} /></label>
        </div>
        <button disabled={busy || !ready || from === to} className={button}>{busy ? "Saving…" : existing ? "Update pair constraint" : "Save pair constraint"}</button>
      </form>}
      <h2 className="mt-7 text-lg font-medium text-white">Saved directed pairs <span className="font-normal text-zinc-400">({constraints.length})</span></h2>
      {constraints.length === 0 ? <p className="mt-2 text-sm text-zinc-400">No travel windows are configured. Cross-camera matches remain candidates awaiting review.</p> : <ul className="mt-3 divide-y divide-zinc-800 border-y border-zinc-800">{constraints.map(item => <li key={`${item.from_camera}>${item.to_camera}`} className="flex flex-wrap items-center justify-between gap-2 py-3 text-sm"><span className="font-medium text-white">{item.from_camera} → {item.to_camera}</span><span className="text-zinc-300">{item.enabled ? `${item.min_travel_seconds}–${item.max_travel_seconds} sec` : "Disconnected"} · {item.current_locations_valid ? "current locations" : "stale location revision"}</span><span className="text-xs text-zinc-500">Reviewed by {item.reviewer}</span></li>)}</ul>}
    </div>
  </section>
}

function message(cause: unknown) {
  if (cause instanceof ApiError && cause.status === 403) return "Route constraints require an operator or administrator account."
  return cause instanceof Error ? cause.message : "Could not update camera-pair constraints."
}
