"""Static checks of the interface: the built panel exists and no emoji are used."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "llm_hub" / "static"
SRC = ROOT / "frontend" / "src"
EMOJI = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27bf]")


def test_built_panel_exists():
    assert (STATIC / "app" / "index.html").exists()
    assert (STATIC / "app" / "assets").exists()


def test_frontend_sources_exist():
    assert (SRC / "App.svelte").exists()
    assert (SRC / "api.js").exists()


def test_no_emoji_in_interface():
    for path in sorted(SRC.rglob("*.svelte")) + sorted(SRC.rglob("*.js")):
        text = path.read_text(encoding="utf-8")
        assert not EMOJI.search(text), f"emoji found in {path}"
