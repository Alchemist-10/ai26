---
name: AI26
description: inherited dark shell and Camera settings metadata interface
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

# Design System: AI26

## Overview

This record covers the inherited AI26 dark application shell and the Camera settings extension. It describes the current implementation, not a replacement identity or a universal redesign. Godseye is outside this record. PRODUCT.md is absent; a creative North Star, brand adjectives, anti-references, and qualitative component philosophy are unrecorded.

The implemented surface uses black backgrounds, zinc controls and dividers, white text and primary actions, and teal focus and status treatments. Native labelled metadata fields sit beside retained revision history on desktop and above it on mobile. Screenshots show an internally scrolling section beneath the application header.

**Creative North Star:** Unrecorded.

**Key Characteristics:**

- Black and zinc surfaces with white actions.
- IBM Plex Sans for this shell and form.
- Visible labels, native controls, and explicit revision review.
- A persistent header with internal content scrolling.

Source of truth: `frontend/src/index.css`, `frontend/src/App.tsx`, `frontend/src/components/NavDrawer.tsx`, `frontend/src/pages/CameraSettings.tsx`, and incumbent controls in `frontend/src/components/panels/AlertsPanel.tsx`. Tailwind utility values resolve from the installed `frontend/node_modules/tailwindcss/theme.css`; its OKLCH values remain canonical. The five existing `.impeccable/review/` screenshots are viewport samples: desktop and desktop-lower at 1280×720; mobile, mobile-form, and mobile-history at 390×844. They cover internal section scroll positions, not a full document. The finish verdict is limited to the notice-lifecycle fix; no new global validation is claimed.

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

The shell and settings use **IBM Plex Sans** with system sans fallbacks. The global stylesheet also defines IBM Plex Mono, but it is not the settings field face. Coordinates use tabular numerals within Plex Sans. No display type role or new font pairing is established here.

- **Headline:** Camera settings page title.
- **Title:** Location metadata and Revision history section headings.
- **Body:** Explanatory text uses the small size, often with relaxed line height; ordinary metadata uses the small default line height.
- **Label:** Form labels and button copy use medium weight.
- **Control:** Text inputs, number inputs, select, and textarea use the base size.

The inherited AI26 wordmark uses a bold small face with wide letter spacing (0.2em). Header context is smaller uppercase copy. These are shell details, not a requirement for field labels.

## Layout

The application fills the viewport, clips the outer document, and leaves the header above a flexible main region. Camera settings fills that region and scrolls internally. Its centered content is capped at 64rem, with padding of 1rem below the small breakpoint and 1.5rem above it. Explanatory copy is capped at 70ch where implemented.

Settings begins with title and explanation, a camera selector/refresh row, current revision metadata, then the editing form and history. At 40rem, the selector and refresh action share a row and coordinate fields form two equal columns. At 64rem, metadata and history become 3:2 columns with a 2rem gap. Below that, history follows the form with a top divider. Flexible button rows wrap instead of forcing horizontal overflow. These compositions belong to Camera settings; other pages retain their existing layouts.

The drawer is fixed at 18rem wide and contains its own scrolling navigation. Header context badges are progressively hidden below the small and medium breakpoints. Settings buttons have a minimum height of 2.75rem.

## Elevation & Depth

Settings uses borders, spacing, and dark tonal surfaces without card shadows. The inherited drawer uses a dark translucent, blurred backdrop and a small shadow on active navigation; the shell identity mark also retains its small shadow. Shadow values and backdrop detail live in the sidecar. Drawer motion lasts 200ms; navigation state transitions use 150ms. The existing global reduced-motion rule shortens animation and transition durations and restores automatic scroll behavior.

## Shapes

Form fields, settings buttons, alerts containers, and notices have small rounded corners. Shell badges and identity elements use the medium radius; navigation items use the larger radius. Thin borders define inputs, action outlines, and section boundaries. Native checkbox and select geometry is retained. The textarea can resize vertically. No new illustration, media, or ornamental shape language is introduced by this extension.

## Components

### Buttons

The primary settings action uses white with black text and a light zinc hover. Secondary actions use a zinc outline and a dark zinc hover. Both preserve the shared focus-visible outline. Disabled actions reduce opacity; settings buttons additionally use the not-allowed cursor. Loading labels explain current activity.

### Inputs / Fields

Native input, number, select, checkbox, and textarea controls have visible associated labels. Fields use a dark zinc fill and zinc border with white text. Focus uses the global teal outline (2px with 3px offset). Disabled controls reduce opacity. The form communicates location, coordinate, reviewer, and reason requirements through native attributes and explicit error copy. Operator confirmation is an assertion; the adjacent text retains the calibration limits.

### Cards / Containers

Existing alerts use bordered, lightly rounded containers. Settings groups and history rely on headings and dividers rather than adding cards. Preserve this distinction when extending either surface.

### Navigation

The AI26 drawer pairs navigation labels with short descriptions and icons. The active item uses white with black text; inactive items use muted zinc with brighter text and a dark fill on hover. Keyboard focus is trapped while open, Escape closes it, and closing restores prior focus. Camera settings appears alongside the incumbent navigation destinations.

### Chips / Status

Header availability chips use zinc surfaces, light text, thin borders, and a small white indicator. Keep the explicit source-availability label. Settings errors use `role="alert"`; notices use `role="status"`. Old saved/no-save notices clear when the metadata draft is edited so they do not describe the new draft as already saved.

### Metadata revisions

The settings form remains mounted after its first visit so draft state survives navigation within AI26. Browser reload or closure still loses the draft. A dirty draft disables camera switching and refresh; discarding is explicit. Revision history is read-only and does not replace the draft. A concurrent or unconfirmed save preserves the draft and requires explicit latest-revision review before saving again. Keeping a draft or loading latest values is a separate decision from saving. Existing observations retain their captured revision.

## Do's and Don'ts

### Do:

- **Do** continue the black/zinc settings surface and existing Plex Sans typography.
- **Do** preserve visible field labels, native control semantics, and the shared teal focus outline.
- **Do** stack settings and history on narrow screens; keep the desktop 3:2 column arrangement.
- **Do** keep revision identity and draft state visible; clear old success/no-save notices when a draft field changes.
- **Do** retain AI26 naming and the boundary between metadata settings and deployment configuration.

### Don't:

- **Don't** import Godseye branding or infer a new shared identity.
- **Don't** turn this settings layout into a mandatory composition for every AI26 page.
- **Don't** replace revision history with an editable snapshot or hide the explicit concurrent-save review.
- **Don't** add media or new settings polling as decoration or imply that operator confirmation establishes calibration.
- **Don't** treat these screenshots as whole-document coverage or this pass as new global validation.
