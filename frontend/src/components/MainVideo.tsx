import { useEffect, useRef, useState } from "react"
import { cameraPlaybackOffset, getPrivacyStatus, streamUrl, videoUrl, type Camera } from "@/lib/api"
import { usePageVisible } from "@/hooks/usePolling"

function VideoFeed({ camera }: { camera: Camera | undefined }) {
  const [mode, setMode] = useState<"playback" | "detections">("detections")
  const [privacyEnabled, setPrivacyEnabled] = useState(true)
  const [retry, setRetry] = useState(0)
  const [failed, setFailed] = useState(false)
  const videoRef = useRef<HTMLVideoElement>(null)
  const visible = usePageVisible()
  useEffect(() => {
    const controller = new AbortController()
    void getPrivacyStatus(controller.signal).then(status => {
      setPrivacyEnabled(status.enabled)
      setMode(status.enabled ? "detections" : "playback")
    }).catch(() => setPrivacyEnabled(true))
    return () => controller.abort()
  }, [])
  useEffect(() => {
    const video = videoRef.current
    if (!video) return
    if (visible) void video.play().catch(() => undefined)
    else video.pause()
  }, [visible, mode, camera?.id])
  const seek = () => {
    const video = videoRef.current
    if (video && camera && Number.isFinite(video.duration)) {
      video.currentTime = cameraPlaybackOffset(camera.id, video.duration)
      if (visible) void video.play().catch(() => undefined)
    }
  }
  if (!camera) return null
  const unavailable = !camera.source_available || failed || (mode === "detections" && ["error", "stopped"].includes(camera.health.status))
  return <div className="flex h-full min-h-0 flex-col bg-black">
    <div className="flex flex-none flex-wrap items-center gap-2 border-b border-zinc-800 px-3 py-2 text-xs">
      {(!privacyEnabled ? (["playback", "detections"] as const) : (["detections"] as const)).map(value => <button key={value} type="button" aria-pressed={mode === value} onClick={() => { setMode(value); setFailed(false) }} className={`rounded border px-3 py-1.5 ${mode === value ? "border-white bg-white text-black" : "border-zinc-700 text-zinc-300"}`}>{value === "playback" ? "Recorded playback" : "Sampled detections"}</button>)}
      <span className="text-zinc-400">{mode === "playback" ? "Smooth source video · no detection overlay" : `Shared inference · ${camera.health.processed_fps.toFixed(2)} FPS sampled`}</span>
    </div>
    <div className="relative flex min-h-0 flex-1 items-center justify-center overflow-hidden">
      {camera.source_available && (mode === "playback" ? <video key={`${camera.id}-${retry}`} ref={videoRef} src={videoUrl(camera.id)} aria-label={`${camera.id} recorded playback`} className="h-full w-full object-contain" controls muted playsInline preload="metadata" onLoadedMetadata={seek} onCanPlay={() => setFailed(false)} onEnded={seek} onError={() => setFailed(true)} /> : visible && <img key={`${camera.id}-${retry}`} src={streamUrl(camera.id, undefined, retry)} alt={`${camera.id} sampled detections`} className="h-full w-full object-contain" onLoad={() => setFailed(false)} onError={() => setFailed(true)} />)}
      {unavailable && <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 bg-black/90 text-center text-xs text-red-200"><span>{!camera.source_available ? "Source file missing" : camera.health.error || "Camera view unavailable"}</span><button type="button" className="rounded border border-red-300/40 px-3 py-2" onClick={() => { setFailed(false); setRetry(value => value + 1) }}>Retry view</button></div>}
      <div className="pointer-events-none absolute left-3 top-3 rounded border border-white/10 bg-black/80 px-3 py-2"><div className="text-sm font-semibold text-white">{camera.id}</div><div className="text-xs text-zinc-400">{camera.location_confirmed ? camera.location : "Location unconfirmed"}</div></div>
    </div>
  </div>
}
export function MainVideo({ camera }: { camera: Camera | undefined }) {
  return <VideoFeed key={camera?.id} camera={camera} />
}
