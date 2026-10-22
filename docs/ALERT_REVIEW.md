# Alert review and escalation

Sakshi stores rule-alert decisions in SQLite. Review actions include acknowledge,
mark reviewed, dismiss and escalate. An escalation requires a recipient and can
be reassigned by recording another escalation decision. Each decision appends a
reviewer, optional note, recipient when relevant, timestamp and audit record.
When the optional authentication overlay is enabled, the backend takes the
reviewer name from the signed-in session and labels that provenance in history;
the submitted freeform name is ignored. Without authentication, the local
reviewer name remains an operator claim and is labeled as such. The prototype
has no external notification delivery.

Authenticated escalations are scoped to the case selected for the review. A
non-admin account can see and resolve active escalations only in its current
case; administrators can inspect and resolve all cases. Legacy active
escalations created before this scope was added remain unscoped and are visible
to administrators for resolution. Local unauthenticated mode remains a shared
queue. This scope applies to active escalation handoffs only; it does not make
the underlying alerts, observations, or evidence row-level case isolated.

The alert panel loads recent rule alerts and active escalations. The escalation
queue uses stable timestamp-and-ID cursor pages, so older unresolved handoffs
remain reachable beyond both the recent-alert window and the first 200 entries.
A later acknowledgement, review or dismissal resolves the handoff and removes it
from the active queue while preserving its history.

`GET /api/alerts?include_escalated=true` is a bounded compatibility view.
`GET /api/alerts/escalations?limit=50` returns one active-queue page; follow its
`next_cursor` with `before_ts` and `before_id` to continue without gaps, including
when multiple alerts share a timestamp. `POST /api/alerts/{alert_id}/review` accepts
`state: "escalated"` only with a non-empty `escalation_target`. Other states reject
an escalation target. The endpoint records a decision; it does not send a message
to the recipient.

## Rule conditions

Watchlist entries can have a time window and a minimum number of supported
sightings in a bounded lookback period. The current observation counts toward
that minimum; the lookback is capped at seven days. Observation retention can be
configured up to 365 days, but longer retention does not expand this rule window.
Local zone permits match a canonical plate, camera and half-open validity
period. A matching permit changes a restricted-camera warning into an informational
permitted-visit alert. These records are manually entered and persisted in local
settings; Sakshi does not verify issuers, legal validity or external permit status.
Rule configuration changes are appended to the local hash-chained audit log.
