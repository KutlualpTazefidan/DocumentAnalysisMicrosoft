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
