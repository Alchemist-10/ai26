---
name: Sakshi
description: inherited dark shell and Camera settings metadata, source inspection, browser clip preparation, and next-startup selection interface
colors:
  background: "#080d12"
  foreground: "#e7eef0"
  border: "#22303a"
  primary: "#38d1c2"
  black: "#000000"
  white: "#ffffff"
  zinc-200: "oklch(92% 0.004 286.32)"
  zinc-300: "oklch(87.1% 0.006 286.286)"
  zinc-400: "oklch(70.5% 0.015 286.067)"
  zinc-500: "oklch(55.2% 0.016 285.938)"
  zinc-600: "oklch(44.2% 0.017 285.786)"
  zinc-700: "oklch(37% 0.013 285.805)"
  zinc-800: "oklch(27.4% 0.006 286.033)"
  zinc-900: "oklch(21% 0.006 285.885)"
  zinc-950: "oklch(14.1% 0.005 285.823)"
  teal-100: "oklch(95.3% 0.051 180.801)"
  teal-400: "oklch(77.7% 0.152 181.912)"
  teal-500: "oklch(70.4% 0.14 182.503)"
  teal-950: "oklch(27.7% 0.046 192.524)"
  red-100: "oklch(93.6% 0.032 17.717)"
  red-200: "oklch(88.5% 0.062 18.334)"
  red-400: "oklch(70.4% 0.191 22.216)"
  red-950: "oklch(25.8% 0.092 26.042)"
typography:
  headline:
    fontFamily: "IBM Plex Sans, system-ui, sans-serif"
    fontSize: "1.5rem"
    fontWeight: 600
    lineHeight: "2rem"
  title:
    fontFamily: "IBM Plex Sans, system-ui, sans-serif"
    fontSize: "1.125rem"
    fontWeight: 600
    lineHeight: "1.75rem"
  body:
    fontFamily: "IBM Plex Sans, system-ui, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 400
    lineHeight: "1.625"
  label:
    fontFamily: "IBM Plex Sans, system-ui, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 500
    lineHeight: "1.25rem"
  control:
    fontFamily: "IBM Plex Sans, system-ui, sans-serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: "1.5rem"
rounded:
  sm: "0.25rem"
  md: "0.375rem"
  lg: "0.5rem"
spacing:
  '2': "0.5rem"
  '3': "0.75rem"
  '4': "1rem"
  '6': "1.5rem"
  '8': "2rem"
components:
  button-primary:
    backgroundColor: "{colors.white}"
    textColor: "{colors.black}"
    typography: "{typography.label}"
    rounded: "{rounded.sm}"
    padding: "0.5rem 0.75rem"
  button-primary-hover:
    backgroundColor: "{colors.zinc-200}"
  button-secondary:
    textColor: "{colors.white}"
    typography: "{typography.label}"
    rounded: "{rounded.sm}"
    padding: "0.5rem 0.75rem"
  button-secondary-hover:
    backgroundColor: "{colors.zinc-800}"
  metadata-input:
    backgroundColor: "{colors.zinc-900}"
    textColor: "{colors.white}"
    typography: "{typography.control}"
    rounded: "{rounded.sm}"
    padding: "0.5rem 0.75rem"
    width: "100%"
  navigation-active:
    backgroundColor: "{colors.white}"
    textColor: "{colors.black}"
    rounded: "{rounded.lg}"
    padding: "0.625rem 0.75rem"
  availability-chip:
    backgroundColor: "{colors.zinc-900}"
    textColor: "{colors.zinc-200}"
    rounded: "{rounded.md}"
    padding: "0.25rem 0.625rem"
  bordered-container:
    textColor: "{colors.white}"
    rounded: "{rounded.sm}"
    padding: "1rem"
  status-notice:
    textColor: "{colors.teal-100}"
    rounded: "{rounded.sm}"
    padding: "0.75rem"
---

# Design System: Sakshi

## Overview

This record covers the inherited Sakshi dark application shell and the Camera settings extension. It describes the current implementation, not a replacement identity or a universal redesign. Godseye is outside this record. PRODUCT.md is absent; a creative North Star, brand adjectives, anti-references, and qualitative component philosophy are unrecorded.

