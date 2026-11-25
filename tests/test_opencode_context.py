"""The opencode sync writes the context the user picked, not a stale default."""
import json

from llm_hub import opencode
from llm_hub.config import load


class FakeSupervisor:
    def __init__(self, running: bool, ctx: int | None):
        self._running = running
        self.opts = {"ctx": ctx} if ctx is not None else {}

    def status(self):
        return {"running": self._running}


def _sync(monkeypatch, tmp_path, sup, requested=None):
    target = tmp_path / "opencode.jsonc"
    monkeypatch.setattr(opencode, "OPENCODE_CONFIG", target)
    # Model files are not present in CI; give every registry entry a fixed id so the entries are written.
    monkeypatch.setattr(opencode, "_model_id", lambda reg, key: f"test/{key}")
    result = opencode.sync_config(load(), sup, requested)
    written = json.loads(target.read_text(encoding="utf-8"))
    return result, written


def test_requested_context_is_written(monkeypatch, tmp_path):
    result, written = _sync(monkeypatch, tmp_path, FakeSupervisor(False, None), requested=262144)
    assert result["context"] == 262144
    models = written["provider"]["local-hub"]["models"]
    assert len(models) == len(load().models) > 0
    assert all(m["limit"]["context"] == 262144 for m in models.values())


def test_running_context_used_when_nothing_requested(monkeypatch, tmp_path):
    result, _ = _sync(monkeypatch, tmp_path, FakeSupervisor(True, 131072))
    assert result["context"] == 131072
    assert result["note"] is None


def test_mismatch_with_running_model_is_reported(monkeypatch, tmp_path):
    result, _ = _sync(monkeypatch, tmp_path, FakeSupervisor(True, 131072), requested=262144)
    assert result["context"] == 262144
    assert "131,072" in result["note"] and "262,144" in result["note"]


def test_default_used_when_nothing_running_or_requested(monkeypatch, tmp_path):
    reg = load()
    result, _ = _sync(monkeypatch, tmp_path, FakeSupervisor(False, None))
    assert result["context"] == int(reg.default.get("ctx", 131072))


def test_output_budget_allows_whole_files(monkeypatch, tmp_path):
    _, written = _sync(monkeypatch, tmp_path, FakeSupervisor(False, None), requested=131072)
    models = written["provider"]["local-hub"]["models"]
    assert all(m["limit"]["output"] >= 32768 for m in models.values())
