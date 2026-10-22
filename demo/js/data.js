/**
 * Sakshi demo — mock dataset.
 * Everything here is fabricated for the pitch demo. No live cameras, no
 * live registry, no live LLM. See demo/README.md for what's real vs mocked.
 * Locations are real Kochi landmarks; camera feeds, plates, and events are not.
 */

const AI26_DATA = (() => {

  const CAMERAS = [
    { id: "cam-01", name: "Vytilla Mobility Hub",       lat: 9.9679,  lng: 76.3186, heading: 40,  road_segment: "NH66 – Vytilla Junction",      status: "online",   fps: 14, last_seen: "09:41:02" },
    { id: "cam-02", name: "Kaloor Junction",             lat: 9.9938,  lng: 76.2989, heading: 210, road_segment: "Kaloor–Kadavanthra Rd",        status: "online",   fps: 15, last_seen: "09:41:05" },
    { id: "cam-03", name: "MG Road – Ravipuram",         lat: 9.9723,  lng: 76.2851, heading: 300, road_segment: "MG Road",                      status: "online",   fps: 15, last_seen: "09:41:01" },
    { id: "cam-04", name: "Marine Drive Walkway",        lat: 9.9756,  lng: 76.2727, heading: 160, road_segment: "Marine Drive",                 status: "online",   fps: 12, last_seen: "09:40:58" },
    { id: "cam-05", name: "Edapally Junction",           lat: 10.0261, lng: 76.3084, heading: 90,  road_segment: "NH66 – Edapally",              status: "online",   fps: 15, last_seen: "09:41:03" },
    { id: "cam-06", name: "Palarivattom Junction",       lat: 10.0004, lng: 76.3081, heading: 270, road_segment: "NH544 – Palarivattom",         status: "degraded", fps: 6,  last_seen: "09:38:11" },
    { id: "cam-07", name: "Fort Kochi Beach Road",       lat: 9.9658,  lng: 76.2422, heading: 180, road_segment: "Beach Road",                   status: "online",   fps: 13, last_seen: "09:41:00" },
    { id: "cam-08", name: "Aluva Junction (NH66)",       lat: 10.1075, lng: 76.3516, heading: 20,  road_segment: "NH66 – Aluva",                 status: "online",   fps: 15, last_seen: "09:41:04" },
    { id: "cam-09", name: "Thevara Junction",            lat: 9.9481,  lng: 76.2977, heading: 130, road_segment: "Thevara–Perandoor Rd",         status: "online",   fps: 14, last_seen: "09:40:59" },
    { id: "cam-10", name: "Infopark Gate, Kakkanad",     lat: 10.0150, lng: 76.3480, heading: 300, road_segment: "Infopark Expressway",          status: "online",   fps: 15, last_seen: "09:41:06" },
  ];

  // Palette used for the mock "camera wall" tile gradients (stand-ins for real thumbnails).
  const CAM_TILE_HUE = { "cam-01": 200, "cam-02": 260, "cam-03": 20, "cam-04": 190, "cam-05": 340,
    "cam-06": 40, "cam-07": 150, "cam-08": 280, "cam-09": 10, "cam-10": 220 };

  const VEHICLES = {
    "KL07AB1234": { color: "blue",   type: "bus",         make: "generic city bus", blacklisted: false },
    "KL05CX5678": { color: "red",    type: "car",         make: "hatchback",        blacklisted: false },
    "KL01XY9999": { color: "white",  type: "suv",         make: "mid-size SUV",     blacklisted: true, reason: "Stolen-vehicle report #KOC-2291", case_ref: "KOC-2291" },
    "MH12DE1433": { color: "silver", type: "car",         make: "sedan",            blacklisted: false },
    "KL08BZ4321": { color: "black",  type: "auto",        make: "three-wheeler",    blacklisted: false },
    "KA03MN7788": { color: "grey",   type: "truck",       make: "mini-truck",       blacklisted: false },
    "KL04PT1122": { color: "blue",   type: "two_wheeler", make: "motorcycle",       blacklisted: false },
    "TN22ZZ0007": { color: "red",    type: "car",         make: "sedan",            blacklisted: true, reason: "Outstanding challan escalation, case #TN-8827", case_ref: "TN-8827" },
  };

  // Each observation mirrors the shape of the real event schema, trimmed to demo fields.
  const OBSERVATIONS = [
    { event_id: "e01", camera_id: "cam-08", plate_norm: "KL07AB1234", ts: "08:12:04", confidence: 0.95, evidence_status: "confirmed" },
    { event_id: "e02", camera_id: "cam-05", plate_norm: "KL07AB1234", ts: "08:31:47", confidence: 0.93, evidence_status: "confirmed" },
    { event_id: "e03", camera_id: "cam-06", plate_norm: "KL07AB1234", ts: "08:39:12", confidence: 0.81, evidence_status: "confirmed" },
    { event_id: "e04", camera_id: "cam-02", plate_norm: "KL07AB1234", ts: "08:47:30", confidence: 0.91, evidence_status: "confirmed" },
    { event_id: "e05", camera_id: "cam-01", plate_norm: "KL07AB1234", ts: "09:02:18", confidence: 0.94, evidence_status: "confirmed" },

    { event_id: "e06", camera_id: "cam-04", plate_norm: "KL01XY9999", ts: "07:50:21", confidence: 0.88, evidence_status: "confirmed" },
    { event_id: "e07", camera_id: "cam-03", plate_norm: "KL01XY9999", ts: "08:05:44", confidence: 0.90, evidence_status: "confirmed" },
    { event_id: "e08", camera_id: "cam-09", plate_norm: "KL01XY9999", ts: "08:22:09", confidence: 0.86, evidence_status: "confirmed" },

    { event_id: "e09", camera_id: "cam-01", plate_norm: "TN22ZZ0007", ts: "09:10:00", confidence: 0.92, evidence_status: "confirmed" },
    { event_id: "e10", camera_id: "cam-08", plate_norm: "TN22ZZ0007", ts: "09:12:30", confidence: 0.89, evidence_status: "review_required" },

    { event_id: "e11", camera_id: "cam-07", plate_norm: "KL05CX5678", ts: "09:00:00", confidence: 0.90, evidence_status: "confirmed" },
    { event_id: "e12", camera_id: "cam-07", plate_norm: "KL05CX5678", ts: "09:25:00", confidence: 0.87, evidence_status: "confirmed" },
    { event_id: "e13", camera_id: "cam-07", plate_norm: "KL05CX5678", ts: "09:50:00", confidence: 0.91, evidence_status: "confirmed" },
    { event_id: "e14", camera_id: "cam-04", plate_norm: "KL05CX5678", ts: "10:20:00", confidence: 0.85, evidence_status: "confirmed" },

    { event_id: "e15", camera_id: "cam-10", plate_norm: "MH12DE1433", ts: "10:05:00", confidence: 0.94, evidence_status: "confirmed" },
    { event_id: "e16", camera_id: "cam-06", plate_norm: "MH12DE1433", ts: "10:24:00", confidence: 0.79, evidence_status: "review_required" },
    { event_id: "e17", camera_id: "cam-02", plate_norm: "MH12DE1433", ts: "10:33:00", confidence: 0.88, evidence_status: "confirmed" },

    { event_id: "e18", camera_id: "cam-03", plate_norm: "KL08BZ4321", ts: "11:00:00", confidence: 0.83, evidence_status: "confirmed" },

    { event_id: "e19", camera_id: "cam-08", plate_norm: "KA03MN7788", ts: "11:15:00", confidence: 0.90, evidence_status: "confirmed" },
    { event_id: "e20", camera_id: "cam-05", plate_norm: "KA03MN7788", ts: "11:34:00", confidence: 0.88, evidence_status: "confirmed" },

    { event_id: "e21", camera_id: "cam-04", plate_norm: "KL04PT1122", ts: "09:45:00", confidence: 0.82, evidence_status: "confirmed" },
    { event_id: "e22", camera_id: "cam-03", plate_norm: "KL04PT1122", ts: "09:58:00", confidence: 0.80, evidence_status: "confirmed" },
  ];

  const ALERTS = [
    {
      id: "al-1", type: "blacklist", severity: "high", plate: "KL01XY9999", camera_id: "cam-03",
      ts: "08:05:44", ack: false,
      message: "Blacklisted vehicle KL01XY9999 (white SUV) observed at MG Road – Ravipuram.",
      detail: "Stolen-vehicle report #KOC-2291. Exact plate_norm match, confidence 0.90.",
    },
    {
      id: "al-2", type: "blacklist", severity: "high", plate: "TN22ZZ0007", camera_id: "cam-01",
      ts: "09:10:00", ack: false,
      message: "Blacklisted vehicle TN22ZZ0007 (red sedan) observed at Vytilla Mobility Hub.",
      detail: "Outstanding challan escalation, case #TN-8827. Exact plate_norm match, confidence 0.92.",
    },
    {
      id: "al-3", type: "impossible_travel", severity: "critical", plate: "TN22ZZ0007",
      camera_id: "cam-08", ts: "09:12:30", ack: false,
      message: "Impossible travel: TN22ZZ0007 seen at Vytilla and Aluva 2m30s apart.",
      detail: "Road distance ≈23 km. Learned 0.1-percentile minimum travel time for this camera pair is 21m40s. Flagged as a possible cloned plate.",
    },
    {
      id: "al-4", type: "loitering", severity: "medium", plate: "KL05CX5678", camera_id: "cam-07",
      ts: "09:50:00", ack: false,
      message: "Loitering: KL05CX5678 sighted 3 times at Fort Kochi Beach Road within 50 minutes.",
      detail: "Threshold: 3 sightings within 60 minutes in one zone. Sightings at 09:00, 09:25, 09:50.",
    },
    {
      id: "al-5", type: "restricted_zone", severity: "medium", plate: "KL08BZ4321", camera_id: "cam-03",
      ts: "11:00:00", ack: true,
      message: "KL08BZ4321 entered MG Road restricted corridor without an on-file permit.",
      detail: "Corridor active window: VIP movement, 10:45–11:15. No matching permit/visit record found.",
    },
  ];

  const CONGESTION = [
    { segment: "NH66 – Edapally",         current: 812, baseline_mean: 480, baseline_stddev: 140, z: 2.37, label: "congested" },
    { segment: "NH544 – Palarivattom",    current: 690, baseline_mean: 470, baseline_stddev: 122, z: 1.80, label: "busy" },
    { segment: "MG Road",                 current: 410, baseline_mean: 385, baseline_stddev: 85,  z: 0.29, label: "normal" },
    { segment: "Marine Drive",            current: 180, baseline_mean: 210, baseline_stddev: 60,  z: -0.50, label: "light" },
    { segment: "NH66 – Vytilla Junction", current: 560, baseline_mean: 505, baseline_stddev: 110, z: 0.50, label: "normal" },
    { segment: "Beach Road",              current: 95,  baseline_mean: null, baseline_stddev: null, z: null, label: "insufficient baseline" },
  ];

  const OD_FLOWS = [
    { origin: "Aluva Junction (NH66)", destination: "Vytilla Mobility Hub", count: 142, dominant_type: "bus" },
    { origin: "Infopark Gate, Kakkanad", destination: "Palarivattom Junction", count: 98, dominant_type: "car" },
    { origin: "Fort Kochi Beach Road", destination: "Marine Drive Walkway", count: 76, dominant_type: "car" },
    { origin: "MG Road – Ravipuram", destination: "Thevara Junction", count: 54, dominant_type: "two_wheeler" },
  ];

  // Hourly vehicle counts, last 12 hours, for two representative segments (demo chart).
  const DENSITY_TREND = {
    hours: ["22:00","23:00","00:00","01:00","02:00","03:00","04:00","05:00","06:00","07:00","08:00","09:00"],
    series: {
      "NH66 – Edapally":      [120, 90, 60, 40, 35, 38, 55, 140, 320, 540, 780, 812],
      "MG Road":              [80, 55, 30, 20, 18, 22, 40, 110, 240, 340, 390, 410],
      "Marine Drive":         [60, 40, 25, 15, 12, 14, 20, 60, 140, 190, 200, 180],
    },
  };

  const TRAJECTORIES = {
    "KL07AB1234": {
      status: "confirmed",
      hops: [
        { camera_id: "cam-08", ts: "08:12:04", state: "confirmed" },
        { camera_id: "cam-05", ts: "08:31:47", state: "confirmed" },
        { camera_id: "cam-06", ts: "08:39:12", state: "confirmed" },
        { camera_id: "cam-02", ts: "08:47:30", state: "confirmed" },
        { camera_id: "cam-01", ts: "09:02:18", state: "confirmed" },
      ],
      rejected: [],
    },
    "KL01XY9999": {
      status: "confirmed",
      hops: [
        { camera_id: "cam-04", ts: "07:50:21", state: "confirmed" },
        { camera_id: "cam-03", ts: "08:05:44", state: "confirmed" },
        { camera_id: "cam-09", ts: "08:22:09", state: "confirmed" },
      ],
      rejected: [
        { camera_id: "cam-07", ts: "08:10:00", reason: "fuzzy plate match below confidence floor (edit distance 2, confidence 0.41)" },
      ],
    },
    "TN22ZZ0007": {
      status: "cloning_candidate",
      hops: [
        { camera_id: "cam-01", ts: "09:10:00", state: "confirmed" },
        { camera_id: "cam-08", ts: "09:12:30", state: "cloning_candidate" },
      ],
      rejected: [],
    },
    "MH12DE1433": {
      status: "probable",
      hops: [
        { camera_id: "cam-10", ts: "10:05:00", state: "confirmed" },
        { camera_id: "cam-06", ts: "10:24:00", state: "probable" },
        { camera_id: "cam-02", ts: "10:33:00", state: "confirmed" },
      ],
      rejected: [],
    },
  };

  function cameraById(id) { return CAMERAS.find(c => c.id === id); }
  function observationsForCameras(cameraIds) {
    return OBSERVATIONS.filter(o => cameraIds.includes(o.camera_id));
  }
  function observationsForPlate(plate) {
    return OBSERVATIONS.filter(o => o.plate_norm === plate);
  }

  return {
    CAMERAS, CAM_TILE_HUE, VEHICLES, OBSERVATIONS, ALERTS, CONGESTION,
    OD_FLOWS, DENSITY_TREND, TRAJECTORIES,
    cameraById, observationsForCameras, observationsForPlate,
  };
})();