The implemented surface uses black backgrounds, zinc controls and dividers, white text and primary actions, and teal focus and status treatments. Source inspection precedes native labelled metadata fields, which sit beside retained revision history on desktop and above it on mobile. Source details use native disclosures within the same internally scrolling section beneath the application header. The Operate direction extends these settings: source inspection leads into browser upload inside the import disclosure, ready footage gains an explicit browser selection form, and recent releases provide retained-parent rollback. Separate nested disclosures retain host-command alternatives and host-file guidance. Metadata editing remains a separate workflow.

**Creative North Star:** Unrecorded.

**Key Characteristics:**

- Black and zinc surfaces with white actions.
- IBM Plex Sans for this shell and form.
- Visible labels, native controls, and explicit revision review.
- Separate running inference and browser sources with explicit restart status.
- A persistent header with internal content scrolling.

Source of truth: `frontend/src/index.css`, `frontend/src/App.tsx`, `frontend/src/components/NavDrawer.tsx`, `frontend/src/pages/CameraSettings.tsx`, `frontend/src/components/settings/CameraSources.tsx`, `frontend/src/components/settings/SourceUpload.tsx`, `frontend/src/components/settings/SourceSelection.tsx`, `frontend/src/lib/api.ts`, and incumbent controls in `frontend/src/components/panels/AlertsPanel.tsx`. Tailwind utility values resolve from the installed `frontend/node_modules/tailwindcss/theme.css`; its OKLCH values remain canonical. The five earlier metadata screenshots in `.impeccable/review/` remain evidence for that pass and its notice-lifecycle fix.

The source extension has six reviewed viewport captures in `.impeccable/review/`: `source-desktop.png` and `source-desktop-history.png` (1280×720), `source-user-786.png` (786×758), and `source-mobile.png`, `source-mobile-pending.png`, and `source-mobile-history.png` (390×844). These cover internal section scroll positions, visible source summaries, missing footage, pending restart, expanded release history, wrapped identifiers, and keyboard focus. Import guidance remained collapsed and source error notices were not captured; their visual treatments are documented from the component source. Separate browser DOM/API checks used an isolated synthetic fixture with processing disabled and zero observations: source-status error/retry, invalid-selection recovery, the expanded host-command disclosure with CAM-07 and `--replace`, and activation of the selected import after API restart followed by source refresh. That refresh cleared pending and recovered error notices. These checks do not add screenshot coverage. The source finish review disposition is ship; its scope is this extension, not new global validation or whole-document coverage.

The browser-upload extension has seven reviewed captures in `.impeccable/review/`: `upload-desktop-ready.png`, `upload-desktop-command.png`, and `upload-desktop-failed.png` (1280×720); `upload-mobile-form.png`, `upload-mobile-ready.png`, and `upload-mobile-failed.png` (nominal 390×844, actual 390×843); and `upload-user-786.png` (786×758). These are internal scrolled viewports covering the native upload form, ready receipt, wrapping host-selection command, and failed preparation. They are not whole-page captures. The scoped finish reviewer returned ship in five sections with no requested fixes; the reported single detector run returned `[]`. This records the supplied review evidence, not a new browser/test/detector run, whole-app approval, or measured sustained performance.

The browser-selection extension has seven reviewed captures in `.impeccable/review/`: `selection-desktop-ready.png`, `selection-desktop-pending.png`, and `selection-desktop-rollback.png` (1280×720); `selection-user-1014.png` (1014×758); and `selection-mobile-ready.png`, `selection-mobile-rollback.png`, and `selection-mobile-conflict.png` (nominal 390×844, saved 390×843). The scoped reviewer inspected all seven after the final UI changes and returned ship with no UI fixes. These cover prepared selection, pending restart, retained-parent rollback, and stale-request recovery. The single supplied detector run returned `[]`; this documentation pass did not rerun it. This is evidence for the named Camera settings extension, not whole-app approval, full-page coverage, or sustained performance measurement. Behavior is grounded in the landed components and `docs/SOURCE_SELECTION.md`.

## Colors

### Primary

- **Primary teal:** The existing global primary/ring value supplies keyboard focus and text-selection treatment. Settings checkboxes and status notices use the existing Tailwind teal scale, rather than redefining that global accent.
- **Teal status scale:** Pale teal notice text, a translucent teal border, and a dark translucent teal background identify status. The checkbox uses the brighter teal control value.

