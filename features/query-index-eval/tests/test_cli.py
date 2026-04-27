"""Tests for the query-eval CLI dispatcher."""

from __future__ import annotations

from unittest.mock import patch


def test_cli_dispatches_curate() -> None:
    from query_index_eval.cli import main

    with patch("query_index_eval.cli.interactive_curate") as mock_curate:
        rc = main(["curate", "--dataset", "ds.jsonl"])
    assert rc == 0
    mock_curate.assert_called_once()


def test_cli_dispatches_eval_with_default_top_k() -> None:
    from query_index_eval.cli import main

    with (
        patch("query_index_eval.cli.run_eval") as mock_run,
        patch("query_index_eval.cli._write_report"),
        patch("query_index_eval.cli.Config") as mock_cfg,
    ):
        mock_cfg.from_env.return_value = mock_cfg
        rc = main(["eval", "--dataset", "ds.jsonl"])
    assert rc == 0
    _args, kwargs = mock_run.call_args
    assert kwargs["top_k_max"] == 20


def test_cli_dispatches_eval_passes_top_argument() -> None:
    from query_index_eval.cli import main

    with (
        patch("query_index_eval.cli.run_eval") as mock_run,
        patch("query_index_eval.cli._write_report"),
        patch("query_index_eval.cli.Config") as mock_cfg,
    ):
        mock_cfg.from_env.return_value = mock_cfg
        main(["eval", "--dataset", "ds.jsonl", "--top", "10"])
    _args, kwargs = mock_run.call_args
    assert kwargs["top_k_max"] == 10


def test_cli_dispatches_schema_discovery() -> None:
    from query_index_eval.cli import main

    with (
        patch("query_index_eval.cli.print_index_schema") as mock_schema,
        patch("query_index_eval.cli.Config") as mock_cfg,
    ):
        mock_cfg.from_env.return_value = mock_cfg
        mock_cfg.ai_search_index_name = "test-idx"
        rc = main(["schema-discovery"])
    assert rc == 0
    mock_schema.assert_called_once()


def test_cli_unknown_subcommand_returns_nonzero() -> None:
    from query_index_eval.cli import main

    rc = main(["unknown-thing"])
    assert rc != 0
