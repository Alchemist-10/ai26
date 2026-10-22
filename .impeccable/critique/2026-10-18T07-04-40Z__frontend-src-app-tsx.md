---
target: Sakshi Camera Wall dashboard
total_score: 23
max_score: 40
na_heuristics: ""
p0_count: 0
p1_count: 2
timestamp: 2026-10-18T07-04-40Z
slug: frontend-src-app-tsx
---
## Sakshi Camera Wall UX review

**Method:** dual-agent (A: `/root/ux_design_assessment` · B: `/root/ux_detector_assessment`). The design review inspected the live dashboard and source independently from the detector. The detector returned no findings for the initial App target; the browser inspection confirmed nine cameras, source availability, view controls, and the large idle media region. Browser overlay injection was unavailable in that assessment environment, so no overlay result is claimed.

### Design health: 23/40 — Acceptable

| # | Heuristic | Score | Finding |
|---|---|---:|---|
| 1 | Visibility of system status | 3/4 | Source availability is visible; recording and processing state need distinct labels. |
| 2 | Match to the real world | 2/4 | “Shared processing” and “sampled detections” are technical terms. |
| 3 | User control and freedom | 3/4 | Camera focus, search, filters, and viewing modes are direct. |
| 4 | Consistency and standards | 3/4 | Controls are coherent; compact all-caps labels reduce readability. |
| 5 | Error prevention | 2/4 | “REC” implied active recording although the flag only confirmed source availability. |
| 6 | Recognition rather than recall | 3/4 | Camera IDs, focus, search, and filters are visible. |
| 7 | Flexibility and efficiency | 2/4 | Search and filters help; no multi-camera workflow is apparent. |
| 8 | Aesthetic and minimalist design | 2/4 | Persistent header chips compete with a mostly empty media area. |
| 9 | Error recovery | 2/4 | API errors are surfaced, but the idle view did not make the next action prominent. |
| 10 | Help and documentation | 1/4 | Brief mode descriptions exist; system terms lack contextual explanation. |

### Specificity and flow

The camera grid and separate playback/detection modes fit Sakshi’s evidence-review task, but generic system chips and status badges make much of the dashboard feel interchangeable with other camera tools. The initial experience is controlled and privacy-conscious, then stalls at a large blank region with a small prompt. Cognitive load is moderate: nine camera choices plus search, three filters, and two modes appear together, while header status language competes for attention.

### Priority issues

1. **P1 — “REC” overclaimed recording.** It was driven by `source_available`, which means a source exists or is available, not that recording is underway. **Fixed:** tiles now say “AVAILABLE” or “MISSING,” with an accessible source-status label.
2. **P1 — The first viewing action was easy to miss.** The empty media area had only a small instruction. **Fixed:** it now presents a prominent, selected-camera-specific choice between recorded playback and sampled detections, with concise descriptions. The toolbar controls remain available after a view is selected.
3. **P2 — Header hierarchy is crowded.** Secondary operational chips compete with the source count and camera view. Consider reducing or contextualizing the persistent “Recorded inputs / shared processing” chip while keeping important verification caveats visible.
4. **P2 — Some system terms need plain-language context.** Clarify “shared processing,” “sampled detections,” and unconfirmed location where users choose a view or interpret a camera state.

### Personas and minor findings

For an accessibility-dependent keyboard user, the controls expose names and the new choices use buttons; verify focus visibility and state announcements across all pages. A first-time operator may still mistake source availability for active processing. The camera cards group nine feeds together; search and filters partially offset that scan burden. The “Kochi” header sits beside mostly unconfirmed camera locations, so users may read the regional label as verified camera placement.

**Remaining direction question:** should the next pass focus on (A) simplifying the persistent header, or (B) clarifying processing and location terminology across the dashboard?