### Neutral

- **Black and white:** Black settings and drawer backgrounds; white field text, active navigation, and primary actions. The shell retains its global background and foreground variables.
- **Zinc surface scale:** Dark zinc fields and header details; zinc borders separate form groups and history. Lighter zinc supports descriptions, inactive navigation, and hover states.
- **Global border:** Retained for scrollbar treatment; settings dividers use the zinc scale.

Error notices use the existing red scale with translucent border and background. These semantic status colors are not extra brand palettes. Frontmatter contains the normative values; sidecar snippets carry opacity, borders, and focus treatment.

## Typography

The shell and settings use **IBM Plex Sans** with system sans fallbacks. The global stylesheet also defines IBM Plex Mono; source hashes and offline command examples use it, while settings fields retain Plex Sans. Coordinates and source video metadata use tabular numerals within Plex Sans. No display type role or new font pairing is established here.

- **Headline:** Camera settings page title.
- **Title:** Source footage, Location metadata, and Revision history section headings.
- **Body:** Explanatory text uses the small size, often with relaxed line height; ordinary metadata uses the small default line height.
- **Label:** Form labels and button copy use medium weight.
- **Control:** Text inputs, number inputs, select, and textarea use the base size.

The inherited Sakshi wordmark uses a bold small face with wide letter spacing (0.2em). Header context is smaller uppercase copy. These are shell details, not a requirement for field labels.

## Layout

The application fills the viewport, clips the outer document, and leaves the header above a flexible main region. Camera settings fills that region and scrolls internally. Its centered content is capped at 64rem, with padding of 1rem below the small breakpoint and 1.5rem above it. Explanatory copy is capped at 70ch where implemented.

Settings begins with title and explanation, a camera selector/refresh row, current revision metadata, then source inspection followed by the editing form and metadata history. At 40rem, the selector and refresh action share a row and coordinate fields form two equal columns. At 64rem, metadata and history become 3:2 columns with a 2rem gap. Below that, history follows the form with a top divider. Flexible button rows wrap instead of forcing horizontal overflow. These compositions belong to Camera settings; other pages retain their existing layouts.

The source section spans the content width with zinc top and bottom dividers and 1.5rem vertical spacing. Its heading and manual refresh action wrap as needed. At 40rem, inference and browser playback form two equal columns; below that they stack. Release details use a label/value grid at that breakpoint and stack below it. Long release identifiers, filenames, hashes, and command examples wrap inside the available width. Disclosures begin closed; their summaries retain a minimum height of 2.75rem. Inside the import disclosure, the upload file field spans the form width; name and reason become two columns at 40rem and stack below it. Explicit replacement confirmation spans both columns. Preparation and selection actions wrap, and long receipt IDs and host commands break within the available width. Selection reviewer and reason fields use the same two-column arrangement at 40rem and stack below it. The rollback target uses a full-width native select, followed by the shared selection form when an earlier import is chosen.

The drawer is fixed at 18rem wide and contains its own scrolling navigation. Header context badges are progressively hidden below the small and medium breakpoints. Settings buttons have a minimum height of 2.75rem.

## Elevation & Depth

Settings uses borders, spacing, and dark tonal surfaces without card shadows. The inherited drawer uses a dark translucent, blurred backdrop and a small shadow on active navigation; the shell identity mark also retains its small shadow. Shadow values and backdrop detail live in the sidecar. Drawer motion lasts 200ms; navigation state transitions use 150ms. The existing global reduced-motion rule shortens animation and transition durations and restores automatic scroll behavior.

## Shapes

Form fields, settings buttons, alerts containers, and notices have small rounded corners. Shell badges and identity elements use the medium radius; navigation items use the larger radius. Thin borders define inputs, action outlines, and section boundaries. Native checkbox and select geometry is retained. The textarea can resize vertically. No new illustration, media, or ornamental shape language is introduced by this extension.

## Components

### Buttons

The primary settings action uses white with black text and a light zinc hover. Secondary actions use a zinc outline and a dark zinc hover. Both preserve the shared focus-visible outline. Disabled actions reduce opacity; settings buttons additionally use the not-allowed cursor. Loading labels explain current activity.

### Inputs / Fields

