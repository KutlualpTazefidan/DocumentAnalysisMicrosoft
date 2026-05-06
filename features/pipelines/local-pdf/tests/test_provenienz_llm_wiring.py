"""Unit tests for the four _llm_* helpers in the provenienz router.

These verify the parser logic and prompt-call shape — no real LLM hits.
The fakes return canned strings, exercising:
- successful JSON parse (with and without ```json fences)
- empty / malformed responses → RuntimeError
- whitespace and quote trimming for the string-returning helpers
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from local_pdf.api.routers.admin import provenienz as router_mod


class _FakeClient:
    def __init__(self, response_text: str):
        self._text = response_text
        self.last_messages = None
        self.last_model = None

    def complete(self, *, messages, model):
        self.last_messages = messages
        self.last_model = model
        return SimpleNamespace(text=self._text)


def _patch(monkeypatch, response_text: str) -> _FakeClient:
    fake = _FakeClient(response_text)
    monkeypatch.setattr(router_mod, "get_llm_client", lambda: fake)
    monkeypatch.setattr(router_mod, "get_default_model", lambda: "test-model")
    return fake


def test_extract_claims_parses_json_array(monkeypatch):
    fake = _patch(monkeypatch, '["Aussage A", "Aussage B"]')
    out = router_mod._llm_extract_claims("Some chunk", "vllm")
    assert out == ["Aussage A", "Aussage B"]
    assert fake.last_model == "test-model"
    assert any("Textabschnitt" in m.content for m in fake.last_messages)


def test_extract_claims_strips_json_fence(monkeypatch):
    _patch(monkeypatch, '```json\n["A", "B"]\n```')
    assert router_mod._llm_extract_claims("x", "vllm") == ["A", "B"]


def test_extract_claims_rejects_garbage(monkeypatch):
    _patch(monkeypatch, "this is not JSON at all")
    with pytest.raises(RuntimeError, match="could not parse"):
        router_mod._llm_extract_claims("x", "vllm")


def test_formulate_task_strips_quotes_and_whitespace(monkeypatch):
    _patch(monkeypatch, '  "Wärmeleistung Kessel 5 kW"  ')
    assert router_mod._llm_formulate_task("Kessel hat 5 kW.", "vllm") == "Wärmeleistung Kessel 5 kW"


def test_formulate_task_empty_raises(monkeypatch):
    _patch(monkeypatch, "   ")
    with pytest.raises(RuntimeError):
        router_mod._llm_formulate_task("x", "vllm")


def test_evaluate_parses_full_dict(monkeypatch):
    _patch(
        monkeypatch,
        '{"verdict":"likely-source","confidence":0.82,"reasoning":"Tabelle Spalte 3."}',
    )
    out = router_mod._llm_evaluate("claim", "candidate", "vllm")
    assert out["verdict"] == "likely-source"
    assert out["confidence"] == 0.82
    assert out["reasoning"] == "Tabelle Spalte 3."


def test_evaluate_passes_through_unknown_verdict(monkeypatch):
    """Unknown verdicts are accepted as-is — frontend's badge styling
    falls back to a neutral chip color. The strict 4-set is a
    convention, not a hard contract."""
    _patch(monkeypatch, '{"verdict":"banana","confidence":0.5,"reasoning":"r"}')
    out = router_mod._llm_evaluate("c", "k", "vllm")
    assert out["verdict"] == "banana"
    assert out["confidence"] == 0.5


def test_evaluate_accepts_positional_array_form(monkeypatch):
    """Qwen et al. occasionally emit ``[verdict, confidence, reasoning]``
    as a JSON array instead of an object. Coerce."""
    _patch(monkeypatch, '["partial-support",0.6,"Verweis auf Abbildung 3."]')
    out = router_mod._llm_evaluate("c", "k", "vllm")
    assert out["verdict"] == "partial-support"
    assert out["confidence"] == 0.6
    assert "Abbildung 3" in out["reasoning"]


def test_evaluate_degrades_gracefully_on_unparseable(monkeypatch):
    """When the response can't be parsed at all, we still return a
    dict so the downstream evaluation node spawns. Verdict is
    'unknown' and reasoning carries the raw output for inspection."""
    _patch(monkeypatch, "this is not JSON at all, sorry")
    out = router_mod._llm_evaluate("c", "k", "vllm")
    assert out["verdict"] == "unknown"
    assert out["confidence"] == 0.0
    assert "this is not JSON" in out["reasoning"]


def test_propose_stop_returns_trimmed_sentence(monkeypatch):
    _patch(monkeypatch, "  Quelle in Tabelle 4 bestätigt.  ")
    assert router_mod._llm_propose_stop("anchor", "vllm") == "Quelle in Tabelle 4 bestätigt."


def test_extra_system_default_does_not_alter_system_prompt(monkeypatch):
    """Calling the helpers without extra_system keeps the existing system
    prompt untouched — i.e. the new keyword-only arg has a true no-op default.
    """
    fake = _patch(monkeypatch, '["A"]')
    router_mod._llm_extract_claims("chunk", "vllm")
    sys_msg = next(m for m in fake.last_messages if m.role == "system").content
    assert "Frühere Korrekturen" not in sys_msg


def test_extra_system_appends_block_to_system_prompt(monkeypatch):
    fake = _patch(monkeypatch, '["A"]')
    router_mod._llm_extract_claims("chunk", "vllm", extra_system="\n\nZUSATZ: bitte beachten.")
    sys_msg = next(m for m in fake.last_messages if m.role == "system").content
    assert sys_msg.endswith("ZUSATZ: bitte beachten.")
