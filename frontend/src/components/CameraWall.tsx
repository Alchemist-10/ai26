import { memo, useMemo, useState } from "react"
import { Search, Video, ScanLine } from "lucide-react"
import type { Camera } from "@/lib/api"
import { cn } from "@/lib/utils"
import { CameraThumb } from "@/components/CameraThumb"

type Filter = "all" | "vehicle" | "plate"

export const CameraWall = memo(function CameraWall({
  cameras,
  focused,
  onFocus,
}: {
  cameras: Camera[]
  focused: string
  onFocus: (id: string, position?: number) => void
}) {
  const [query, setQuery] = useState("")
  const [filter, setFilter] = useState<Filter>("all")

  const filtered = useMemo(() => {
    return cameras.filter((c) => {
      if (filter !== "all" && c.kind !== filter) return false
      const q = query.trim().toLowerCase()
      if (!q) return true
      return c.id.toLowerCase().includes(q) || c.location.toLowerCase().includes(q)
    })
  }, [cameras, query, filter])

  return (
    <div className="flex h-full w-full flex-col bg-black text-white font-sans select-none">
      {/* Top Toolbar */}
      <div className="flex flex-none flex-wrap items-center gap-3 border-b border-zinc-800 bg-zinc-950 px-3 py-2">
        <div className="flex items-center gap-2">
          <span className="text-[11px] font-semibold uppercase tracking-wider text-zinc-400">
            Camera Wall
          </span>
          <span className="rounded-full border border-zinc-800 bg-zinc-900 px-2 py-0.5 text-[11px] font-medium text-zinc-300">
            {cameras.length}
          </span>
        </div>

        {/* Search */}
        <div className="relative ml-auto w-48 sm:w-56">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-zinc-500" />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            aria-label="Search cameras"
            placeholder="Search ID or location…"
            className="h-7 w-full rounded-md border border-zinc-800 bg-zinc-900/90 pl-8 pr-2.5 text-base font-sans text-zinc-100 placeholder:text-zinc-500 transition-colors focus:border-zinc-400 focus:outline-none focus:ring-1 focus:ring-zinc-400"
          />
        </div>

        {/* Filter Pills */}
        <div className="flex items-center gap-1">
          {(["all", "vehicle", "plate"] as Filter[]).map((f) => {
            const isSelected = filter === f
            return (
              <button
                key={f}
                type="button"
                onClick={() => setFilter(f)}
                className={cn(
                  "rounded-md border px-2.5 py-1 text-xs font-sans font-medium capitalize transition-all duration-150",
                  isSelected
                    ? "border-white bg-white text-black shadow-sm"
                    : "border-zinc-800 bg-zinc-900/70 text-zinc-400 hover:border-zinc-700 hover:bg-zinc-800 hover:text-white"
                )}
              >
                {f}
              </button>
            )
          })}
        </div>
      </div>

      {/* Grid */}
      <div className="min-h-0 flex-1 overflow-y-auto bg-black p-2.5">
        <div className="grid grid-cols-3 gap-2 sm:grid-cols-5 lg:grid-cols-6">
          {filtered.map((cam) => {
            const active = cam.id === focused
            return (
              <button
                key={cam.id}
                type="button"
                onClick={() => onFocus(cam.id)}
                className={cn(
                  "group relative aspect-video  overflow-hidden rounded-md border text-left transition-all duration-150",
                  active
                    ? "border-white ring-2 ring-white shadow-[0_0_16px_rgba(255,255,255,0.18)] z-10"
                    : "border-zinc-800/90 bg-zinc-950 hover:border-zinc-600 hover:brightness-105"
                )}
              >
                <CameraThumb
                  key={`${cam.id}-${cam.source_available}`}
                  cameraId={cam.id}
                  available={cam.source_available}
                  processingEnabled={cam.health.processing_enabled}
                  processingStatus={cam.health.status}
                  className="h-full w-full object-cover"
                />

                {/* Active Indicator Tag */}
                {active && (
                  <span className="absolute left-1.5 top-1.5 rounded bg-white px-1.5 py-0.5 text-[9px] font-sans font-bold uppercase tracking-wider text-black shadow-sm">
                    FOCUS
                  </span>
                )}

                {/* Status Indicator */}
                <span aria-label={cam.source_available ? "Source available" : "Source missing"} className="absolute right-1.5 top-1.5 flex items-center gap-1.5 rounded border border-white/10 bg-black/75 px-1.5 py-0.5 text-[9px] font-sans font-medium tracking-wide text-zinc-300 backdrop-blur-sm">
                  <span className={cn("h-1.5 w-1.5 rounded-full", active ? "bg-white" : "bg-zinc-400")} />
                  {cam.source_available ? "AVAILABLE" : "MISSING"}
                </span>

                {/* Bottom Metadata */}
                <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black via-black/80 to-transparent px-2 py-1.5">
                  <div className="flex items-center gap-1.5">
                    <span className="truncate text-xs font-semibold text-white tracking-tight font-sans">
                      {cam.id}
                    </span>
                    {cam.kind === "plate" ? (
                      <ScanLine className="h-3 w-3 flex-none text-zinc-400" />
                    ) : (
                      <Video className="h-3 w-3 flex-none text-zinc-400" />
                    )}
                  </div>
                  <div className="truncate text-[10px] text-zinc-400 font-sans">
                    {cam.location_confirmed ? cam.location : "Location unconfirmed"}
                  </div>
                </div>
              </button>
            )
          })}
          {cameras.length === 0 ? (
            <div role="status" className="col-span-full py-12 text-center text-xs text-zinc-400 font-sans">
              No cameras are assigned to this case. An administrator can assign cameras in User administration.
            </div>
          ) : filtered.length === 0 && (
            <div className="col-span-full py-12 text-center text-xs text-zinc-500 font-sans">
              No cameras match your search or filter.
            </div>
          )}
        </div>
      </div>
    </div>
  )
}, (previous, next) => {
  if (previous.focused !== next.focused || previous.onFocus !== next.onFocus || previous.cameras.length !== next.cameras.length) return false
  return previous.cameras.every((camera, index) => {
    const updated = next.cameras[index]
    return camera.id === updated.id
      && camera.kind === updated.kind
      && camera.location === updated.location
      && camera.location_confirmed === updated.location_confirmed
      && camera.source_available === updated.source_available
      && camera.health.processing_enabled === updated.health.processing_enabled
      && camera.health.status === updated.health.status
  })
})
