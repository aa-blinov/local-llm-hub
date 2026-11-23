---
name: Local LLM Hub
description: A quiet control panel for local models: warm neutral background, one dark accent, thin lines instead of shadows.
colors:
  ground: "#f6f4ef"
  panel: "#fbfaf7"
  ink: "#1c1a17"
  muted: "#5f5b54"
  action: "#1d3557"
  ok: "#2f6b4f"
  wait: "#8a5a12"
  off: "#9b2c2c"
---

# Local LLM Hub: design system

## Overview

The panel looks like a tool, not a showcase: a lot of information, little decoration. The background is warm and neutral, with one dark accent for the main action. Statuses use color without filled backgrounds. Shadows and gradients are not used.

## Colors

The light and dark themes are defined by the tokens `--ground`, `--panel`, `--ink`, `--muted`, `--hair`, `--action`, `--ok`, `--wait` and `--off`. The theme switch in the header remembers the choice. Primary text is at least 7:1 contrast, secondary text at least 4.5:1.

## Typography

IBM Plex Sans (Google Fonts) with a system font fallback. Body text is 16 px, labels 14 px, panel titles 20 px, step titles 19–20 px. Numbers use tabular figures so they do not shift when refreshed.

## Layout

Desktop: three columns at the top, the log across the full width at the bottom. Row heights are reserved, so updating the state does not move neighboring blocks. Narrow screens (up to 1100 px): a single column with normal page scrolling. Spacing is in multiples of 4 px.

## Elevation & Depth

There is no depth. Panels are separated by a thin `--hair` line and spacing. Shadows are not allowed.

## Shapes

Panel radius is 12 px, fields and buttons 8 px. The progress indicator is fully rounded.

## Components

Buttons are at least 44 px high. There is only one primary button on screen: the one the current step needs. Input fields are at least 44 px high. Progress indicator: a thin bar; when the duration is unknown it moves, when known it fills, both through `transform`. Status is a dot in the header with text next to it.

## Do's and Don'ts

Do: keep one primary button on screen, show error text that says what to do, add hints under technical labels.

Don't: use emoji or check-mark symbols in text, shadows, gradients, animation that moves neighboring blocks, or font sizes below 13 px.
