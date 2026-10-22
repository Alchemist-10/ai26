import { lazy, Suspense, useCallback, useEffect, useState } from "react"
import { usePolling } from "@/hooks/usePolling"
import { Menu, ShieldCheck } from "lucide-react"
import { getCameras, setSecurityContext, type AuthUser, type Camera } from "@/lib/api"
import { AuthGate } from "@/components/AuthGate"
import { CameraWall } from "@/components/CameraWall"
import { MainVideo } from "@/components/MainVideo"
import { NavDrawer } from "@/components/NavDrawer"

const MapView = lazy(() => import("@/components/panels/MapView").then(module => ({ default: module.MapView })))
const AlertsPanel = lazy(() => import("@/components/panels/AlertsPanel").then(module => ({ default: module.AlertsPanel })))
const AnalyticsPanel = lazy(() => import("@/components/panels/AnalyticsPanel").then(module => ({ default: module.AnalyticsPanel })))
const TimelinePage = lazy(() => import("@/pages/TimelinePage").then(module => ({ default: module.TimelinePage })))
const QueryPage = lazy(() => import("@/pages/QueryPage").then(module => ({ default: module.QueryPage })))
const CongestionPage = lazy(() => import("@/pages/CongestionPage").then(module => ({ default: module.CongestionPage })))
const CameraSettings = lazy(() => import("@/pages/CameraSettings"))
const UserAdministration = lazy(() => import("@/pages/UserAdministration"))
const SecuritySettings = lazy(() => import("@/pages/SecuritySettings"))
const RouteConstraintsPage = lazy(() => import("@/pages/RouteConstraintsPage"))

export type Page = "cameras" | "map" | "congestion" | "timeline" | "alerts" | "analytics" | "query" | "settings" | "accounts" | "security" | "routes"

const TITLES: Record<Page, string> = {
  cameras: "Camera Wall",
  map: "Map",
  congestion: "Traffic activity",
  timeline: "Evidence Timeline",
  alerts: "Alerts",
  analytics: "Analytics",
  query: "Ask the Grid",
  settings: "Camera settings",
  accounts: "User administration",
  security: "Account security",
  routes: "Travel constraints",
}

export default function App() {
  return <AuthGate>{(user, caseIds, context, signOut, changeContext) => <Dashboard user={user} caseIds={caseIds} context={context} signOut={signOut} changeContext={changeContext} />}</AuthGate>
}

