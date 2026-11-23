"""Поиск моделей в папках, которые указал пользователь (внешний диск, LM Studio, свой каталог).

Ищем две вещи:
  • MLX-модель: папка с config.json и файлами *.safetensors;
  • GGUF-модель: файл *.gguf (кроме mmproj*), рядом возможен mmproj-файл для vision.
Папки обходим не глубже MAX_DEPTH и пропускаем скрытые каталоги и .venv.
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
            # пропускаем скрытые каталоги и окружения
            dirnames[:] = [d for d in dirnames if not d.startswith(".") and d != ".venv"]
            if depth >= MAX_DEPTH:
                dirnames[:] = []
            names = set(filenames)
            if "config.json" in names and any(n.endswith(".safetensors") for n in names):
                if str(p) not in seen:
                    seen.add(str(p))
                    found.append({"key": _key(p), "engine": "mlx", "path": str(p), "mmproj": None,
                                  "label": f"{p.name} (MLX)", "from": str(root)})
                dirnames[:] = []  # внутри модели дальше не ищем
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
    """Совпадает ли найденная папка с репозиторием Hugging Face (например, owner/name)."""
    low = found_path.lower().replace("\\", "/")
    r = repo.lower()
    return f"/{r}" in low or f"models--{r.replace('/', '--')}" in low
