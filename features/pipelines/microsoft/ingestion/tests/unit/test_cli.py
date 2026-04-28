"""Tests for the ingest CLI dispatcher."""

from __future__ import annotations

from unittest.mock import patch


def test_cli_dispatches_analyze() -> None:
    from ingestion.cli import main

    with patch("ingestion.cli.analyze_pdf") as mock_fn:
        rc = main(["analyze", "--in", "data/foo.pdf"])
    assert rc == 0
    mock_fn.assert_called_once()


def test_cli_dispatches_chunk_with_strategy() -> None:
    from ingestion.cli import main

    with patch("ingestion.cli.chunk") as mock_fn:
        rc = main(["chunk", "--in", "x.json", "--strategy", "section"])
    assert rc == 0
    args, kwargs = mock_fn.call_args
    # strategy passed through (either as kwarg or positional)
    assert kwargs.get("strategy") == "section" or "section" in args


def test_cli_dispatches_embed() -> None:
    from ingestion.cli import main

    with patch("ingestion.cli.embed_chunks") as mock_fn:
        rc = main(["embed", "--in", "x.jsonl"])
    assert rc == 0
    mock_fn.assert_called_once()


def test_cli_dispatches_upload() -> None:
    from ingestion.cli import main

    with patch("ingestion.cli.upload_chunks") as mock_fn:
        rc = main(["upload", "--in", "x.jsonl"])
    assert rc == 0
    mock_fn.assert_called_once()


def test_cli_upload_passes_force_recreate_flag() -> None:
    from ingestion.cli import main

    with patch("ingestion.cli.upload_chunks") as mock_fn:
        main(["upload", "--in", "x.jsonl", "--force-recreate"])
    _, kwargs = mock_fn.call_args
    assert kwargs.get("force_recreate") is True


def test_cli_upload_passes_index_name_flag() -> None:
    from ingestion.cli import main

    with patch("ingestion.cli.upload_chunks") as mock_fn:
        main(["upload", "--in", "x.jsonl", "--index", "my-index"])
    _, kwargs = mock_fn.call_args
    assert kwargs.get("index_name") == "my-index"


def test_cli_unknown_subcommand_returns_nonzero() -> None:
    from ingestion.cli import main

    rc = main(["unknown-thing"])
    assert rc != 0


def test_cli_chunk_default_strategy_is_section() -> None:
    """When --strategy is not passed, default is 'section'."""
    from ingestion.cli import main

    with patch("ingestion.cli.chunk") as mock_fn:
        main(["chunk", "--in", "x.json"])
    _, kwargs = mock_fn.call_args
    assert kwargs.get("strategy") == "section"
