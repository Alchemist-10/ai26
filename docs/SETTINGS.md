# Camera metadata settings

Open **Camera settings** from the navigation drawer. Select a camera, change its
location label, latitude/longitude or label confirmation, enter a reviewer name
and reason, then **Save new revision**. The camera ID, detector kind and video
source remain deployment configuration. Missing source files are displayed
explicitly; editing their metadata does not supply footage.

The editor uses the existing GET/PUT camera configuration API. Every successful
save creates an immutable revision and records the supplied name/reason in the
local audit log. Historical observations keep their original configuration;
new observations use the latest saved metadata. See [PERSISTENCE.md](PERSISTENCE.md)
for legacy snapshot fallbacks and the API contract.

## Drafts, conflicts and interruptions

A draft survives navigation to another AI26 page because the editor stays mounted
once visited. Catalog refreshes do not replace it. Save or discard before switching
cameras; **Discard draft** is available even during a revision conflict. Unsaved
drafts are in browser memory only. Reloading or closing the browser loses them;
a `beforeunload` listener requests the browser's native warning while dirty, which
browsers may suppress. The form also states this limit explicitly.

A stale save returns 409. The editor preserves every draft field and disables
saving until the user reviews the latest revision. **Keep my draft against
revision N** changes the expected revision only; it does not submit a save. It
keeps all draft fields, including values another editor changed. Review each
field and press Save separately, or **Use latest values and discard draft**.
Another concurrent edit is still rejected by the API. If the latest metadata
already matches the draft, the editor clears it without making a redundant save.

An interrupted or server-failed request might have committed before the response
was lost. The editor therefore treats it as unconfirmed, retains the draft and
requires the same latest-revision review. It never automatically retries a PUT.
A failed review can be retried, or the draft can be discarded locally and the
current revision refreshed when the API returns.

## History and truthfulness

Enter a saved revision number and choose **View revision** to inspect its label,
coordinates, confirmation flag, metadata source, calibration status and saved
local time. Viewing history does not change the editing baseline or draft. The
configuration response does not include audit reviewer/reason; the page does not
invent those values or present an authenticated history.

Label confirmation records a local assertion. Repository defaults may already
carry a confirmed flag, so history exposes their actual metadata source.
Coordinates, recording clocks and travel-time constraints remain uncalibrated.
Reviewer identity is unauthenticated. This is a local prototype metadata editor,
not source onboarding, authorization or an independent survey workflow.

## Performance and validation

The settings bundle loads on the first visit. It reuses App's catalog and adds
no polling, media playback, inference workers or dependencies. Configuration GETs
occur on initial visit, camera selection, explicit refresh/history or conflict
review; PUTs occur only on explicit save. An initiated request can settle after
navigation. Inactive settings do not start additional requests. The existing
shared catalog still polls as documented elsewhere.

The production settings chunk was 13.56 kB raw / 4.06 kB gzip in local validation
(the exact built digest/size is recorded in the validation file). This is build
output size, not a latency or sustained FPS measurement. The implementation uses
[React's lazy-loading mechanism](https://react.dev/reference/react/lazy).

[Validation evidence](validation/settings-validation.json) records manual browser
integration checks against a disposable database on 5175/8002 with processing
disabled and zero observations: coordinate rejection; immutable revision save and
history; draft preservation across navigation; concurrent-save rejection and
explicit rebase/save; API outage, review retry and restart recovery; explicit
discard; and no redundant save when the latest metadata matches. Five revisions
and four audit rows were retained. The main app catalog was unchanged. Desktop
1280×720 and mobile 390×844 had no horizontal overflow, 16 px text inputs and no
video elements on the settings page. Six idle seconds added zero configuration
requests. These checks do not establish sustained performance or model accuracy.

All 113 existing isolated backend tests passed, including the persistence API
contracts. Frontend lint and production build passed with the two existing shared
component Fast Refresh warnings. Browser integration checks are manual proof;
this milestone does not add an automated frontend testing framework.
