import { memo, useEffect, useRef, useState } from "react"
import { usePolling } from "@/hooks/usePolling"
import { scopedResourceUrl } from "@/lib/api"

export const CameraThumb = memo(function CameraThumb({ cameraId, available, processingEnabled, processingStatus, className }: { cameraId: string; available: boolean; processingEnabled: boolean; processingStatus: string; className?: string }) {
  const [image, setImage] = useState("")
  const [failed, setFailed] = useState(false)
  const [nearViewport, setNearViewport] = useState(() => !("IntersectionObserver" in window))
  const container = useRef<HTMLDivElement>(null)
  const etag = useRef("")
  const objectUrl = useRef("")
  useEffect(() => {
    const element = container.current
    if (!element) return
    if (!("IntersectionObserver" in window)) return
    const observer = new IntersectionObserver(([entry]) => {
      setNearViewport(Boolean(entry?.isIntersecting))
    }, { rootMargin: "120px 0px" })
    observer.observe(element)
    return () => observer.disconnect()
  }, [])
  usePolling(async signal => {
    try {
      const response = await fetch(scopedResourceUrl(`/api/preview/${cameraId}`), { signal, credentials: "same-origin", headers: etag.current ? { "If-None-Match": etag.current } : {} })
      if (response.status === 304) { if (!signal.aborted) setFailed(false); return }
      if (!response.ok) throw new Error("Preview unavailable")
      const nextEtag = response.headers.get("etag") || ""
      if (nextEtag && nextEtag === etag.current && image) { if (!signal.aborted) setFailed(false); return }
      const blob = await response.blob()
      if (signal.aborted) return
      const next = URL.createObjectURL(blob)
      const previous = objectUrl.current
      objectUrl.current = next; etag.current = nextEtag
      setImage(next); setFailed(false)
      if (previous) URL.revokeObjectURL(previous)
    } catch { if (!signal.aborted && processingStatus !== "loading") setFailed(true) }
  }, 3000, nearViewport && available && processingEnabled && ["loading", "processing"].includes(processingStatus))
  useEffect(() => () => { if (objectUrl.current) URL.revokeObjectURL(objectUrl.current) }, [])
  if (!available || !processingEnabled || !["loading", "processing"].includes(processingStatus) || failed || !image) {
    const message = !available ? "Source missing" : !processingEnabled ? "Processing paused" : processingStatus === "error" ? "Processing error" : failed ? "Preview unavailable" : "Preview preparing"
    return <div ref={container} role="img" aria-label={`${cameraId} ${message}`} className="flex h-full w-full items-center justify-center bg-zinc-950 px-1 text-center text-[0px] leading-none text-zinc-500 lg:text-xs lg:leading-normal">{message}</div>
  }
  return <div ref={container} className="h-full w-full"><img src={image} alt={`${cameraId} sampled preview`} className={className} decoding="async" /></div>
})
