import type { Camera } from "@/lib/api"
import { OsmMap } from "@/components/OsmMap"
import { CameraThumb } from "@/components/CameraThumb"
import { MapPin } from "lucide-react"

export function MapView({
  cameras,
  focused,
  onFocus,
}: {
  cameras: Camera[]
  focused: string
  onFocus: (id: string) => void
}) {
  const points = cameras.map((cam) => ({
    id: cam.id,
    lat: cam.lat,
    lon: cam.lon,
    label: cam.id,
    detail: cam.location_confirmed ? cam.location : "Location unconfirmed",
    active: cam.id === focused,
    color: cam.id === focused ? "#3b82f6" : "#60a5fa",
  }))

  const activeCam = cameras.find((c) => c.id === focused)

  return (
    <div className="relative h-full w-full overflow-hidden bg-[#0a0d14]">
      <OsmMap points={points} onPointClick={onFocus} className="h-full w-full" />

      {activeCam && (
        <div className="absolute left-4 top-4 z-10 w-72 rounded-xl bg-zinc-900/90 p-3.5 border border-white/10 shadow-xl backdrop-blur-md">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
              <span className="font-mono text-xs font-semibold text-white tracking-wide">
                {activeCam.id}
              </span>
            </div>
            <span className="rounded bg-white/10 px-2 py-0.5 text-[10px] font-medium text-zinc-300">
              {activeCam.kind === "plate" ? "ANPR OCR" : "Vehicle Tracking"}
            </span>
          </div>

          <div className="relative aspect-video w-full overflow-hidden rounded-lg border border-white/10 bg-black mb-2.5">
            <CameraThumb cameraId={activeCam.id} className="h-full w-full object-cover" />
            <div className="absolute top-1.5 right-1.5 rounded bg-black/70 px-1.5 py-0.5 font-mono text-[8px] font-semibold text-white">
              PREVIEW
            </div>
          </div>

          <div className="space-y-1.5 text-xs">
            <div className="flex items-start gap-1.5 text-zinc-300">
              <MapPin className="h-3.5 w-3.5 text-zinc-400 mt-0.5 flex-none" />
              <span className="leading-tight">
                {activeCam.location_confirmed ? activeCam.location : "Location unconfirmed"}
              </span>
            </div>
            <div className="flex items-center justify-between text-[11px] font-mono text-zinc-500 pt-1.5 border-t border-white/[0.08]">
              <span>{activeCam.lat.toFixed(4)}°N, {activeCam.lon.toFixed(4)}°E</span>
              <span className="text-emerald-400">Online</span>
            </div>
          </div>
        </div>
      )}

      <div className="absolute bottom-4 right-4 z-10 flex items-center gap-3 rounded-lg bg-zinc-900/90 px-3 py-1.5 text-xs text-zinc-300 border border-white/10 backdrop-blur-md">
        <span className="flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-full bg-blue-500" /> Focused Node
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-full bg-blue-400" /> Active Camera
        </span>
      </div>
    </div>
  )
}
