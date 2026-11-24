"""Sampling modes: each model resolves its named mode, falls back to its default, and has none if it defines none."""
from types import SimpleNamespace

from llm_hub.config import sampling_params


def _model(sampling):
    return SimpleNamespace(sampling=sampling)


def test_named_mode_returns_its_parameters():
    m = _model({"default": "coding", "modes": {
        "coding": {"label": "C", "temperature": 0.6, "top_p": 0.95, "top_k": 20, "presence_penalty": 0.0},
        "instruct": {"label": "I", "temperature": 0.7, "top_p": 0.8, "top_k": 20, "presence_penalty": 1.5}}})
    assert sampling_params(m, "instruct") == {"temperature": 0.7, "top_p": 0.8, "top_k": 20, "presence_penalty": 1.5}


def test_missing_or_unknown_mode_uses_default():
    m = _model({"default": "coding", "modes": {"coding": {"label": "C", "temperature": 0.6}}})
    assert sampling_params(m) == {"temperature": 0.6}
    assert sampling_params(m, "nope") == {"temperature": 0.6}


def test_label_is_not_sent_as_a_parameter():
    m = _model({"default": "x", "modes": {"x": {"label": "X", "temperature": 1.0, "top_p": 0.95}}})
    assert "label" not in sampling_params(m, "x")


def test_model_without_modes_returns_empty():
    assert sampling_params(_model(None)) == {}
    assert sampling_params(_model({"default": "x", "modes": {}})) == {}
