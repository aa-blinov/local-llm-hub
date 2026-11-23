"""Models the user adds by Hugging Face repository name.

The repository is checked through the Hugging Face API: it must exist, contain
MLX (.safetensors) or GGUF files, and be reachable with the saved token if gated.
"""
import json
import re
import urllib.error
import urllib.request

from .config import USER_MODELS_PATH, Model, load_user_models, save_user_models
from .settings import hf_token

REPO_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*$")
PREFIX = "user-"


class ModelAddError(Exception):
    """A message the interface can show to the user as it is."""


def inspect_repo(repo: str) -> tuple[str, float]:
    """Return (engine, size in GiB) for a Hugging Face repository, or raise ModelAddError."""
    req = urllib.request.Request(f"https://huggingface.co/api/models/{repo}?blobs=true")
    token = hf_token()
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise ModelAddError("There is no model with this name on Hugging Face. Check the spelling.")
        if e.code in (401, 403):
            raise ModelAddError("This model is gated. Accept its terms on its Hugging Face page, "
                                "then add a token in Settings.")
        raise ModelAddError(f"Hugging Face answered with an error ({e.code}). Try again later.")
    except OSError:
        raise ModelAddError("Could not reach Hugging Face. Check the internet connection.")
    siblings = data.get("siblings", [])
    names = [f.get("rfilename", "") for f in siblings]
    size_gib = sum((f.get("size") or 0) for f in siblings) / 2 ** 30
    if any(n.endswith(".safetensors") for n in names) and "config.json" in names:
        return "mlx", size_gib
    if any(n.endswith(".gguf") for n in names):
        return "llamacpp", size_gib
    raise ModelAddError("This repository has no MLX (.safetensors) or GGUF files, so this app cannot run it.")


def add_user_model(reg, repo: str, path=USER_MODELS_PATH, inspect=inspect_repo) -> dict:
    repo = (repo or "").strip()
    if not REPO_RE.match(repo):
        raise ModelAddError("Enter the repository name as owner/model-name, "
                            "for example mlx-community/Qwen3.6-27B-4bit.")
    key = PREFIX + repo.lower().replace("/", "--")
    items = load_user_models(path)
    if any(i.get("key") == key for i in items):
        raise ModelAddError("This model is already in the list.")
    engine, size_gib = inspect(repo)
    if engine not in reg.engines:
        raise ModelAddError(f"The {engine} engine is not available in this installation.")
    label = repo.split("/", 1)[1]
    notes = f"Added from Hugging Face. About {size_gib:.1f} GiB. Engine: {reg.engines[engine].label}."
    items.append({"key": key, "label": label, "engine": engine, "repo": repo, "notes": notes})
    save_user_models(items, path)
    reg.base_models[key] = Model(key, label, engine, repo, None, None, notes)
    reg.refresh_discovered()
    return {"ok": True, "key": key, "label": label, "engine": engine, "size_gib": round(size_gib, 1)}


def remove_user_model(reg, key: str, path=USER_MODELS_PATH) -> dict:
    items = load_user_models(path)
    kept = [i for i in items if i.get("key") != key]
    if len(kept) == len(items):
        raise ModelAddError("This model was not added by you, so it cannot be removed here.")
    save_user_models(kept, path)
    reg.base_models.pop(key, None)
    reg.refresh_discovered()
    return {"ok": True}
