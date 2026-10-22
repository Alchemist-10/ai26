import { useEffect, useRef } from "react"
import { MapIcon, History, TriangleAlert, ChartColumn, Gauge, MessageSquare, LayoutGrid, Settings, X, ShieldCheck, Users, KeyRound, Route } from "lucide-react"
import { cn } from "@/lib/utils"
import type { Page } from "@/App"

const NAV: { id: Page; label: string; icon: typeof MapIcon; blurb: string }[] = [
  { id: "cameras", label: "Camera Wall", icon: LayoutGrid, blurb: "Live grid + main feed" },
  { id: "map", label: "Map", icon: MapIcon, blurb: "Camera locations, Kochi" },
  { id: "congestion", label: "Traffic activity", icon: Gauge, blurb: "Sampled track passages" },
  { id: "timeline", label: "Evidence Timeline", icon: History, blurb: "Per-camera detection log" },
  { id: "alerts", label: "Alerts", icon: TriangleAlert, blurb: "Route-anomaly rules" },
  { id: "analytics", label: "Analytics", icon: ChartColumn, blurb: "Stats + congestion map" },
  { id: "query", label: "Ask the Grid", icon: MessageSquare, blurb: "Natural-language query" },
  { id: "settings", label: "Camera settings", icon: Settings, blurb: "Footage, metadata and history" },
  { id: "routes", label: "Travel constraints", icon: Route, blurb: "Directed camera-pair windows" },
  { id: "accounts", label: "User administration", icon: Users, blurb: "Accounts, roles and passwords" },
  { id: "security", label: "Account security", icon: KeyRound, blurb: "Password, authenticator and recovery codes" },
]

export function NavDrawer({
  open,
  page,
  onNavigate,
  onClose,
  isAdmin = false,
  isAuthenticated = false,
  canManageRoutes = false,
}: {
  open: boolean
  page: Page
  onNavigate: (p: Page) => void
  onClose: () => void
  isAdmin?: boolean
  isAuthenticated?: boolean
  canManageRoutes?: boolean
}) {
  const root = useRef<HTMLElement>(null)
  useEffect(() => {
    if (!open) return
    const previous = document.activeElement as HTMLElement | null
    root.current?.querySelector<HTMLButtonElement>("button")?.focus()
    const keys = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose()
      if (e.key !== "Tab") return
      const buttons = Array.from(root.current?.querySelectorAll<HTMLButtonElement>("button") ?? [])
      const first=buttons[0], last=buttons.at(-1)
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last?.focus() }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first?.focus() }
    }
    document.addEventListener("keydown", keys)
    return () => { document.removeEventListener("keydown", keys); previous?.focus() }
  }, [open, onClose])
  return (
    <>
      {/* Backdrop */}
      <div
        className={cn(
          "fixed inset-0 z-40 bg-black/75 backdrop-blur-sm transition-opacity duration-200",
          open ? "opacity-100" : "pointer-events-none opacity-0"
        )}
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Drawer */}
      <aside
        ref={root}
        inert={!open}
        aria-hidden={!open}
        className={cn(
          "fixed left-0 top-0 z-50 flex h-full w-72 flex-col border-r border-zinc-800 bg-black font-sans text-white transition-transform duration-200 ease-out select-none",
          open ? "translate-x-0" : "-translate-x-full"
        )}
        aria-label="Sidebar navigation"
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-zinc-800 bg-zinc-950 px-4 py-3.5">
          <div className="flex items-center gap-2.5">
            <span className="flex h-7 w-7 items-center justify-center rounded-md border border-white/20 bg-white text-black">
              <ShieldCheck className="h-4 w-4" strokeWidth={2} />
            </span>
            <div className="flex flex-col">
              <span className="text-sm font-bold tracking-[0.2em] text-white">Sakshi</span>
              <span className="text-[10px] uppercase tracking-wider text-zinc-500">SURVEILLANCE GRID</span>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close navigation"
            className="rounded-md p-1.5 text-zinc-400 transition-colors hover:bg-zinc-900 hover:text-white"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Navigation items */}
        <nav className="flex flex-1 flex-col gap-1 overflow-y-auto p-3">
          {NAV.filter(item => (item.id !== "accounts" || isAdmin) && (item.id !== "security" || isAuthenticated) && (item.id !== "routes" || canManageRoutes)).map((item) => {
            const Icon = item.icon
            const active = page === item.id
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => onNavigate(item.id)}
                className={cn(
                  "group flex items-center gap-3 rounded-lg border px-3 py-2.5 text-left transition-all duration-150",
                  active
                    ? "border-white bg-white text-black shadow-sm"
                    : "border-transparent text-zinc-400 hover:border-zinc-800/80 hover:bg-zinc-900/90 hover:text-white"
                )}
                aria-current={active ? "page" : undefined}
              >
                <Icon
                  className={cn(
                    "h-4 w-4 flex-none transition-colors",
                    active ? "text-black" : "text-zinc-400 group-hover:text-white"
                  )}
                />
                <div className="min-w-0">
                  <div
                    className={cn(
                      "text-sm font-medium leading-tight font-sans",
                      active ? "font-semibold text-black" : "text-zinc-200 group-hover:text-white"
                    )}
                  >
                    {item.label}
                  </div>
                  <div
                    className={cn(
                      "truncate text-[11px] leading-tight font-sans mt-0.5",
                      active ? "text-zinc-600" : "text-zinc-500 group-hover:text-zinc-400"
                    )}
                  >
                    {item.blurb}
                  </div>
                </div>
              </button>
            )
          })}
        </nav>

        {/* Footer info */}
        <div className="border-t border-zinc-800/80 bg-zinc-950/60 px-4 py-3 text-[11px] text-zinc-500 font-sans">
          Sakshi course project · Recorded inputs
        </div>
      </aside>
    </>
  )
}
