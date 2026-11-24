"""Context advice: largest context whose weights + KV cache + overhead fit in the Mac's usable memory."""
from types import SimpleNamespace

import pytest

from llm_hub import preflight

GIB = 2 ** 30
CHOICES = [32768, 65536, 131072, 262144]


@pytest.fixture
def ornith_like(monkeypatch):
    # 18 GiB of weights, 20 KiB of KV cache per token (full-attention layers only)
    monkeypatch.setattr(preflight, "_weights_bytes", lambda m: 18 * GIB)
    monkeypatch.setattr(preflight, "_kv_bytes_per_token", lambda m: 20 * 1024)
    return SimpleNamespace(key="m")


def test_48gb_mac_gets_the_largest_context(ornith_like):
    out = preflight.recommend_context(ornith_like, CHOICES, total_gib=48)
    assert out["ok"] and out["fits"] and out["ctx"] == 262144


def test_32gb_mac_steps_down(ornith_like):
    out = preflight.recommend_context(ornith_like, CHOICES, total_gib=32)
    assert out["ctx"] == 131072 and out["fits"]


def test_too_small_mac_reports_it(ornith_like):
    out = preflight.recommend_context(ornith_like, CHOICES, total_gib=16)
    assert out["ok"] and not out["fits"] and out["ctx"] == 32768
    assert "smaller model" in out["message"]


def test_options_are_listed_from_largest_to_smallest(ornith_like):
    out = preflight.recommend_context(ornith_like, CHOICES, total_gib=48)
    assert [o["ctx"] for o in out["options"]] == sorted(CHOICES, reverse=True)


def test_missing_weights_asks_to_download(monkeypatch):
    monkeypatch.setattr(preflight, "_weights_bytes", lambda m: None)
    out = preflight.recommend_context(SimpleNamespace(), CHOICES, total_gib=48)
    assert out["ok"] is False and "Download" in out["message"]
