# Import provenance and repository separation

The shared implementation was copied from `moneytosms/godseye` at commit
`3d575f68de391e178d18380092e816cd1d2b4eef` on 2026-10-08 into Sakshi's own Git history.
The source repository was not modified. The import is a snapshot: changes in one
repository do not automatically update the other.

## Copied and adapted

- Backend inference, tracking, events, normalization, queries, API, dependency lock,
  existing playback clips, and the YOLO model checkpoint.
- React frontend and its package lock.
- Static HTML/CSS/JS walkthrough with synthetic data, renamed to Sakshi.
- Launcher, rewritten for Sakshi's ports and first-run dependency installation.

App titles, package names, static-demo globals, and environment variables now use
Sakshi. Original user-specific footage paths were replaced with a local default.
The frontend uses port 5174 and backend port 8001. Missing stream footage returns
404; metadata/API startup no longer initializes inference models.

## Kept in the SIH repository

- SIH problem-statement references, competition plans, deadlines, and submission fields.
- Pitch decks, abstracts, scripts, jury Q&A, SIH research, and the pivot ADR.
- SIH product introduction video and presentation artwork.
- Source agent instructions, skills, issue-tracker configuration, and Git history.

Sakshi has its own README, run guide, architecture documentation, and regression
checks. Application behavior and current prototype limitations are documented
without presenting planned SIH work as already implemented. The source contains
no project LICENSE file; this import does not assign a new license. Upstream
libraries and model checkpoints retain their own licensing terms.

## Future transfers

Review individual code changes before porting them. Keep course reports and
competition material in their respective repositories. Do not point Sakshi's issue
tracker, deployment configuration, or footage variables at the SIH repository.
