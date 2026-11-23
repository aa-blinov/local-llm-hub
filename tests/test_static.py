"""Статические проверки интерфейса: файлы на месте, в интерфейсе нет эмодзи."""
import re
from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "src" / "llm_hub" / "static"
EMOJI = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27bf]")


def test_interface_files_exist():
    assert (STATIC / "index.html").exists()
    assert (STATIC / "app.js").exists()


def test_no_emoji_in_interface():
    for name in ("index.html", "app.js"):
        text = (STATIC / name).read_text(encoding="utf-8")
        assert not EMOJI.search(text), f"эмодзи в {name}"
