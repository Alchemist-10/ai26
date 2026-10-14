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
  review?: { reviewer: string; state: string; note: string; escalation_target?: string | null; ts: number }[]
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
}

export class ApiError extends Error {
  readonly status: number
  constructor(message: string, status: number) {
    super(message)
    this.name = "ApiError"
    this.status = status
  }
}

async function requestJson<T>(input: RequestInfo | URL, init?: RequestInit): Promise<T> {
  const response = await fetch(input, init)
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new ApiError(body?.error?.message ?? `Request failed (${response.status})`, response.status)
  }
  return response.json() as Promise<T>
}

export async function getCameras(signal?: AbortSignal): Promise<Camera[]> {
  return requestJson<Camera[]>("/api/cameras", { signal })
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
  return `/api/stream/${cameraId}?${params}`
}

export function videoUrl(cameraId: string) {
  return `/api/video/${cameraId}`
}

export function cameraPlaybackOffset(cameraId: string, duration: number, now = Date.now()) {
  const cameraNumber = Number(cameraId.match(/\d+$/)?.[0] ?? 0)
  const cycle = Math.max(duration - 0.5, 0.5)
  return (now / 1000 + cameraNumber * 4.5) % cycle
}

export function snapshotUrl(cameraId: string) {
  return `/api/snapshot/${cameraId}?t=${Date.now()}`
}

export async function getFlows(signal?: AbortSignal): Promise<{ from: string; to: string; count: number }[]> {
  return requestJson("/api/flows", { signal })
}
export async function reviewAlert(id: string, state: string, reviewer: string, note: string, escalationTarget?: string) {
  return requestJson(`/api/alerts/${encodeURIComponent(id)}/review`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({state, reviewer, note, ...(escalationTarget ? { escalation_target: escalationTarget } : {})}) })
}
export interface RuleConfig {
  watchlist: Record<string, string>
  restricted_cameras: string[]
  dwell_zones: { camera_id: string; zone: [number,number,number,number]; dwell_seconds: number; max_gap_seconds: number }[]
}
export async function getRules(): Promise<RuleConfig> { return requestJson("/api/rules") }
export async function saveRules(config: RuleConfig): Promise<RuleConfig> {
  return requestJson("/api/rules", {method: "PUT", headers: {"Content-Type":"application/json"}, body: JSON.stringify(config)})
}
