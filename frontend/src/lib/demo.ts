import type { Alert } from "@/lib/api"

export const DEMO_PLATE = {
  plate: "KL07AB1234",
  vehicle: "Blue city bus",
  status: "Trajectory reconstructed",
  hops: [
    { camera: "CAM-07", location: "Subhash Chandra Bose Jn", time: "08:12:14", confidence: 0.96 },
    { camera: "CAM-08", location: "Kathrikkadavu Junction", time: "08:21:42", confidence: 0.93 },
    { camera: "CAM-01", location: "Unconfirmed camera node", time: "08:29:08", confidence: 0.89 },
  ],
  rejected: "CAM-09 → CAM-07 · 228 km/h implied · retained as rejected candidate",
}

export const DEMO_ALERTS: Alert[] = [
  {
    severity: "critical",
    type: "route review",
    summary: "Synthetic plate example has a rejected camera transition",
    detail: "Demo scenario · 228 km/h implied between CAM-08 and CAM-07 · human review required",
    ts: Date.now() / 1000,
  },
  {
    severity: "warning",
    type: "zone dwell",
    summary: "Synthetic track remained in a configured zone for 45 seconds",
    detail: "Synthetic example · 30-second dwell threshold; camera-local identity requires review",
    ts: Date.now() / 1000 - 42,
  },
]

export const DEMO_FLOWS = [
  { from: "Subhash Chandra Bose Jn", to: "Kathrikkadavu Junction", count: 42, state: "elevated" },
  { from: "Kathrikkadavu Junction", to: "Petta Junction", count: 27, state: "baseline" },
  { from: "CAM-01", to: "CAM-05", count: 18, state: "baseline" },
]
