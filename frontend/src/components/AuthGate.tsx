import { useEffect, useState, type FormEvent, type ReactNode } from "react"
import { KeyRound, ShieldCheck } from "lucide-react"
import { ApiError, getAuthState, login, logout, setSecurityContext, type AuthUser } from "@/lib/api"

const PURPOSES = [
  ["investigation", "Investigation"],
  ["traffic_analysis", "Traffic analysis"],
  ["incident_response", "Incident response"],
  ["system_test", "System test"],
] as const

export function AuthGate({ children }: { children: (user: AuthUser | null, context: { caseId: string; purpose: string }, signOut: () => Promise<void>, changeContext: (caseId: string, purpose: string) => void) => ReactNode }) {
  const [ready, setReady] = useState(false)
  const [enabled, setEnabled] = useState(false)
  const [user, setUser] = useState<AuthUser | null>(null)
  const [caseId, setCaseId] = useState("")
  const [purpose, setPurpose] = useState("investigation")
  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")
  const [error, setError] = useState("")
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    let active = true
    getAuthState().then(state => {
      if (!active) return
      setEnabled(state.enabled)
      setUser(state.user)
      setReady(true)
    }).catch(cause => {
      if (!active) return
      setError(cause instanceof Error ? cause.message : "Could not reach the AI26 service")
      setReady(true)
    })
    return () => { active = false }
  }, [])

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setBusy(true)
    setError("")
    try {
      const state = await login(username, password)
      setUser(state.user)
      setPassword("")
    } catch (cause) {
      setError(cause instanceof ApiError && cause.status === 429
        ? "Too many sign-in attempts. Wait 15 minutes before trying again."
        : cause instanceof Error ? cause.message : "Sign-in failed")
    } finally { setBusy(false) }
  }

  async function signOut() {
    try { await logout() }
    finally { setUser(null); setCaseId("") }
  }

  function changeContext(nextCaseId: string, nextPurpose: string) {
    setCaseId(nextCaseId)
    setPurpose(nextPurpose)
    setSecurityContext(nextCaseId, nextPurpose)
  }

  if (!ready) return <div className="flex min-h-screen items-center justify-center bg-background text-sm text-zinc-300" role="status">Connecting to AI26…</div>
  if (error && !enabled && !user) return <div className="flex min-h-screen items-center justify-center bg-background p-6 text-sm text-red-200" role="alert">{error}</div>
  if (enabled && !user) return <main className="flex min-h-screen items-center justify-center bg-background px-5 py-10 text-foreground">
    <form onSubmit={submit} className="w-full max-w-md rounded-lg border border-zinc-800 bg-black p-7 shadow-xl shadow-black/40">
      <div className="mb-7 flex items-center gap-3"><span className="flex h-10 w-10 items-center justify-center rounded-md bg-white text-black"><ShieldCheck size={21} /></span><div><h1 className="text-xl font-semibold text-white">Sign in to AI26</h1><p className="mt-1 text-sm text-zinc-400">Use your assigned account to access camera evidence.</p></div></div>
      <label className="mb-4 block text-sm text-zinc-300">Username<input autoComplete="username" required value={username} onChange={event => setUsername(event.target.value)} className="mt-1.5 block w-full rounded-md border border-zinc-700 bg-zinc-950 px-3 py-2.5 text-white placeholder:text-zinc-500" /></label>
      <label className="mb-5 block text-sm text-zinc-300">Password<input type="password" autoComplete="current-password" required value={password} onChange={event => setPassword(event.target.value)} className="mt-1.5 block w-full rounded-md border border-zinc-700 bg-zinc-950 px-3 py-2.5 text-white placeholder:text-zinc-500" /></label>
      {error && <p role="alert" className="mb-4 rounded-md border border-red-400/30 bg-red-950/40 px-3 py-2 text-sm text-red-200">{error}</p>}
      <button disabled={busy} className="flex w-full items-center justify-center gap-2 rounded-md bg-primary px-4 py-2.5 font-semibold text-primary-foreground disabled:cursor-wait disabled:opacity-60"><KeyRound size={16} />{busy ? "Signing in…" : "Sign in"}</button>
    </form>
  </main>

  if (enabled && !/^[A-Za-z0-9][A-Za-z0-9._-]{2,63}$/.test(caseId)) return <main className="flex min-h-screen items-center justify-center bg-background px-5 py-10 text-foreground">
    <form onSubmit={event => { event.preventDefault(); changeContext(caseId, purpose) }} className="w-full max-w-lg rounded-lg border border-zinc-800 bg-black p-7 shadow-xl shadow-black/40">
      <h1 className="text-xl font-semibold text-white">Set an access purpose</h1><p className="mt-2 max-w-prose text-sm leading-6 text-zinc-300">Sensitive camera, event, and evidence requests are recorded with a case ID and purpose. Enter the authorized case before opening the dashboard.</p>
      <label className="mt-6 block text-sm text-zinc-300">Case ID<input autoFocus required minLength={3} maxLength={64} pattern="[A-Za-z0-9][A-Za-z0-9._-]{2,63}" value={caseId} onChange={event => setCaseId(event.target.value)} placeholder="For example, CASE-2026-001" className="mt-1.5 block w-full rounded-md border border-zinc-700 bg-zinc-950 px-3 py-2.5 text-white placeholder:text-zinc-500" /></label>
      <label className="mt-4 block text-sm text-zinc-300">Purpose<select value={purpose} onChange={event => setPurpose(event.target.value)} className="mt-1.5 block w-full rounded-md border border-zinc-700 bg-zinc-950 px-3 py-2.5 text-white">{PURPOSES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
      <div className="mt-6 flex gap-3"><button type="submit" className="rounded-md bg-primary px-4 py-2.5 font-semibold text-primary-foreground">Open dashboard</button><button type="button" onClick={() => void signOut()} className="rounded-md border border-zinc-700 px-4 py-2.5 text-zinc-200">Sign out</button></div>
    </form>
  </main>

  return <>{children(user, { caseId, purpose }, signOut, changeContext)}</>
}
