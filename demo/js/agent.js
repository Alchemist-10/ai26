/**
 * Sakshi Agent — MOCKED interactive agent (replaces a plain chat tab).
 *
 * This walkthrough simulates a local model with a fixed
 * tool list (find_trajectory, list_camera_events, get_congestion, get_alerts)
 * and a read-only DB role. This file fakes that loop: it pattern-matches the
 * question to one hardcoded "tool call", renders the call + its arguments
 * (so the tool-calling shape is visible, not hidden behind prose), then
 * renders a canned result pulled from data.js. No LLM runs in this demo.
 *
 * Hardcoded prompts this agent understands (see demo/README.md):
 *   "where has KL07AB1234 been today"
 *   "any blacklisted vehicles right now"
 *   "how's traffic on NH66 near Edapally"
 *   "list events at Vytilla in the last hour"
 *   "why was there an alert for TN22ZZ0007"
 *   "top OD routes today"
 */

const AI26_AGENT = (() => {

  function findTrajectory(plate) {
    const traj = AI26_DATA.TRAJECTORIES[plate];
    if (!traj) return null;
    const hops = traj.hops.map(h => ({ ...h, camera: AI26_DATA.cameraById(h.camera_id) }));
    return { plate, status: traj.status, hops, rejected: traj.rejected };
  }

  function getAlerts(type) {
    return AI26_DATA.ALERTS.filter(a => !type || a.type === type)
      .map(a => ({ ...a, camera: AI26_DATA.cameraById(a.camera_id) }));
  }

  function getCongestion(segmentSubstring) {
    return AI26_DATA.CONGESTION.find(c =>
      c.segment.toLowerCase().includes(segmentSubstring.toLowerCase()));
  }

  function listCameraEvents(cameraId) {
    return AI26_DATA.OBSERVATIONS.filter(o => o.camera_id === cameraId)
      .map(o => ({ ...o, vehicle: AI26_DATA.VEHICLES[o.plate_norm] }));
  }

  function getOdFlows() {
    return AI26_DATA.OD_FLOWS;
  }

  const HANDLERS = [
    {
      test: /where.*(kl07ab1234)|trajectory.*(kl07ab1234)|kl07ab1234.*been/i,
      tool: "find_trajectory", args: { plate: "KL07AB1234" },
      run: () => findTrajectory("KL07AB1234"),
      render: (r) => renderTrajectory(r),
    },
    {
      test: /blacklist(ed)?\b/i,
      tool: "get_alerts", args: { type: "blacklist" },
      run: () => getAlerts("blacklist"),
      render: (r) => renderAlerts(r, "Blacklist alerts"),
    },
    {
      test: /edapally|nh66/i,
      tool: "get_congestion", args: { segment: "Edapally" },
      run: () => getCongestion("Edapally"),
      render: (r) => renderCongestion(r),
    },
    {
      test: /vytilla/i,
      tool: "list_camera_events", args: { camera_id: "cam-01", window: "1h" },
      run: () => listCameraEvents("cam-01"),
      render: (r) => renderEvents(r, "cam-01"),
    },
    {
      test: /tn22zz0007|why.*alert/i,
      tool: "get_alerts", args: { plate: "TN22ZZ0007" },
      run: () => getAlerts().filter(a => a.plate === "TN22ZZ0007"),
      render: (r) => renderAlerts(r, "Alerts for TN22ZZ0007"),
    },
    {
      test: /od routes|origin.destination|top routes/i,
      tool: "get_od_flows", args: {},
      run: () => getOdFlows(),
      render: (r) => renderOd(r),
    },
  ];

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  function renderTrajectory(r) {
    if (!r) return `<p class="agent-empty">No trajectory on file for that plate in this demo dataset.</p>`;
    const rows = r.hops.map(h => `<li><span class="mono">${h.ts}</span> — ${escapeHtml(h.camera.name)} <span class="badge badge-${h.state}">${h.state}</span></li>`).join("");
    return `
      <p>Trajectory for <strong>${r.plate}</strong> — overall status <span class="badge badge-${r.status}">${r.status}</span></p>
      <ol class="agent-hops">${rows}</ol>
      ${r.rejected.length ? `<p class="agent-note">Rejected candidate hops: ${r.rejected.map(x => escapeHtml(x.reason)).join("; ")}</p>` : ""}
      <p class="agent-note"><a href="investigation.html?plate=${r.plate}">Open on the investigation map →</a></p>`;
  }

  function renderAlerts(list, title) {
    if (!list.length) return `<p class="agent-empty">No matching alerts right now.</p>`;
    const rows = list.map(a => `<li><span class="badge badge-sev-${a.severity}">${a.severity}</span> <span class="mono">${a.ts}</span> — ${escapeHtml(a.message)}</li>`).join("");
    return `<p><strong>${title}</strong> (${list.length})</p><ul class="agent-hops">${rows}</ul>`;
  }

  function renderCongestion(c) {
    if (!c) return `<p class="agent-empty">No congestion baseline for that segment.</p>`;
    if (c.z === null) return `<p><strong>${escapeHtml(c.segment)}</strong>: insufficient baseline to score congestion yet.</p>`;
    return `<p><strong>${escapeHtml(c.segment)}</strong>: ${c.current} vehicles/hr vs baseline ${c.baseline_mean}±${c.baseline_stddev} → z = ${c.z.toFixed(2)} → <span class="badge badge-${c.label.replace(/\s/g,'_')}">${c.label}</span></p>`;
  }

  function renderEvents(list, cameraId) {
    const cam = AI26_DATA.cameraById(cameraId);
    if (!list.length) return `<p class="agent-empty">No events at ${escapeHtml(cam.name)} in this window.</p>`;
    const rows = list.map(o => `<li><span class="mono">${o.ts}</span> — ${o.plate_norm} (${o.vehicle.color} ${o.vehicle.type}), confidence ${o.confidence.toFixed(2)}</li>`).join("");
    return `<p><strong>${escapeHtml(cam.name)}</strong> — ${list.length} events</p><ul class="agent-hops">${rows}</ul>`;
  }

  function renderOd(list) {
    const rows = list.map(f => `<li>${escapeHtml(f.origin)} → ${escapeHtml(f.destination)} — ${f.count} trips, mostly ${f.dominant_type}</li>`).join("");
    return `<p><strong>Top origin–destination routes today</strong></p><ul class="agent-hops">${rows}</ul>`;
  }

  function ask(question) {
    const q = (question || "").trim();
    if (!q) return null;
    const handler = HANDLERS.find(h => h.test.test(q));
    if (!handler) {
      return {
        question: q,
        toolCall: null,
        html: `<p class="agent-empty">I can only answer from the allowlisted tools in this demo (<code>find_trajectory</code>, <code>get_alerts</code>, <code>get_congestion</code>, <code>list_camera_events</code>, <code>get_od_flows</code>). Try one of the sample prompts below.</p>`,
      };
    }
    const result = handler.run();
    return {
      question: q,
      toolCall: { tool: handler.tool, args: handler.args },
      html: handler.render(result),
    };
  }

  const SAMPLE_QUESTIONS = [
    "Where has KL07AB1234 been today?",
    "Any blacklisted vehicles right now?",
    "How's traffic on NH66 near Edapally?",
    "List events at Vytilla in the last hour",
    "Why was there an alert for TN22ZZ0007?",
    "Top OD routes today",
  ];

  return { ask, SAMPLE_QUESTIONS };
})();
