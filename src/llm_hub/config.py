"""Load the registry of models, engines and presets from config/registry.json.

Models found in user folders (model_dirs) are added on top of the registry.
"""
import json
import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = Path(os.environ.get("LLM_HUB_REGISTRY", ROOT / "config" / "registry.json"))
LOG_DIR = ROOT / "logs"
CACHE_DIR = ROOT / "cache"
APC_DIR = CACHE_DIR / "apc"
HISTORY_PATH = LOG_DIR / "history.jsonl"
OPENCODE_CONFIG = Path.home() / ".config" / "opencode" / "opencode.jsonc"
USER_MODELS_PATH = ROOT / "config" / "user_models.json"  # models added from Hugging Face (not in git)


def _expand(p: str | None) -> Path | None:
    """Expand ~ and resolve ./ against the project folder, so the registry works after cloning anywhere."""
    if not p:
        return None
    if p.startswith("./"):
        return ROOT / p[2:]
    return Path(os.path.expanduser(p))


@dataclass
class Model:
    key: str
    label: str
    engine: str
    repo: str | None           # Hugging Face repository id, used for downloads
    path: Path | None          # explicit path to the files
    mmproj: Path | None
    notes: str
    found: Path | None = None  # path found by scanning model folders
    origin: str = "registry"   # registry | folder
    simple: dict | None = None  # optional block for the Simple view: size, about, recommended
    sampling: dict | None = None  # {'default': mode, 'modes': {mode: {temperature, top_p, top_k, presence_penalty}}}
    memory: dict | None = None  # measured overhead per context length: {'overhead_gib': {ctx: GiB}}

    def resolve(self) -> Path | None:
        """Path to the model files: explicit path, folder scan result, or Hugging Face cache snapshot."""
        if self.path and self.path.exists():
            return self.path
        if self.found and self.found.exists():
            return self.found
        if self.repo:
            from huggingface_hub import snapshot_download
            from .settings import all_hf_roots
            for root in all_hf_roots():
                try:
                    return Path(snapshot_download(self.repo, local_files_only=True, cache_dir=str(root)))
                except Exception:
                    continue
        return None

    @property
    def exists(self) -> bool:
        return self.resolve() is not None

    @property
    def in_hf_cache(self) -> bool:
        from .settings import all_hf_roots
        p = self.resolve()
        return bool(p) and any(str(p).startswith(str(r)) for r in all_hf_roots())


@dataclass
class Engine:
    key: str
    label: str
    binary: Path
    ctx_choices: list[int]
    prefill_choices: list[int]


@dataclass
class Registry:
    port: int
    ui_port: int
    autostart: bool
    default: dict
    presets: dict[str, dict] = field(default_factory=dict)
    engines: dict[str, Engine] = field(default_factory=dict)
    models: dict[str, Model] = field(default_factory=dict)
    base_models: dict[str, Model] = field(default_factory=dict)
    model_dirs: list[str] = field(default_factory=list)

    def refresh_discovered(self) -> int:
        """Recompute models: registry plus models found in folders. Returns the number found."""
        from .localscan import scan, matches_repo
        found = scan(self.model_dirs)
        merged = {k: m for k, m in self.base_models.items()}
        # registry models located in found folders get their path
        for m in merged.values():
            if m.repo and not (m.path and m.path.exists()):
                m.found = None
                for f in found:
                    if m.engine == f["engine"] and matches_repo(f["path"], m.repo):
                        m.found = Path(f["path"])
                        break
        known_paths = {str(m.found) for m in merged.values() if m.found} | \
                      {str(m.path) for m in merged.values() if m.path}
        for f in found:
            if f["path"] in known_paths or f["engine"] not in self.engines:
                continue
            merged[f["key"]] = Model(
                key=f["key"], label=f["label"], engine=f["engine"], repo=None,
                path=Path(f["path"]), mmproj=Path(f["mmproj"]) if f["mmproj"] else None,
                notes=f"Found in folder {f['from']}", origin="folder",
            )
        self.models = merged
        return len(found)


def load_user_models(path: Path = USER_MODELS_PATH) -> list[dict]:
    """Models the user added by repository name. A missing or broken file means an empty list."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return data if isinstance(data, list) else []


def save_user_models(items: list[dict], path: Path = USER_MODELS_PATH) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(items, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


SAMPLING_KEYS = ("temperature", "top_p", "top_k", "presence_penalty", "min_p")


def sampling_params(model, mode: str | None = None) -> dict:
    """Sampling parameters for a model's mode (default mode if none is given). Empty if the model has no modes."""
    cfg = getattr(model, "sampling", None) or {}
    modes = cfg.get("modes") or {}
    if not modes:
        return {}
    key = mode if mode in modes else cfg.get("default")
    if key not in modes:
        return {}
    return {k: v for k, v in modes[key].items() if k in SAMPLING_KEYS}


def registry_stamp(path: Path = REGISTRY_PATH, user_path: Path = USER_MODELS_PATH) -> tuple:
    """Modification times of the registry files; a change means the registry should be reloaded."""
    return tuple(Path(p).stat().st_mtime_ns if Path(p).exists() else 0 for p in (path, user_path))


def reload_into(reg: "Registry", path: Path = REGISTRY_PATH, user_path: Path = USER_MODELS_PATH) -> None:
    """Re-read the registry files into the existing Registry object, so every holder of it sees the change."""
    fresh = load(path, user_path)
    vars(reg).update(vars(fresh))


def load(path: Path = REGISTRY_PATH, user_path: Path = USER_MODELS_PATH) -> Registry:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    engines = {
        k: Engine(k, v["label"], _expand(v["binary"]), v.get("ctx_choices", []), v.get("prefill_choices", []))
        for k, v in data["engines"].items()
    }
    base = {}
    for k, v in data["models"].items():
        if v["engine"] not in engines:
            raise ValueError(f"model {k}: unknown engine {v['engine']}")
        base[k] = Model(k, v["label"], v["engine"], v.get("repo"), _expand(v.get("path")),
                        _expand(v.get("mmproj")), v.get("notes", ""),
                        simple=v.get("simple"), sampling=v.get("sampling"),
                        memory=v.get("memory"))
    for item in load_user_models(user_path):
        if item.get("engine") in engines and item.get("key") and item.get("repo"):
            base[item["key"]] = Model(item["key"], item.get("label", item["key"]), item["engine"],
                                      item["repo"], None, None, item.get("notes", ""))
    reg = Registry(
        port=int(data.get("port", 8000)),
        ui_port=int(data.get("ui_port", 8765)),
        autostart=bool(data.get("autostart", False)),
        default=data.get("default", {}),
        presets=data.get("presets", {}),
        engines=engines,
        base_models=base,
        model_dirs=list(data.get("model_dirs", [])),
    )
    reg.refresh_discovered()
    return reg


def save_model_dirs(dirs: list[str], path: Path = REGISTRY_PATH) -> None:
    """Write the folder list to registry.json, leaving other fields untouched."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    data["model_dirs"] = dirs
    tmp = Path(str(path) + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
