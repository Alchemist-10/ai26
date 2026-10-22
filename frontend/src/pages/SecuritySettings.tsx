import { useEffect, useState, type FormEvent } from "react"
import { ApiError, changeOwnPassword, disableMfa, enableMfa, getMfaStatus, setupMfa, type MfaStatus } from "@/lib/api"

const input = "mt-1 block min-h-11 w-full rounded border border-zinc-700 bg-zinc-950 px-3 py-2 text-base text-white"
const button = "min-h-11 rounded border border-zinc-600 px-4 py-2 text-sm text-white hover:bg-zinc-800 disabled:cursor-wait disabled:opacity-50"

export default function SecuritySettings() {
  const [status, setStatus] = useState<MfaStatus | null>(null)
  const [secret, setSecret] = useState("")
  const [code, setCode] = useState("")
  const [password, setPassword] = useState("")
  const [currentPassword, setCurrentPassword] = useState("")
  const [newPassword, setNewPassword] = useState("")
  const [confirmPassword, setConfirmPassword] = useState("")
  const [recoveryCodes, setRecoveryCodes] = useState<string[]>([])
  const [busy, setBusy] = useState(false)
  const [passwordChanged, setPasswordChanged] = useState(false)
  const [error, setError] = useState("")
  const [notice, setNotice] = useState("")

  async function refresh(signal?: AbortSignal) {
    const next = await getMfaStatus(signal)
    if (!signal?.aborted) setStatus(next)
  }

  useEffect(() => {
    const controller = new AbortController()
    // oxlint-disable-next-line react/set-state-in-effect -- async status fetch synchronizes with the auth API.
    void refresh(controller.signal).catch(cause => { if (!controller.signal.aborted) setError(message(cause)) })
    return () => controller.abort()
  }, [])

  async function begin() {
    setBusy(true); setError(""); setNotice(""); setRecoveryCodes([])
    try { const result = await setupMfa(); setSecret(result.secret); setCode("") }
    catch (cause) { setError(message(cause)) }
    finally { setBusy(false) }
  }

  async function confirm(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError(""); setNotice("")
    try {
      const result = await enableMfa(code)
      setRecoveryCodes(result.recovery_codes); setSecret(""); setCode("")
      await refresh(); setNotice("MFA is enabled. Save these recovery codes now; they are shown only once.")
    } catch (cause) { setError(message(cause)) }
    finally { setBusy(false) }
  }

  async function disable(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError(""); setNotice("")
    try {
      await disableMfa(password, code); setPassword(""); setCode(""); setRecoveryCodes([])
      await refresh(); setNotice("MFA was disabled. Other active sessions were revoked.")
    } catch (cause) { setError(message(cause)) }
    finally { setBusy(false) }
  }

  async function changePassword(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError(""); setNotice("")
    if (newPassword !== confirmPassword) { setBusy(false); setError("New passwords do not match."); return }
    try {
      await changeOwnPassword(currentPassword, newPassword)
      setCurrentPassword(""); setNewPassword(""); setConfirmPassword("")
      setPasswordChanged(true)
      setNotice("Password changed. All sessions were revoked; returning to sign in…")
      window.setTimeout(() => window.location.reload(), 900)
    } catch (cause) { setError(message(cause)) }
    finally { setBusy(false) }
  }

  return <section className="h-full overflow-y-auto bg-background px-4 py-6 text-foreground sm:px-6">
    <div className="mx-auto max-w-3xl">
      <h1 className="text-2xl font-semibold text-white">Account security</h1>
      <p className="mt-2 max-w-2xl text-sm leading-6 text-zinc-300">Change your password or add an authenticator app as a second sign-in factor. MFA secrets are encrypted in the local database. Administrator recovery resets MFA and revokes the account’s sessions.</p>
      {error && <p role="alert" className="mt-4 rounded border border-red-400/30 bg-red-950/40 px-3 py-2 text-sm text-red-100">{error}</p>}
      {notice && <p role="status" className="mt-4 rounded border border-teal-400/30 bg-teal-950/30 px-3 py-2 text-sm text-teal-100">{notice}</p>}
      <form onSubmit={changePassword} className="mt-6 grid gap-3 border-y border-zinc-800 py-5 sm:grid-cols-2">
        <div className="sm:col-span-2"><h2 className="font-medium text-white">Change password</h2><p className="mt-1 text-sm text-zinc-400">Use at least 14 characters. Changing it signs out every active session.</p></div>
        <label className="text-sm text-zinc-300">Current password<input required type="password" autoComplete="current-password" maxLength={256} value={currentPassword} onChange={event => setCurrentPassword(event.target.value)} className={input} /></label>
        <span aria-hidden="true" className="hidden sm:block" />
        <label className="text-sm text-zinc-300">New password<input required minLength={14} maxLength={256} type="password" autoComplete="new-password" value={newPassword} onChange={event => setNewPassword(event.target.value)} className={input} /></label>
        <label className="text-sm text-zinc-300">Confirm new password<input required minLength={14} maxLength={256} type="password" autoComplete="new-password" value={confirmPassword} onChange={event => setConfirmPassword(event.target.value)} className={input} /></label>
        <button disabled={busy || passwordChanged} className={`${button} sm:col-span-2 sm:justify-self-start`}>Change password</button>
      </form>
      {!status ? <p role="status" className="mt-6 text-sm text-zinc-400">Loading security status…</p> : <div className="mt-6 border-y border-zinc-800 py-5">
        <p className="font-medium text-white">Authenticator MFA · {status.enabled ? "Enabled" : "Disabled"}</p>
        {status.enabled ? <form onSubmit={disable} className="mt-4 grid gap-3 sm:grid-cols-2">
          <label className="text-sm text-zinc-300">Current password<input required type="password" autoComplete="current-password" value={password} onChange={event => setPassword(event.target.value)} className={input} /></label>
          <label className="text-sm text-zinc-300">Current authenticator code<input required inputMode="numeric" autoComplete="one-time-code" value={code} onChange={event => setCode(event.target.value)} className={`${input} font-mono`} /></label>
          <button disabled={busy} className={`${button} sm:col-span-2 sm:justify-self-start`}>Disable MFA</button>
        </form> : <div className="mt-4">
          {!status.supported && <p className="mb-3 text-sm text-amber-200">MFA is not configured on this server. An administrator must set a protected AI26_AUTH_MFA_KEY_FILE before enrollment.</p>}
          {!secret ? <button type="button" disabled={busy || !status.supported} onClick={() => void begin()} className={button}>Set up authenticator</button> : <form onSubmit={confirm} className="mt-4 space-y-4">
            <div><p className="text-sm text-zinc-300">Add this account to an authenticator app using the key below, then enter its six-digit code. This setup expires in ten minutes.</p><p className="mt-3 select-all break-all rounded border border-zinc-800 bg-black p-3 font-mono text-sm text-white">{secret}</p></div>
            <label className="block max-w-sm text-sm text-zinc-300">Six-digit code<input required inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" maxLength={6} value={code} onChange={event => setCode(event.target.value)} className={`${input} font-mono`} /></label>
            <button disabled={busy} className={button}>Verify and enable MFA</button>
          </form>}
        </div>}
      </div>}
      {recoveryCodes.length > 0 && <div className="mt-5 rounded border border-amber-400/40 bg-amber-950/20 p-4">
        <h2 className="font-medium text-amber-100">Save your recovery codes</h2>
        <p className="mt-1 text-sm text-amber-100/80">Each code works once. Store them somewhere private; Sakshi will not show them again.</p>
        <ul className="mt-3 grid grid-cols-2 gap-2 font-mono text-sm text-white sm:grid-cols-5">{recoveryCodes.map(value => <li key={value}>{value}</li>)}</ul>
      </div>}
    </div>
  </section>
}

function message(cause: unknown) {
  if (cause instanceof ApiError && cause.status === 403) return "Sign in again before changing account security."
  return cause instanceof Error ? cause.message : "Could not update account security."
}
