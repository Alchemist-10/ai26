import { useEffect, useState, type FormEvent } from "react"
import { ApiError, getCameraConfiguration, saveCameraConfiguration, type Camera, type CameraConfiguration } from "@/lib/api"
import CameraSources from "@/components/settings/CameraSources"

const control = "w-full min-w-0 rounded border border-zinc-700 bg-zinc-900 px-3 py-2 text-base text-white disabled:opacity-50"
const button = "min-h-11 rounded border border-zinc-600 px-3 py-2 text-sm font-medium hover:bg-zinc-800 disabled:cursor-not-allowed disabled:opacity-50"
interface Draft { location: string; lat: string; lon: string; location_confirmed: boolean; reviewer: string; reason: string }
const emptyDraft: Draft = { location: "", lat: "", lon: "", location_confirmed: false, reviewer: "", reason: "" }
function draftFrom(config: CameraConfiguration): Draft {
  return { ...emptyDraft, location: config.location, lat: String(config.lat), lon: String(config.lon), location_confirmed: config.location_confirmed }
}
function metadataChanged(draft: Draft, config: CameraConfiguration) {
  return draft.location.trim() !== config.location || draft.lat.trim() === "" || draft.lon.trim() === "" ||
    Number(draft.lat) !== config.lat || Number(draft.lon) !== config.lon || draft.location_confirmed !== config.location_confirmed
}
function errorText(error: unknown) { return error instanceof Error ? error.message : "Camera API unavailable" }
function savedAt(config: CameraConfiguration) { return config.updated_at ? new Date(config.updated_at * 1000).toLocaleString() : "Repository defaults" }