function Dashboard({ user, caseIds, context, signOut, changeContext }: {
  user: AuthUser | null
  caseIds: string[]
  context: { caseId: string; purpose: string }
  signOut: () => Promise<void>
  changeContext: (caseId: string, purpose: string) => void
}) {
  const [cameras, setCameras] = useState<Camera[]>([])
  const [cameraError, setCameraError] = useState<string | null>(null)
  const [focused, setFocused] = useState<string>("CAM-01")
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [page, setPage] = useState<Page>("cameras")
  const [settingsVisited, setSettingsVisited] = useState(false)
  const [caseDraft, setCaseDraft] = useState(context.caseId)
  const [purposeDraft, setPurposeDraft] = useState(context.purpose)

  useEffect(() => { setSecurityContext(context.caseId, context.purpose) }, [context.caseId, context.purpose])

  usePolling(async signal => {
    try {
      const result = await getCameras(signal)
      if (!signal.aborted) { setCameras(result); setCameraError(null) }
    } catch (error) { if (!signal.aborted) setCameraError(error instanceof Error ? error.message : "Camera API unavailable") }
  }, 5000)

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
          <span className="truncate text-sm font-bold tracking-[0.2em] text-white font-sans">Sakshi</span>
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

      {user && <form onSubmit={event => { event.preventDefault(); changeContext(caseDraft, purposeDraft) }} className="flex flex-none flex-wrap items-center gap-2 border-b border-zinc-800 bg-zinc-950 px-4 py-2 text-xs sm:px-5">
        <span className="mr-1 text-zinc-400">Signed in as <strong className="text-zinc-200">{user.username}</strong> · {user.role}</span>
        <label className="flex items-center gap-2 text-zinc-300">Case ID{user.role === "admin" ? <input value={caseDraft} onChange={event => setCaseDraft(event.target.value)} required minLength={3} maxLength={64} pattern="[A-Za-z0-9][A-Za-z0-9._-]{2,63}" className="w-40 rounded border border-zinc-700 bg-black px-2 py-1.5 text-white" /> : <select value={caseDraft} onChange={event => setCaseDraft(event.target.value)} className="max-w-48 rounded border border-zinc-700 bg-black px-2 py-1.5 text-white">{caseIds.map(id => <option key={id} value={id}>{id}</option>)}</select>}</label>
        <label className="flex items-center gap-2 text-zinc-300">Purpose<select value={purposeDraft} onChange={event => setPurposeDraft(event.target.value)} className="rounded border border-zinc-700 bg-black px-2 py-1.5 text-white"><option value="investigation">Investigation</option><option value="traffic_analysis">Traffic analysis</option><option value="incident_response">Incident response</option><option value="system_test">System test</option></select></label>
        <button type="submit" className="rounded border border-zinc-600 px-2.5 py-1.5 text-zinc-100 hover:bg-zinc-800">Apply context</button>
        <button type="button" onClick={() => void signOut()} className="ml-auto rounded border border-zinc-700 px-2.5 py-1.5 text-zinc-300 hover:bg-zinc-800">Sign out</button>
      </form>}

      <NavDrawer open={drawerOpen} page={page} onNavigate={navigate} onClose={closeNavigation} isAdmin={user?.role === "admin"} isAuthenticated={!!user} canManageRoutes={!user || user.role === "admin" || user.role === "operator"} />

      <main className="min-h-0 flex-1">
        {cameraError && <div className="absolute left-1/2 top-16 z-30 -translate-x-1/2 rounded-md border border-red-400/30 bg-red-950/90 px-3 py-2 text-xs text-red-100">Camera API unavailable: {cameraError}</div>}
        {page === "cameras" && (
          <div className="grid h-full grid-rows-[260px_1fr]">
            <div className="min-h-0 border-b border-zinc-800 bg-black">
              <CameraWall cameras={cameras} focused={focused} onFocus={focusCamera} />
            </div>
            <div className="min-h-0">
              <MainVideo camera={focusedCam} />
            </div>
          </div>
        )}
        <Suspense fallback={<p role="status" className="p-6 text-zinc-300">Loading dashboard view…</p>}>
          {page === "map" && <MapView cameras={cameras} focused={focused} onFocus={focusCamera} />}
          {page === "congestion" && <CongestionPage cameras={cameras} />}
          {page === "timeline" && <TimelinePage cameras={cameras} />}
          {page === "alerts" && <AlertsPanel />}
          {page === "analytics" && <AnalyticsPanel cameras={cameras} />}
          {page === "query" && <QueryPage />}
        </Suspense>
        {page === "accounts" && user?.role === "admin" && <Suspense fallback={<p role="status" className="p-6 text-zinc-300">Loading user administration…</p>}><UserAdministration /></Suspense>}
        {page === "security" && user && <Suspense fallback={<p role="status" className="p-6 text-zinc-300">Loading account security…</p>}><SecuritySettings /></Suspense>}
        {page === "routes" && (!user || user.role === "admin" || user.role === "operator") && <Suspense fallback={<p role="status" className="p-6 text-zinc-300">Loading camera-pair constraints…</p>}><RouteConstraintsPage cameras={cameras} /></Suspense>}
        {settingsVisited && (
          <div hidden={page !== "settings"} className="h-full">
            <Suspense fallback={<p role="status" className="p-6 text-zinc-300">Loading camera settings…</p>}>
              <CameraSettings cameras={cameras} initialCamera={focused} isAdmin={!user || user.role === "admin"} />
            </Suspense>
          </div>
        )}
      </main>
    </div>
  )
}
