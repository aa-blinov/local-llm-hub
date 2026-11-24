"""The running panel re-reads registry edits in place: the same Registry object sees new models."""
import json
import time

from llm_hub.config import load, registry_stamp, reload_into


def _write(path, models):
    path.write_text(json.dumps({
        "port": 8000, "ui_port": 8765,
        "engines": {"mlx": {"label": "MLX", "binary": "/bin/true", "ctx_choices": [], "prefill_choices": []}},
        "models": models, "default": {}, "presets": {},
    }), encoding="utf-8")


def test_edit_becomes_visible_without_restart(tmp_path):
    reg_file = tmp_path / "registry.json"
    user_file = tmp_path / "user_models.json"
    _write(reg_file, {"a": {"label": "A", "engine": "mlx", "repo": "org/a"}})
    reg = load(reg_file, user_file)
    before = registry_stamp(reg_file, user_file)
    assert set(reg.models) == {"a"}

    time.sleep(0.01)
    _write(reg_file, {"a": {"label": "A", "engine": "mlx", "repo": "org/a"},
                      "b": {"label": "B", "engine": "mlx", "repo": "org/b"}})
    assert registry_stamp(reg_file, user_file) != before

    reload_into(reg, reg_file, user_file)
    assert set(reg.models) == {"a", "b"}
    assert reg.models["b"].repo == "org/b"
