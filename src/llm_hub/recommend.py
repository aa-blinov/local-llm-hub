"""Recommend a model that fits this Mac and matches what the user needs it for.

Selection is pure logic over registry data: a model must fit in the memory the
Mac can use (weights plus headroom), then the lowest rank for the purpose wins.
Speed is reported only when it was measured on this Mac.
"""
import subprocess

HEADROOM_GIB = 4.0   # room for the cache and the system beyond the weights
USABLE_SHARE = 0.75  # do not plan to use more than this share of total memory
PURPOSES = {"agent": "agentic coding", "chat": "chat", "quick": "quick answers"}


def memory_gib() -> float | None:
    """Total memory of this Mac in GiB, or None when it cannot be read."""
    try:
        out = subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True, timeout=5).stdout
        return int(out.strip()) / 2 ** 30
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def recommend(candidates: list[dict], purpose: str, ram_gib: float | None) -> dict:
    """candidates: dicts with key, label, size_gib, rank ({purpose: int}), speed."""
    if purpose not in PURPOSES:
        return {"ok": False, "message": "Choose what you need the model for."}
    ranked = sorted((c for c in candidates if purpose in c.get("rank", {})), key=lambda c: c["rank"][purpose])
    if not ranked:
        return {"ok": False, "message": "No model is listed for this purpose yet."}
    if ram_gib is None:
        fits = ranked
    else:
        limit = ram_gib * USABLE_SHARE
        fits = [c for c in ranked if c["size_gib"] + HEADROOM_GIB <= limit]
    if not fits:
        return {"ok": False, "ram_gib": ram_gib,
                "message": f"No model for {PURPOSES[purpose]} fits in the {ram_gib:.0f} GiB of this Mac. "
                           "Close other apps or add a smaller model."}
    best = fits[0]
    if ram_gib is None:
        reason = "Memory of this Mac could not be read, so the fit is not checked."
    else:
        spare = ram_gib - best["size_gib"]
        reason = f"Fits in this Mac's {ram_gib:.0f} GiB with about {spare:.0f} GiB to spare."
    if best.get("speed"):
        reason += " " + best["speed"]
    return {"ok": True, "key": best["key"], "label": best["label"], "reason": reason, "ram_gib": ram_gib}
