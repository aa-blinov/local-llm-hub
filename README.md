# Local LLM Hub

[![ci](https://github.com/aa-blinov/local-llm-hub/actions/workflows/ci.yml/badge.svg)](https://github.com/aa-blinov/local-llm-hub/actions/workflows/ci.yml)
[![house style](https://github.com/aa-blinov/local-llm-hub/actions/workflows/house-style.yml/badge.svg)](https://github.com/aa-blinov/local-llm-hub/actions/workflows/house-style.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

A web panel for running language models on a Mac with Apple Silicon. Pick a model and an engine, start the assistant with one button, check its answers, and keep an eye on memory. Everything runs locally, with no cloud.

![Simple view: four steps from installation to the first question](docs/screenshots/simple.png)

## Installation

**Requirements**

- A Mac with Apple Silicon (M1 or newer). Verified on macOS 27.2 with 48 GB of memory.
- About 20 GB of free disk space for one model.
- Xcode Command Line Tools (the installer offers to install them).

**Quick start**

1. Download the repository and double-click `install.command`.
2. Wait for the installation to finish. The panel opens at http://127.0.0.1:8765.
3. Follow the four steps on screen: install the model program, download a model, start the assistant, ask a question.

**From the terminal**

```bash
./scripts/bootstrap.sh --engine mlx        # mlx, llamacpp or both
```

The installer creates the environment, installs the packages, builds llama.cpp when needed, sets up autostart and opens the panel. Running it again is safe.

## What it does

- **Two engines.** MLX (`mlx_vlm.server`) for models in MLX format and llama.cpp (`llama-server`, Metal) for GGUF. You choose the engine during installation or in the interface.
- **Memory check before start.** The panel estimates the weights and KV cache for the chosen conversation length and compares them with available memory. It warns you before the model loads.
- **Automatic restart.** If an engine crashes, it restarts by itself, at most three times in ten minutes. Every event is written to a local history.
- **Model downloads** from Hugging Face in the background, with progress and resume after an interruption. Gated models are supported with a token.
- **Existing models.** Point the panel at a folder with models (an external drive, LM Studio) and it uses them without downloading again.
- **opencode integration.** A button writes a `local-hub` provider into the opencode configuration. Other providers are left untouched, and a backup is created first.
- **Settings.** Autostart at login, start view, download folder, token, swap warning threshold.

The app writes to disk only inside the project folder and to a few standard locations: the Hugging Face cache, the opencode configuration (`~/.config/opencode/`) and, if autostart is on, a launch agent in `~/Library/LaunchAgents/`. Settings that contain a token are stored in `config/settings.json` with owner-only permissions, and they are excluded from git.

## Development

```bash
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -e '.[dev]'
.venv/bin/python -m llm_hub              # panel on http://127.0.0.1:8765
.venv/bin/python -m pytest tests         # tests: offline, no models required
```

Layout:

- `src/llm_hub/` — backend: configuration, engines, process supervisor, downloads, memory check, HTTP API.
- `src/llm_hub/static/` — interface: one HTML file and one script, no build step.
- `config/registry.json` — engines, models and presets.
- `scripts/` — installation, launchd agent, launcher.

The architecture is described in [`docs/architecture.md`](docs/architecture.md). Conventions and pitfalls for contributors and coding agents are in [`AGENTS.md`](AGENTS.md). To propose a change, see [`CONTRIBUTING.md`](CONTRIBUTING.md).

## Known limitations

- macOS only. Memory and process checks use macOS tools (`vm_stat`, `sysctl`).
- The memory estimate is approximate. Hybrid models are estimated from their full-attention layers; the GGUF KV cache is not estimated.
- A loaded model is not unloaded automatically when another one starts: stop the current one first.
- The setup has been tested on one machine. A clean installation on another Mac has not been verified yet.
- Starting `install.command` by double-click in Finder has not been tested; use the terminal command above if it does not open.

## Security

Settings, including a Hugging Face token, are stored in `config/settings.json` with owner-only permissions and are excluded from git. To report a vulnerability, follow [`SECURITY.md`](SECURITY.md).

## License

MIT. See [LICENSE](LICENSE). © Alexander Blinov.
