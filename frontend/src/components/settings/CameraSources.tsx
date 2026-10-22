import { useEffect, useState } from "react"
import { getCameraSourceStatus, type CameraSourceStatus, type SourceRelease } from "@/lib/api"
import SourceUpload from "@/components/settings/SourceUpload"
import { SourceRollback } from "@/components/settings/SourceSelection"

const button = "min-h-11 rounded border border-zinc-600 px-3 py-2 text-sm font-medium hover:bg-zinc-800 disabled:cursor-not-allowed disabled:opacity-50"
const sourceNames = { managed: "Imported original", configured_original: "Configured original", bundled_proxy: "Bundled playback copy", missing: "No footage available" }
function bytes(value: number | null) {
  if (value === null) return "Size unavailable"
  const divisor = value < 1024 ? 1 : value < 1024 * 1024 ? 1024 : 1024 * 1024
  return `${(value / divisor).toLocaleString(undefined, { maximumFractionDigits: 2 })} ${divisor === 1 ? "bytes" : divisor === 1024 ? "KiB" : "MiB"}`
}
function importedAt(release: SourceRelease) { return release.imported_at ? new Date(release.imported_at * 1000).toLocaleString() : "Date unavailable" }

function ReleaseDetails({ release }: { release: SourceRelease }) {
  const video = release.original.video
  return <dl className="mt-3 grid gap-2 text-sm leading-relaxed sm:grid-cols-[auto_minmax(0,1fr)] sm:gap-x-4">
    <dt className="text-zinc-300">Imported</dt><dd>{importedAt(release)}</dd>
    <dt className="text-zinc-300">Operator claim</dt><dd className="break-words">{release.reviewer || "Not recorded"}</dd>
    <dt className="text-zinc-300">Authenticated uploader</dt><dd className="break-words">{release.uploader_authenticated ? release.authenticated_uploader || "Account unavailable" : "Not recorded for this import"}</dd>
    <dt className="text-zinc-300">Reason</dt><dd className="break-words">{release.reason || "Not recorded"}</dd>
    <dt className="text-zinc-300">Recording clock</dt><dd className="break-words">{release.recording_clock ? `${new Date(release.recording_clock.start_utc).toLocaleString()} · ${release.recording_clock.uncertainty_seconds === null ? "uncertainty unknown" : `±${release.recording_clock.uncertainty_seconds} s`} · operator claim, unverified` : "Not supplied; source clock unknown"}</dd>
    <dt className="text-zinc-300">Source provenance</dt><dd className="break-words">{release.source_provenance.status === "not_provided" ? "Not provided" : `Operator claims, unverified · ${[
      release.source_provenance.archive_creator && `supplier: ${release.source_provenance.archive_creator}`,
      release.source_provenance.export_system && `export: ${release.source_provenance.export_system}`,
      release.source_provenance.external_camera_id && `source camera: ${release.source_provenance.external_camera_id}`,
      `timezone: ${release.source_provenance.recording_timezone}`,
      release.source_provenance.authorization_basis && `authorization: ${release.source_provenance.authorization_basis}`,
      release.source_provenance.retention_note && `retention: ${release.source_provenance.retention_note}`,
    ].filter(Boolean).join(" · ")}`}</dd>
    <dt className="text-zinc-300">Video metadata</dt><dd className="tabular-nums">{video.width ?? "?"} × {video.height ?? "?"} · {video.fps ?? "?"} fps · {video.duration_seconds ?? "?"} seconds</dd>
    <dt className="text-zinc-300">Original</dt><dd>{bytes(release.original.bytes)}</dd>
    <dt className="text-zinc-300">Playback copy</dt><dd>{bytes(release.playback.bytes)}</dd>
    <dt className="text-zinc-300">Original SHA-256</dt><dd className="min-w-0 break-all font-mono">{release.original.sha256 || "Not recorded"}</dd>
    <dt className="text-zinc-300">Playback SHA-256</dt><dd className="min-w-0 break-all font-mono">{release.playback.sha256 || "Not recorded"}</dd>
  </dl>
}

