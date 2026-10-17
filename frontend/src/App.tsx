import { useEffect, useState } from "react"
import {
  Menu,
  Shield,
  LayoutGrid,
  MapPin,
  GitBranch,
  FileCheck2,
  AlertTriangle,
  BarChart2,
  Search,
} from "lucide-react"
import { getCameras, type Camera } from "@/lib/api"
import { CameraWall } from "@/components/CameraWall"
import { MainVideo } from "@/components/MainVideo"
import { NavDrawer } from "@/components/NavDrawer"
import { MapView } from "@/components/panels/MapView"
import { AlertsPanel } from "@/components/panels/AlertsPanel"
import { AnalyticsPanel } from "@/components/panels/AnalyticsPanel"
import { TimelinePage } from "@/pages/TimelinePage"
import { QueryPage } from "@/pages/QueryPage"
import { CongestionPage } from "@/pages/CongestionPage"

export type Page = "cameras" | "map" | "congestion" | "timeline" | "alerts" | "analytics" | "query"

const NAV_ITEMS: { id: Page; label: string; icon: typeof LayoutGrid }[] = [
  { id: "cameras", label: "Live Feeds", icon: LayoutGrid },
  { id: "map", label: "Camera Map", icon: MapPin },
  { id: "congestion", label: "Traffic Corridors", icon: GitBranch },
  { id: "timeline", label: "ANPR Evidence", icon: FileCheck2 },
  { id: "alerts", label: "Incidents", icon: AlertTriangle },
  { id: "analytics", label: "Analytics", icon: BarChart2 },
  { id: "query", label: "Query", icon: Search },
]

export default function App() {
  const [cameras, setCameras] = useState<Camera[]>([])
  const [cameraError, setCameraError] = useState<string | null>(null)
  const [focused, setFocused] = useState<string>("CAM-01")
  const [focusedPosition, setFocusedPosition] = useState<number>()
  const [focusedAnchor, setFocusedAnchor] = useState<number>()
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [page, setPage] = useState<Page>("cameras")

  useEffect(() => {
    getCameras()
      .then((c) => {
        setCameras(c)
        if (c.length) setFocused(c[0].id)
      })
      .catch((error: Error) => setCameraError(error.message))
  }, [])

  const focusedCam = cameras.find((c) => c.id === focused)

  function navigate(p: Page) {
    setPage(p)
    setDrawerOpen(false)
  }

  function focusCamera(id: string, position?: number) {
    setFocused(id)
    setFocusedPosition(position)
    setFocusedAnchor(position === undefined ? undefined : Date.now() / 1000)
  }

  return (
    <div className="flex h-screen w-screen flex-col overflow-hidden bg-[#08090d] text-[#f1f5f9] select-none">
      <header className="grid grid-cols-[1fr_auto_1fr] flex-none items-center border-b border-white/[0.08] bg-[#090b10]/95 backdrop-blur-xl px-5 py-2 z-20">
        <div className="flex items-center justify-start gap-3">
          <button
            type="button"
            onClick={() => setDrawerOpen(true)}
            aria-label="Open Navigation"
            className="rounded-lg p-1.5 text-zinc-400 hover:text-white hover:bg-white/[0.06] transition-colors cursor-pointer"
          >
            <Menu className="h-4 w-4" />
          </button>

          <div
            onClick={() => navigate("cameras")}
            className="flex items-center gap-2.5 cursor-pointer"
          >
            <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-gradient-to-br from-blue-500 to-blue-700 text-white shadow-md shadow-blue-500/25 border border-blue-400/30">
              <Shield className="h-4 w-4 stroke-[2.2]" />
            </div>
            <div className="flex items-baseline gap-2">
              <span className="font-bold text-sm tracking-tight text-white font-mono">AI26</span>
              <span className="hidden sm:inline text-xs text-zinc-400 border-l border-white/[0.08] pl-2 font-medium">
                Surveillance & ANPR Console
              </span>
            </div>
          </div>
        </div>

        <nav className="hidden md:flex items-center rounded-xl bg-zinc-900/90 p-1 border border-white/[0.08] shadow-inner shadow-black/40">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon
            const active = page === item.id
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => navigate(item.id)}
                className={`flex items-center gap-2 rounded-lg px-3 py-1.5 text-xs font-medium transition-all duration-150 cursor-pointer ${
                  active
                    ? "bg-blue-600 text-white shadow-md shadow-blue-500/25 font-semibold"
                    : "text-zinc-400 hover:text-zinc-100 hover:bg-white/[0.04]"
                }`}
              >
                <Icon className={`h-3.5 w-3.5 ${active ? "text-white" : "text-zinc-400"}`} />
                <span>{item.label}</span>
              </button>
            )
          })}
        </nav>

        <div className="flex items-center justify-end gap-3">
          <div className="flex items-center gap-2 rounded-lg bg-zinc-900/90 px-3 py-1.5 text-xs border border-white/[0.08] shadow-sm font-mono">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse shadow-[0_0_8px_rgba(52,211,153,0.6)]" />
            <span className="text-zinc-200 font-semibold">{cameras.length} Channels</span>
          </div>
        </div>
      </header>

      <NavDrawer
        open={drawerOpen}
        page={page}
        onNavigate={navigate}
        onClose={() => setDrawerOpen(false)}
      />

      <main className="relative min-h-0 flex-1">
        {cameraError && (
          <div className="absolute left-1/2 top-4 z-50 -translate-x-1/2 rounded-md border border-red-500/30 bg-red-950/90 px-4 py-2 text-xs text-red-200 shadow-lg backdrop-blur-md">
            Camera API unavailable: {cameraError}
          </div>
        )}

        {page === "cameras" && (
          <div className="grid h-full grid-rows-[220px_1fr]">
            <div className="min-h-0 border-b border-white/[0.08] bg-[#0c0e14]">
              <CameraWall cameras={cameras} focused={focused} onFocus={focusCamera} />
            </div>

            <div className="min-h-0 bg-black relative">
              <MainVideo
                key={focused}
                camera={focusedCam}
                startAt={focusedPosition}
                anchorAt={focusedAnchor}
              />
            </div>
          </div>
        )}

        {page === "map" && <MapView cameras={cameras} focused={focused} onFocus={focusCamera} />}
        {page === "congestion" && <CongestionPage />}
        {page === "timeline" && <TimelinePage cameras={cameras} />}
        {page === "alerts" && <AlertsPanel />}
        {page === "analytics" && <AnalyticsPanel />}
        {page === "query" && <QueryPage />}
      </main>
    </div>
  )
}
