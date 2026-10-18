import type { Camera } from "@/lib/api"
import { OsmMap } from "@/components/OsmMap"
import { Badge } from "@/components/ui/badge"

export function MapView({
  cameras,
  focused,
  onFocus,
}: {
  cameras: Camera[]
  focused: string
  onFocus: (id: string) => void
}) {
  const points = cameras.filter(cam => cam.location_confirmed && Number.isFinite(cam.lat) && Number.isFinite(cam.lon)).map((cam) => ({
    id: cam.id,
    lat: cam.lat,
    lon: cam.lon,
    label: cam.id,
    detail: cam.location_confirmed ? cam.location : "Location unconfirmed",
    active: cam.id === focused,
  }))
  const unlocated = cameras.filter(cam => !cam.location_confirmed || !Number.isFinite(cam.lat) || !Number.isFinite(cam.lon))

  return (
    <div className="relative h-full w-full overflow-hidden">
      <OsmMap points={points} onPointClick={onFocus} className="h-full w-full" />
      <Badge variant="outline" className="absolute right-3 top-3 bg-background/85">Confirmed camera locations</Badge>
      {unlocated.length > 0 && <div className="absolute left-3 top-3 max-w-[70%] rounded border border-border bg-background/90 px-3 py-2 text-xs text-muted-foreground">Location unconfirmed; not plotted: {unlocated.map(cam => cam.id).join(", ")}</div>}
      {points.length === 0 && <div className="absolute left-1/2 top-1/2 max-w-xs -translate-x-1/2 -translate-y-1/2 rounded border border-border bg-background/95 p-4 text-center text-sm text-muted-foreground">No camera has a confirmed map location. Cameras remain available in settings and the wall.</div>}
      <div className="absolute bottom-2 left-2 flex items-center gap-3 rounded bg-background/80 px-2 py-1 text-[9px] text-muted-foreground backdrop-blur-sm">
        <span className="flex items-center gap-1">
          <span className="h-1.5 w-1.5 rounded-full bg-primary" /> camera node
        </span>
        <span className="flex items-center gap-1">
          <span className="h-1.5 w-1.5 rounded-full bg-[#ff5c72]" /> focused
        </span>
      </div>
    </div>
  )
}
