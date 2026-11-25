---
name: Local LLM Hub
description: A quiet control panel for local models, built on the monos-ui kit: warm paper, one 6px radius, text buttons, Gruvbox in light and dark.
colors:
  ground: "#fbf1c7"
  surface: "#ebdbb2"
  ink: "#3c3836"
  ink-soft: "#6a5e55"
  line: "#d5c4a1"
  accent: "#458588"
  success: "#646411"
  warning: "#a1460b"
  danger: "#bc211b"
---

# Local LLM Hub: design system

## Source

The panel uses the plain-CSS layer of [monos-ui](https://github.com/aa-blinov/monos-ui) 2.1.0 (commit `78158dc`):
`static/monos/tokens.css`, `static/monos/themes.css` and `static/monos/fonts.css`. The files are copied, not built;
do not edit them by hand. The kit's Svelte components and Tailwind preset are not used: the panel is plain HTML, CSS
and JavaScript with no build step.

The panel's own rules read the kit's tokens through a short alias block at the top of `index.html`
(`--ground`, `--ink`, `--hair`, `--action`, `--s-1`…`--s-8`, `--r-btn`). Change a colour in the kit and the panel follows.

## Overview

The panel is a tool, not a showcase: a lot of information, little decoration. The page is warm paper with dark ink.
Actions are words, not boxes. Statuses use colour with text next to them. There are no shadows and no gradients.

## Colors

The panel offers two modes, light and dark, and follows the system when the choice is "auto". The header button cycles
auto, dark, light and shows the current choice. Modes are set with `data-mode` on the root element. The kit also ships
five other palettes (GitHub, Dracula, Nord, Solarized, Catppuccin) selected with `data-theme`; the panel does not expose
them.

Gruvbox light (`data-mode="light"`, the default): ground `#fbf1c7`, surface `#ebdbb2`, ink `#3c3836`, soft ink
`#6a5e55`, line `#d5c4a1`, accent `#458588`.

Gruvbox dark (`data-mode="dark"`): ground `#282828`, surface `#3c3836`, ink `#ebdbb2`, soft ink `#b1a491`.

Contrast: body ink is at least 7:1 on the ground in both modes; secondary text is at least 4.5:1.

## Typography

Medeo Mono, shipped in `static/fonts/` (SIL Open Font License 1.1). No remote font is loaded. Body text is 16 px,
labels 14 px, panel titles 20 px. Text is never smaller than 14 px. Numbers use the same face, so they line up.

## Layout

Desktop: a fixed sidebar with the sections, the running mode, the status and the theme switch. The content scrolls
beside it. On the Settings view the launch and status panels sit side by side, and the diagnostics block is collapsed
by default. Narrow screens (up to 900 px): the sidebar becomes a top bar, the status takes its own row, and the page
scrolls normally.

Row heights are reserved for the content, so updating the state does not move neighbouring blocks.

### Spacing

The kit's scale, in pixels: 4, 8, 12, 16, 24, 32. Use the `--s-*` names, not raw values.

## Elevation & Depth

There is no depth. Panels are separated by a `--hair` line and spacing. Shadows are not used.

## Shapes

One radius for every rectangle: 6 px. Panels, cards, fields and buttons all use it. The step number and the status dot
are circles.

## Components

Status is a dot with the status word next to it. The progress indicator is a thin bar: indeterminate when the duration
is unknown, filled when known, both through `transform`. Error text says what to do.

### Buttons

A button is a word. It has no fill and no frame. The primary action is bold ink; other actions are regular weight.
Every button is at least 44 px high. Hover and press change the opacity, not the colour. There is one primary action
on screen: the one the current step needs.

### Fields

Fields are at least 44 px high, use the same radius and the `--hair` border, and read 16 px. Focus is shown with the
theme's focus ring (`--ui-focus`), never removed.

## Do's and Don'ts

Do: keep one primary action on screen, show error text that says what to do, add hints under technical labels, keep
every target at least 44 px.

Don't: use emoji or check-mark symbols in text, shadows, gradients, animation that moves neighbouring blocks, text
smaller than 14 px, or a second font.
