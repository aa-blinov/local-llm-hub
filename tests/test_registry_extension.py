"""Registry: the Simple-view block is read per model, and ./ paths resolve against the project folder."""
import json

from llm_hub.config import ROOT, load


def test_simple_block_and_relative_engine_path(tmp_path):
    reg_file = tmp_path / "registry.json"
    reg_file.write_text(json.dumps({
        "port": 8000,
        "ui_port": 8765,
        "engines": {"mlx": {"label": "MLX", "binary": "./.venv/bin/mlx_vlm.server",
                            "ctx_choices": [], "prefill_choices": []}},
        "models": {"demo": {"label": "Demo", "engine": "mlx", "repo": "org/demo",
                            "simple": {"size": "1 GiB", "about": "A demo model."}}},
        "default": {},
        "presets": {},
    }), encoding="utf-8")
    reg = load(reg_file)
    assert reg.models["demo"].simple == {"size": "1 GiB", "about": "A demo model."}
    assert reg.engines["mlx"].binary == ROOT / ".venv" / "bin" / "mlx_vlm.server"


def test_model_without_simple_block_is_not_shown_in_simple(tmp_path):
    reg_file = tmp_path / "registry.json"
    reg_file.write_text(json.dumps({
        "port": 8000, "ui_port": 8765,
        "engines": {"mlx": {"label": "MLX", "binary": "/bin/true", "ctx_choices": [], "prefill_choices": []}},
        "models": {"plain": {"label": "Plain", "engine": "mlx", "repo": "org/plain"}},
        "default": {}, "presets": {},
    }), encoding="utf-8")
    assert load(reg_file).models["plain"].simple is None
