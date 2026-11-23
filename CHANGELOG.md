# Changelog

All notable changes. Newest versions first, in the Keep a Changelog format.

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
