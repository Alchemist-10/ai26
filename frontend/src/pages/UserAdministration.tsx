import { useEffect, useState, type FormEvent } from "react"
import { ApiError, createUser, getUsers, resetUserMfa, resetUserPassword, updateUser, type AuthRole, type ManagedUser } from "@/lib/api"

const roles: AuthRole[] = ["admin", "operator", "analyst", "viewer"]
const control = "min-h-10 rounded border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-white"
const button = "min-h-10 rounded border border-zinc-600 px-3 py-2 text-sm text-zinc-100 hover:bg-zinc-800 disabled:cursor-wait disabled:opacity-50"

export default function UserAdministration() {
  const [users, setUsers] = useState<ManagedUser[]>([])
  const [rolesDraft, setRolesDraft] = useState<Record<string, AuthRole>>({})
  const [disabledDraft, setDisabledDraft] = useState<Record<string, boolean>>({})
  const [casesDraft, setCasesDraft] = useState<Record<string, string>>({})
  const [username, setUsername] = useState("")
  const [newPassword, setNewPassword] = useState("")
  const [newRole, setNewRole] = useState<AuthRole>("viewer")
  const [newCases, setNewCases] = useState("")
  const [resetPasswords, setResetPasswords] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")
  const [notice, setNotice] = useState("")

  async function refresh(signal?: AbortSignal) {
    const result = await getUsers(signal)
    if (signal?.aborted) return
    setUsers(result)
    setRolesDraft(Object.fromEntries(result.map(user => [user.username, user.role])))
    setDisabledDraft(Object.fromEntries(result.map(user => [user.username, user.disabled])))
    setCasesDraft(Object.fromEntries(result.map(user => [user.username, user.case_ids.join(", ")])))
  }

  function showLoadError(cause: unknown) {
    setError(message(cause))
  }

  useEffect(() => {
    const controller = new AbortController()
    // Async request failures must reach the visible recovery message.
    // oxlint-disable-next-line react/set-state-in-effect
    void refresh(controller.signal).catch(cause => { if (!controller.signal.aborted) showLoadError(cause) })
    return () => controller.abort()
  }, [])

  async function submitCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError(""); setNotice("")
    try {
      await createUser(username, newPassword, newRole, parseCaseIds(newCases))
      setUsername(""); setNewPassword(""); setNewCases(""); setNotice(`Created ${username.trim()}.`); await refresh()
    } catch (cause) { setError(message(cause)) }
    finally { setBusy(false) }
  }

  async function saveUser(user: ManagedUser) {
    setBusy(true); setError(""); setNotice("")
    try {
      await updateUser(user.username, { role: rolesDraft[user.username], disabled: disabledDraft[user.username], case_ids: parseCaseIds(casesDraft[user.username] ?? "") })
      setNotice(`Updated ${user.username}. Active sessions are revoked when role, case access, or account status changes.`); await refresh()
    } catch (cause) { setError(message(cause)) }
    finally { setBusy(false) }
  }

  async function savePassword(username: string) {
    setBusy(true); setError(""); setNotice("")
    try {
      await resetUserPassword(username, resetPasswords[username] ?? "")
      setResetPasswords(previous => ({ ...previous, [username]: "" }))
      setNotice(`Reset ${username}'s password; existing sessions were revoked.`)
    } catch (cause) { setError(message(cause)) }
    finally { setBusy(false) }
  }

  async function resetMfa(username: string) {
    setBusy(true); setError(""); setNotice("")
    try { await resetUserMfa(username); setNotice(`Reset ${username}'s MFA; active sessions were revoked.`); await refresh() }
    catch (cause) { setError(message(cause)) }
    finally { setBusy(false) }
  }

  return <section className="h-full overflow-y-auto bg-background px-4 py-6 text-foreground sm:px-6">
    <div className="mx-auto max-w-5xl">
      <h1 className="text-2xl font-semibold text-white">User administration</h1>
      <p className="mt-2 max-w-3xl text-sm leading-6 text-zinc-300">Create accounts, assign access roles, suspend accounts, or reset passwords. Password changes and role or status changes revoke existing sessions.</p>
      {error && <p role="alert" className="mt-4 rounded border border-red-400/30 bg-red-950/40 px-3 py-2 text-sm text-red-100">{error}</p>}
      {notice && <p role="status" className="mt-4 rounded border border-teal-400/30 bg-teal-950/30 px-3 py-2 text-sm text-teal-100">{notice}</p>}

      <form onSubmit={submitCreate} className="mt-6 border-y border-zinc-800 py-5">
        <h2 className="text-base font-medium text-white">Create account</h2>
        <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-[1fr_1.3fr_160px_1.2fr_auto]">
          <label className="text-xs text-zinc-300">Username<input required minLength={3} maxLength={32} pattern="[A-Za-z0-9][A-Za-z0-9._-]{2,31}" value={username} onChange={event => setUsername(event.target.value)} className={`${control} mt-1 block w-full`} /></label>
          <label className="text-xs text-zinc-300">Temporary password<input required minLength={14} maxLength={256} type="password" autoComplete="new-password" value={newPassword} onChange={event => setNewPassword(event.target.value)} className={`${control} mt-1 block w-full`} /></label>
          <label className="text-xs text-zinc-300">Role<select value={newRole} onChange={event => setNewRole(event.target.value as AuthRole)} className={`${control} mt-1 block w-full`}>{roles.map(role => <option key={role} value={role}>{role}</option>)}</select></label>
          <label className="text-xs text-zinc-300">Assigned case IDs<input value={newCases} onChange={event => setNewCases(event.target.value)} placeholder="CASE-2026-001, CASE-2026-002" className={`${control} mt-1 block w-full`} /></label>
          <button disabled={busy} className={`${button} self-end`}>Create account</button>
        </div>
        <p className="mt-2 text-xs text-zinc-400">Use at least 14 characters. Non-admin accounts need at least one assigned case to read scoped data. Separate case IDs with commas.</p>
      </form>

      <div className="mt-6 flex items-center justify-between gap-3"><h2 className="text-base font-medium text-white">Accounts <span className="font-normal text-zinc-400">({users.length})</span></h2><button type="button" disabled={busy} onClick={() => { setError(""); void refresh().catch(cause => setError(message(cause))) }} className={button}>Refresh</button></div>
      {users.length === 0 ? <p className="mt-4 text-sm text-zinc-400">No accounts were returned.</p> : <ul className="mt-3 divide-y divide-zinc-800 border-y border-zinc-800">{users.map(user => <li key={user.username} className="grid gap-3 py-4 lg:grid-cols-[minmax(130px,1fr)_150px_1.2fr_140px_auto] lg:items-end">
        <div><p className="font-medium text-white">{user.username}</p><p className="mt-1 text-xs text-zinc-400">Created {new Date(user.created_at * 1000).toLocaleDateString()} · {user.disabled ? "Disabled" : "Active"} · MFA {user.mfa_enabled ? "enabled" : "off"}</p>{user.mfa_enabled && <button type="button" disabled={busy} onClick={() => void resetMfa(user.username)} className="mt-2 text-xs text-amber-200 underline underline-offset-2">Reset MFA and revoke sessions</button>}</div>
        <label className="text-xs text-zinc-300">Role<select value={rolesDraft[user.username] ?? user.role} onChange={event => setRolesDraft(previous => ({ ...previous, [user.username]: event.target.value as AuthRole }))} className={`${control} mt-1 block w-full`}>{roles.map(role => <option key={role} value={role}>{role}</option>)}</select></label>
        <label className="text-xs text-zinc-300">Assigned case IDs<input value={casesDraft[user.username] ?? ""} onChange={event => setCasesDraft(previous => ({ ...previous, [user.username]: event.target.value }))} placeholder="No cases assigned" className={`${control} mt-1 block w-full`} /></label>
        <label className="flex min-h-10 items-center gap-2 text-sm text-zinc-300"><input type="checkbox" checked={disabledDraft[user.username] ?? user.disabled} onChange={event => setDisabledDraft(previous => ({ ...previous, [user.username]: event.target.checked }))} /> Disabled</label>
        <button type="button" disabled={busy} onClick={() => void saveUser(user)} className={button}>Save access</button>
        <form onSubmit={event => { event.preventDefault(); void savePassword(user.username) }} className="grid gap-2 sm:grid-cols-[1fr_auto] lg:col-span-5 lg:ml-[calc(20%+0.75rem)]">
          <label className="text-xs text-zinc-300">Set a new password for {user.username}<input type="password" autoComplete="new-password" minLength={14} maxLength={256} required value={resetPasswords[user.username] ?? ""} onChange={event => setResetPasswords(previous => ({ ...previous, [user.username]: event.target.value }))} className={`${control} mt-1 block w-full`} /></label>
          <button disabled={busy} className={`${button} self-end`}>Reset password</button>
        </form>
      </li>)}</ul>}
    </div>
  </section>
}

function message(cause: unknown) {
  if (cause instanceof ApiError && cause.status === 403) return "This account cannot manage users. Sign in with an administrator account."
  return cause instanceof Error ? cause.message : "Could not complete the account change."
}

function parseCaseIds(value: string) {
  return [...new Set(value.split(",").map(item => item.trim()).filter(Boolean))]
}
