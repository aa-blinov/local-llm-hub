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

## Memory estimate

One formula, used by the pre-start check and by the context advice:

    needed = weights + KV cache + overhead + prefix cache

- **weights**: size of the model files on disk.
- **KV cache**: `full_attention_layers × 2 × kv_heads × head_dim × 2 bytes × context`. The numbers come from the model's `config.json`. For Ornith and the other Qwen 3.5/3.6 MoE models this is 20 KiB per token; 128k tokens is about 2.5 GiB.
- **overhead**: activation buffers and runtime memory above weights and KV, measured with MLX at a 512-token prefill step. Each model stores its measured points in `config/registry.json` (`memory.overhead_gib`, at 8k, 32k, 64k and 128k tokens) and the value is interpolated between them. Above the measured range the generic rule applies: 0.6 GiB plus 1 GiB per 64k tokens, which is the conservative side. Models without measurements use the generic rule.
- **prefix cache**: the `apc_mem_gb` cap (6 GB on Macs with 48 GB or more, 2 GB below). The engine never exceeds this cap, so the full cap is counted.

The advice compares `needed` with 75% of the Mac's total memory and picks the largest context that fits. The 75% share is a planning margin, not a measured limit.

Measured with MLX, prefill step 512: the KV term matches the formula within about 0.2 GiB up to 64k; at 128k the formula is about 0.9 GiB higher than the measurement, which is the safe side. Contexts above 128k are not measured.
