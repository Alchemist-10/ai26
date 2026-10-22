import { useEffect, useRef, useState, type FormEvent } from "react"
import { cancelSourcePreparation, getSourcePreparation, prepareCameraSource, type CameraSourceStatus, type SourcePreparation, type SourceProvenanceClaims } from "@/lib/api"
import SourceSelection from "@/components/settings/SourceSelection"

const control="w-full min-w-0 rounded border border-zinc-700 bg-zinc-900 px-3 py-2 text-base text-white disabled:opacity-50"
const button="min-h-11 rounded border border-zinc-600 px-3 py-2 text-sm font-medium hover:bg-zinc-800 disabled:cursor-not-allowed disabled:opacity-50"
const maxBytes=128*1024*1024
const emptyProvenance:SourceProvenanceClaims={archive_creator:"",export_system:"",external_camera_id:"",recording_timezone:"unknown",authorization_basis:"",retention_note:""}
function message(error: unknown) { return error instanceof Error ? error.message : "Preparation unavailable" }
function storedId(camera: string) { try { const id=localStorage.getItem(`ai26:source-preparation:${camera}`); return id && /^[0-9a-f]{32}$/.test(id) ? id : null } catch { return null } }

export default function SourceUpload({cameraId,source,disabled,onBusyChange,onSelectionBusyChange,onSelected}: {cameraId:string;source:CameraSourceStatus;disabled:boolean;onBusyChange:(busy:boolean)=>void;onSelectionBusyChange:(busy:boolean)=>void;onSelected:(source:CameraSourceStatus)=>void}) {
  const [file,setFile]=useState<File|null>(null)
  const [reviewer,setReviewer]=useState("")
  const [reason,setReason]=useState("")
  const [recordingStart,setRecordingStart]=useState("")
  const [clockUncertainty,setClockUncertainty]=useState("")
  const [provenance,setProvenance]=useState<SourceProvenanceClaims>(emptyProvenance)
  const [replace,setReplace]=useState(false)
  const [job,setJob]=useState<SourcePreparation|null>(null)
  const [error,setError]=useState("")
  const [busy,setBusy]=useState(false)
  const [initialId]=useState(()=>storedId(cameraId))
  const [checking,setChecking]=useState(!!initialId)
  const transfer=useRef<AbortController|null>(null)
  const needsReplace=source.active.inference.available || !!source.selection.release
  const preparing=job?.status==="preparing" || job?.status==="uploading"
  const release=job?.release
  const selected=release && source.selection.release?.release===release.release
  const running=release && source.active.release?.release===release.release
  const canSelectPrepared=release && (release.previous_release || null)===(source.selection.release?.release || null)

  useEffect(()=>{
    const controller=new AbortController()
    if(initialId) getSourcePreparation(initialId,controller.signal).then(result=>{
      if(!controller.signal.aborted) { setJob(result);onBusyChange(result.status==="preparing" || result.status==="uploading") }
    }).catch(error=>{if(!controller.signal.aborted)setError(`Could not restore preparation: ${message(error)}. Choose a file to start again.`)})
      .finally(()=>{if(!controller.signal.aborted)setChecking(false)})
    return ()=>{ controller.abort();transfer.current?.abort();onBusyChange(false) }
  },[initialId,onBusyChange])

  async function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if(!file || disabled || busy || preparing || checking) return
    if(!file.size || file.size>maxBytes) {setError("Choose a nonempty video up to 128 MiB.");return}
    if(file.name.length>200 || !reviewer.trim() || !reason.trim()) {setError("Enter your name and reason. The filename must be at most 200 characters.");return}
    if(needsReplace && !replace) {setError("Confirm replacement of this camera’s existing footage before preparing a new clip.");return}
    if(clockUncertainty && !recordingStart) {setError("Add the original recording start time before entering clock uncertainty.");return}
    const uncertainty=clockUncertainty ? Number(clockUncertainty) : undefined
    if(uncertainty!==undefined && (!Number.isFinite(uncertainty) || uncertainty<0 || uncertainty>86400)) {setError("Clock uncertainty must be between 0 and 86400 seconds.");return}
    if(recordingStart && !Number.isFinite(new Date(recordingStart).getTime())) {setError("Enter a valid original recording start time.");return}
    const startUTC=recordingStart ? new Date(recordingStart).toISOString() : ""
    setBusy(true);onBusyChange(true);setError("");setJob(null)
    const controller=new AbortController();transfer.current=controller
    let keepBusy=false
    try {
      const result=await prepareCameraSource(cameraId,file,reviewer.trim(),reason.trim(),replace,startUTC,uncertainty,provenance,controller.signal)
      setJob(result);keepBusy=result.status==="preparing" || result.status==="uploading"
      try {localStorage.setItem(`ai26:source-preparation:${cameraId}`,result.job_id)} catch { /* Receipt ID remains visible if storage is unavailable. */ }
    } catch(error) {setError(controller.signal.aborted ? "Upload cancelled. Existing footage is unchanged." : message(error))}
    finally {setBusy(false);onBusyChange(keepBusy);transfer.current=null}
  }
  async function check() {
    if(!job) return
    setChecking(true);setError("")
    try {const result=await getSourcePreparation(job.job_id);setJob(result);onBusyChange(result.status==="preparing" || result.status==="uploading")}
    catch(error) {setError(`Could not check preparation: ${message(error)}. Try checking again.`)}
    finally {setChecking(false)}
  }
  async function cancel() {
    if(!job) return
    setChecking(true);setError("")
    try {const result=await cancelSourcePreparation(job.job_id);setJob(result);onBusyChange(result.status==="preparing" || result.status==="uploading")}
    catch(error) {setError(`Cancellation could not be confirmed: ${message(error)}. Check preparation again.`)}
    finally {setChecking(false)}
  }

  return <div className="mt-4 border-t border-zinc-800 pt-4">
    <h3 className="font-medium">Prepare footage from your browser</h3>
    <p className="mt-2 max-w-[70ch] text-sm leading-relaxed text-zinc-300">Upload a clip up to 128 MiB. Sakshi preserves its bytes and prepares a separate playback copy. Current inference and playback continue using their existing source. Select ready footage here, then restart on the host to activate it.</p>
    <form onSubmit={upload} className="mt-4">
      <fieldset disabled={disabled || busy || preparing || checking} className="grid min-w-0 gap-4 sm:grid-cols-2">
        <label htmlFor="source-upload-file" className="block text-sm font-medium sm:col-span-2">Recorded video
          <input id="source-upload-file" type="file" accept="video/*,.mp4,.mkv,.avi,.mov,.webm" required className={`${control} mt-2 file:mr-3 file:rounded file:border-0 file:bg-zinc-700 file:px-3 file:py-1 file:text-white`} onChange={event=>{setFile(event.target.files?.[0]??null);setError("")}} />
        </label>
        <label htmlFor="source-upload-reviewer" className="block text-sm font-medium">Your name
          <input id="source-upload-reviewer" required maxLength={100} value={reviewer} className={`${control} mt-2`} onChange={event=>setReviewer(event.target.value)} />
        </label>
        <label htmlFor="source-upload-reason" className="block text-sm font-medium">Reason for this footage
          <input id="source-upload-reason" required maxLength={1000} value={reason} className={`${control} mt-2`} onChange={event=>setReason(event.target.value)} />
        </label>
        <label htmlFor="source-upload-recording-start" className="block text-sm font-medium">Original recording start (optional)
          <input id="source-upload-recording-start" type="datetime-local" value={recordingStart} className={`${control} mt-2`} onChange={event=>setRecordingStart(event.target.value)} />
          <span className="mt-1 block text-xs font-normal text-zinc-400">Interpreted in this browser’s timezone and stored in UTC.</span>
        </label>
        <label htmlFor="source-upload-clock-uncertainty" className="block text-sm font-medium">Clock uncertainty in seconds (optional)
          <input id="source-upload-clock-uncertainty" type="number" min="0" max="86400" step="any" value={clockUncertainty} className={`${control} mt-2`} onChange={event=>setClockUncertainty(event.target.value)} />
        </label>
        <details className="rounded border border-zinc-800 p-3 text-sm sm:col-span-2">
          <summary className="min-h-11 cursor-pointer py-2 font-medium">Source provenance claims (optional)</summary>
          <p className="mb-3 max-w-[70ch] leading-relaxed text-zinc-400">These are operator-provided claims only. Sakshi does not independently verify source ownership, export details, recording timezone, authorization or retention terms.</p>
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="block">Archive creator or supplier<input maxLength={200} value={provenance.archive_creator} className={`${control} mt-1`} onChange={event=>setProvenance(value=>({...value,archive_creator:event.target.value}))} /></label>
            <label className="block">Export system / NVR<input maxLength={200} value={provenance.export_system} className={`${control} mt-1`} onChange={event=>setProvenance(value=>({...value,export_system:event.target.value}))} /></label>
            <label className="block">Camera identifier in source system<input maxLength={100} value={provenance.external_camera_id} className={`${control} mt-1`} onChange={event=>setProvenance(value=>({...value,external_camera_id:event.target.value}))} /></label>
            <label className="block">Recording timezone (IANA or “unknown”)<input maxLength={64} value={provenance.recording_timezone} className={`${control} mt-1`} onChange={event=>setProvenance(value=>({...value,recording_timezone:event.target.value}))} /></label>
            <label className="block">Authorization basis<input maxLength={500} value={provenance.authorization_basis} className={`${control} mt-1`} placeholder="Why this footage may be stored and processed" onChange={event=>setProvenance(value=>({...value,authorization_basis:event.target.value}))} /></label>
            <label className="block">Retention / deletion terms<input maxLength={500} value={provenance.retention_note} className={`${control} mt-1`} placeholder="Operator claim; does not configure deletion" onChange={event=>setProvenance(value=>({...value,retention_note:event.target.value}))} /></label>
          </div>
        </details>
        {needsReplace && <label htmlFor="source-upload-replace" className="flex min-h-11 items-start gap-3 text-sm leading-relaxed sm:col-span-2"><input id="source-upload-replace" type="checkbox" required checked={replace} className="mt-1 h-5 w-5 shrink-0 accent-teal-400" onChange={event=>setReplace(event.target.checked)} />I intend to replace this camera’s footage after validation, selection and restart.</label>}
        <p className="text-sm leading-relaxed text-zinc-300 sm:col-span-2">One clip can be prepared at a time. Your name, source details and recording clocks are operator claims, not verification. When sign-in is enabled, Sakshi records the authenticated uploader account separately. A supplied start time is paired with frame index ÷ reported FPS as an approximate source offset; it does not replace replay time or enable calibrated cross-camera links. Ready releases remain on the host until managed separately.</p>
        <button type="submit" className={`${button} w-fit border-white bg-white text-black hover:bg-zinc-200`} disabled={!file}>{busy ? "Uploading clip…" : "Upload and prepare clip"}</button>
      </fieldset>
    </form>
    {busy && <div className="mt-3 flex flex-wrap items-center gap-3"><p role="status" className="text-sm text-zinc-300">Uploading clip. This can take up to two minutes.</p><button type="button" className={button} onClick={()=>transfer.current?.abort()}>Cancel upload</button></div>}
    {error && <p role="alert" className="mt-3 rounded border border-red-400/40 bg-red-950/40 p-3 text-sm text-red-100">{error}</p>}
    {job && <div className="mt-4 text-sm">
      <p className="break-words text-zinc-300">{job.filename} · Preparation <span className="break-all font-mono">{job.job_id}</span></p>
      {release && <p className="mt-2 break-words text-zinc-300">Reviewer claim: {release.reviewer || "Not recorded"} · Authenticated uploader: {release.uploader_authenticated ? release.authenticated_uploader || "Account unavailable" : "Not recorded for this import"}</p>}
      <p role={job.status==="failed" ? "alert" : "status"} className={`mt-2 leading-relaxed ${job.status==="failed" ? "rounded border border-red-400/40 bg-red-950/40 p-3 text-red-100" : ""}`}>{preparing ? "Preparing and validating playback. Check when ready; the current camera source is unchanged." : job.status==="ready" ? selected ? running ? "This prepared release is selected and running." : "This release is selected. Restart the API to activate it." : "Prepared footage is ready for selection. It is not selected for restart." : job.status==="cancelled" ? "Preparation cancelled. Current footage is unchanged." : job.error || "Preparation failed. Choose a readable clip and retry."}</p>
      <div className="mt-3 flex flex-wrap gap-3"><button type="button" className={button} disabled={disabled || checking} onClick={check}>{checking ? "Checking preparation…" : "Check preparation"}</button>{preparing && <button type="button" className={button} disabled={disabled || checking} onClick={cancel}>Cancel preparation</button>}</div>
      {release && !selected && canSelectPrepared && <SourceSelection cameraId={cameraId} release={release} source={source} intent="select" disabled={disabled || busy || checking || preparing} onBusyChange={onSelectionBusyChange} onSelected={onSelected} />}
      {release && !selected && !canSelectPrepared && <p className="mt-4 text-sm leading-relaxed text-zinc-300">The selection changed since this clip was prepared. Prepare another clip, or select this release from Recent imported releases if it is listed as an earlier import.</p>}
      {release && !selected && <details className="mt-4 text-sm"><summary className="min-h-11 cursor-pointer py-3 font-medium">Select with a host command instead</summary><div className="rounded border border-teal-500/40 bg-teal-950/30 p-3 text-teal-100">
        <p className="leading-relaxed">On the API host, use the same data/source settings. Stop the app with Ctrl+C, select this release, then restart. Selection rechecks file hashes and rejects an imported selection changed since preparation.</p>
        <code className="mt-3 block whitespace-pre-wrap break-all font-mono">uv run --frozen --directory backend python select_source.py {cameraId} {release.release} --expected-current {release.previous_release || "default"}</code>
        <p className="mt-3">Restart with <code>uv run run.py --skip-install</code> and refresh source status. Validation was performed at preparation time; actual content and original clocks remain unverified.</p>
      </div></details>}
    </div>}
  </div>
}
