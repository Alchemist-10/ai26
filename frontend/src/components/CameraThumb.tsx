import { memo, useEffect, useRef, useState } from "react"
import { usePolling } from "@/hooks/usePolling"
import { scopedResourceUrl } from "@/lib/api"

export const CameraThumb = memo(function CameraThumb({ cameraId, available, className }: { cameraId: string; available: boolean; className?: string }) {
  const [image, setImage] = useState("")
  const [failed, setFailed] = useState(false)
  const etag = useRef("")
  const objectUrl = useRef("")
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
    } catch { if (!signal.aborted) setFailed(true) }
  }, 3000, available)
  useEffect(() => () => { if (objectUrl.current) URL.revokeObjectURL(objectUrl.current) }, [])
  if (!available || failed || !image) return <div role="img" aria-label={`${cameraId} ${available ? "preview unavailable" : "source missing"}`} className="flex h-full items-center justify-center bg-zinc-950 text-xs text-zinc-500">{available ? "Preview preparing" : "Source missing"}</div>
  return <img src={image} alt={`${cameraId} sampled preview`} className={className} decoding="async" />
})
