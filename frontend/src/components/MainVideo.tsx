import { useState, useEffect, useRef } from "react"
import { streamUrl, type Camera } from "@/lib/api"
import {
  RotateCw,
  VideoOff,
  MapPin,
  Camera as CameraIcon,
  ScanLine,
  Maximize2,
  Minimize2,
} from "lucide-react"

export function MainVideo({
  camera,
  startAt,
  anchorAt,
}: {
  camera: Camera | undefined
  startAt?: number
  anchorAt?: number
}) {
  const [retry, setRetry] = useState(0)
  const [failed, setFailed] = useState(false)
  const [isFullscreen, setIsFullscreen] = useState(false)
  const [timestamp, setTimestamp] = useState("")
  const containerRef = useRef<HTMLDivElement>(null)
  const imgRef = useRef<HTMLImageElement>(null)

  useEffect(() => {
    setFailed(false)
    setRetry(0)
    return () => {
      if (imgRef.current) {
        imgRef.current.src = ""
      }
    }
  }, [camera?.id, startAt, anchorAt])

  useEffect(() => {
    const update = () => {
      const now = new Date()
      setTimestamp(
        now.toLocaleDateString("en-US", { month: "short", day: "2-digit" }) +
          " " +
          now.toTimeString().split(" ")[0]
      )
    }
    update()
    const timer = setInterval(update, 1000)
    return () => clearInterval(timer)
  }, [])

  function toggleFullscreen() {
    if (!containerRef.current) return
    if (!document.fullscreenElement) {
      void containerRef.current.requestFullscreen().then(() => setIsFullscreen(true)).catch(() => {})
    } else {
      void document.exitFullscreen().then(() => setIsFullscreen(false)).catch(() => {})
    }
  }

  if (!camera) {
    return (
      <div className="flex h-full w-full items-center justify-center bg-[#07080c] text-zinc-500 text-xs font-mono">
        Select a camera feed to display
      </div>
    )
  }

  return (
    <div
      ref={containerRef}
      className="group relative flex h-full w-full items-center justify-center overflow-hidden bg-[#06070a] select-none"
    >
      <div className="pointer-events-none absolute inset-3 z-10">
        <div className="absolute left-0 top-0 h-3 w-3 border-l-2 border-t-2 border-white/20" />
        <div className="absolute right-0 top-0 h-3 w-3 border-r-2 border-t-2 border-white/20" />
        <div className="absolute bottom-0 left-0 h-3 w-3 border-b-2 border-l-2 border-white/20" />
        <div className="absolute bottom-0 right-0 h-3 w-3 border-b-2 border-r-2 border-white/20" />
      </div>

      <img
        ref={imgRef}
        key={`${camera.id}-${retry}`}
        src={streamUrl(camera.id, startAt, retry, anchorAt)}
        alt={`Live inference feed: ${camera.id}`}
        className={`h-full w-full object-contain ${failed ? "hidden" : "block"}`}
        onLoad={() => setFailed(false)}
        onError={() => setFailed(true)}
      />

      <div className="absolute top-0 inset-x-0 z-20 flex items-center justify-between p-4 bg-gradient-to-b from-black/80 via-black/30 to-transparent pointer-events-none">
        <div className="flex items-center gap-2 pointer-events-auto">
          <div className="flex items-center gap-2 rounded-lg bg-black/65 px-3 py-1.5 backdrop-blur-md border border-white/10 shadow-sm">
            <span
              className={`h-2 w-2 rounded-full ${
                failed ? "bg-rose-500" : "bg-emerald-400 animate-pulse"
              }`}
            />
            <span className="font-mono text-xs font-bold text-white tracking-wider">
              {camera.id}
            </span>
          </div>

          <div className="flex items-center gap-1.5 rounded-lg bg-black/60 px-2.5 py-1.5 text-xs text-zinc-300 backdrop-blur-md border border-white/10">
            {camera.kind === "plate" ? (
              <>
                <ScanLine className="h-3.5 w-3.5 text-blue-400" />
                <span className="text-[11px] font-mono font-medium text-zinc-200">Fast-ALPR OCR</span>
              </>
            ) : (
              <>
                <CameraIcon className="h-3.5 w-3.5 text-emerald-400" />
                <span className="text-[11px] font-mono font-medium text-zinc-200">YOLOv8 + Centroid</span>
              </>
            )}
          </div>
        </div>

        <div className="flex items-center gap-2 pointer-events-auto">
          <div className="hidden sm:flex font-mono text-xs text-zinc-300 bg-black/60 px-3 py-1.5 rounded-lg backdrop-blur-md border border-white/10 tabular-nums">
            {timestamp}
          </div>

          <button
            type="button"
            onClick={() => {
              setFailed(false)
              setRetry((r) => r + 1)
            }}
            title="Reload feed"
            className="rounded-lg bg-black/60 p-2 text-zinc-400 hover:text-white hover:bg-black/80 transition-all border border-white/10 backdrop-blur-md cursor-pointer shadow-sm"
          >
            <RotateCw className="h-3.5 w-3.5" />
          </button>

          <button
            type="button"
            onClick={toggleFullscreen}
            title={isFullscreen ? "Exit Fullscreen" : "Fullscreen"}
            className="rounded-lg bg-black/60 p-2 text-zinc-400 hover:text-white hover:bg-black/80 transition-all border border-white/10 backdrop-blur-md cursor-pointer shadow-sm"
          >
            {isFullscreen ? <Minimize2 className="h-3.5 w-3.5" /> : <Maximize2 className="h-3.5 w-3.5" />}
          </button>
        </div>
      </div>

      <div className="absolute bottom-0 inset-x-0 z-10 flex items-center justify-between p-3.5 bg-gradient-to-t from-black/80 via-black/40 to-transparent pointer-events-none">
        <div className="flex items-center gap-2 pointer-events-auto">
          <div className="flex items-center gap-1.5 rounded-md bg-black/60 px-2.5 py-1 text-xs text-zinc-300 backdrop-blur-md border border-white/10">
            <MapPin className="h-3.5 w-3.5 text-zinc-400 flex-shrink-0" />
            <span className="truncate max-w-xs sm:max-w-md">
              {camera.location_confirmed ? camera.location : "Location unconfirmed"}
            </span>
          </div>

          <span className="hidden md:inline font-mono text-[11px] text-zinc-400 bg-black/40 px-2 py-1 rounded border border-white/5 backdrop-blur-md">
            {camera.lat.toFixed(4)}°N, {camera.lon.toFixed(4)}°E
          </span>
        </div>

        <div className="pointer-events-auto">
          <span className="font-mono text-[10px] text-zinc-400 bg-black/50 px-2 py-0.5 rounded border border-white/10">
            H.264 / LIVE INFERENCE
          </span>
        </div>
      </div>

      {failed && (
        <div className="absolute inset-0 z-20 flex flex-col items-center justify-center bg-[#090b10]/95 backdrop-blur-sm p-6 text-center">
          <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-zinc-900 border border-zinc-800 text-zinc-400 mb-3">
            <VideoOff className="h-6 w-6 text-zinc-500" />
          </div>
          <div className="font-mono text-sm font-semibold text-zinc-200">
            Feed Offline: {camera.id}
          </div>
          <p className="mt-1 max-w-sm text-xs text-zinc-400 leading-relaxed">
            {camera.kind === "plate"
              ? "ANPR video clip not found in local footage directory. Supply footage to enable inference."
              : "Unable to establish live inference connection for this camera channel."}
          </p>
          <button
            type="button"
            onClick={() => {
              setFailed(false)
              setRetry((r) => r + 1)
            }}
            className="mt-4 inline-flex items-center gap-2 rounded-md bg-zinc-200 px-3.5 py-1.5 text-xs font-semibold text-zinc-900 hover:bg-white transition-colors cursor-pointer shadow-sm"
          >
            <RotateCw className="h-3.5 w-3.5" />
            <span>Retry Connection</span>
          </button>
        </div>
      )}
    </div>
  )
}
