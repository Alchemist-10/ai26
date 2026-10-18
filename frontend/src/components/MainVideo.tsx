import { useEffect, useRef, useState } from "react"
import { Play, ScanLine } from "lucide-react"
import { cameraPlaybackOffset, getPrivacyStatus, streamUrl, videoUrl, type Camera } from "@/lib/api"
import { usePageVisible } from "@/hooks/usePolling"

type PlaybackQuality = { droppedFrames: number; totalFrames: number }
type ViewMode = "idle" | "playback" | "detections"

function VideoFeed({ camera }: { camera: Camera | undefined }) {
  const [mode, setMode] = useState<ViewMode>("idle")
  const [privacyEnabled, setPrivacyEnabled] = useState(true)
  const [privacyStatusReady, setPrivacyStatusReady] = useState(false)
  const [retry, setRetry] = useState(0)
  const [failed, setFailed] = useState(false)
  const [streamReady, setStreamReady] = useState(false)
  const [playbackQuality, setPlaybackQuality] = useState<PlaybackQuality | null>(null)
  const [playbackQualitySupported, setPlaybackQualitySupported] = useState<boolean | null>(null)
  const videoRef = useRef<HTMLVideoElement>(null)
  const visible = usePageVisible()
  useEffect(() => {
    const controller = new AbortController()
    void getPrivacyStatus(controller.signal).then(status => {
      setPrivacyEnabled(status.enabled)
      setMode(status.enabled ? "detections" : "idle")
      setPrivacyStatusReady(true)
    }).catch(() => setPrivacyEnabled(true))
    return () => controller.abort()
  }, [retry])
  useEffect(() => {
    const video = videoRef.current
    if (!video) return
    if (visible) void video.play().catch(() => undefined)
    else video.pause()
  }, [visible, mode, camera?.id])
  useEffect(() => {
    const video = videoRef.current
    if (!video || !visible || mode !== "playback" || failed) {
      setPlaybackQuality(null)
      setPlaybackQualitySupported(null)
      return
    }
    if (typeof video.getVideoPlaybackQuality !== "function") {
      setPlaybackQuality(null)
      setPlaybackQualitySupported(false)
      return
    }
    setPlaybackQualitySupported(true)
    const update = () => {
      const quality = video.getVideoPlaybackQuality()
      const next = { droppedFrames: quality.droppedVideoFrames, totalFrames: quality.totalVideoFrames }
      setPlaybackQuality(current => current?.droppedFrames === next.droppedFrames && current.totalFrames === next.totalFrames
        ? current
        : next)
    }
    update()
    const timer = window.setInterval(update, 2000)
    return () => window.clearInterval(timer)
  }, [visible, mode, camera?.id, retry, failed])
  const seek = () => {
    const video = videoRef.current
    if (video && camera && Number.isFinite(video.duration)) {
      video.currentTime = cameraPlaybackOffset(camera.id, video.duration)
      if (visible) void video.play().catch(() => undefined)
    }
  }
  if (!camera) return null
  const unavailable = !privacyStatusReady || !camera.source_available || failed || (mode === "detections" && ["error", "stopped"].includes(camera.health.status))
  return <div className="flex h-full min-h-0 flex-col bg-black">
    <div className="flex flex-none flex-wrap items-center gap-2 border-b border-zinc-800 px-3 py-2 text-xs">
      {mode !== "idle" && (!privacyEnabled ? (["playback", "detections"] as const) : (["detections"] as const)).map(value => <button key={value} type="button" aria-pressed={mode === value} onClick={() => { setMode(value); setFailed(false); setStreamReady(false) }} className={`min-h-9 rounded border px-3 py-1.5 ${mode === value ? "border-white bg-white text-black" : "border-zinc-700 text-zinc-300 hover:border-zinc-500 hover:bg-zinc-900"}`}>{value === "playback" ? "Recorded playback" : "Sampled detections"}</button>)}
      <span className="text-zinc-400">{mode === "playback" ? "Original source video · no detection overlay" : mode === "detections" ? camera.health.processing_enabled ? `Shared inference · ${camera.health.processed_fps.toFixed(2)} FPS sampled` : "Sampled detections unavailable · processing paused" : `No view loaded · ${camera.id}`}</span>
      {mode === "playback" && <span className="ml-auto text-[11px] tabular-nums text-zinc-400" aria-label="Local browser playback frame loss">
        {playbackQualitySupported === false ? "Browser playback counters unavailable" : playbackQuality
          ? `Browser playback frame loss: ${playbackQuality.droppedFrames}/${playbackQuality.totalFrames} (${playbackQuality.totalFrames ? (playbackQuality.droppedFrames / playbackQuality.totalFrames * 100).toFixed(1) : "0.0"}%)`
          : "Reading browser playback counters…"}
      </span>}
    </div>
    <div className="relative flex min-h-0 flex-1 items-center justify-center overflow-hidden">
      {privacyStatusReady && camera.source_available && (mode === "playback" ? <video key={`${camera.id}-${retry}`} ref={videoRef} src={videoUrl(camera.id)} aria-label={`${camera.id} recorded playback`} className="h-full w-full object-contain" controls muted playsInline preload="metadata" onLoadedMetadata={seek} onCanPlay={() => setFailed(false)} onEnded={seek} onError={() => setFailed(true)} /> : mode === "detections" && visible && camera.health.processing_enabled ? <img key={`${camera.id}-${retry}`} src={streamUrl(camera.id, undefined, retry)} alt={`${camera.id} sampled detections`} className="h-full w-full object-contain" onLoad={() => { setFailed(false); setStreamReady(true) }} onError={() => { setFailed(true); setStreamReady(false) }} /> : mode === "idle" ? <section aria-labelledby="view-choice-heading" className="flex w-full max-w-3xl flex-col items-center gap-3 px-5 py-6 text-center">
        <h2 id="view-choice-heading" className="text-lg font-semibold text-white">Choose a view for {camera.id}</h2>
        <p className="max-w-prose text-sm leading-relaxed text-zinc-400">Media stays unloaded until you choose. Pick the footage you need to inspect.</p>
        <div className="mt-2 grid w-full gap-3 sm:grid-cols-2">
          <button type="button" onClick={() => { setMode("playback"); setFailed(false); setStreamReady(false) }} className="group flex min-h-20 items-center gap-4 rounded-md border border-zinc-700 bg-zinc-950 px-4 py-3 text-left transition-colors hover:border-zinc-500 hover:bg-zinc-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary">
            <span className="flex h-10 w-10 flex-none items-center justify-center rounded border border-zinc-700 bg-black text-zinc-200 group-hover:border-zinc-500"><Play className="h-4 w-4" aria-hidden="true" /></span>
            <span><span className="block text-sm font-semibold text-white">Recorded playback</span><span className="mt-1 block text-xs leading-relaxed text-zinc-400">Original video without detection overlays.</span></span>
          </button>
          <button type="button" onClick={() => { setMode("detections"); setFailed(false); setStreamReady(false) }} className="group flex min-h-20 items-center gap-4 rounded-md border border-zinc-700 bg-zinc-950 px-4 py-3 text-left transition-colors hover:border-zinc-500 hover:bg-zinc-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary">
            <span className="flex h-10 w-10 flex-none items-center justify-center rounded border border-zinc-700 bg-black text-primary group-hover:border-primary/60"><ScanLine className="h-4 w-4" aria-hidden="true" /></span>
            <span><span className="block text-sm font-semibold text-white">Sampled detections</span><span className="mt-1 block text-xs leading-relaxed text-zinc-400">Frames from the shared inference feed.</span></span>
          </button>
        </div>
      </section> : null)}
      {mode === "detections" && visible && camera.source_available && privacyStatusReady && !camera.health.processing_enabled && <div role="status" className="absolute inset-0 flex items-center justify-center bg-black/75 px-4 text-center text-sm text-zinc-200">Processing is paused; no sampled frame is available.</div>}
      {mode === "detections" && visible && camera.source_available && privacyStatusReady && camera.health.processing_enabled && !failed && !streamReady && !["error", "stopped"].includes(camera.health.status) && <div role="status" aria-live="polite" className="absolute inset-0 flex flex-col items-center justify-center gap-2 bg-black/75 px-4 text-center text-sm text-zinc-200"><span>{camera.health.status === "loading" ? "Preparing the detection model; the first sample can take several seconds." : "Waiting for the first sampled frame…"}</span></div>}
      {unavailable && <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 bg-black/90 text-center text-xs text-red-200"><span>{!privacyStatusReady ? "Privacy status unavailable; camera view hidden" : !camera.source_available ? "Source file missing" : camera.health.error || "Camera view unavailable"}</span><button type="button" className="rounded border border-red-300/40 px-3 py-2" onClick={() => { setFailed(false); setStreamReady(false); setPrivacyStatusReady(false); setRetry(value => value + 1) }}>Retry view</button></div>}
      <div className="pointer-events-none absolute left-3 top-3 rounded border border-white/10 bg-black/80 px-3 py-2"><div className="text-sm font-semibold text-white">{camera.id}</div><div className="text-xs text-zinc-400">{camera.location_confirmed ? camera.location : "Location unconfirmed"}</div></div>
    </div>
  </div>
}
export function MainVideo({ camera }: { camera: Camera | undefined }) {
  return <VideoFeed key={camera?.id} camera={camera} />
}
