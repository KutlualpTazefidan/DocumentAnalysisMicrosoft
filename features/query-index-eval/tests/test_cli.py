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
        patch("query_index_eval.cli._print_summary"),
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
        patch("query_index_eval.cli._print_summary"),
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


def test_cli_eval_with_doc_uses_per_doc_dataset_default() -> None:
    """query-eval eval --doc foo defaults --dataset to outputs/foo/datasets/golden_v1.jsonl."""
    from query_index_eval.cli import main

    with (
        patch("query_index_eval.cli.run_eval") as mock_run,
        patch("query_index_eval.cli._write_report"),
        patch("query_index_eval.cli._print_summary"),
        patch("query_index_eval.cli.Config") as mock_cfg,
    ):
        mock_cfg.from_env.return_value = mock_cfg
        main(["eval", "--doc", "myslug"])

    _, kwargs = mock_run.call_args
    assert "outputs/myslug/datasets/golden_v1.jsonl" in str(kwargs["dataset_path"])


def test_cli_eval_with_doc_writes_report_to_per_doc_reports_dir() -> None:
    """query-eval eval --doc foo writes report under outputs/foo/reports/."""
    from query_index_eval.cli import main

    with (
        patch("query_index_eval.cli.run_eval"),
        patch("query_index_eval.cli._write_report") as mock_write,
        patch("query_index_eval.cli._print_summary"),
        patch("query_index_eval.cli.Config") as mock_cfg,
    ):
        mock_cfg.from_env.return_value = mock_cfg
        main(["eval", "--doc", "myslug", "--strategy", "section"])

    args_call, kwargs_call = mock_write.call_args
    # _write_report(report, out_dir, strategy="section")
    out_dir = args_call[1] if len(args_call) > 1 else kwargs_call.get("out_dir")
    strategy = kwargs_call.get("strategy") or (args_call[2] if len(args_call) > 2 else None)
    assert "outputs/myslug/reports" in str(out_dir)
    assert strategy == "section"


def test_cli_eval_strategy_default_is_unspecified() -> None:
    """When --strategy is not passed, the default is 'unspecified'."""
    from query_index_eval.cli import main

    with (
        patch("query_index_eval.cli.run_eval"),
        patch("query_index_eval.cli._write_report") as mock_write,
        patch("query_index_eval.cli._print_summary"),
        patch("query_index_eval.cli.Config") as mock_cfg,
    ):
        mock_cfg.from_env.return_value = mock_cfg
        main(["eval", "--doc", "myslug"])

    _, kwargs_call = mock_write.call_args
    args_call = mock_write.call_args.args
    strategy = kwargs_call.get("strategy") or (args_call[2] if len(args_call) > 2 else None)
    assert strategy == "unspecified"
