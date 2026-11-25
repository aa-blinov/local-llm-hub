"""Sync the provider in the opencode configuration.

Only the provider.local-hub block is touched. Other keys (providers, MCP) are left as they are.
A backup opencode.jsonc.bak-<time> is made before writing.
"""
import json
import shutil
import time
from pathlib import Path

from .config import OPENCODE_CONFIG, Registry, sampling_params
from .engines import make_adapter

PROVIDER = "local-hub"


def _load() -> dict:
    if not OPENCODE_CONFIG.exists():
        return {"$schema": "https://opencode.ai/config.json"}
    text = OPENCODE_CONFIG.read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"the opencode config is not valid JSON (does it contain comments?): {e}")


def _model_id(reg: Registry, key: str) -> str | None:
    m = reg.models[key]
    if m.engine == "mlx":
        p = m.resolve()
        return str(p) if p else None
    return key


def status_config(reg: Registry) -> dict:
    try:
        cfg = _load()
    except ValueError as e:
        return {"ok": False, "error": str(e), "path": str(OPENCODE_CONFIG)}
    block = cfg.get("provider", {}).get(PROVIDER)
    return {
        "ok": True,
        "path": str(OPENCODE_CONFIG),
        "configured": block is not None,
        "models": list((block or {}).get("models", {}).keys()),
        "base_url": (block or {}).get("options", {}).get("baseURL"),
    }


def sync_config(reg: Registry, sup, requested_ctx: int | None = None) -> dict:
    try:
        cfg = _load()
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    # The context the user picked on the page wins; the running engine is only used when nothing was sent.
    running_ctx = (sup.opts or {}).get("ctx") if sup.status()["running"] else None
    ctx = int(requested_ctx or running_ctx or reg.default.get("ctx", 131072))
    models = {}
    for key, m in reg.models.items():
        mid = _model_id(reg, key)
        if mid is None:
            continue
        models[mid] = {
            "name": m.label,
            "limit": {"context": int(ctx), "output": 8192},
            # Recommended sampling for general and coding tasks (model cards); greedy decoding loops on some models.
            "options": sampling_params(m),
        }
    block = {
        "npm": "@ai-sdk/openai-compatible",
        "name": "Local LLM Hub",
        "options": {"baseURL": f"http://127.0.0.1:{reg.port}/v1", "apiKey": "local"},
        "models": models,
    }
    cfg.setdefault("provider", {})[PROVIDER] = block
    OPENCODE_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    if OPENCODE_CONFIG.exists():
        backup = OPENCODE_CONFIG.with_name(f"{OPENCODE_CONFIG.name}.bak-{time.strftime('%Y%m%d-%H%M%S')}")
        shutil.copy2(OPENCODE_CONFIG, backup)
    OPENCODE_CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    note = None
    if running_ctx and int(running_ctx) != ctx:
        note = f"The running model was started with {int(running_ctx):,} tokens. Start it with {ctx:,} tokens, or opencode requests will be too long."
    return {"ok": True, "path": str(OPENCODE_CONFIG), "models": len(models), "context": ctx, "note": note}
