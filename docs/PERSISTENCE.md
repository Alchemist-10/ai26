# Camera revisions and journey decision persistence

Schema version 3 stores the nine-camera catalog and immutable queried link decisions
alongside existing sessions, immutable reads, camera-local passages, alerts, rules,
reports and audit records. Versions 1 and 2 migrate automatically; future schema
versions fail explicitly. Startup seeds missing catalog IDs without replacing
operator edits. Recording paths and detector kinds remain deployment configuration.
Godseye's SIH checkout is unchanged.

## Metadata editing API

`GET /api/cameras` returns the current persisted catalog with source availability and
processor health. `GET /api/cameras/CAM-07/configuration` returns its current metadata;
`?revision=1` retrieves an earlier revision. Neither endpoint exposes recording paths.

To edit metadata, first read its current revision, then send the complete editable
fields to `PUT /api/cameras/CAM-07/configuration`:

```json
{
  "expected_revision": 1,
  "location": "Subhash Chandra Bose Jn",
  "location_confirmed": true,
  "lat": 9.968,
  "lon": 76.281,
  "reviewer": "Local operator",
  "reason": "Correct the local site label"
}
```

The update creates the next revision and records the supplied reviewer/reason in
local audit history. A stale revision returns 409 with a reload instruction; invalid
or nonfinite coordinates, blank text, extra fields and source/kind/ID edits return
422. Unknown cameras/revisions return 404. Current location-name queries use the
persisted catalog; duplicate matching names require a camera ID.

Reviewer names are unauthenticated local claims. `location_confirmed` is a local
label assertion, not coordinate or clock validation. `calibration_status` remains
`unverified`; metadata edits cannot change it. The [Camera settings page](SETTINGS.md)
edits metadata and inspects saved revisions with explicit stale-save recovery.
Dynamic source onboarding and an independent survey/calibration workflow remain
separate work.

## Historical observations and links

Validated ingestion stores the current camera metadata/revision with each new
immutable observation. Retrying the same source frame/track keeps its original
snapshot. Subsequent edits apply to new observations. Trajectory hops use the
observation snapshot, so changing today's camera name/coordinates does not rewrite
newly captured historical evidence. Legacy reads without a snapshot explicitly use
`current_catalog_legacy`; their original metadata cannot be reconstructed.

Querying a trajectory, creating a report, or calculating flows/rule alerts saves
the link decisions encountered by that query. A link includes its decision status,
algorithm version, supporting observation and passage IDs, camera configuration
snapshots, time bases, reason and `identity_verified: false`. Its deterministic hash
ID makes repeated identical queries idempotent. A changed support pair, legacy
metadata fallback or algorithm version produces another immutable decision while
preserving earlier versions. Different intervals may select different supporting
reads; those are separate decisions even when passage IDs match.

`GET /api/journey-links` reads already materialized decisions without running route
inference. Optional `plate`, `since`, `until` and `limit` filters use the transition's
arrival timestamp; the default limit is 5,000 and results are newest first. This is
query decision history, not an exhaustive graph of all unqueried plate passages.
Decisions are not automatically retracted after later OCR conflicts; current
trajectory queries exclude conflicting passages, while stored decision history
preserves what that earlier query concluded.

Replay clocks and unconfirmed locations produce unresolved candidates with null
physical speed. For manual observations with confirmed location labels, the existing
straight-line speed gate can produce an `accepted` baseline link; that status still
does not validate coordinates, clocks or vehicle identity. No learned cross-camera
appearance model or calibrated road topology is introduced.

## Reports, retention and verification

JSON/ZIP/print continue using the immutable report snapshot. Camera edits, new
observations or decision algorithm changes leave stored report content and its
hash unchanged. Maintenance removes decision rows with arrival times older than
seven days; reports retain their copied decision snapshot until their separate
24-hour expiry. Camera revision/audit history currently has no automatic expiry.

82 isolated backend tests pass, including 13 persistence tests for migrations,
restarts, stale edits, validation, snapshot/report immutability, all decision
categories, deterministic IDs, version history, legacy fallback and cleanup.
The app restart retained all ten sampled historical observation IDs and decoded
six camera snapshots. Twenty new live observations contained matching metadata
snapshots. Live CAM-07–09 plate sources remain absent, so link cases use isolated
fixtures and establish storage correctness, not OCR or identity accuracy.

Twenty localhost requests per route measured median response times of 3.033 ms for
catalog, 1.747 ms for link history and 1.345 ms for an empty trajectory. These short
samples do not establish browser responsiveness or sustained throughput.
See [raw validation](validation/persistence-validation.json) and the
[full checklist](PROGRESS.md).

Validation details follow the official [Pydantic configuration reference](https://docs.pydantic.dev/latest/api/config/)
and [SQLite transaction semantics](https://www.sqlite.org/lang_transaction.html).
