"""Models added by repository name: validation, storage, reload, and removal. No network: inspection is replaced."""
import json

import pytest

from llm_hub.config import load
from llm_hub.usermodels import ModelAddError, add_user_model, remove_user_model


def _registry(tmp_path):
    reg_file = tmp_path / "registry.json"
    reg_file.write_text(json.dumps({
        "port": 8000, "ui_port": 8765,
        "engines": {"mlx": {"label": "MLX", "binary": "/bin/true", "ctx_choices": [], "prefill_choices": []}},
        "models": {}, "default": {}, "presets": {},
    }), encoding="utf-8")
    return reg_file, tmp_path / "user_models.json"


def _fake_mlx(repo):
    return "mlx", 2.5


def test_rejects_malformed_repository_name(tmp_path):
    reg_file, user_file = _registry(tmp_path)
    reg = load(reg_file, user_file)
    with pytest.raises(ModelAddError, match="owner/model-name"):
        add_user_model(reg, "not a repo", path=user_file, inspect=_fake_mlx)


def test_add_persists_and_survives_reload(tmp_path):
    reg_file, user_file = _registry(tmp_path)
    reg = load(reg_file, user_file)
    out = add_user_model(reg, "org/Demo-4bit", path=user_file, inspect=_fake_mlx)
    assert out == {"ok": True, "key": "user-org--demo-4bit", "label": "Demo-4bit", "engine": "mlx", "size_gib": 2.5}
    assert reg.models["user-org--demo-4bit"].repo == "org/Demo-4bit"
    again = load(reg_file, user_file)
    assert again.models["user-org--demo-4bit"].engine == "mlx"


def test_duplicate_is_rejected(tmp_path):
    reg_file, user_file = _registry(tmp_path)
    reg = load(reg_file, user_file)
    add_user_model(reg, "org/Demo", path=user_file, inspect=_fake_mlx)
    with pytest.raises(ModelAddError, match="already"):
        add_user_model(reg, "org/demo", path=user_file, inspect=_fake_mlx)


def test_unknown_engine_is_rejected(tmp_path):
    reg_file, user_file = _registry(tmp_path)
    reg = load(reg_file, user_file)
    with pytest.raises(ModelAddError, match="not available"):
        add_user_model(reg, "org/Demo", path=user_file, inspect=lambda r: ("llamacpp", 1.0))


def test_remove_only_touches_user_models(tmp_path):
    reg_file, user_file = _registry(tmp_path)
    reg = load(reg_file, user_file)
    add_user_model(reg, "org/Demo", path=user_file, inspect=_fake_mlx)
    remove_user_model(reg, "user-org--demo", path=user_file)
    assert "user-org--demo" not in reg.models
    with pytest.raises(ModelAddError, match="not added by you"):
        remove_user_model(reg, "ornith-4bit", path=user_file)
