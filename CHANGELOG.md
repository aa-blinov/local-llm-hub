# Changelog

All notable changes. Newest versions first, in the Keep a Changelog format.

## [0.2.0] - 2026-11-25

### Added

- KV cache compression for MLX models: 8-bit or 4-bit (4-bit is the recommended default). The memory check and the context advice account for the smaller cache.
- More context sizes for MLX: 48k, 96k, 160k, 180k and 224k tokens, besides 32k, 64k, 128k and 256k.
- Sidebar navigation on desktop; on phones the same sections are a top bar.
- Settings is grouped into "Launch and status", a collapsed "Diagnostics" block (answer check, program log, history) and "General settings".
- Light, dark and automatic themes from the monos-ui kit (Catppuccin palette), with the choice kept between launches.
- Cancel for model downloads and for installing or removing a program.

### Changed

- The interface is rewritten as a Svelte 4 app on the monos-ui kit components. It is built with `cd frontend && npm install && npm run build`; the built files are committed in `src/llm_hub/static/app/`, so the panel runs without Node.
- Fonts are bundled (Medeo Mono, SIL OFL 1.1). The panel no longer loads anything from Google Fonts.
- The opencode configuration gets a 32k output limit per model. Long files written in one tool call were cut at 8k and failed.
- "Update opencode config" writes the context that is selected on the page, not the context of the running engine. The panel warns when the two differ.
- Start and Stop check the memory with the options the engine will really start with, including the registry defaults and autostart.

### Fixed

- Program and port are shown in Status while the engine runs.
- The mode shown in the Simple view matches the running mode.
- Status text stays visible on phones.
- Step 1 of the Simple view no longer shows "Checking…" until the Programs tab is opened.
- The Install button hides once the program is installed.
- The installer prints the panel port from the registry.

### Removed

- The old plain-HTML interface (`static/index.html`, `static/app.js`) and the IBM Plex font.

## [0.1.0] - 2026-11-23

### Added

- Web panel with three sections: "Simple" (four steps), "Settings", and "Programs and models".
- Running models through MLX (`mlx_vlm.server`) and llama.cpp (`llama-server`, Metal).
- Memory check before start, based on weights and the KV cache.
- Automatic engine restart after a failure, no more than three times in ten minutes.
- Background downloads of models from Hugging Face, with progress and resume after an interruption.
- Finding models in user folders without downloading them again.
- Installing and removing engines and models from the interface.
- opencode integration: a `local-hub` provider block, with a backup of the config.
- Settings: autostart, start section, download folder, Hugging Face token, swap threshold.
- Installer `scripts/bootstrap.sh` and the `install.command` file for double-click installation.
