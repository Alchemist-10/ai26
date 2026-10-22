# Select recorded footage and roll back

In **Camera settings**, choose a camera and prepare a clip through the browser
upload form. At **ready**, enter a **Selection reviewer** and **Selection reason**,
then choose **Select for restart**. Sakshi verifies the retained original and playback
SHA-256 digests before publishing the next-startup pointer. This works while the
processor is running because its original/playback paths were cached at startup.
A different selection shows **Restart required** with both currently running roles.

For the local launcher, stop the app with Ctrl+C on its host, then run
`uv run run.py --skip-install` with the same data/source settings. For a Docker
Compose deployment, run `ops/restart-backend.sh` from the deployment directory; it
restarts only the API and waits up to 90 seconds for its health endpoint.
**Refresh source status** afterwards. Startup verifies the selected files again
and activates both roles together. There is no browser restart control or live
source switching. Selecting the already-running release to revert a pending
replacement clears the notice without a restart.

## Retained-parent rollback

Expand **Recent imported releases**, choose **Earlier release to select**, then
enter a reviewer/reason and select it for restart. Only the displayed selected
release's parent chain is eligible: at most nine earlier releases plus the selected
release, with no directory scan. Both target files must pass containment, size and
hash checks. Older originals and proxies remain on disk. Missing/invalid parent
files fail explicitly; they are not repaired by this operation.

The UI does not enumerate arbitrary unlinked prepared releases. A ready upload can
be selected only against the managed release it was prepared from. If that base
changed, review current status and prepare another upload or use parent rollback.
Invalid pointers and return to configured/bundled defaults require manual host
recovery with the app stopped, as described in [SOURCE_IMPORT.md](SOURCE_IMPORT.md).

## Concurrency and recovery

A canonical metadata fingerprint from source status is the expected selection
token. A unique record ID changes the token on each committed browser selection,
including a later return to the same release. Formatting JSON differently does
not change it. It is a metadata fingerprint, not fresh proof of video integrity;
GET inspection continues to use file stats and bounded manifest reads.

The server holds the source import lock, verifies both target hashes and rechecks
the token before atomically publishing `active.json`. The processor ownership
lock is intentionally unnecessary for this immutable, next-startup selection.
Preparation/import ownership conflicts and changed tokens return 409. The offline
selector still requires processor shutdown and guards the expected release ID.

A stale or failed/unconfirmed browser request preserves reviewer/reason, disables
resubmission and requires **Refresh source status**. Review the refreshed selection
before making another explicit attempt; a lost response may already have committed.
No automatic retry or polling is added. Camera selection and source/current-revision
refresh are disabled during verification, while other pages remain available.
Drafts survive internal navigation/source refresh, but not browser reload.

## Local records and limitations

The selected pointer contains `source_selection`: a unique ID, camera, version,
selection time, intent, from/to releases, reviewer/reason, authentication status,
authenticated account when available, and prior selection ID. With authentication
enabled, the server replaces the typed reviewer with the signed-in operator account;
without authentication, the reviewer remains a local claim. The route requires an
operator role and case/purpose scope in authenticated mode, and mutations also
require CSRF validation.
The same proposal is retained under `CAM-XX/selection_history/ID.json` before
pointer publication. A proposal is committed only if the current pointer references
its ID or a later committed record links back to it. Publication failure removes
an uncommitted proposal; interruption after publication retains the record. A
forced kill/power failure can leave an unlinked proposal. Camera settings shows
linked records in reverse chronological order, bounded to twenty entries; unsafe,
missing or mismatched links are reported as partial history. There is no aggregate
selection-history cleanup or independently verifiable audit chain.
Offline/manual pointer edits may break the selection-record chain.

Original release manifests and footage are unchanged by selection. Old, unselected
managed releases can be pruned with the guarded offline dry-run/apply tool described
in [SOURCE_IMPORT.md](SOURCE_IMPORT.md); the selected rollback chain is retained.
Source selection creates no SQLite observations, configuration revisions or audit
rows. **Last browser selection** projects reviewer/reason/time and, when API
authentication is enabled, the server-verified account. It records selection, not
activation or verified content. The default local prototype remains unauthenticated.
Capture clocks, location, real plate/OCR accuracy, host restart orchestration, RTSP
and automatic imported-video retention remain pending.

Hashing adds explicit selection and startup I/O; it is performed in a request worker
thread, never in source polling or per-frame selection. It does not create another
inference worker. Short idle checks establish request behavior, not sustained latency.

## API

`POST /api/cameras/{camera_id}/source/selection` accepts JSON:

```json
{
  "release": "32-lowercase-hex-release-id",
  "expected_token": "64-lowercase-hex-token-or-default",
  "intent": "select",
  "reviewer": "Local operator",
  "reason": "Select the prepared recording for the next startup"
}
```

Replace placeholders with status/ready-release values. `intent` is `select` or
`rollback`; reviewer/reason are strict nonblank strings limited to 100/1000 chars.
Unknown fields and invalid IDs/tokens are rejected. Success is 200 with camera_id,
release, already_selected and refreshed source status. An already-selected target
is idempotent only with a current token and valid files. Refreshed status includes
up to twenty linked selection records, newest first, with authenticated-account
attribution where available; an invalid link marks history partial. Unknown camera is 404;
stale selection or import ownership is 409; invalid input, hashes, paths or failed
publication is 422 with a path-safe error. No endpoint stops or restarts the API.

## Validation

[Selection validation](validation/source-selection-validation.json) records actual
browser selection/rollback of generated color clips in disposable processing-disabled
services on 5175/8002. Both stale selection and rollback requests preserved entries,
required refresh and succeeded on explicit retry. Pending operations retained the
running original and byte-matching playback. Two owned API restarts activated blue,
then restored red; six committed linked records and old files were retained. The
fixture had zero observations/audit rows and a seeded camera set, then its services,
data and tab were removed. No generated clips entered the main app.

Thirteen new contracts cover processing-lock independence, cached roles/no SQL,
rollback/revert, stale tokens including return-to-same-release, metadata fingerprinting,
wrong preparation bases, bounded/malformed parents, both hashes, publication failure,
post-publication interruption, linked/idempotent records, path escape and API errors.
All 170 backend tests pass. Frontend lint/build pass with two existing Fast Refresh
warnings. The settings chunk is 36.18 kB raw / 9.21 kB gzip; main bundle 313.57 kB /
96.45 kB gzip. These are build sizes, not latency measurements.

Desktop 1280×720, mobile 390×844 and user 1014×758 captures cover prepared selection,
pending restart, rollback and stale recovery. Document width stayed within each
viewport; Settings contained no video elements. Six idle seconds added zero source
status/preparation/selection requests. Visual review status is recorded separately.
These checks do not establish real OCR/identity accuracy or sustained performance.

The later [sampling-budget milestone](RUNTIME_PROFILE.md) had 182 backend tests.
The 170-test figures above remain this source-selection milestone's evidence.