export default function CameraSources({ cameraId,sourceBusy,onBusyChange }: { cameraId: string;sourceBusy:boolean;onBusyChange:(busy:boolean)=>void }) {
  const [source, setSource] = useState<CameraSourceStatus | null>(null)
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(true)
  const [refresh, setRefresh] = useState(0)
  const [uploadBusy,setUploadBusy]=useState(false)
  const [selectionBusy,setSelectionBusy]=useState(false)
  useEffect(()=>{onBusyChange(uploadBusy || selectionBusy)},[uploadBusy,selectionBusy,onBusyChange])
  useEffect(()=>()=>onBusyChange(false),[onBusyChange])
  function selectedSource(value:CameraSourceStatus) {setSource(value);setError("")}
  useEffect(() => {
    const controller = new AbortController()
    getCameraSourceStatus(cameraId, controller.signal).then(result => {
      if (!controller.signal.aborted) setSource(result)
    }).catch(error => { if (!controller.signal.aborted) setError(error instanceof Error ? error.message : "Source details unavailable") })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [cameraId, refresh])
  const current = source?.camera_id === cameraId ? source : null
  const active = current?.active
  const selected = current?.selection
  const command = `uv run --frozen --directory backend python import_source.py ${cameraId} "/absolute/path/to/clip.mp4"`

  return <section aria-labelledby="camera-source-title" className="mt-6 min-w-0 border-y border-zinc-800 py-6">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <h2 id="camera-source-title" className="text-lg font-semibold">Source footage</h2>
      <button type="button" className={button} disabled={loading || sourceBusy} onClick={() => { setLoading(true); setError(""); setRefresh(value => value + 1) }}>{loading ? "Checking sources…" : "Refresh source status"}</button>
    </div>
    {error && <p role="alert" className="mt-3 rounded border border-red-400/40 bg-red-950/40 p-3 text-sm text-red-100">Could not check footage: {error}. Refresh source status to try again.</p>}
    {current && active && selected && <>
      <div className="mt-4 grid gap-4 text-sm sm:grid-cols-2">
        <div><h3 className="font-medium">Inference source</h3><p className="mt-1 text-zinc-300">{sourceNames[active.kind]}</p><p className="mt-1 break-all">{active.inference.available ? `${active.inference.filename} · ${bytes(active.inference.bytes)}` : "Source file missing. Supply footage to enable this camera."}</p></div>
        <div><h3 className="font-medium">Browser playback</h3><p className="mt-1 break-all text-zinc-300">{active.playback.available ? `${active.playback.filename} · ${bytes(active.playback.bytes)}` : "Playback file missing"}</p><p className="mt-1 text-zinc-300">Recorded replay; original capture clocks are unverified.</p></div>
      </div>
      {(active.inference.size_matches_import === false || active.playback.size_matches_import === false) && <p role="alert" className="mt-3 rounded border border-red-400/40 bg-red-950/40 p-3 text-sm text-red-100">A running import file is missing or its size has changed. Restore the original release files before restarting.</p>}
      {selected.status === "restart_required" && <div role="status" className="mt-3 rounded border border-teal-500/40 bg-teal-950/30 p-3 text-sm leading-relaxed text-teal-100"><p>Restart required. {selected.release ? "A different import is selected." : "The imported selection was removed; configured footage will be used."} Running inference and playback keep their current source until the API restarts.</p><p className="mt-2">On the API host, restart the deployment. For the local launcher, stop it with Ctrl+C and run <code>uv run run.py --skip-install</code> with the same data/source settings. For Docker Compose, run <code>ops/restart-backend.sh</code> from the deployment directory; it waits for the backend health check. Then refresh source status.</p></div>}
      {selected.error && <p role="alert" className="mt-3 rounded border border-red-400/40 bg-red-950/40 p-3 text-sm leading-relaxed text-red-100">{selected.error} The running source has not been switched.</p>}
      {selected.last_action && <details className="mt-3 text-sm"><summary className="min-h-11 cursor-pointer py-3 font-medium">Last browser selection · {selected.last_action.intent === "rollback" ? "Earlier import" : "Prepared import"}</summary>
        <p className="break-words leading-relaxed text-zinc-300">{selected.last_action.selected_at ? new Date(selected.last_action.selected_at*1000).toLocaleString() : "Date unavailable"} · {selected.last_action.reviewer || "Reviewer unavailable"}</p>
        <p className="mt-2 break-words leading-relaxed text-zinc-300">{selected.last_action.reviewer_authenticated ? `Authenticated account: ${selected.last_action.authenticated_user || "unavailable"}` : "Reviewer is an unauthenticated local claim."}</p>
        <p className="mt-2 break-words leading-relaxed">{selected.last_action.reason || "Reason unavailable"}</p>
        <p className="mt-2 leading-relaxed text-zinc-300">Selection records the change; it does not mean the release is active or its content verified.</p>
      </details>}
      {(selected.history.entries.length > 0 || selected.history.error) && <details className="mt-2 border-t border-zinc-800 pt-2 text-sm">
        <summary className="min-h-11 cursor-pointer py-3 font-medium">Source selection history · {selected.history.entries.length}{selected.history.more ? "+" : ""}</summary>
        {selected.history.error && <p role="alert" className="mt-2 text-red-200">{selected.history.error} The linked history may be incomplete.</p>}
        <ol className="divide-y divide-zinc-800">
          {selected.history.entries.map((entry,index)=><li key={entry.id} className="py-3">
            <p className="break-words font-medium">{index===0 ? "Latest selection" : entry.intent === "rollback" ? "Earlier release selected" : "Prepared release selected"} · {entry.selected_at ? new Date(entry.selected_at*1000).toLocaleString() : "Date unavailable"}</p>
            <p className="mt-1 break-words text-zinc-300">{entry.reviewer_authenticated ? `Authenticated account: ${entry.authenticated_user || "unavailable"}` : `Reviewer claim: ${entry.reviewer || "unavailable"}`}</p>
            <p className="mt-1 break-words text-zinc-300">{entry.reason || "Reason unavailable"}</p>
            <p className="mt-1 break-all text-xs text-zinc-400">{entry.from_release || "Default source"} → {entry.to_release || "Unknown release"}</p>
          </li>)}
        </ol>
        {selected.history.more && <p className="mt-2 text-zinc-300">Older records remain on the host; this view is limited to the latest twenty selections.</p>}
      </details>}
      {active.release && <details className="mt-4 text-sm"><summary className="min-h-11 cursor-pointer py-3 font-medium">Running import · {active.release.release}</summary><ReleaseDetails release={active.release} /></details>}
      <p className="mt-3 max-w-[70ch] text-sm leading-relaxed text-zinc-300">Checked {new Date(current.checked_at * 1000).toLocaleTimeString()}. {current.verification}</p>
      {active.kind === "bundled_proxy" && <p className="mt-2 text-sm leading-relaxed text-zinc-300">Inference currently uses the bundled playback copy. Original recording bytes are not available for this source.</p>}
      <details className="mt-4 border-t border-zinc-800 pt-2 text-sm">
        <summary className="min-h-11 cursor-pointer py-3 font-medium">Import or replace recorded footage</summary>
        <SourceUpload cameraId={cameraId} source={current} disabled={loading || selectionBusy} onBusyChange={setUploadBusy} onSelectionBusyChange={setSelectionBusy} onSelected={selectedSource} />
        <details className="mt-4 border-t border-zinc-800 pt-2">
        <summary className="min-h-11 cursor-pointer py-3 font-medium">Import a file already on the API host</summary>
        <ol className="list-decimal space-y-3 pl-5 leading-relaxed text-zinc-300">
          <li>On the API host, install FFmpeg with libx264 and ffprobe. Open a terminal in the Sakshi repository and export the same data/source settings as the app.</li>
          <li>Check your file first. Replace the example path with the file’s absolute path.<code className="mt-2 block whitespace-pre-wrap break-all rounded bg-zinc-900 p-3 font-mono text-white">{command} --check</code></li>
          <li>Stop the app with Ctrl+C in its terminal. Import the file, supplying your name and reason. Use <code>--replace</code> only when replacing existing footage.<code className="mt-2 block whitespace-pre-wrap break-all rounded bg-zinc-900 p-3 font-mono text-white">{command}{active.inference.available || selected.release ? " --replace" : ""} --reviewer "Your name" --reason "Why this footage belongs to this camera"</code></li>
          <li>Restart the app with <code>uv run run.py --skip-install</code>, then refresh source status. Review location metadata separately; importing footage does not verify its location.</li>
        </ol>
        </details>
        <p className="mt-3 leading-relaxed text-zinc-300">Selection takes effect after host restart. Live source switching and automatic video cleanup are not available. Original files and prior imports are retained.</p>
      </details>
      <details className="mt-2 border-t border-zinc-800 pt-2 text-sm">
        <summary className="min-h-11 cursor-pointer py-3 font-medium">Recent imported releases · {current.history.releases.length}{current.history.more ? "+" : ""}</summary>
        {current.history.error && <p role="alert" className="mt-2 text-red-200">{current.history.error}</p>}
        {!current.history.releases.length && !current.history.error && <p className="mt-2 text-zinc-300">No managed imports are selected for this camera. Bundled and configured files have no import history.</p>}
        <ul className="divide-y divide-zinc-800">
          {current.history.releases.map(release => <li key={release.release} className="py-3"><details>
            <summary className="min-h-11 cursor-pointer break-all py-2 font-medium">{release.release} · {release.release === selected.release?.release && selected.status === "restart_required" ? "Selected for restart" : release.release === active.release?.release ? "Running" : "Earlier import"}</summary>
            <ReleaseDetails release={release} />
          </details></li>)}
        </ul>
        <SourceRollback cameraId={cameraId} source={current} disabled={loading || uploadBusy || selectionBusy} onBusyChange={setSelectionBusy} onSelected={selectedSource} />
        <p className="mt-2 leading-relaxed text-zinc-300">Up to ten releases from the selected import’s parent chain. {current.history.more ? "Older releases remain on the host." : "Unlinked releases are not listed."} History metadata and retained files have not been revalidated here.</p>
      </details>
    </>}
  </section>
}
