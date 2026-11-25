"""KV cache compression: the memory estimate shrinks, and the engine gets the flag only when it is set."""
from types import SimpleNamespace

import pytest

from llm_hub import preflight
from llm_hub.engines import MLXAdapter

GIB = 2 ** 30


@pytest.fixture
def ornith_like(monkeypatch):
    monkeypatch.setattr(preflight, "_weights_bytes", lambda m: 18 * GIB)
    monkeypatch.setattr(preflight, "_kv_bytes_per_token", lambda m: 20 * 1024)
    return SimpleNamespace(key="ornith-4bit")


def test_scale_is_one_without_compression_and_shrinks_with_bits():
    assert preflight.kv_scale(None) == 1.0
    assert preflight.kv_scale(0) == 1.0
    assert preflight.kv_scale(8) < 0.6   # 8 bits plus scale and bias
    assert preflight.kv_scale(4) < preflight.kv_scale(8)


def test_compression_lowers_the_need_at_long_context(ornith_like):
    full = preflight.context_need_gib(ornith_like, 262144)
    eight = preflight.context_need_gib(ornith_like, 262144, kv_bits=8)
    four = preflight.context_need_gib(ornith_like, 262144, kv_bits=4)
    assert four < eight < full
    kv_full = 20 * 1024 * 262144 / GIB
    assert full - eight == pytest.approx(kv_full * (1 - preflight.kv_scale(8)), rel=1e-6)


def test_estimate_reports_the_compressed_kv_cache(ornith_like):
    plain = preflight.estimate(ornith_like, 262144)
    packed = preflight.estimate(ornith_like, 262144, kv_bits=8)
    assert packed["kv_gib"] < plain["kv_gib"]
    assert packed["total_gib"] < plain["total_gib"]


def test_engine_gets_the_flag_only_when_set():
    engine = SimpleNamespace(binary="mlx_vlm.server")
    adapter = MLXAdapter(engine, 8000)
    model = SimpleNamespace(resolve=lambda: "/models/ornith")
    argv, _ = adapter.build_command(model, {"ctx": 131072})
    assert "--kv-bits" not in argv
    argv, _ = adapter.build_command(model, {"ctx": 131072, "kv_bits": 8})
    assert argv[argv.index("--kv-bits") + 1] == "8"
    argv, _ = adapter.build_command(model, {"ctx": 131072, "kv_bits": 4})
    assert argv[argv.index("--kv-bits") + 1] == "4"
