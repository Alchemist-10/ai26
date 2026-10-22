# Requesting CAM-07–09 source footage

Sakshi is a citywide vehicle tracking system, exercised so far on sample footage.
Its catalog expects readable-plate sources for these three junction locations:

| Sakshi ID | Catalog location | Expected footage path (catalog) |
| --- | --- | --- |
| CAM-07 | Subhash Chandra Bose Jn | `numberplate-vids/clip 4.mp4` |
| CAM-08 | Kathrikkadavu Junction | `numberplate-vids/clip_2_00_25-00_50.mp4` |
| CAM-09 | Petta Junction | `numberplate-vids/clip_2_00_30-01_00.mp4` |

These paths document the current catalog expectation; they do not prove the
filenames used by the original camera system. A 2023 [Government of India
response](https://sansad.in/getFile/loksabhaquestions/annex/1711/AU1239.pdf?source=pqals)
lists all three junctions among Cochin Smart Mission Limited's ITMS camera
locations. Kerala's [Smart Cities project description](https://lsgd.kerala.gov.in/en/centrally-sponsored-schemes/through-lsgd/mohua/smart-cities/)
describes live and recorded video access as role-based operator access. The
[Kochi Corporation CSML page](https://kochicorporation.lsgkerala.gov.in/en/cochin-smart-mission-limited/401)
lists the public CSML contact details.

## Latest repository check

On 2026-10-16, the current upstream `moneytosms/ai26` main commit
(`d41500d5e9d79ecd0a7c14461fd3322de5944bbd`) and all three current
`moneytosms/godseye` branches were checked again. Sakshi main and each Godseye
branch contain only `CAM-01.mp4` through `CAM-06.mp4` as camera playback; the
Godseye branches also contain `frontend/public/sakshi-intro.mp4`, which is not a
camera source. No CAM-07–09 footage, video archive or new media branch was
found. Repository media is only a check for files that were committed there; it
does not establish whether CSML or another authorized custodian has archived
recordings. A fresh exact-filename scan of the current Codex workspace and
accessible files under `/mnt` on 2026-10-16 found no CAM-07–09 source clips;
`/media` is not present in this environment.

## User-supplied candidate archive (2026-10-16)

The user supplied `multi sample bus-20261015T121500Z-1-001.zip`. It contains
three MP4 files whose names match the CAM-07–09 catalog expectations above.
They were fingerprinted and prepared in the local, Git-ignored
`backend/data/sources` directory, then selected as active managed releases after
the user's explicit activation request. After restart, the API reports all
three sources available, and HTTP byte-range playback requests return 206. A
120-second read-only profile on 2026-10-16 observed inference enabled and all
three sources continuing to process without failed attempts; this is not a
junction or source-authorization check. CAM-07 decoded as 1,285 frames;
CAM-08 decoded as 627 frames despite a stale container count of
752; CAM-09 decoded as 540 frames despite a stale container count of 580. The
importer now compares fully decoded counts for import validation, while its
read-only check remains metadata-only. Representative frames show burned-in
camera/location labels matching each catalog entry and an on-screen date of
18 May 2025 with differing local times. Those labels and clock overlays are
clip-provided claims, not independently
authenticated camera identity or verified NVR timestamps. Readable-plate labels,
source authorization, export provenance, timezone/clock accuracy, retention
terms and camera-clock offsets remain unverified. The earlier smoke run produced
two format-valid, unreviewed OCR candidates on CAM-09, none on CAM-07 and only
invalid/low-confidence candidates on CAM-08; this is not an accuracy result. No plate
values or frame images are recorded here. See `docs/SOURCE_IMPORT.md` for the
managed-import workflow.

On 2026-10-18, the supplied ZIP and all three active managed originals were
hashed again. Each archive member's SHA-256 matched both the corresponding
active-release manifest and stored original bytes, tying the currently used
clips byte-for-byte to this supplied archive. The archive SHA-256 is
`607332afd0f26de98ce6de6ae465d6313ba0d1d183937f3dfbfbdef7fb924587`; the
per-camera comparison is recorded in
[`source-archive-integrity-2026-10-18.json`](validation/source-archive-integrity-2026-10-18.json).
This establishes local byte integrity and the archive-to-import mapping only.
It does not identify the archive's creator or exporting system, prove that the
footage shows the named junctions, grant permission, or validate its overlays
as original camera timestamps.

A local ZIP/MP4 metadata inspection found only DOS member modification times
(February 28 and March 5, 2026; timezone unknown) and a UTF-8 filename extra
field. The MP4s have generic `Lavf` muxer tags but no `creation_time`, recording
timecode, NVR/camera identifier, or location metadata. CAM-08 and CAM-09
container frame-count fields (752 and 580) disagree with the fully decoded
counts (627 and 540). The findings are recorded in
[`source-media-metadata-2026-10-18.json`](validation/source-media-metadata-2026-10-18.json).
These are container/archive properties, not evidence of capture date, exporter,
site, authorization or authenticity.

## Public contact for routing

The Kochi Corporation page lists Cochin Smart Mission Limited (CSML) at 4th
floor, JLN Metro Station, Kaloor, Kochi 682017; `info@csml.co.in`; and
`0484-2795700`, and links to the [official CSML website](https://csml.co.in/).
These are general public contacts, not a verified CCTV-footage desk. Ask them
to route the request below to the authorized ITMS/CCTV data custodian. No one
has been contacted as part of this work.

Kerala's [e-Application portal](https://eoffice.kerala.gov.in/Eapplication/)
offers general government applications and an RTI entry point. It is a possible
formal routing option if CSML directs the requester there; the portal is not a
footage download service, and its current recipient list and applicable
disclosure rules must be checked before filing. The [Kerala LSGD Smart City
description](https://lsgd.kerala.gov.in/en/about-the-department/aligned-institutions/smart-city-mission/)
describes live and recorded CCTV access as role-based operator access, so a
public clip or unrestricted stream should not be assumed to exist.

## Request template

Send this through an authorized project or university channel. No request has
been sent as part of this work.

> **Subject:** Authorized research sample request — Kochi ITMS junction footage
>
> Hello Cochin Smart Mission Limited,
>
> We are preparing an academic Sakshi traffic-observation prototype. Could you
> advise whether CSML can authorize a short, low-resolution research sample from
> the ITMS cameras at Subhash Chandra Bose Junction, Kathrikkadavu Junction and
> Petta Junction, corresponding to our CAM-07, CAM-08 and CAM-09 catalog entries?
>
> We need the original recording timestamps and timezone, the camera/junction
> mapping, and any known clock or buffering uncertainty. Please also specify
> permitted storage, access, retention, publication and deletion conditions. We
> can keep raw footage in restricted local storage and publish only derived
> metrics or approved, redacted samples. We will not claim government registry
> verification or use these clips for enforcement.
>
> If footage cannot be shared, could you point us to an authorized application
> or data-access process, or confirm which non-sensitive sample metadata can be
> provided instead?
>
> Thank you.

## Intake checklist

Before putting a received clip into Sakshi:

- Confirm written permission covers the actual intended use, storage location,
  people with access, retention period and any display or publication.
- Record the issuing camera and physical junction, original filename, export
  time, recording start/end, timezone, NVR/camera clock basis and known offset or
  uncertainty. Preserve operator-provided claims as claims until independently
  checked.
- Keep the unmodified source in access-controlled storage. Do not commit video,
  credentials, plate labels or identifiable screenshots to the public Git repo.
- Compute a SHA-256 digest and record source provenance before creating any
  proxy, sampled frame or annotation. Preserve the source separately from
  derivatives.
- Use the Camera settings source-preparation workflow or a protected
  `AI26_FOOTAGE_ROOT`; verify the selected camera ID and playback binding after
  restart.
- Label readable plates and difficult/negative examples with a documented
  policy. Keep vehicle, camera/location and recording-session splits disjoint
  before reporting held-out results.
- Verify that the clip actually shows the requested junction and that its
  plates are sufficiently readable. A news or handheld recording of the same
  area is not an equivalent fixed-camera ITMS source and must not be relabeled as
  CAM-07, CAM-08 or CAM-09.

The supplied candidates are currently active at the user's direction while
source authorization and origin remain unverified. A user has manually
transcribed four readable crop candidates; all four stored OCR outputs differed
and were rejected by the format gate. Sixteen other sampled crops were marked
unreadable and one uncertain. These selected detections are not a representative
or held-out evaluation and do not measure detector misses; synthetic fixtures do
not close that gate.
