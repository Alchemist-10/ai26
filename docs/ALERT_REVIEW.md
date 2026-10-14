# Alert review and escalation

AI26 stores rule-alert decisions in SQLite. Review actions include acknowledge,
mark reviewed, dismiss and escalate. An escalation requires a recipient and can
be reassigned by recording another escalation decision. Each decision appends a
reviewer-name claim, optional note, recipient when relevant, timestamp and audit
record. Authentication and role checks are available in the optional auth
overlay, but the freeform reviewer name is not bound to the signed-in identity.
The prototype has no external notification delivery.

The alert panel loads recent rule alerts and active escalations. Active escalations
remain in the queue after they age out of the default recent-alert window. A later
acknowledgement, review or dismissal resolves the handoff and removes it from the
active queue while preserving its history.

`GET /api/alerts?include_escalated=true` includes active escalations in addition
to alerts for the requested interval. `POST /api/alerts/{alert_id}/review` accepts
`state: "escalated"` only with a non-empty `escalation_target`. Other states reject
an escalation target. The endpoint records a decision; it does not send a message
to the recipient.

## Rule conditions

Watchlist entries can have a time window and a minimum number of supported
sightings in a bounded lookback period. The current observation counts toward
that minimum; the lookback is capped at the seven-day local observation-retention
window. Local zone permits match a canonical plate, camera and half-open validity
period. A matching permit changes a restricted-camera warning into an informational
permitted-visit alert. These records are manually entered and persisted in local
settings; AI26 does not verify issuers, legal validity or external permit status.
Rule configuration changes are appended to the local hash-chained audit log.
