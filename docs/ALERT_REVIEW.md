# Alert review and escalation

AI26 stores rule-alert decisions in SQLite. Review actions include acknowledge,
mark reviewed, dismiss and escalate. An escalation requires a recipient and can
be reassigned by recording another escalation decision. Each decision appends a
reviewer, optional note, recipient when relevant, timestamp and audit record.
When the optional authentication overlay is enabled, the backend takes the
reviewer name from the signed-in session and labels that provenance in history;
the submitted freeform name is ignored. Without authentication, the local
reviewer name remains an operator claim and is labeled as such. The prototype
has no external notification delivery.

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
