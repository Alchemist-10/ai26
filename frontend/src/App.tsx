import { lazy, Suspense, useCallback, useState } from "react"
import { usePolling } from "@/hooks/usePolling"
import { Menu, ShieldCheck } from "lucide-react"
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
import { IntroSplash } from "@/components/IntroSplash"

const CameraSettings = lazy(() => import("@/pages/CameraSettings"))

export type Page = "cameras" | "map" | "congestion" | "timeline" | "alerts" | "analytics" | "query" | "settings"

const TITLES: Record<Page, string> = {
  cameras: "Camera Wall",
  map: "Map",
  congestion: "Traffic activity",
  timeline: "Evidence Timeline",
  alerts: "Alerts",
  analytics: "Analytics",
  query: "Ask the Grid",
  settings: "Camera settings",
}

export default function App() {
  const [cameras, setCameras] = useState<Camera[]>([])
  const [cameraError, setCameraError] = useState<string | null>(null)
  const [focused, setFocused] = useState<string>("CAM-01")
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [page, setPage] = useState<Page>("cameras")
  const [settingsVisited, setSettingsVisited] = useState(false)
  const [introVisible, setIntroVisible] = useState(() => !window.matchMedia("(prefers-reduced-motion: reduce)").matches)

  usePolling(async signal => {
    try {
      const result = await getCameras(signal)
      if (!signal.aborted) { setCameras(result); setCameraError(null) }
    } catch (error) { if (!signal.aborted) setCameraError(error instanceof Error ? error.message : "Camera API unavailable") }
  }, 3000)

  const closeNavigation = useCallback(() => setDrawerOpen(false), [])
  const focusedCam = cameras.find((c) => c.id === focused)

  function navigate(p: Page) {
    if (p === "settings") setSettingsVisited(true)
    setPage(p)
    setDrawerOpen(false)
  }

  const focusCamera = useCallback((id: string) => setFocused(id), [])

  return (
    <div className="flex h-screen w-screen flex-col overflow-hidden bg-background text-foreground">
      {introVisible && <IntroSplash onComplete={() => setIntroVisible(false)} />}
      <header className="flex flex-none items-center justify-between border-b border-zinc-800 bg-black/95 px-4 py-2.5 backdrop-blur-md sm:px-5 font-sans text-white select-none">
        <button
          type="button"
          onClick={() => setDrawerOpen(true)}
          aria-label="Open navigation"
          className="group flex min-w-0 items-center gap-3 rounded-md px-2 py-1 text-left transition-colors hover:bg-zinc-900"
        >
          <Menu className="h-4 w-4 flex-none text-zinc-400 transition-colors group-hover:text-white" />
          <span className="flex h-7 w-7 flex-none items-center justify-center rounded-md border border-white/20 bg-white text-black shadow-sm">
            <ShieldCheck className="h-4 w-4" strokeWidth={2} />
          </span>
          <span className="truncate text-sm font-bold tracking-[0.2em] text-white font-sans">AI26</span>
          <span className="hidden truncate border-l border-zinc-800 pl-3 text-[10px] uppercase tracking-[0.22em] text-zinc-400 font-sans sm:inline">
            {TITLES[page]} / Kochi
          </span>
        </button>
        <div className="flex flex-none items-center gap-2">
          <span className="hidden md:inline-flex items-center rounded-md border border-zinc-800 bg-zinc-900/80 px-2.5 py-1 text-xs font-sans font-medium text-zinc-400">
            Recorded inputs / shared processing
          </span>
          <span className="hidden sm:inline-flex items-center rounded-md border border-zinc-800 bg-zinc-900/80 px-2.5 py-1 text-xs font-sans font-medium text-zinc-400">
            Plate format / no registry verification
          </span>
          <span className="inline-flex items-center gap-1.5 rounded-md border border-white/20 bg-zinc-900 px-2.5 py-1 text-xs font-sans font-medium text-zinc-200">
            <span className="h-1.5 w-1.5 rounded-full bg-white" /> {cameras.filter((c) => c.source_available).length}/{cameras.length} sources available
          </span>
        </div>
      </header>

      <NavDrawer open={drawerOpen} page={page} onNavigate={navigate} onClose={closeNavigation} />

      <main className="min-h-0 flex-1">
        {cameraError && <div className="absolute left-1/2 top-16 z-30 -translate-x-1/2 rounded-md border border-red-400/30 bg-red-950/90 px-3 py-2 text-xs text-red-100">Camera API unavailable: {cameraError}</div>}
        {page === "cameras" && !introVisible && (
          <div className="grid h-full grid-rows-[260px_1fr]">
            <div className="min-h-0 border-b border-zinc-800 bg-black">
              <CameraWall cameras={cameras} focused={focused} onFocus={focusCamera} />
            </div>
            <div className="min-h-0">
              <MainVideo camera={focusedCam} />
            </div>
          </div>
        )}
        {page === "map" && <MapView cameras={cameras} focused={focused} onFocus={focusCamera} />}
        {page === "congestion" && <CongestionPage cameras={cameras} />}
        {page === "timeline" && <TimelinePage cameras={cameras} />}
        {page === "alerts" && <AlertsPanel />}
        {page === "analytics" && <AnalyticsPanel cameras={cameras} />}
        {page === "query" && <QueryPage />}
        {settingsVisited && (
          <div hidden={page !== "settings"} className="h-full">
            <Suspense fallback={<p role="status" className="p-6 text-zinc-300">Loading camera settings…</p>}>
              <CameraSettings cameras={cameras} initialCamera={focused} />
            </Suspense>
          </div>
        )}
      </main>
    </div>
  )
}
