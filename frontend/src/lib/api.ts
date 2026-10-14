export interface Camera {
  id: string
  kind: "vehicle" | "plate"
  location: string
  location_confirmed: boolean
  lat: number
  lon: number
  source_available: boolean
  health: CameraHealth
}
export interface PrivacyStatus {
  enabled: boolean
  plate_identifiers: "raw" | "keyed_pseudonyms"
  sampled_person_mask: "disabled" | "person_box_pixelation"
  scope: string
}
export interface CameraConfiguration {
  id: string
  kind: "vehicle" | "plate"
  location: string
  location_confirmed: boolean
  lat: number
  lon: number
  revision: number
  metadata_source: string
  calibration_status: string
  updated_at: number
}
export interface CameraConfigurationUpdate {
  expected_revision: number
  location: string
  location_confirmed: boolean
  lat: number
  lon: number
  reviewer: string
  reason: string
}
export interface CameraPairConstraint {
  from_camera: string
  to_camera: string
  from_revision: number
  to_revision: number
  min_travel_seconds: number
  max_travel_seconds: number
  enabled: boolean
  reviewer: string
  reason: string
  updated_at: number
  current_locations_valid: boolean
}
export interface CameraPairConstraintUpdate {
  from_camera_id: string
  to_camera_id: string
  min_travel_seconds: number
  max_travel_seconds: number
  enabled: boolean
  reviewer: string
  reason: string
}
export interface SourceRelease {
  release: string
  reviewer: string | null
  reason: string | null
  imported_at: number | null
  time_basis: string | null
  previous_release: string | null
  original: SourceFileMetadata
  playback: SourceFileMetadata
}
export interface SourceFileMetadata {
  bytes: number | null
  sha256: string | null
  video: { width: number | null; height: number | null; fps: number | null; duration_seconds: number | null; frame_count: number | null }
}
export interface CameraSourceStatus {
  camera_id: string
  checked_at: number
  time_basis: string
  active: {
    kind: "managed" | "configured_original" | "bundled_proxy" | "missing"
    release: SourceRelease | null
    inference: { filename: string; available: boolean; bytes: number | null; size_matches_import: boolean | null }
    playback: { filename: string; available: boolean; bytes: number | null; size_matches_import: boolean | null }
  }
  selection: {
    status: "current" | "restart_required" | "invalid"; release: SourceRelease | null; error: string | null
    token: string | null
    last_action: { id: string | null; intent: string | null; reviewer: string | null; reason: string | null; from_release: string | null; to_release: string | null; selected_at: number | null } | null
  }
  history: { releases: SourceRelease[]; more: boolean; error: string | null }
  verification: string
}
export interface SourcePreparation {
  job_id: string
  camera_id: string
  filename: string
  status: "uploading" | "preparing" | "ready" | "failed" | "cancelled"
  created_at: number
  error: string | null
  release: SourceRelease | null
}
export function prepareCameraSource(cameraId: string, file: File, reviewer: string, reason: string, replace: boolean, signal: AbortSignal): Promise<SourcePreparation> {
  const metadata = JSON.stringify({filename:file.name,bytes:file.size,reviewer,reason,replace})
  const encoded = btoa(String.fromCharCode(...new TextEncoder().encode(metadata)))
  if (encoded.length > 8192) return Promise.reject(new Error("Upload details are too long. Shorten the filename or reason."))
  return requestJson(`/api/cameras/${encodeURIComponent(cameraId)}/source/prepare`, {
    method:"POST",headers:{"Content-Type":"application/octet-stream","X-AI26-Upload":encoded},body:file,signal,
  })
}
export function getSourcePreparation(jobId: string, signal?: AbortSignal): Promise<SourcePreparation> {
  return requestJson(`/api/source-preparations/${encodeURIComponent(jobId)}`, {signal})
}
export function cancelSourcePreparation(jobId: string): Promise<SourcePreparation> {
  return requestJson(`/api/source-preparations/${encodeURIComponent(jobId)}/cancel`, {method:"POST"})
}
export function selectCameraSource(cameraId: string, release: string, expectedToken: string, intent: "select" | "rollback", reviewer: string, reason: string): Promise<{source:CameraSourceStatus;already_selected:boolean}> {
  return requestJson(`/api/cameras/${encodeURIComponent(cameraId)}/source/selection`, {
    method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({release,expected_token:expectedToken,intent,reviewer,reason}),
  })
}
export interface CameraHealth {
  camera_id: string
  status: string
  processing_enabled: boolean
  inference_branches: { vehicle_detection_enabled: boolean; plate_recognition_enabled: boolean }
  last_frame_at: number | null
  frame_age_seconds: number | null
  processed_fps: number
  error: string | null
}

