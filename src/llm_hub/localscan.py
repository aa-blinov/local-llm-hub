"""Find models in user-specified folders (external drive, LM Studio, a custom directory).

We look for two kinds of model:
  - MLX model: a folder with config.json and *.safetensors files;
  - GGUF model: a *.gguf file (except mmproj*); an mmproj file next to it is used for vision.
Folders are walked no deeper than MAX_DEPTH; hidden directories and .venv are skipped.
"""
import hashlib
import os
from pathlib import Path

MAX_DEPTH = 6


def _key(path: Path) -> str:
    return "local-" + hashlib.sha1(str(path).encode()).hexdigest()[:8]


def scan(dirs: list[str]) -> list[dict]:
    found: list[dict] = []
    seen: set[str] = set()
    for raw in dirs:
        root = Path(os.path.expanduser(raw))
        if not root.is_dir():
            continue
        base_depth = len(root.parts)
        for dirpath, dirnames, filenames in os.walk(root):
            p = Path(dirpath)
            depth = len(p.parts) - base_depth
            # skip hidden directories and virtual environments
            dirnames[:] = [d for d in dirnames if not d.startswith(".") and d != ".venv"]
            if depth >= MAX_DEPTH:
                dirnames[:] = []
            names = set(filenames)
            if "config.json" in names and any(n.endswith(".safetensors") for n in names):
                if str(p) not in seen:
                    seen.add(str(p))
                    found.append({"key": _key(p), "engine": "mlx", "path": str(p), "mmproj": None,
                                  "label": f"{p.name} (MLX)", "from": str(root)})
                dirnames[:] = []  # do not search inside a model
                continue
            for n in filenames:
                if n.endswith(".gguf") and not n.lower().startswith("mmproj"):
                    f = p / n
                    if str(f) in seen:
                        continue
                    seen.add(str(f))
                    mm = next((p / x for x in filenames if x.lower().startswith("mmproj") and x.endswith(".gguf")), None)
                    found.append({"key": _key(f), "engine": "llamacpp", "path": str(f),
                                  "mmproj": str(mm) if mm else None,
                                  "label": f"{f.stem} (GGUF)", "from": str(root)})
    return found


def matches_repo(found_path: str, repo: str) -> bool:
    """Whether a found path matches a Hugging Face repository (for example owner/name)."""
    low = found_path.lower().replace("\\", "/")
    r = repo.lower()
    return f"/{r}" in low or f"models--{r.replace('/', '--')}" in low