Native input, number, select, checkbox, textarea, and file controls have visible associated labels. Fields use a dark zinc fill and zinc border with white text. Focus uses the global teal outline (2px with 3px offset). Disabled controls reduce opacity. The form communicates location, coordinate, reviewer, and reason requirements through native attributes and explicit error copy. Operator confirmation is an assertion; the adjacent text retains the calibration limits.

### Cards / Containers

Existing alerts use bordered, lightly rounded containers. Settings groups and history rely on headings and dividers rather than adding cards. Preserve this distinction when extending either surface.

### Navigation

The Sakshi drawer pairs navigation labels with short descriptions and icons. The active item uses white with black text; inactive items use muted zinc with brighter text and a dark fill on hover. Keyboard focus is trapped while open, Escape closes it, and closing restores prior focus. Camera settings appears alongside the incumbent navigation destinations.

### Chips / Status

Header availability chips use zinc surfaces, light text, thin borders, and a small white indicator. Keep the explicit source-availability label. Settings errors use `role="alert"`; notices use `role="status"`. Old saved/no-save notices clear when the metadata draft is edited so they do not describe the new draft as already saved.

### Metadata revisions

The settings form remains mounted after its first visit so draft state survives navigation within Sakshi. Browser reload or closure still loses the draft. A dirty draft disables camera switching and current-revision refresh; source-status refresh remains independent of that draft. Upload/preparation and selection verification also disable source-status refresh, camera switching, and current-revision refresh; the metadata form stays independent of footage operations. Discarding is explicit. Revision history is read-only and does not replace the draft. A concurrent or unconfirmed save preserves the draft and requires explicit latest-revision review before saving again. Keeping a draft or loading latest values is a separate decision from saving. Existing observations retain their captured revision.

### Source inspection

Source summaries are read-only; preparation and selection are explicit mutation workflows in the same source section. Inference source and browser playback are separate summaries with filenames, sizes, missing-file messages, and recorded-replay context. A manual refresh checks source status; it has its own loading label and is available independently of metadata draft changes, while upload/preparation and selection verification temporarily disable it. Refresh retains the upload component and its draft. The section adds no video, background timer, or automatic polling.

Running imports and selected imports remain distinct. A teal `role="status"` notice explains when a selection requires an API restart and that running inference and playback retain their current source until then. Red `role="alert"` notices communicate status-fetch failure with manual retry guidance, changed or missing running files, and invalid selected imports without implying that the running source switched. The checked timestamp is paired with the returned verification scope; file presence/size, startup hash checks, pending selection, and history are not presented as interchangeable assurances.

Native `details`/`summary` disclosures expose running-import metadata, browser preparation with separate host-file import guidance, and recent releases. Nested release summaries identify Running, Selected for restart, or Earlier import. Expanded details show the import date, local operator claim and reason, video dimensions/rate/duration, file sizes, and original/playback hashes. History is bounded to up to ten releases from the selected import's parent chain; retained older or unlinked files and unvalidated history remain explicit. The Earlier release to select control offers the displayed retained parents, excluding the current selection; it does not enumerate unlinked prepared releases. Offline commands use wrapping zinc code blocks and a check → stop/import → restart/refresh sequence. Import guidance keeps footage provenance and location metadata review separate and states the local unauthenticated nature of operator claims.

### Browser clip preparation

The upload is a separate mutation workflow within the source section; source inspection remains read-only. A native file picker accepts recorded video, followed by visible name and reason fields and required explicit replacement confirmation when existing or selected footage is present. Files must be nonempty and no larger than 128 MiB; filenames are limited to 200 characters, names to 100, and reasons to 1000. The white Upload and prepare clip action uses the incumbent settings button; the native file-picker button has a zinc fill. Names and reasons remain local claims rather than verified provenance or location.

Uploading disables the upload fieldset and exposes a status label plus Cancel upload. Preparation uses explicit Check preparation and Cancel preparation actions, with checking labels and disabled repeated actions. Failed preparation and request failures use the established red alert treatment; cancellation and ready receipts use explicit status copy. No progress percentage is invented. The receipt keeps its filename and wrapping monospace job ID visible. Manual Check preparation updates the receipt and releases the busy state when it reports ready, failed, or cancelled; a preparation that is still running keeps the controls guarded. This workflow introduces no timers, automatic polling, media previews, or model loads.