export interface DetectionEvent {
  event_id: string
  passage_id: string
  track_id?: number
  identity_status?: string
  source_mode?: string
  camera_id: string
  kind: "vehicle" | "plate"
  label?: string
  plate?: string
  plate_norm?: string
  plate_raw?: string
  format_valid?: boolean
  repairs?: string[]
  confidence: number
  bbox: [number, number, number, number]
  ts: number
}

export interface Alert {
  alert_id?: string
  state?: string
  review?: { reviewer: string; reviewer_authenticated?: boolean; state: string; note: string; escalation_target?: string | null; ts: number }[]
  escalation_target?: string | null
  severity: "info" | "warning" | "critical"
  type: string
  summary: string
  detail: string
  ts: number
}

export interface Stats {
  vehicle_passages: number
  per_camera_passages: Record<string, number>
  total_events: number
  events_last_minute: number
  per_camera: Record<string, number>
  busiest_camera: string | null
  avg_confidence: number
}

export interface TrajectoryHop {
  time_basis?: string
  source_mode?: string
  camera_id: string
  location: string
  location_confirmed: boolean
  lat: number
  lon: number
  ts: number
  confidence: number
  plate?: string
  plate_raw?: string
  repairs: string[]
  bbox?: [number, number, number, number]
}

export interface TrajectoryLink {
  from_camera_id: string
  to_camera_id: string
  from_ts: number
  to_ts: number
  distance_km: number
  elapsed_seconds: number
  implied_speed_kmh: number | null
  reason?: string
}

export interface Trajectory {
  mode: "live"
  status: "not_found" | "observed" | "candidate" | "review_required"
  plate: string
  observations: TrajectoryHop[]
  accepted_links: TrajectoryLink[]
  rejected_links: TrajectoryLink[]
  candidate_links: TrajectoryLink[]
}

export interface EvidenceReport {
  report_id: string
  generated_at: number
  retention: string
  expires_at: number
  artifacts: {sha256: string; role: string; url: string}[]
  package_hash: string
  trajectory: Trajectory
  image_review_candidates?: {
    scorer: string
    status: string
    raw_reads_retained: boolean
    accuracy_claim: false
    groups: {
      passage_id: string
      candidate_count: number
      top_k: {
        event_id?: string
        crop_sha256: string
        score: number
        quality_components: Record<string, number>
        ts?: number
      }[]
    }[]
  }
}

export class ApiError extends Error {
  readonly status: number
  constructor(message: string, status: number) {
    super(message)
    this.name = "ApiError"
    this.status = status
  }
}

export interface AuthUser { username: string; role: "admin" | "operator" | "analyst" | "viewer" }
export type AuthRole = AuthUser["role"]
export interface ManagedUser extends AuthUser { disabled: boolean; case_ids: string[]; created_at: number; updated_at: number; mfa_enabled: boolean }
export interface AuthState { enabled: boolean; user: AuthUser | null; caseIds: string[]; csrfToken: string }
export interface MfaStatus { enabled: boolean; setup_pending: boolean; supported: boolean }
let csrfToken = ""
let securityContext = { caseId: "", purpose: "investigation" }

export function setSecurityContext(caseId: string, purpose: string) {
  securityContext = { caseId: caseId.trim(), purpose }
}

export function scopedResourceUrl(url: string): string {
  const target = new URL(url, window.location.href)
  target.searchParams.set("case_id", securityContext.caseId)
  target.searchParams.set("purpose", securityContext.purpose)
  return `${target.pathname}${target.search}`
}

export async function getAuthState(): Promise<AuthState> {
  const status = await requestJson<{ enabled: boolean }>("/api/auth/status")
  if (!status.enabled) return { enabled: false, user: null, caseIds: [], csrfToken: "" }
  try {
    const session = await requestJson<{ user: AuthUser; case_ids: string[]; csrf_token: string }>("/api/auth/me")
    csrfToken = session.csrf_token
    return { enabled: true, user: session.user, caseIds: session.case_ids, csrfToken }
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) return { enabled: true, user: null, caseIds: [], csrfToken: "" }
    throw error
  }
}

