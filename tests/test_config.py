"""Реестр, поиск моделей и понятные ошибки. Без сети, без моделей, без macOS-команд."""
import json

from llm_hub import config
from llm_hub.localscan import matches_repo, scan


def _registry(tmp_path, models=None, dirs=None):
    data = {
        "port": 8000,
        "ui_port": 8765,
        "autostart": False,
        "default": {"model": "demo", "ctx": 32768},
        "engines": {
            "mlx": {"label": "MLX", "binary": str(tmp_path / "mlx_vlm.server"),
                    "ctx_choices": [32768], "prefill_choices": [512]},
        },
        "models": models or {},
        "model_dirs": dirs or [],
    }
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_registry_loads_and_missing_model_is_not_existing(tmp_path):
    path = _registry(tmp_path, models={
        "demo": {"label": "Demo", "engine": "mlx", "path": str(tmp_path / "nowhere")},
    })
    reg = config.load(path)
    assert reg.port == 8000
    assert reg.models["demo"].exists is False


def test_unknown_engine_is_rejected(tmp_path):
    import pytest

    path = _registry(tmp_path, models={"bad": {"label": "Bad", "engine": "nope", "path": "/x"}})
    with pytest.raises(ValueError):
        config.load(path)


def test_scan_finds_mlx_and_gguf_models(tmp_path):
    mlx = tmp_path / "models" / "Demo-MLX"
    mlx.mkdir(parents=True)
    (mlx / "config.json").write_text("{}", encoding="utf-8")
    (mlx / "model.safetensors").write_bytes(b"")
    gguf = tmp_path / "models" / "gguf"
    gguf.mkdir()
    (gguf / "Demo-Q4.gguf").write_bytes(b"")
    (gguf / "mmproj-Demo.gguf").write_bytes(b"")

    found = scan([str(tmp_path / "models")])
    engines = sorted(f["engine"] for f in found)
    assert engines == ["llamacpp", "mlx"]
    gguf_item = next(f for f in found if f["engine"] == "llamacpp")
    assert gguf_item["mmproj"] is not None  # vision-проектор рядом находится


def test_matches_repo_both_layouts():
    assert matches_repo("/x/models--ornith-ai--Demo/snapshots/abc", "ornith-ai/Demo")
    assert matches_repo("/x/lmstudio-community/Inkling-GGUF/model.gguf", "lmstudio-community/Inkling-GGUF")
    assert not matches_repo("/x/other/model", "ornith-ai/Demo")


def test_settings_store_token_with_private_permissions(tmp_path, monkeypatch):
    from llm_hub import settings

    monkeypatch.setattr(settings, "SETTINGS_PATH", tmp_path / "settings.json")
    saved = settings.save({"hf_token": "hf_test", "start_view": "nonsense", "swap_warn_gb": 9})
    assert saved["start_view"] == "simple"  # неизвестный раздел заменяется на безопасный
    assert settings.hf_token() == "hf_test"
    assert (tmp_path / "settings.json").stat().st_mode & 0o777 == 0o600


def test_autostart_is_not_stored_in_settings(tmp_path, monkeypatch):
    from llm_hub import settings

    monkeypatch.setattr(settings, "SETTINGS_PATH", tmp_path / "settings.json")
    saved = settings.save({"autostart": True})
    assert "autostart" in saved and saved["autostart"] is False  # источник правды — файл агента launchd


def test_gated_model_error_is_explained(monkeypatch):
    from llm_hub import settings
    from llm_hub.downloads import friendly_download_error

    class GatedRepoError(Exception):
        pass

    monkeypatch.setattr(settings, "hf_token", lambda: None)
    text = friendly_download_error(GatedRepoError("401"), "owner/name")
    assert "закрытая" in text and "токен" in text
