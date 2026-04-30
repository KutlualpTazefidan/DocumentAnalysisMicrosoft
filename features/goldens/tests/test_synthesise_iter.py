"""Generator semantics for the streaming variant of synthesise()."""

from __future__ import annotations

from pathlib import Path


def test_synthesise_iter_yields_per_element_in_dry_run(tmp_path: Path) -> None:
    """In dry-run mode, the generator yields a (DocumentElement, ElementResult)
    pair for every element seen — both kept and skipped — and never makes
    LLM calls."""
    import shutil

    from goldens.creation.elements.analyze_json import AnalyzeJsonLoader
    from goldens.creation.synthetic import synthesise_iter

    fixtures = Path(__file__).parent / "fixtures"
    analyze = tmp_path / "doc-a" / "analyze"
    analyze.mkdir(parents=True)
    shutil.copy(fixtures / "analyze_minimal.json", analyze / "ts.json")

    loader = AnalyzeJsonLoader("doc-a", outputs_root=tmp_path)

    yielded = list(
        synthesise_iter(
            slug="doc-a",
            loader=loader,
            client=None,
            embed_client=None,
            model="gpt-4o-mini",
            embedding_model=None,
            dry_run=True,
            events_path=tmp_path / "events.jsonl",
        )
    )
    assert len(yielded) >= 1
    for el, result in yielded:
        assert el.element_id
        # Either kept>=0 OR skipped_reason set; never both contradicting.
        assert result.kept >= 0
        assert result.tokens_estimated >= 0


def test_synthesise_wrapper_still_returns_summary(tmp_path: Path) -> None:
    """The original synthesise() function continues to return a SynthesiseResult
    (it now wraps synthesise_iter under the hood)."""
    import shutil

    from goldens.creation.elements.analyze_json import AnalyzeJsonLoader
    from goldens.creation.synthetic import SynthesiseResult, synthesise

    fixtures = Path(__file__).parent / "fixtures"
    analyze = tmp_path / "doc-a" / "analyze"
    analyze.mkdir(parents=True)
    shutil.copy(fixtures / "analyze_minimal.json", analyze / "ts.json")

    loader = AnalyzeJsonLoader("doc-a", outputs_root=tmp_path)
    result = synthesise(
        slug="doc-a",
        loader=loader,
        client=None,
        embed_client=None,
        model="gpt-4o-mini",
        embedding_model=None,
        dry_run=True,
        events_path=tmp_path / "events.jsonl",
    )
    assert isinstance(result, SynthesiseResult)
    assert result.dry_run is True
