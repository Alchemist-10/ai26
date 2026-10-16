# Requesting CAM-07–09 source footage

The AI26 catalog expects readable-plate sources for these locations:

| AI26 ID | Catalog location | Expected footage path (catalog) |
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
`moneytosms/godseye` branches were checked again. AI26 main and each Godseye
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
They were fingerprinted and prepared as inactive managed releases in the local,
Git-ignored `backend/data/sources` directory. The app was left running with
processing disabled and the prepared sources were not activated. CAM-07 decoded
as 1,285 frames; CAM-08 decoded as 627 frames despite a stale container count of
752; CAM-09 decoded as 540 frames despite a stale container count of 580. The
importer now compares fully decoded counts for import validation, while its
read-only check remains metadata-only. These checks confirm valid video decode
and filename mapping only: the requested junction views, readable plates,
source authorization, export provenance, recording times/timezone, retention
terms and camera-clock offsets have not been independently verified. No plate
values or frame images are recorded here. See `docs/SOURCE_IMPORT.md` for the
managed-import workflow.

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
> We are preparing an academic AI26 traffic-observation prototype. Could you
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

Before putting a received clip into AI26:

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

Until the supplied candidates pass source authorization and content review, keep
them inactive. Real-plate evaluation remains unverified until readable plates
are manually labeled and reviewed; synthetic fixtures do not close that gate.
