"""Pre-flight memory estimate: weights + KV cache for the chosen context versus available memory.

The estimate is rough. For hybrid models (linear + full attention) the KV cache grows only in the
full-attention layers, as in the Ornith/Qwen3.5 config. GGUF KV cache is not estimated.
"""
import json
import re
import subprocess
from pathlib import Path

from .config import Model

GIB = 2**30
PAGE = 16384
# Activation buffers and runtime allocations, measured with MLX (prefill step 512):
# peak memory above weights + KV cache was 0.7 GiB at 8k, 1.1 at 32k and 1.6 at 64k tokens.
OVERHEAD_BASE_GIB = 0.6
OVERHEAD_PER_64K_GIB = 1.0


def overhead_gib(ctx: int) -> float:
    """Runtime overhead for a context of `ctx` tokens; grows with the length of the context."""
    return OVERHEAD_BASE_GIB + OVERHEAD_PER_64K_GIB * ctx / 65536
FP16 = 2             # bytes per KV cache element (default)


def _vm() -> dict:
    out = subprocess.run(["vm_stat"], capture_output=True, text=True).stdout

    def pages(name):
        m = re.search(rf"{name}:\s+(\d+)", out)
        return int(m.group(1)) if m else 0

    free = pages("Pages free") + pages("Pages speculative")
    inactive = pages("Pages inactive")
    swap = subprocess.run(["sysctl", "-n", "vm.swapusage"], capture_output=True, text=True).stdout
    m = re.search(r"used = ([\d.]+)M", swap)
    swap_used = float(m.group(1)) / 1024 if m else 0.0
    return {
        "free_gib": free * PAGE / GIB,
        "inactive_gib": inactive * PAGE / GIB,
        "swap_used_gib": swap_used,
    }


def _weights_bytes(model: Model) -> int | None:
    base = model.resolve()
    if base is None:
        return None
    if base.is_file():
        return base.stat().st_size
    total = 0
    for f in base.rglob("*"):
        if f.is_file() and (f.suffix in (".safetensors", ".gguf") or f.name.endswith(".bin")):
            total += f.stat().st_size if not f.is_symlink() else f.resolve().stat().st_size
    return total


def _kv_bytes_per_token(model: Model) -> int | None:
    base = model.resolve()
    if base is None or base.is_file():
        return None  # GGUF: no model config next to the file, KV is not estimated
    cfg_path = base / "config.json"
    if not cfg_path.exists():
        return None
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    t = cfg.get("text_config", cfg)
    layers = t.get("num_hidden_layers")
    kv_heads = t.get("num_key_value_heads") or t.get("num_attention_heads")
    head_dim = t.get("head_dim") or (t.get("hidden_size", 0) // max(1, t.get("num_attention_heads", 1)))
    if not (layers and kv_heads and head_dim):
        return None
    layer_types = t.get("layer_types")
    if layer_types:
        full = sum(1 for x in layer_types if x == "full_attention")
    elif t.get("full_attention_interval"):
        full = layers // int(t["full_attention_interval"])
    else:
        full = layers
    return full * 2 * kv_heads * head_dim * FP16


BUDGET_SHARE = 0.75  # plan to use at most this share of the Mac's total memory


def recommend_context(model: Model, choices: list[int], total_gib: float, share: float = BUDGET_SHARE,
                      apc_gib: float = 0.0) -> dict:
    """Largest context from `choices` whose weights + KV cache + overhead + prefix cache fit in `share` of total memory.

    Uses total memory, not the currently free memory, so the advice is about the hardware, not the moment.
    """
    weights = _weights_bytes(model)
    if weights is None:
        return {"ok": False, "message": "Download the model first: its size is needed for the advice."}
    if not choices:
        return {"ok": False, "message": "This engine has no context choices."}
    kv_tok = _kv_bytes_per_token(model)
    budget = total_gib * share
    options = []
    for ctx in sorted(choices, reverse=True):
        kv = (kv_tok * ctx / GIB) if kv_tok else 0.0
        need = weights / GIB + kv + overhead_gib(ctx) + apc_gib
        options.append({"ctx": ctx, "need_gib": round(need, 1), "fits": need <= budget})
    fitting = [o["ctx"] for o in options if o["fits"]]
    best = max(fitting) if fitting else min(choices)
    message = (f"Recommended for this Mac ({total_gib:.0f} GiB): {best // 1024}k context."
               if fitting else
               f"Even the smallest context ({min(choices) // 1024}k) is above the comfortable limit for this Mac "
               f"({budget:.0f} GiB of {total_gib:.0f} GiB). Use a smaller model.")
    return {"ok": True, "ctx": best, "fits": bool(fitting), "budget_gib": round(budget, 1),
            "total_gib": round(total_gib, 1), "options": options, "message": message}


def estimate(model: Model, ctx: int, reclaim_gib: float = 0.0) -> dict:
    """reclaim_gib: memory freed if the current run of this same model is stopped."""
    weights = _weights_bytes(model)
    kv_tok = _kv_bytes_per_token(model)
    vm = _vm()
    available = vm["free_gib"] + vm["inactive_gib"] + reclaim_gib
    result = {
        "weights_gib": round(weights / GIB, 2) if weights else None,
        "kv_gib": None,
        "overhead_gib": round(overhead_gib(ctx), 2),
        "total_gib": None,
        "available_gib": round(available, 2),
        "reclaim_gib": round(reclaim_gib, 2),
        "swap_used_gib": round(vm["swap_used_gib"], 2),
        "verdict": "unknown",
        "message": "",
    }
    if weights is None:
        result["message"] = "model files not found"
        return result
    if kv_tok is None:
        result["total_gib"] = round(weights / GIB + overhead_gib(ctx), 2)
        result["message"] = "KV cache not estimated (no config.json); estimate uses weights only"
        result["verdict"] = "ok" if result["total_gib"] < available * 0.8 else "risk"
        return result
    kv = kv_tok * ctx / GIB
    total = weights / GIB + kv + overhead_gib(ctx)
    result.update({"kv_gib": round(kv, 2), "total_gib": round(total, 2)})
    if total > available:
        result["verdict"] = "risk"
        result["message"] = (f"About {total:.1f} GiB needed, about {available:.1f} GiB free. "
                             "Starting will use swap or fail. Reduce the context length or close other apps.")
    elif total > available * 0.85:
        result["verdict"] = "tight"
        result["message"] = (f"About {total:.1f} GiB needed out of {available:.1f} GiB free. "
                             "Little headroom: close heavy apps.")
    else:
        result["verdict"] = "ok"
        result["message"] = f"About {total:.1f} GiB needed, {available:.1f} GiB free."
    if vm["swap_used_gib"] > 8:
        result["message"] += f" Swap is already in use ({vm['swap_used_gib']:.1f} GB)."
    return result