export default function CameraSettings({ cameras, initialCamera }: { cameras: Camera[]; initialCamera: string }) {
  const [selected, setSelected] = useState(initialCamera)
  const [config, setConfig] = useState<CameraConfiguration | null>(null)
  const [draft, setDraft] = useState<Draft>(emptyDraft)
  const [loadVersion, setLoadVersion] = useState(0)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [sourceBusy, setSourceBusy] = useState(false)
  const [error, setError] = useState("")
  const [notice, setNotice] = useState("")
  const [needsReview, setNeedsReview] = useState(false)
  const [latest, setLatest] = useState<CameraConfiguration | null>(null)
  const [revision, setRevision] = useState("1")
  const [history, setHistory] = useState<CameraConfiguration | null>(null)
  const [historyError, setHistoryError] = useState("")
  const changed = config ? metadataChanged(draft, config) : false
  const dirty = changed || draft.reviewer !== "" || draft.reason !== ""
  const camera = cameras.find(item => item.id === selected)

  // App keeps this page mounted after the first visit. Catalog polling never replaces a draft.
  useEffect(() => {
    const controller = new AbortController()
    getCameraConfiguration(selected, undefined, controller.signal).then(result => {
      if (controller.signal.aborted) return
      setConfig(result); setDraft(draftFrom(result)); setRevision(String(result.revision))
    }).catch(error => { if (!controller.signal.aborted) setError(errorText(error)) })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [selected, loadVersion])

  useEffect(() => {
    if (!dirty) return
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = "" }
    window.addEventListener("beforeunload", warn)
    return () => window.removeEventListener("beforeunload", warn)
  }, [dirty])

  function updateDraft(change: Partial<Draft>) {
    setDraft(previous => ({ ...previous, ...change })); setNotice("")
  }
  function resetTo(result: CameraConfiguration) {
    setConfig(result); setDraft(draftFrom(result)); setRevision(String(result.revision))
    setNeedsReview(false); setLatest(null); setError("")
  }
  function selectCamera(id: string) {
    setSelected(id); setConfig(null); setLoading(true); setDraft(emptyDraft); setHistory(null)
    setHistoryError(""); setNotice(""); setError(""); setNeedsReview(false); setLatest(null)
  }
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!config || !changed || busy || needsReview) return
    const lat = Number(draft.lat), lon = Number(draft.lon)
    if (!draft.location.trim() || !draft.reviewer.trim() || !draft.reason.trim()) {
      setError("Enter a location, reviewer name and reason using more than spaces."); return
    }
    if (!draft.lat.trim() || !draft.lon.trim() || !Number.isFinite(lat) || !Number.isFinite(lon) || Math.abs(lat) > 90 || Math.abs(lon) > 180) {
      setError("Enter a latitude from −90 to 90 and a longitude from −180 to 180."); return
    }
    setBusy(true); setError(""); setNotice("")
    try {
      const saved = await saveCameraConfiguration(selected, {
        expected_revision: config.revision, location: draft.location.trim(), location_confirmed: draft.location_confirmed,
        lat, lon, reviewer: draft.reviewer.trim(), reason: draft.reason.trim(),
      })
      resetTo(saved); setNotice(`Saved revision ${saved.revision}. Historical observations keep their original metadata.`)
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        setNeedsReview(true); setError("A newer revision was saved. Your draft is preserved. Review the latest revision before saving again.")
      } else if (!(error instanceof ApiError) || error.status >= 500) {
        setNeedsReview(true); setError("The save could not be confirmed. Your draft is preserved. Review the latest revision before trying again.")
      } else setError(errorText(error))
    } finally { setBusy(false) }
  }
  async function reviewLatest() {
    setBusy(true); setError("")
    try { setLatest(await getCameraConfiguration(selected)) }
    catch (error) { setError(`Could not load the latest revision: ${errorText(error)}. Try reviewing it again.`) }
    finally { setBusy(false) }
  }
  function keepDraft() {
    if (!latest) return
    if (!metadataChanged(draft, latest)) {
      resetTo(latest); setNotice("The latest revision already contains your metadata. No additional save is needed.")
      return
    }
    setConfig(latest); setNeedsReview(false); setLatest(null); setError("")
    setNotice("Draft kept against the reviewed revision. Check every field, then save when ready.")
  }
  async function viewRevision(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const value = Number(revision)
    if (!config || !Number.isSafeInteger(value) || value < 1 || value > Math.max(config.revision, latest?.revision ?? 0)) return
    setBusy(true); setHistoryError(""); setHistory(null)
    try { setHistory(await getCameraConfiguration(selected, value)) }
    catch (error) { setHistoryError(errorText(error)) }
    finally { setBusy(false) }
  }

  return (
    <section aria-labelledby="camera-settings-title" className="h-full overflow-y-auto bg-black p-4 text-white sm:p-6">
      <div className="mx-auto max-w-5xl pb-8">
        <h1 id="camera-settings-title" className="text-2xl font-semibold">Camera settings</h1>
        <p className="mt-2 max-w-[70ch] text-sm leading-relaxed text-zinc-300">Inspect source footage, edit location metadata and review saved revisions. Metadata changes apply to future observations; existing evidence keeps the revision captured with it.</p>
        <div className="mt-6 grid gap-3 border-b border-zinc-800 pb-6 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-end">
          <label className="block text-sm font-medium" htmlFor="settings-camera">Camera
            <select id="settings-camera" className={`${control} mt-2`} value={selected} disabled={dirty || busy || loading || sourceBusy} aria-describedby="camera-selection-help" onChange={event => selectCamera(event.target.value)}>
              {cameras.map(item => <option key={item.id} value={item.id}>{item.id} · {item.location}</option>)}
              {!camera && <option value={selected}>{selected}</option>}
            </select>
          </label>
          <button type="button" className={button} disabled={dirty || busy || loading || sourceBusy} onClick={() => { setConfig(null); setLoading(true); setError(""); setLoadVersion(value => value + 1); setNotice(""); setHistory(null); setHistoryError("") }}>Refresh current revision</button>
          <p id="camera-selection-help" className="text-sm text-zinc-300 sm:col-span-2">{sourceBusy ? "Finish or cancel preparation and check its status before switching cameras. You can navigate to another page while it runs." : dirty ? "Save or discard your draft before switching cameras. It stays here when you navigate to another page." : "Choose a camera to inspect its footage and metadata. Detector types remain fixed."}</p>
        </div>
        {loading && <p role="status" className="mt-4 text-sm text-zinc-300">Loading configuration…</p>}
        {error && <p role="alert" className="mt-4 rounded border border-red-400/40 bg-red-950/40 p-3 text-sm leading-relaxed text-red-100">{error}</p>}
        {notice && <p role="status" className="mt-4 rounded border border-teal-500/40 bg-teal-950/30 p-3 text-sm text-teal-100">{notice}</p>}
        {config && <>
          <div className="mt-6 flex flex-wrap items-center gap-x-6 gap-y-2 text-sm text-zinc-300">
            <span className="font-medium text-white">{config.id} · Revision {config.revision}</span>
            <span>{config.kind === "plate" ? "Plate detector" : "Vehicle detector"}</span>
            <span>{camera ? (camera.source_available ? "Source file available" : "Source file missing") : "Source availability unknown"}</span>
          </div>
          <p className="mt-2 text-sm text-zinc-300">Saved: {savedAt(config)} · Calibration: {config.calibration_status}</p>
          <p className="mt-2 break-words text-sm text-zinc-300">Metadata source: {config.metadata_source}</p>
          <CameraSources key={selected} cameraId={selected} sourceBusy={sourceBusy} onBusyChange={setSourceBusy} />
          <div className="mt-6 grid gap-8 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
            <div className="min-w-0">
              <h2 className="text-lg font-semibold">Location metadata</h2>
              <form onSubmit={save} className="mt-4">
                <fieldset disabled={busy} className="grid min-w-0 gap-4">
                  <label className="block text-sm font-medium" htmlFor="settings-location">Location label
                    <input id="settings-location" value={draft.location} required maxLength={200} className={`${control} mt-2`} onChange={event => updateDraft({ location: event.target.value })} />
                  </label>
                  <div className="grid gap-4 sm:grid-cols-2">
                    <label className="block text-sm font-medium" htmlFor="settings-lat">Latitude
                      <input id="settings-lat" type="number" step="any" min={-90} max={90} required value={draft.lat} className={`${control} mt-2 tabular-nums`} onChange={event => updateDraft({ lat: event.target.value })} />
                    </label>
                    <label className="block text-sm font-medium" htmlFor="settings-lon">Longitude
                      <input id="settings-lon" type="number" step="any" min={-180} max={180} required value={draft.lon} className={`${control} mt-2 tabular-nums`} onChange={event => updateDraft({ lon: event.target.value })} />
                    </label>
                  </div>
                  <label className="flex min-h-11 items-center gap-3 text-sm" htmlFor="settings-confirmed">
                    <input id="settings-confirmed" type="checkbox" className="h-5 w-5 shrink-0 accent-teal-400" checked={draft.location_confirmed} aria-describedby="settings-confirmed-help" onChange={event => updateDraft({ location_confirmed: event.target.checked })} />
                    Location label confirmed by local operator
                  </label>
                  <p id="settings-confirmed-help" className="-mt-2 text-sm leading-relaxed text-zinc-300">This records an operator assertion. Coordinates, camera clocks and travel times remain uncalibrated.</p>
                  <label className="block text-sm font-medium" htmlFor="settings-reviewer">Reviewer name
                    <input id="settings-reviewer" required maxLength={100} autoComplete="off" value={draft.reviewer} className={`${control} mt-2`} onChange={event => updateDraft({ reviewer: event.target.value })} />
                  </label>
                  <label className="block text-sm font-medium" htmlFor="settings-reason">Reason for change
                    <textarea id="settings-reason" required maxLength={1000} rows={3} value={draft.reason} className={`${control} mt-2 resize-y`} onChange={event => updateDraft({ reason: event.target.value })} />
                  </label>
                  <p className="text-sm leading-relaxed text-zinc-300">The name and reason are recorded in the local audit log. Reviewer identity is unauthenticated. Drafts survive page navigation, but are lost if the browser is closed or reloaded.</p>
                  <div className="flex flex-wrap gap-3">
                    <button type="submit" className={`${button} border-white bg-white text-black hover:bg-zinc-200`} disabled={!changed || needsReview}>{busy ? "Working…" : "Save new revision"}</button>
                    <button type="button" className={button} disabled={!dirty} onClick={() => { resetTo(config); setNotice("Draft discarded. Refresh current revision to check for newer saved metadata.") }}>Discard draft</button>
                  </div>
                </fieldset>
              </form>
              {needsReview && <div className="mt-6 border-t border-zinc-700 pt-5">
                <h3 className="font-semibold">Review before saving</h3>
                <p className="mt-2 text-sm leading-relaxed text-zinc-300">Compare the latest values with your draft above. Keeping your draft uses every draft field, including fields changed by another editor. Nothing is saved until you press Save new revision again.</p>
                <button type="button" disabled={busy} className={`${button} mt-3`} onClick={reviewLatest}>{busy ? "Loading…" : "Review latest revision"}</button>
                {latest && <>
                  <dl className="mt-4 grid gap-2 break-words text-sm">
                    <div><dt className="text-zinc-300">Latest revision</dt><dd>{latest.revision} · {savedAt(latest)}</dd></div>
                    <div><dt className="text-zinc-300">Latest location</dt><dd>{latest.location}</dd></div>
                    <div><dt className="text-zinc-300">Latest coordinates</dt><dd className="tabular-nums">{latest.lat}, {latest.lon}</dd></div>
                    <div><dt className="text-zinc-300">Latest label confirmation</dt><dd>{latest.location_confirmed ? "Marked confirmed" : "Unconfirmed"}</dd></div>
                  </dl>
                  <div className="mt-4 flex flex-wrap gap-3">
                    <button type="button" disabled={busy} className={button} onClick={keepDraft}>Keep my draft against revision {latest.revision}</button>
                    <button type="button" disabled={busy} className={button} onClick={() => { resetTo(latest); setNotice("Latest values loaded. Your draft was discarded.") }}>Use latest values and discard draft</button>
                  </div>
                </>}
              </div>}
            </div>
            <aside className="min-w-0 border-t border-zinc-800 pt-6 lg:border-t-0 lg:pt-0" aria-labelledby="settings-history-title">
              <h2 id="settings-history-title" className="text-lg font-semibold">Revision history</h2>
              <p className="mt-2 text-sm leading-relaxed text-zinc-300">Each save creates a retained metadata snapshot. Viewing a revision does not replace your draft.</p>
              <form onSubmit={viewRevision} className="mt-4 flex flex-wrap items-end gap-3">
                <label className="min-w-0 flex-1 text-sm font-medium" htmlFor="settings-revision">Revision number
                  <input id="settings-revision" type="number" min={1} max={Math.max(config.revision, latest?.revision ?? 0)} step={1} required value={revision} className={`${control} mt-2 tabular-nums`} disabled={busy} onChange={event => setRevision(event.target.value)} />
                </label>
                <button type="submit" className={button} disabled={busy}>View revision</button>
              </form>
              {historyError && <p role="alert" className="mt-4 text-sm text-red-200">{historyError}</p>}
              {history && <div className="mt-5 border-t border-zinc-800 pt-4" role="status">
                <h3 className="font-semibold">Saved revision {history.revision}</h3>
                <dl className="mt-3 grid gap-3 break-words text-sm">
                  <div><dt className="text-zinc-300">Location</dt><dd>{history.location}</dd></div>
                  <div><dt className="text-zinc-300">Coordinates</dt><dd className="tabular-nums">{history.lat}, {history.lon}</dd></div>
                  <div><dt className="text-zinc-300">Label confirmation</dt><dd>{history.location_confirmed ? "Marked confirmed; see metadata source" : "Unconfirmed"}</dd></div>
                  <div><dt className="text-zinc-300">Metadata source</dt><dd>{history.metadata_source}</dd></div>
                  <div><dt className="text-zinc-300">Calibration</dt><dd>{history.calibration_status}</dd></div>
                  <div><dt className="text-zinc-300">Saved</dt><dd>{savedAt(history)}</dd></div>
                </dl>
              </div>}
              <p className="mt-6 max-w-[70ch] text-sm leading-relaxed text-zinc-300">Prepare footage using the upload or host command above. This form edits location metadata; detector types stay fixed.</p>
            </aside>
          </div>
        </>}
      </div>
    </section>
  )
}