Ready footage remains inactive until explicitly selected and activated by an API host restart. A ready receipt offers Select for restart with separate Selection reviewer and Selection reason fields. Selected-for-restart and already-running receipts use distinct copy. A collapsed Select with a host command instead disclosure retains the camera-specific `select_source.py` command with `--expected-current` and the stop/select/restart/refresh sequence. Preparation-time validation does not verify actual content or original clocks. Existing inference and playback continue throughout preparation and browser selection.

The app keeps Camera settings mounted after first use, so the file, name, reason, and replacement draft survive navigation to other Sakshi pages and source-status refresh. These drafts are lost on browser reload; changing cameras remounts the source workflow. Only the job ID is saved under a camera-specific localStorage key, allowing a status restoration attempt when that same camera is revisited after reload. This does not persist the upload file or claim fields, and a failed restoration asks the user to choose a file again. Metadata drafts have their own lifecycle and can still be edited while source preparation runs.

### Browser selection and retained-parent rollback

The shared selection form extends the incumbent ruled settings section: visible labels, native base-size inputs, white primary action, zinc divider, and no added card or identity. Select for restart selects a ready release only against the managed release it was prepared from. Recent imported releases offers a bounded retained-parent target and the same reviewer/reason form, with Select earlier release for restart. A changed preparation base prompts another preparation or an eligible parent rollback.

Both retained original and playback files are explicitly rehashed on selection POST. The expected token is a canonical metadata fingerprint, with a unique per-selection marker that rejects stale requests even after a return to the same release. Inspection tokens are not fresh video-integrity proof. During verification the fieldset and repeated action are disabled, the action reads Verifying and selecting…, and a status line explains that current footage and other pages remain available. Running original and playback paths stay cached at startup until the API restarts; selecting the already-running release to undo a pending replacement clears the pending notice without restarting.

A failed, stale, or unconfirmed request preserves reviewer and reason, shows a red alert, and disables resubmission until manual Refresh source status. The refreshed selection must be reviewed before another explicit attempt because a lost response may already have committed. Selection adds no automatic retry, polling, media preview, model worker, or SQL metadata/observation writes. Selection claims survive internal navigation and source refresh but are lost on browser reload.

A native Last browser selection disclosure exposes the local reviewer, reason, time, and prepared/earlier-import intent. Its copy explicitly records selection, not activation, verified content, or authenticated identity. Restart required remains a teal status notice with API host stop/restart and manual refresh instructions. There is no browser restart action, live activation, automatic cleanup, full selection-history browser, RTSP extension, or authentication added by this surface. Invalid selections and return to configured/bundled defaults still require manual host recovery while stopped.

## Do's and Don'ts

### Do:

- **Do** continue the black/zinc settings surface and existing Plex Sans typography.
- **Do** preserve visible field labels, native control semantics, and the shared teal focus outline.
- **Do** stack settings and history on narrow screens; keep the desktop 3:2 column arrangement.
- **Do** keep revision identity and draft state visible; clear old success/no-save notices when a draft field changes.
- **Do** retain Sakshi naming and the boundary between metadata settings and deployment configuration.
- **Do** distinguish running sources, inactive prepared releases, and selections awaiting restart in Camera settings; keep source refresh independent of metadata drafts and guarded during upload/preparation and selection verification.
- **Do** keep browser preparation, explicit next-startup selection, host restart, and location metadata editing distinct, with explicit replacement and manual preparation checks.
- **Do** preserve selection reviewer/reason after an error and require manual source refresh before another explicit attempt; label Last browser selection as a local claim about selection.

### Don't:

- **Don't** import Godseye branding or infer a new shared identity.
- **Don't** turn this settings layout into a mandatory composition for every Sakshi page.
- **Don't** replace revision history with an editable snapshot or hide the explicit concurrent-save review.
- **Don't** add media or new settings polling as decoration or imply that operator confirmation establishes calibration.
- **Don't** treat these screenshots as whole-document coverage or this pass as new global validation.
- **Don't** imply that upload or selection activates footage, persists file/name/reason drafts across reload, verifies source clocks, authenticates reviewer identity, or restarts the API from the browser.
- **Don't** present bounded retained-parent rollback as arbitrary release browsing, full selection history, automatic cleanup, or live switching.
