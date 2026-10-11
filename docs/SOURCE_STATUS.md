# Inspect camera sources

Open **Camera settings** and choose a camera. **Source footage** separates the
process's inference source from its browser playback file. It identifies an
imported original, configured original, bundled playback copy or missing input.
When the original is absent and inference uses a bundled derivative, that is
stated explicitly. A present file does not prove readable frames, detections or
plate accuracy; use camera health and independently validate supplied footage.

**Refresh source status** checks sources without changing a metadata draft. The
source section fetches on mount/camera change or explicit refresh only. It does
not poll, hash videos, open media players, run models or activate a selection.
Settings stays mounted after its first visit; shared catalog polling remains
separate. Requests abort when the source component unmounts; navigation alone
keeps the settings component mounted. Native disclosures expose imported file
hashes/video metadata, recent imports and camera-specific offline commands.

## Running source versus selected import

The API process keeps the managed binding loaded at startup. A new active.json
selection remains pending until restart, so the page shows **Restart required**
while the inference and playback roles still describe the previous release. A
removed pointer also requires restart to return to configured/bundled defaults.
Changing manifest fields under the same release ID is a pending change too.
An invalid selected manifest produces recovery guidance while retaining the
running binding. Source inspection never silently activates or repairs it.

The checked timestamp refers to file presence/size and manifest inspection.
Managed file hashes were checked at API startup. Pending imports and retained
history are not rehashed by inspection; same-size content tampering after startup
is not detected here. Missing/size-changed running imported files are flagged.
Displayed reviewer/reason, times, source assignments and metadata are local,
unauthenticated claims. The recording time basis remains replay_clock.

**Recent imported releases** follows up to ten parent manifests from the selected
release without scanning directories. It labels Running, Selected for restart
and Earlier import, displays missing/corrupt history as partial, and indicates
when older parents exist. Unlinked releases are not enumerated. Historical video
files are not checked by the history reader. Prior originals/playback copies
remain on disk; there is no automatic imported-video cleanup.

Follow **Import or replace recorded footage** for check, stop, import and restart
commands on the API host. Example paths/names must be replaced. Use the same
exported data/source settings as the app. See [SOURCE_IMPORT.md](SOURCE_IMPORT.md)
for bounds and recovery. Browser upload, release activation/rollback controls,
new camera creation, RTSP and authenticated source administration remain pending.

## API contract and bounded work

`GET /api/cameras/{camera_id}/source` returns camera_id, checked_at, time_basis,
active source roles/release, selection status/release/error, history and verification
scope. Unknown catalog IDs return 404 using the standard JSON error envelope.
Invalid selections return 200 with selection.status=invalid so the active binding
can still be inspected. No SQL writes or configuration revisions are created.

Only basenames and whitelisted metadata are exposed; host absolute paths and
arbitrary manifest fields are omitted. Current and parent manifests are limited
to 64 KiB each. Parent traversal is limited to ten releases, rejects path escapes,
invalid identities and cycles, and retains already-read history when a parent
fails. Requests perform bounded metadata reads and file stats rather than video
hashing or decode. The endpoint is part of the existing local unauthenticated
prototype API and adds no source mutation route.

## Validation scope

[Source inspection validation](validation/source-status-validation.json) records
manual desktop 1280x720, mobile 390x844 and user viewport 786x758 checks. All had
no document/settings horizontal overflow or video elements; text fields were
16px. Source refresh preserved an unsaved metadata draft. Native disclosures
worked by keyboard. Six idle seconds added zero source requests; this short
sample is not a sustained performance measurement. The lazy settings chunk is
22.24 kB raw / 6.24 kB gzip in this build; the main bundle remains about 312.69 kB.

A disposable API/database on 8002 with processing disabled used two generated
one-second red/blue clips. Browser checks distinguished the cached red release
from the selected blue release; invalid-selection guidance preserved the active
source; a 502 outage offered retry; and API restart plus refresh cleared errors,
activated blue and removed the pending notice. Expanded host-command guidance
contained the selected camera ID and explicit replacement flag. This fixture had
zero observations, zero audit writes and no metadata revisions beyond seeded
revision 1. No generated footage entered the main app; fixtures were stopped and
removed after verification. No real plate-source accuracy is established.

Twelve new backend contracts cover source roles, read-only/no-hash API behavior,
selection changes/removal/corruption, file changes, metadata projection, bounded
history and malformed/unsafe/cyclic parent references. All 140 backend tests and
frontend lint/build pass; lint retains two existing Fast Refresh warnings.
The Impeccable finish reviewer returned ship for the source extension with no
material fixes. Screenshots cover source status/history and responsive layouts;
error/retry and expanded command behavior were verified through browser DOM.
