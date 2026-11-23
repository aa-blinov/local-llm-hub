# Architecture

The application has three layers: a FastAPI backend, an interface made of one HTML file and one JavaScript file, and external engine processes.

## Backend

`app.py` creates the application. On startup it loads the registry (`config.py`): engines, models, presets and folders. Models from user folders are added on top of the registry (`localscan.py`).

`supervisor.py` keeps one engine process. It knows which model is running, checks readiness through `/health`, and restarts the engine after a failure. Every event (start, stop, failure, request) is written to `logs/history.jsonl`.

`engines.py` builds the launch command for each engine. To add an engine, you need a new adapter class and an entry in the registry.

## Downloads and components

`downloads.py` downloads models in the background through `huggingface_hub`. Progress is calculated from the size of the blob files relative to the repository size. After an interruption, the download continues.

`components.py` installs and removes engines and models. Operations run as background jobs, and each one writes its own log.

## Memory

`preflight.py` estimates the weights and the KV cache. For hybrid models, the KV cache is calculated only for the full-attention layers, using `config.json`.

## Interface

One HTML file and one JavaScript file, with no build step. Data is refreshed by polling the API. The DOM is written only when the content changes, so the update does not flicker.

## External data

Settings are kept in `config/settings.json` (with the token, permissions 600). Logs go to `logs/`. Models are cached in the default Hugging Face folder or in the folder chosen by the user.