export async function login(username: string, password: string, mfaCode?: string): Promise<AuthState> {
  const session = await requestJson<{ user: AuthUser; case_ids: string[]; csrf_token: string }>("/api/auth/login", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username, password, ...(mfaCode ? {mfa_code:mfaCode} : {}) }),
  })
  csrfToken = session.csrf_token
  return { enabled: true, user: session.user, caseIds: session.case_ids, csrfToken }
}

export function getMfaStatus(signal?: AbortSignal): Promise<MfaStatus> {
  return requestJson<MfaStatus>("/api/auth/mfa", {signal})
}
export function setupMfa(): Promise<{secret:string;otpauth_uri:string;expires_at:number}> {
  return requestJson("/api/auth/mfa/setup", {method:"POST"})
}
export function enableMfa(code:string): Promise<{enabled:boolean;recovery_codes:string[]}> {
  return requestJson("/api/auth/mfa/enable", {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({code})})
}
export function disableMfa(password:string,code:string): Promise<{enabled:boolean;sessions_revoked:boolean}> {
  return requestJson("/api/auth/mfa/disable", {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({password,code})})
}
export function resetUserMfa(username:string): Promise<{mfa_reset:boolean;sessions_revoked:boolean}> {
  return requestJson(`/api/auth/users/${encodeURIComponent(username)}/mfa`, {method:"DELETE"})
}

export async function logout(): Promise<void> {
  await requestJson("/api/auth/logout", { method: "POST" })
  csrfToken = ""
}

