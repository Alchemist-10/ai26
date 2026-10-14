# Alert review and escalation

AI26 stores rule-alert decisions in SQLite. Review actions include acknowledge,
mark reviewed, dismiss and escalate. An escalation requires a recipient and can
be reassigned by recording another escalation decision. Each decision appends a
reviewer-name claim, optional note, recipient when relevant, timestamp and audit
record. Reviewer names and recipients are local claims; the prototype has no
user authentication, access control or external notification delivery.

The alert panel loads recent rule alerts and active escalations. Active escalations
remain in the queue after they age out of the default recent-alert window. A later
acknowledgement, review or dismissal resolves the handoff and removes it from the
active queue while preserving its history.

`GET /api/alerts?include_escalated=true` includes active escalations in addition
to alerts for the requested interval. `POST /api/alerts/{alert_id}/review` accepts
`state: "escalated"` only with a non-empty `escalation_target`. Other states reject
an escalation target. The endpoint records a decision; it does not send a message
to the recipient.
