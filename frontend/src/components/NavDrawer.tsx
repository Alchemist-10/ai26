import {
  MapPin,
  FileCheck2,
  AlertTriangle,
  BarChart2,
  GitBranch,
  Search,
  LayoutGrid,
  X,
  Shield,
  ChevronRight,
} from "lucide-react"
import { cn } from "@/lib/utils"
import type { Page } from "@/App"

const NAV: { id: Page; label: string; icon: typeof LayoutGrid; blurb: string }[] = [
  { id: "cameras", label: "Live Feeds", icon: LayoutGrid, blurb: "Multi-camera wall and focused inference channel" },
  { id: "map", label: "Camera Map", icon: MapPin, blurb: "Spatial node locations and coverage across Kochi" },
  { id: "congestion", label: "Traffic Corridors", icon: GitBranch, blurb: "Corridor density and volume bottleneck ranking" },
  { id: "timeline", label: "ANPR Evidence", icon: FileCheck2, blurb: "License plate search and vehicle route history" },
  { id: "alerts", label: "Incidents", icon: AlertTriangle, blurb: "Automated route violations and plate cloning alerts" },
  { id: "analytics", label: "Analytics", icon: BarChart2, blurb: "Rolling 5-minute event statistics and channel health" },
  { id: "query", label: "Query", icon: Search, blurb: "Ask natural language questions across the log" },
]

export function NavDrawer({
  open,
  page,
  onNavigate,
  onClose,
}: {
  open: boolean
  page: Page
  onNavigate: (p: Page) => void
  onClose: () => void
}) {
  return (
    <>
      <div
        className={cn(
          "fixed inset-0 z-40 bg-black/60 backdrop-blur-sm transition-opacity duration-200",
          open ? "opacity-100" : "pointer-events-none opacity-0"
        )}
        onClick={onClose}
        aria-hidden="true"
      />

      <aside
        className={cn(
          "fixed left-0 top-0 z-50 flex h-full w-80 flex-col border-r border-white/[0.08] bg-[#0c0e15] text-white shadow-2xl transition-transform duration-200 ease-out select-none",
          open ? "translate-x-0" : "-translate-x-full"
        )}
        aria-label="Navigation drawer"
      >
        <div className="flex items-center justify-between border-b border-white/[0.08] px-5 py-4 bg-[#0e111a]">
          <div className="flex items-center gap-3">
            <div className="flex h-8 w-8 items-center justify-center rounded-md bg-blue-600 text-white shadow-sm">
              <Shield className="h-4 w-4 stroke-[2.2]" />
            </div>
            <div>
              <div className="text-sm font-semibold text-white">AI26 Console</div>
              <div className="text-xs text-zinc-400">Navigation</div>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close navigation"
            className="rounded p-1.5 text-zinc-400 hover:bg-white/[0.08] hover:text-white transition-colors cursor-pointer"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <nav className="flex flex-1 flex-col gap-1 overflow-y-auto p-3">
          {NAV.map((item) => {
            const Icon = item.icon
            const active = page === item.id
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => onNavigate(item.id)}
                className={cn(
                  "group flex items-center justify-between rounded-lg border px-3 py-2.5 text-left transition-colors cursor-pointer",
                  active
                    ? "border-zinc-700 bg-zinc-800 text-white shadow-sm"
                    : "border-transparent text-zinc-400 hover:bg-zinc-900 hover:text-white"
                )}
                aria-current={active ? "page" : undefined}
              >
                <div className="flex items-center gap-3 min-w-0">
                  <div
                    className={cn(
                      "flex h-7 w-7 flex-none items-center justify-center rounded-md transition-colors",
                      active ? "bg-blue-600 text-white" : "bg-zinc-900 text-zinc-400 group-hover:text-white"
                    )}
                  >
                    <Icon className="h-4 w-4" />
                  </div>
                  <div className="min-w-0">
                    <div
                      className={cn(
                        "text-xs font-semibold leading-tight",
                        active ? "text-white" : "text-zinc-200 group-hover:text-white"
                      )}
                    >
                      {item.label}
                    </div>
                    <div className="truncate text-[11px] text-zinc-400 mt-0.5">
                      {item.blurb}
                    </div>
                  </div>
                </div>

                <ChevronRight
                  className={cn(
                    "h-4 w-4 flex-none transition-transform",
                    active ? "text-blue-400" : "text-zinc-600 group-hover:text-zinc-400"
                  )}
                />
              </button>
            )
          })}
        </nav>

        <div className="border-t border-white/[0.08] p-4 text-xs text-zinc-400 bg-[#0e111a]">
          <div className="font-medium text-zinc-300">Kochi Municipal ANPR Deployment</div>
          <div className="text-[11px] text-zinc-500 mt-0.5">
            Model pipeline: YOLOv8 tracking + Fast-ALPR
          </div>
        </div>
      </aside>
    </>
  )
}
