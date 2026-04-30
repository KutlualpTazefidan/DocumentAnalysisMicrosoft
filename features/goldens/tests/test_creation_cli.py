"""CLI test: `query-eval synthesise --doc X --dry-run` returns 0 and
invokes cmd_synthesise. We import `main` from query_index_eval.cli
and call it with argv directly.

Spec: docs/superpowers/specs/2026-04-29-a5-synthetic-design.md §4.7, §9.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


def test_synthesise_subparser_wires_correctly_in_dry_run(monkeypatch, tmp_path: Path):
    """`query-eval synthesise --doc X --dry-run` returns 0; the
    cmd_synthesise handler is invoked. We monkeypatch cmd_synthesise
    to record the call without making real LLM requests."""
    from goldens.creation import synthetic as syn_mod
    from query_index_eval import cli as eval_cli

    captured: dict = {}

    def fake_cmd_synthesise(args) -> int:
        captured["doc"] = args.doc
        captured["dry_run"] = args.dry_run
        return 0

    # The CLI imports cmd_synthesise from goldens.creation.synthetic;
    # patch both module slots so whichever is the live binding wins.
    monkeypatch.setattr(syn_mod, "cmd_synthesise", fake_cmd_synthesise, raising=True)
    monkeypatch.setattr(eval_cli, "cmd_synthesise", fake_cmd_synthesise, raising=True)

    rc = eval_cli.main(["synthesise", "--doc", "docX", "--dry-run"])
    assert rc == 0
    assert captured["doc"] == "docX"
    assert captured["dry_run"] is True


def test_dry_run_does_not_require_llm_api_key(monkeypatch, tmp_path: Path, capsys):
    """Spec §4.5: dry_run issues no LLM calls (neither completion nor
    embedding). Therefore cmd_synthesise must not hard-fail when
    LLM_API_KEY is unset under --dry-run.

    We stub the loader + synthesise() so the test stays offline.
    """
    from goldens.creation import elements as elements_mod
    from goldens.creation import synthetic as syn_mod
    from query_index_eval import cli as eval_cli

    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("LLM_EMBEDDING_MODEL", raising=False)

    class _StubLoader:
        def __init__(self, slug: str) -> None:
            self.slug = slug

        def elements(self):
            return iter(())

    monkeypatch.setattr(elements_mod, "AnalyzeJsonLoader", _StubLoader, raising=True)

    captured: dict = {}

    def fake_synthesise(**kwargs) -> syn_mod.SynthesiseResult:
        captured["client"] = kwargs.get("client")
        captured["embed_client"] = kwargs.get("embed_client")
        captured["dry_run"] = kwargs.get("dry_run")
        return syn_mod.SynthesiseResult(
            slug=kwargs["slug"],
            events_path=tmp_path / "events.jsonl",
            elements_seen=0,
            elements_skipped=0,
            elements_with_questions=0,
            questions_generated=0,
            questions_kept=0,
            questions_dropped_dedup=0,
            questions_dropped_cap=0,
            events_written=0,
            prompt_tokens_estimated=0,
            dry_run=True,
        )

    monkeypatch.setattr(syn_mod, "synthesise", fake_synthesise, raising=True)

    rc = eval_cli.main(
        [
            "synthesise",
            "--doc",
            "smoke-doc",
            "--dry-run",
            "--llm-model",
            "gpt-4o-mini",
        ]
    )
    assert rc == 0
    assert captured["dry_run"] is True
    assert captured["client"] is None
    assert captured["embed_client"] is None
    out = capsys.readouterr().out
    assert "ERROR: LLM_API_KEY" not in out
