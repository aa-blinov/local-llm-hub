"""Recommendation: fit in memory first, then the best rank for the purpose. Pure logic, no hardware needed."""
from llm_hub.recommend import recommend

CANDIDATES = [
    {"key": "big", "label": "Big", "size_gib": 19.0, "rank": {"agent": 2}, "speed": ""},
    {"key": "main", "label": "Main", "size_gib": 18.2, "rank": {"agent": 1, "chat": 1}, "speed": "Measured."},
    {"key": "small", "label": "Small", "size_gib": 4.7, "rank": {"quick": 1}, "speed": ""},
]


def test_best_rank_that_fits_is_chosen():
    out = recommend(CANDIDATES, "agent", 48.0)
    assert out["ok"] and out["key"] == "main"
    assert "about 30 GiB to spare" in out["reason"] and "Measured." in out["reason"]


def test_model_too_big_for_memory_is_skipped():
    out = recommend(CANDIDATES, "agent", 24.0)  # usable 18 GiB: nothing with headroom fits
    assert not out["ok"] and "fits" in out["message"]


def test_small_model_still_fits_small_memory():
    assert recommend(CANDIDATES, "quick", 16.0)["key"] == "small"


def test_unknown_memory_still_recommends_without_fit_claim():
    out = recommend(CANDIDATES, "agent", None)
    assert out["ok"] and out["key"] == "main" and "could not be read" in out["reason"]


def test_unknown_purpose_is_refused():
    assert not recommend(CANDIDATES, "poetry", 48.0)["ok"]
