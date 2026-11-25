# AGENTS.md

A reference for people and AI agents who work on this project.

## Commands

```bash
uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -e .
.venv/bin/python -m llm_hub                   # panel, port from config/registry.json (8765)
.venv/bin/python -m pytest tests              # tests, no network and no models
.venv/bin/python -m py_compile src/llm_hub/*.py
node --check src/llm_hub/static/app.js        # interface syntax
bash -n scripts/bootstrap.sh
```

## Structure

- `src/llm_hub/config.py` — registry and models, model file lookup.
- `src/llm_hub/engines.py` — engine launch commands and readiness checks.
- `src/llm_hub/supervisor.py` — engine process, automatic restart, event log, test chat.
- `src/llm_hub/downloads.py` — background downloads from Hugging Face.
- `src/llm_hub/components.py` — installing and removing engines and models.
- `src/llm_hub/preflight.py` — memory estimate.
- `src/llm_hub/localscan.py` — finding models in user folders.
- `src/llm_hub/settings.py` — settings, including the token.
- `src/llm_hub/opencode.py` — provider block in the opencode config.
- `src/llm_hub/app.py` — HTTP API.
- `src/llm_hub/static/` — interface.

## Pitfalls

- Do not commit `config/settings.json`: it contains the token. The file is listed in `.gitignore`.
- Do not add `cache/`, `logs/`, `engines/` or `.venv/` to git: they hold models, builds and logs, several hundred megabytes.
- Model paths in the registry start with `~`. Do not insert absolute paths from your own machine.
- The MLX engine and the llama.cpp engine need different binaries. The `binary_ok` field in the catalog shows whether the binary is present.
- Updating the interface must not move elements: block heights are set in advance.
- Restarting the panel from its own request cuts off that request. For autostart, only the agent file is written.
- Emoji are not used in project files.
- `static/monos/` and `static/fonts/` are copied from aa-blinov/monos-ui (MIT / SIL OFL). Do not edit them by hand; take a newer copy from the kit instead.
- The panel is plain HTML, CSS and JavaScript. Do not add a framework or a build step without a decision in DESIGN.md.

## Working rules

- Keep changes small and verify them: syntax, tests, a run in the browser.
- Error messages for the user are written in plain language and always say what to do.
- Public artifacts (screenshots, descriptions) must not contain tokens, paths to personal files or account data.