export function getUsers(signal?: AbortSignal): Promise<ManagedUser[]> {
  return requestJson("/api/auth/users", { signal })
}
export function createUser(username: string, password: string, role: AuthRole, caseIds: string[]): Promise<ManagedUser> {
  return requestJson("/api/auth/users", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username, password, role, case_ids: caseIds }) })
}
export function updateUser(username: string, changes: { role?: AuthRole; disabled?: boolean; case_ids?: string[] }): Promise<ManagedUser> {
  return requestJson(`/api/auth/users/${encodeURIComponent(username)}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(changes) })
}
export function resetUserPassword(username: string, password: string): Promise<{ password_reset: boolean; sessions_revoked: boolean }> {
  return requestJson(`/api/auth/users/${encodeURIComponent(username)}/password`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ password }) })
}

async function requestJson<T>(input: RequestInfo | URL, init?: RequestInit): Promise<T> {
  const requestUrl = input instanceof Request ? input.url : String(input)
  const path = new URL(requestUrl, window.location.href)
  const scoped = path.pathname.startsWith("/api/") && ["/api/cameras/", "/api/source-preparations/", "/api/journey-links", "/api/stream/", "/api/video/", "/api/snapshot/", "/api/preview/", "/api/events", "/api/stats", "/api/flows", "/api/alerts", "/api/rules", "/api/nlquery", "/api/trajectory/", "/api/evidence/", "/api/reports/", "/api/artifacts/"].some(prefix => path.pathname.startsWith(prefix))
  const headers = new Headers(init?.headers ?? (input instanceof Request ? input.headers : undefined))
  if (scoped) {
    headers.set("X-AI26-Case-ID", securityContext.caseId)
    headers.set("X-AI26-Purpose", securityContext.purpose)
  }
  if (csrfToken && ["POST", "PUT", "PATCH", "DELETE"].includes((init?.method ?? (input instanceof Request ? input.method : "GET")).toUpperCase())) headers.set("X-AI26-CSRF-Token", csrfToken)
  const response = await fetch(scoped ? path : input, { ...init, headers, credentials: "same-origin" })
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new ApiError(body?.error?.message ?? `Request failed (${response.status})`, response.status)
  }
  return response.json() as Promise<T>
}

export async function getCameras(signal?: AbortSignal): Promise<Camera[]> {
  return requestJson<Camera[]>("/api/cameras", { signal })
}

export function getPrivacyStatus(signal?: AbortSignal): Promise<PrivacyStatus> {
  return requestJson<PrivacyStatus>("/api/privacy/status", { signal })
}

export function getCameraConfiguration(cameraId: string, revision?: number, signal?: AbortSignal): Promise<CameraConfiguration> {
  const query = revision === undefined ? "" : `?revision=${revision}`
  return requestJson(`/api/cameras/${encodeURIComponent(cameraId)}/configuration${query}`, { signal })
}

export function getCameraSourceStatus(cameraId: string, signal?: AbortSignal): Promise<CameraSourceStatus> {
  return requestJson(`/api/cameras/${encodeURIComponent(cameraId)}/source`, { signal })
}

export function saveCameraConfiguration(cameraId: string, change: CameraConfigurationUpdate): Promise<CameraConfiguration> {
  return requestJson(`/api/cameras/${encodeURIComponent(cameraId)}/configuration`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(change),
  })
}

export function getCameraPairConstraints(signal?: AbortSignal): Promise<CameraPairConstraint[]> {
  return requestJson("/api/camera-pair-constraints", { signal })
}

export function saveCameraPairConstraint(change: CameraPairConstraintUpdate): Promise<CameraPairConstraint> {
  return requestJson("/api/camera-pair-constraints", {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(change),
  })
}

export async function getEvents(params: { camera?: string; plate?: string; limit?: number } = {}, signal?: AbortSignal): Promise<DetectionEvent[]> {
  const q = new URLSearchParams(Object.entries(params).map(([key, value]) => [key, String(value)])).toString()
  return requestJson<DetectionEvent[]>(`/api/events${q ? `?${q}` : ""}`, { signal })
}

export async function getAlerts(signal?: AbortSignal, includeEscalated = false): Promise<Alert[]> {
  return requestJson<Alert[]>(`/api/alerts${includeEscalated ? "?include_escalated=true" : ""}`, { signal })
}

export async function getStats(signal?: AbortSignal): Promise<Stats> {
  return requestJson<Stats>("/api/stats", { signal })
}

export async function askNL(question: string): Promise<{ text: string; sql?: string }> {
  return requestJson<{ text: string; sql?: string }>("/api/nlquery", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  })
}

export async function getTrajectory(plate: string, interval: Record<string, string> = {}, signal?: AbortSignal): Promise<Trajectory> {
  return requestJson<Trajectory>(`/api/trajectory/${encodeURIComponent(plate)}?${new URLSearchParams(interval)}`, { signal })
}

export async function createEvidenceReport(plate: string, interval: Record<string, string> = {}): Promise<EvidenceReport> {
  return requestJson<EvidenceReport>(`/api/evidence/${encodeURIComponent(plate)}?${new URLSearchParams(interval)}`, { method: "POST" })
}

export function streamUrl(cameraId: string, startAt?: number, retry = 0, anchorAt?: number) {
  const params = new URLSearchParams({ retry: String(retry) })
  if (startAt !== undefined) params.set("start", startAt.toFixed(3))
  if (anchorAt !== undefined) params.set("anchor", anchorAt.toFixed(3))
  return scopedResourceUrl(`/api/stream/${cameraId}?${params}`)
}

export function videoUrl(cameraId: string) {
  return scopedResourceUrl(`/api/video/${cameraId}`)
}

export function cameraPlaybackOffset(cameraId: string, duration: number, now = Date.now()) {
  const cameraNumber = Number(cameraId.match(/\d+$/)?.[0] ?? 0)
  const cycle = Math.max(duration - 0.5, 0.5)
  return (now / 1000 + cameraNumber * 4.5) % cycle
}

export function snapshotUrl(cameraId: string) {
  return scopedResourceUrl(`/api/snapshot/${cameraId}?t=${Date.now()}`)
}

export async function getFlows(signal?: AbortSignal): Promise<{ from: string; to: string; count: number }[]> {
  return requestJson("/api/flows", { signal })
}
export async function reviewAlert(id: string, state: string, reviewer: string, note: string, escalationTarget?: string) {
  return requestJson(`/api/alerts/${encodeURIComponent(id)}/review`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({state, reviewer, note, ...(escalationTarget ? { escalation_target: escalationTarget } : {})}) })
}
export interface RuleConfig {
  watchlist: Record<string, string>
  watchlist_conditions: Record<string, { active_from?: number | null; active_until?: number | null; minimum_sightings: number; history_window_seconds: number }>
  restricted_cameras: string[]
  zone_permits: { permit_id: string; plate: string; camera_ids: string[]; valid_from: number; valid_until: number; reason: string }[]
  dwell_zones: { camera_id: string; zone: [number,number,number,number]; dwell_seconds: number; max_gap_seconds: number }[]
}
export async function getRules(): Promise<RuleConfig> { return requestJson("/api/rules") }
export async function saveRules(config: RuleConfig): Promise<RuleConfig> {
  return requestJson("/api/rules", {method: "PUT", headers: {"Content-Type":"application/json"}, body: JSON.stringify(config)})
}
