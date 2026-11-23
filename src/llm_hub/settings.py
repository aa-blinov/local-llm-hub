"""Настройки приложения: хранятся в config/settings.json (не попадает в git).

Поля:
  autostart      — запускать панель при входе в систему (отражает установленный launchd-агент)
  start_view     — с какого раздела открывать панель: simple | panel | components
  download_dir   — папка для новых загрузок моделей; пусто = кэш Hugging Face по умолчанию
  hf_token       — токен Hugging Face для закрытых моделей; пусто = не используется
  swap_warn_gb   — при каком объёме свопа показывать предупреждение
"""
import json
import os
from pathlib import Path

from .config import ROOT

SETTINGS_PATH = ROOT / "config" / "settings.json"
DEFAULT_HF_HUB = Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface")) / "hub"
DEFAULTS = {
    "autostart": False,
    "start_view": "simple",
    "download_dir": "",
    "hf_token": "",
    "swap_warn_gb": 12,
}


def load() -> dict:
    data = dict(DEFAULTS)
    if SETTINGS_PATH.exists():
        try:
            data.update(json.loads(SETTINGS_PATH.read_text(encoding="utf-8")))
        except (ValueError, OSError):
            pass
    return data


def save(changes: dict) -> dict:
    data = load()
    for k, v in changes.items():
        if k in DEFAULTS and k != "autostart":  # автозапуск хранится в файле агента launchd, не здесь
            data[k] = v
    data["swap_warn_gb"] = float(data["swap_warn_gb"])
    if data["start_view"] not in ("simple", "panel", "components"):
        data["start_view"] = "simple"
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = SETTINGS_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.chmod(tmp, 0o600)  # в файле может лежать токен
    tmp.replace(SETTINGS_PATH)
    return data


def hf_cache_root() -> Path:
    """Папка, где лежат модели Hugging Face: своя (если задана) или кэш по умолчанию."""
    d = load().get("download_dir", "")
    return Path(os.path.expanduser(d)) if d else DEFAULT_HF_HUB


def all_hf_roots() -> list[Path]:
    """Все папки, где ищем модели: выбранная пользователем и стандартный кэш (без повторов)."""
    roots = [hf_cache_root()]
    if DEFAULT_HF_HUB not in roots:
        roots.append(DEFAULT_HF_HUB)
    return roots


def hf_token() -> str | None:
    t = load().get("hf_token", "")
    return t or None
