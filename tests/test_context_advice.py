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
    out = preflight.recommend_context(ornith_like, CHOICES, total_gib=32, apc_gib=2.0)
    assert out["ctx"] == 65536 and out["fits"]  # 128k needs more than the 24 GiB budget with a 2 GB cache


def test_overhead_grows_with_context():
    assert preflight.overhead_gib(8192) < preflight.overhead_gib(32768) < preflight.overhead_gib(65536)
    assert round(preflight.overhead_gib(65536), 2) == 1.6


def test_prefix_cache_counts_against_the_budget(ornith_like):
    # With a 6 GB prefix cache a 32 GB Mac no longer fits 128k, so the advice must step down.
    out = preflight.recommend_context(ornith_like, CHOICES, total_gib=32, apc_gib=6.0)
    assert out["fits"] is False  # nothing fits with a 6 GB cache on 32 GB: 128k is no longer offered


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


MEASURED = {"overhead_gib": {"8192": 0.72, "32768": 1.11, "65536": 1.63, "131072": 1.71}}


def test_measured_points_are_used_and_interpolated():
    m = SimpleNamespace(memory=MEASURED)
    assert preflight.overhead_for(m, 8192) == 0.72
    assert preflight.overhead_for(m, 131072) == 1.71
    mid = preflight.overhead_for(m, 49152)  # between 32k and 64k
    assert 1.11 < mid < 1.63


def test_beyond_measured_range_is_conservative():
    m = SimpleNamespace(memory=MEASURED)
    assert preflight.overhead_for(m, 262144) >= 1.71 + 1.0


def test_model_without_measurements_uses_generic_rule():
    m = SimpleNamespace(memory=None)
    assert preflight.overhead_for(m, 65536) == preflight.overhead_gib(65536)
