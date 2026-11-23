"""Загрузка реестра моделей, движков и пресетов из config/registry.json.

Модели из папок, которые указал пользователь (model_dirs), добавляются поверх реестра.
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


def _expand(p: str | None) -> Path | None:
    return Path(os.path.expanduser(p)) if p else None


@dataclass
class Model:
    key: str
    label: str
    engine: str
    repo: str | None           # идентификатор на Hugging Face, для скачивания
    path: Path | None          # явный путь к файлам
    mmproj: Path | None
    notes: str
    found: Path | None = None  # путь, найденный сканированием папок моделей
    origin: str = "registry"   # registry | folder

    def resolve(self) -> Path | None:
        """Путь к файлам: явный путь, найденный в папках, либо снимок из кэша Hugging Face."""
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
        """Пересчитывает модели: реестр + найденные в папках. Возвращает число найденных."""
        from .localscan import scan, matches_repo
        found = scan(self.model_dirs)
        merged = {k: m for k, m in self.base_models.items()}
        # модели из реестра, которые лежат в найденных папках, получают путь
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
                notes=f"Найдено в папке {f['from']}", origin="folder",
            )
        self.models = merged
        return len(found)


def load(path: Path = REGISTRY_PATH) -> Registry:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    engines = {
        k: Engine(k, v["label"], _expand(v["binary"]), v.get("ctx_choices", []), v.get("prefill_choices", []))
        for k, v in data["engines"].items()
    }
    base = {}
    for k, v in data["models"].items():
        if v["engine"] not in engines:
            raise ValueError(f"модель {k}: неизвестный движок {v['engine']}")
        base[k] = Model(k, v["label"], v["engine"], v.get("repo"), _expand(v.get("path")),
                        _expand(v.get("mmproj")), v.get("notes", ""))
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
    """Записывает список папок в registry.json, не трогая остальные поля."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    data["model_dirs"] = dirs
    tmp = Path(str(path) + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
