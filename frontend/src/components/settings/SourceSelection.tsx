import { useState, type FormEvent } from "react"
import { selectCameraSource, type CameraSourceStatus, type SourceRelease } from "@/lib/api"

const control="w-full min-w-0 rounded border border-zinc-700 bg-zinc-900 px-3 py-2 text-base text-white disabled:opacity-50"
const button="min-h-11 rounded border border-zinc-600 px-3 py-2 text-sm font-medium hover:bg-zinc-800 disabled:cursor-not-allowed disabled:opacity-50"
type Props={cameraId:string;release:SourceRelease;source:CameraSourceStatus;intent:"select"|"rollback";disabled:boolean;onBusyChange:(busy:boolean)=>void;onSelected:(source:CameraSourceStatus)=>void}

export default function SourceSelection({cameraId,release,source,intent,disabled,onBusyChange,onSelected}:Props) {
  const [reviewer,setReviewer]=useState("")
  const [reason,setReason]=useState("")
  const [busy,setBusy]=useState(false)
  const [error,setError]=useState("")
  const [failedAt,setFailedAt]=useState<number|null>(null)
  const needsRefresh=failedAt===source.checked_at
  const selected=source.selection.release?.release===release.release
  const prefix=`source-${intent}`
  async function submit(event:FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if(disabled || busy || needsRefresh || selected || !source.selection.token) return
    if(!reviewer.trim() || !reason.trim()) {setError("Enter a selection reviewer and reason.");return}
    setBusy(true);onBusyChange(true);setError("")
    try {
      const result=await selectCameraSource(cameraId,release.release,source.selection.token,intent,reviewer.trim(),reason.trim())
      onSelected(result.source)
    } catch(error) {
      setError(`${error instanceof Error ? error.message : "Selection could not be confirmed"} Refresh source status and review the selected release before trying again. Your entries are preserved.`)
      setFailedAt(source.checked_at)
    } finally {setBusy(false);onBusyChange(false)}
  }
  return <form onSubmit={submit} className="mt-4 border-t border-zinc-800 pt-4">
    <h4 className="text-sm font-medium">{intent==="rollback" ? "Select an earlier import" : "Select prepared footage"}</h4>
    <p className="mt-2 max-w-[70ch] text-sm leading-relaxed text-zinc-300">{intent==="rollback" ? "Both retained files are verified before selecting this earlier release." : "Both prepared files are verified before selection."} Running inference and playback keep their current footage until the API restarts. Authenticated sessions record the signed-in account; local mode records the reviewer as an unauthenticated claim.</p>
    <fieldset disabled={disabled || busy || needsRefresh || selected || !source.selection.token} className="mt-4 grid min-w-0 gap-4 sm:grid-cols-2">
      <label htmlFor={`${prefix}-reviewer`} className="block text-sm font-medium">Selection reviewer
        <input id={`${prefix}-reviewer`} required maxLength={100} value={reviewer} className={`${control} mt-2`} onChange={event=>setReviewer(event.target.value)} />
      </label>
      <label htmlFor={`${prefix}-reason`} className="block text-sm font-medium">Selection reason
        <input id={`${prefix}-reason`} required maxLength={1000} value={reason} className={`${control} mt-2`} onChange={event=>setReason(event.target.value)} />
      </label>
      <button type="submit" className={`${button} w-fit border-white bg-white text-black hover:bg-zinc-200 sm:col-span-2`}>{busy ? "Verifying and selecting…" : intent==="rollback" ? "Select earlier release for restart" : "Select for restart"}</button>
    </fieldset>
    {busy && <p role="status" className="mt-3 text-sm text-zinc-300">Verifying both imported files. Other pages and current footage remain available.</p>}
    {error && (failedAt===null || needsRefresh) && <p role="alert" className="mt-3 rounded border border-red-400/40 bg-red-950/40 p-3 text-sm leading-relaxed text-red-100">{error}</p>}
    {(!source.selection.token || selected) && <p className="mt-3 text-sm text-zinc-300">{selected ? "This release is already selected. Review the source status above." : "The selected import is invalid. Restore it on the host while the app is stopped before using browser selection."}</p>}
  </form>
}

export function SourceRollback({cameraId,source,disabled,onBusyChange,onSelected}:Omit<Props,"release"|"intent">) {
  const [choice,setChoice]=useState("")
  const earlier=source.history.releases.filter(item=>item.release!==source.selection.release?.release)
  const target=earlier.find(item=>item.release===choice)
  if(!earlier.length) return null
  return <div className="mt-4 border-t border-zinc-800 pt-4">
    <label htmlFor="source-rollback-release" className="block text-sm font-medium">Earlier release to select
      <select id="source-rollback-release" value={target ? choice : ""} disabled={disabled} className={`${control} mt-2`} onChange={event=>setChoice(event.target.value)}>
        <option value="">Choose a retained earlier import</option>
        {earlier.map(item=><option key={item.release} value={item.release}>{item.release} · {item.imported_at ? new Date(item.imported_at*1000).toLocaleString() : "Date unavailable"}</option>)}
      </select>
    </label>
    {target && <SourceSelection cameraId={cameraId} release={target} source={source} intent="rollback" disabled={disabled} onBusyChange={onBusyChange} onSelected={onSelected} />}
  </div>
}
