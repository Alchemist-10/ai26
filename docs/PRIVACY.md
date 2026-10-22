# Optional privacy display mode

Sakshi can pseudonymize valid plate identifiers in analytics responses and pixelate detected person and plate regions in sampled camera views. Person-region pixelation covers the face when it falls inside a detected person box. This mode is opt-in and is intended to reduce exposure in day-to-day dashboards; it is not a guarantee that all personally identifying information has been removed.

## Enable it

Create a per-installation random key and restrict it to the service account. For example, on Linux:

```sh
umask 077
openssl rand -out /absolute/path/to/ai26-privacy.key 32
chmod 600 /absolute/path/to/ai26-privacy.key
```

Set `AI26_PRIVACY_KEY_FILE` in the environment and add the overlay to each Compose command:

```sh
docker compose -f compose.yaml -f compose.privacy.yaml up --build
```

The key must be readable by the backend container user (`10001` in the supplied image) and must not grant group or other access. For a host-mounted key, set its owner to UID `10001` (for example, `chown 10001:10001 /absolute/path/to/ai26-privacy.key`) before starting Compose. The API validates it at startup and fails closed if it is missing, too short, or too broadly accessible. Keep the key stable for an installation: changing it changes every pseudonym and breaks comparisons with previously displayed aliases. Back it up securely if stable aliases are required. If rotation is needed, use the offline workflow in [PRIVACY_KEY_ROTATION.md](PRIVACY_KEY_ROTATION.md); it records the key transition and rejects startup with a stale key when privacy mode is enabled.

## What the mode changes

- `/api/events`, `/api/alerts`, `/api/trajectory/...`, and `/api/nlquery` responses replace valid plate identifiers with an installation-keyed HMAC pseudonym. The transformation is applied to a response copy; stored observations are unchanged.
- Sampled camera previews detect COCO person boxes and pixelate those regions. Plate-camera views also pixelate detected plate regions, and valid plate text in the overlay is replaced with the keyed pseudonym.
- Native recorded playback (`/api/video/...`) is rejected by the API while privacy mode is enabled. The UI selects sampled detections and hides the playback control.
- Signed evidence reports, evidence images, source files, and database records retain original pixels and plate values for authorized review. Privacy mode is not a redaction workflow for evidence exports.

## Limits

Person and plate masking depends on sampled model detections. The person mask is a coarse full-box pixelation rather than a separate face-local detector. Missed, occluded, low-resolution, or out-of-frame subjects may remain visible; the sampling rate also means intermediate video frames are not checked. Unrecognized plate formats are not pseudonymized in analytics text. No labeled field footage has been used to establish a false-negative rate or privacy threshold. Validate detection coverage with representative authorized footage before relying on this mode for a deployment requirement. Describe it as best-effort masking of detected person and plate regions, not guaranteed or complete anonymization.
