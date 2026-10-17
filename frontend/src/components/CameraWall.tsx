import { useMemo, useState } from "react"
import { Search, Video, ScanLine, X } from "lucide-react"
import type { Camera } from "@/lib/api"
import { cn } from "@/lib/utils"
import { CameraThumb } from "@/components/CameraThumb"

type Filter = "all" | "vehicle" | "plate"

export function CameraWall({
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
  const [positions, setPositions] = useState<Record<string, number>>({})

  const filtered = useMemo(() => {
    return cameras.filter((c) => {
      if (filter !== "all" && c.kind !== filter) return false
      const q = query.trim().toLowerCase()
      if (!q) return true
      return c.id.toLowerCase().includes(q) || c.location.toLowerCase().includes(q)
    })
  }, [cameras, query, filter])

  return (
    <div className="flex h-full w-full flex-col bg-[#08090d] text-white select-none">
      <div className="grid grid-cols-[1fr_auto_1fr] flex-none items-center gap-3 border-b border-white/[0.08] px-4 py-2 bg-[#0a0c12]">
        <div className="flex items-center justify-start gap-1 bg-zinc-900/90 p-0.5 rounded-lg border border-white/[0.06] w-fit">
          {(
            [
              { id: "all", label: "All" },
              { id: "vehicle", label: "Vehicle" },
              { id: "plate", label: "ANPR" },
            ] as { id: Filter; label: string }[]
          ).map((item) => (
            <button
              key={item.id}
              type="button"
              onClick={() => setFilter(item.id)}
              className={cn(
                "rounded-md px-3 py-1 text-xs font-medium transition-colors cursor-pointer",
                filter === item.id
                  ? "bg-zinc-800 text-white shadow-sm font-semibold"
                  : "text-zinc-400 hover:text-zinc-200"
              )}
            >
              {item.label}
            </button>
          ))}
        </div>

        <div className="hidden sm:flex items-center justify-center gap-2 px-3 py-1 rounded-full border border-white/[0.06] bg-black/40 text-[11px] font-mono text-zinc-400">
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
          <span>{filtered.length} Channels Monitored</span>
        </div>

        <div className="flex items-center justify-end">
          <div className="relative w-44 sm:w-56">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-zinc-500" />
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Filter camera or junction…"
              className="h-7 w-full rounded-md border border-white/[0.08] bg-zinc-900/90 pl-8 pr-6 text-xs text-zinc-200 placeholder:text-zinc-500 transition-colors focus:border-blue-500 focus:outline-none"
            />
            {query && (
              <button
                type="button"
                onClick={() => setQuery("")}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-zinc-500 hover:text-zinc-300"
              >
                <X className="h-3 w-3" />
              </button>
            )}
          </div>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto p-2.5">
        <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-6 xl:grid-cols-9 gap-2">
          {filtered.map((cam) => {
            const active = cam.id === focused
            return (
              <button
                key={cam.id}
                type="button"
                onClick={() => onFocus(cam.id, positions[cam.id])}
                className={cn(
                  "group relative aspect-video overflow-hidden rounded-lg border text-left transition-all duration-200 cursor-pointer",
                  active
                    ? "border-blue-500 ring-1 ring-blue-500/80 shadow-[0_0_16px_rgba(59,130,246,0.3)] z-10 scale-[1.01]"
                    : "border-white/[0.08] bg-[#090b10] hover:border-white/20 hover:brightness-105"
                )}
              >
                <CameraThumb
                  cameraId={cam.id}
                  className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-105"
                  onTimeUpdate={
                    cam.id === focused
                      ? (time) => setPositions((current) => ({ ...current, [cam.id]: time }))
                      : undefined
                  }
                />

                <div className="absolute top-1.5 inset-x-1.5 flex items-center justify-between pointer-events-none">
                  <span
                    className={cn(
                      "flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[8px] font-mono font-bold tracking-wider uppercase backdrop-blur-md",
                      active
                        ? "bg-blue-600 text-white shadow-sm"
                        : "bg-black/80 text-zinc-300 border border-white/10"
                    )}
                  >
                    <span
                      className={cn(
                        "h-1.5 w-1.5 rounded-full",
                        active ? "bg-white" : "bg-emerald-400"
                      )}
                    />
                    {active ? "FOCUSED" : "LIVE"}
                  </span>

                  <span className="flex items-center gap-1 rounded-md bg-black/80 px-1.5 py-0.5 text-[8px] font-mono text-zinc-300 border border-white/10 backdrop-blur-md">
                    {cam.kind === "plate" ? (
                      <ScanLine className="h-2.5 w-2.5 text-blue-400" />
                    ) : (
                      <Video className="h-2.5 w-2.5 text-zinc-400" />
                    )}
                    <span>{cam.kind === "plate" ? "ANPR" : "CAM"}</span>
                  </span>
                </div>

                <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/95 via-black/70 to-transparent p-2 pt-4">
                  <div className="font-mono text-xs font-bold text-white tracking-wide">
                    {cam.id}
                  </div>
                  <div className="truncate text-[10px] text-zinc-400 font-mono">
                    {cam.location_confirmed ? cam.location : "Location unconfirmed"}
                  </div>
                </div>
              </button>
            )
          })}
          {filtered.length === 0 && (
            <div className="col-span-full py-8 text-center text-xs text-zinc-500">
              No cameras match your search or filter.
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
