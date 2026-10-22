# Camera revisions and journey decision persistence

Schema version 15 stores users, per-case grants, case-to-camera access grants, hashed authentication sessions, atomic authentication-attempt windows, encrypted TOTP enrollment, one-use recovery-code hashes and the last accepted TOTP counter,
the camera catalog, and immutable queried link decisions alongside existing
directed camera-pair travel constraints, sessions, immutable reads, camera-local passages, alerts, rules, reports and
hash-chained audit records, and 90-day camera/quarter-hour aggregate buckets for live-source processed samples and unique vehicle passages. Supported legacy versions migrate automatically; future schema
versions fail explicitly. Startup seeds missing catalog IDs without replacing
operator edits. Recording paths and detector kinds remain deployment configuration.

Schema version 13 adds a nullable case scope to active alert escalations. Schema version 14 adds explicit camera assignments per case for scoped analytics and footage access. New
authenticated escalations inherit the reviewer's selected case, and non-admin
users can list or resolve only escalations scoped to that case. Existing
unscoped local escalations are preserved; administrators can inspect and resolve
them. Schema version 14 adds administrator-managed camera assignments per case;
scoped analytics and footage queries enforce those assignments, while direct
requests for unassigned cameras are denied. This is a camera-level boundary,
not per-observation case ownership: cases sharing a camera can access the same
camera's observations. Legacy alerts without camera IDs remain admin-visible.

Directed camera-pair constraints store inclusive minimum/maximum travel windows,
connected/disconnected state, reviewer, reason and update time. Saving requires
both camera locations to be marked confirmed and contain coordinates; this is an
operator assertion, not independent geospatial validation. Journey links keep
coordinates, distance and speed null for unconfirmed positions. Manual, legacy
and unknown timestamp bases remain unresolved; only the explicit
`synchronized_capture_clock` basis can pass the time gate, and no current runtime
source emits it. Each newly materialized journey-link decision
captures the active pair constraint. Missing constraints leave links unresolved,
disconnected pairs are rejected, and travel outside a configured window is
rejected. Existing immutable decisions retain their original constraint snapshot.
Godseye's SIH checkout is unchanged.

## Signed audit checkpoints

The audit chain can be signed at a verified head and checked later against the
database with `backend/audit_checkpoint.py`. Optional host wrapper/systemd
templates can schedule daily checkpoints to an active mounted destination. The
checkpoint file and trusted public key must be retained independently to provide
rollback evidence; the template does not prove the mount is off-host or manage
remote trust distribution. Checkpoint signer rotation supports overlapping
old/new trusted public keys during local verification; public-key distribution
and revocation outside this verifier remain operator-managed. MFA encryption-key
rotation is separate; see
[MFA_KEY_ROTATION.md](MFA_KEY_ROTATION.md). See [AUDIT_CHECKPOINTS.md](AUDIT_CHECKPOINTS.md)
for checkpoint setup and verification.

## Live traffic history

`GET /api/traffic/baselines?days=28` compares each camera's latest completed
local hour with covered prior hours at the same weekday/hour. Only successfully
processed `source_mode=live`, `time_basis=capture_arrival_clock` frames and
camera-local vehicle passage starts contribute. The aggregates contain camera,
UTC quarter-hour, processed-sample count and passage count; they do not retain
plate IDs or raw observations. They are retained for 90 days, independently of
the configurable raw-observation cleanup (seven days by default). A zero count is meaningful only when the
hour has at least four processed frames across two UTC quarter-hour buckets.
Missing or partial coverage is left unknown. Replay
time is excluded so looping demo media cannot create a false historical pattern.

These are camera-local sampled passage histories, not road-segment volumes.
Passage counts inherit local tracking errors. Speeds remain unavailable until
route distance and source clocks are independently calibrated. The baseline
endpoint reports no-history, insufficient-history and stale states rather than
filling missing hours with zero.

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
operator assertion, not coordinate or clock validation. Repository defaults keep
CAM-07–09 unconfirmed because a junction name burned into a clip is not independent
source or site verification. Schema 15 adds a new unconfirmed revision only where
the old repository default was still current; it preserves the earlier revision and
does not change later operator edits. `calibration_status` remains
`unverified`; metadata edits cannot change it. The [Camera settings page](SETTINGS.md)
edits metadata and inspects saved revisions with explicit stale-save recovery.
Recorded sources can now be imported through the [offline command](SOURCE_IMPORT.md).
Read-only [source inspection/history](SOURCE_STATUS.md) is available in settings.
Source upload/activation UI and an independent survey/calibration workflow
remain separate work.

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

Replay clocks, live capture-arrival clocks and unconfirmed locations produce
unresolved candidates with null physical speed. For manual observations with
confirmed location labels, the existing straight-line speed gate can produce an
`accepted` baseline link; that status still
does not validate coordinates, clocks or vehicle identity. No learned cross-camera
appearance model or calibrated road topology is introduced.

## Reports, retention and verification

JSON/ZIP/print continue using the immutable report snapshot. Camera edits, new
observations or decision algorithm changes leave stored report content and its
hash unchanged. Maintenance removes decision rows with arrival times older than
the configured observation-retention period, which defaults to seven days. Set
`AI26_OBSERVATION_RETENTION_DAYS` to an integer from 7 to 365 to choose a longer
period; invalid settings prevent API startup. Reports retain their copied
decision snapshot until their separate 24-hour expiry. Camera revision/audit
history currently has no automatic expiry.

Audit rows for camera configuration edits, alert reviews and report reads include
the previous record hash and a SHA-256 hash over the canonical row fields. Existing
audit rows receive a local baseline chain during migration. `GET /api/audit/integrity`
checks links and row hashes and returns the record count and current head hash; a
broken row returns its ID and expected versus recorded previous hash. This is an
internal consistency check: someone able to rewrite the database can rebuild the
chain or truncate its tail. The operator-run `audit_checkpoint.py` tool can sign a
verified chain head; the checkpoint must be retained off-host to detect rollback
past that point. With optional authentication,
sensitive-access audit entries carry the session actor, case and purpose, and
alert-review history uses the signed-in account. Local no-auth reviewer names are
still operator claims.

Evidence report version 5 has an optional Ed25519 signature over the canonical
report payload, separate from its unkeyed `package_hash`. A configured private key
signs new reports; the offline verifier requires a public key supplied independently
and checks its SHA-256 fingerprint before accepting the signature. Without a
configured key, new reports explicitly contain `signature: null`. Signatures bind
bytes to a key, not to correct footage, a real camera, a true plate identity or a
trusted operator. Key custody, distribution and external audit anchoring remain
operator responsibilities. Report-signing rotation supports overlapping trusted
keys for offline verification; see [report signing](REPORT_SIGNING.md).

213 isolated backend tests pass, including 14 persistence tests for migrations,
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
