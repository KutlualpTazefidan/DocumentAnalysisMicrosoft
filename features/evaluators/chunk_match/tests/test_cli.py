"""Tests for the query-eval CLI dispatcher."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch


def test_cli_dispatches_eval_with_default_top_k(tmp_path: Path) -> None:
    from query_index_eval.cli import main

    dataset = tmp_path / "events.jsonl"
    dataset.write_text("")  # empty but exists

    with (
        patch("query_index_eval.cli.run_eval") as mock_run,
        patch("query_index_eval.cli.iter_active_retrieval_entries", return_value=iter([])),
        patch("query_index_eval.cli._write_report"),
        patch("query_index_eval.cli._print_summary"),
        patch("query_index_eval.cli.Config") as mock_cfg,
    ):
        mock_cfg.from_env.return_value = mock_cfg
        rc = main(["eval", "--dataset", str(dataset)])
    assert rc == 0
    _args, kwargs = mock_run.call_args
    assert kwargs["top_k_max"] == 20


def test_cli_dispatches_eval_passes_top_argument(tmp_path: Path) -> None:
    from query_index_eval.cli import main

    dataset = tmp_path / "events.jsonl"
    dataset.write_text("")

    with (
        patch("query_index_eval.cli.run_eval") as mock_run,
        patch("query_index_eval.cli.iter_active_retrieval_entries", return_value=iter([])),
        patch("query_index_eval.cli._write_report"),
        patch("query_index_eval.cli._print_summary"),
        patch("query_index_eval.cli.Config") as mock_cfg,
    ):
        mock_cfg.from_env.return_value = mock_cfg
        main(["eval", "--dataset", str(dataset), "--top", "10"])
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


def test_cli_eval_with_doc_uses_per_doc_dataset_default(tmp_path: Path, monkeypatch) -> None:
    """--doc foo defaults --dataset to outputs/foo/datasets/golden_events_v1.jsonl."""
    from query_index_eval.cli import main

    monkeypatch.chdir(tmp_path)
    expected = tmp_path / "outputs" / "myslug" / "datasets" / "golden_events_v1.jsonl"
    expected.parent.mkdir(parents=True)
    expected.write_text("")

    captured: dict = {}

    def fake_iter(path):
        captured["path"] = path
        return iter([])

    with (
        patch("query_index_eval.cli.run_eval"),
        patch("query_index_eval.cli.iter_active_retrieval_entries", side_effect=fake_iter),
        patch("query_index_eval.cli._write_report"),
        patch("query_index_eval.cli._print_summary"),
        patch("query_index_eval.cli.Config") as mock_cfg,
    ):
        mock_cfg.from_env.return_value = mock_cfg
        main(["eval", "--doc", "myslug"])

    assert captured["path"] == Path("outputs") / "myslug" / "datasets" / "golden_events_v1.jsonl"


def test_cli_eval_with_doc_writes_report_to_per_doc_reports_dir(
    tmp_path: Path, monkeypatch
) -> None:
    """query-eval eval --doc foo writes report under outputs/foo/reports/."""
    from query_index_eval.cli import main

    monkeypatch.chdir(tmp_path)
    expected = tmp_path / "outputs" / "myslug" / "datasets" / "golden_events_v1.jsonl"
    expected.parent.mkdir(parents=True)
    expected.write_text("")

    with (
        patch("query_index_eval.cli.run_eval"),
        patch("query_index_eval.cli.iter_active_retrieval_entries", return_value=iter([])),
        patch("query_index_eval.cli._write_report") as mock_write,
        patch("query_index_eval.cli._print_summary"),
        patch("query_index_eval.cli.Config") as mock_cfg,
    ):
        mock_cfg.from_env.return_value = mock_cfg
        main(["eval", "--doc", "myslug", "--strategy", "section"])

    args_call, kwargs_call = mock_write.call_args
    out_dir = args_call[1] if len(args_call) > 1 else kwargs_call.get("out_dir")
    strategy = kwargs_call.get("strategy") or (args_call[2] if len(args_call) > 2 else None)
    assert "outputs/myslug/reports" in str(out_dir).replace("\\", "/")
    assert strategy == "section"


def test_cli_eval_strategy_default_is_unspecified(tmp_path: Path, monkeypatch) -> None:
    """When --strategy is not passed, the default is 'unspecified'."""
    from query_index_eval.cli import main

    monkeypatch.chdir(tmp_path)
    expected = tmp_path / "outputs" / "myslug" / "datasets" / "golden_events_v1.jsonl"
    expected.parent.mkdir(parents=True)
    expected.write_text("")

    with (
        patch("query_index_eval.cli.run_eval"),
        patch("query_index_eval.cli.iter_active_retrieval_entries", return_value=iter([])),
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


def test_cli_eval_returns_2_when_dataset_missing(tmp_path: Path, capsys) -> None:
    """If the events log file does not exist, the CLI fails hard with
    exit code 2 and a clear stderr message — preventing a silent
    empty-eval that produces zero-aggregate reports."""
    from query_index_eval.cli import main

    absent = tmp_path / "absent.jsonl"
    rc = main(["eval", "--dataset", str(absent)])
    captured = capsys.readouterr()
    assert rc == 2
    assert "events log not found" in captured.err
    assert str(absent) in captured.err


def test_cli_eval_only_passes_active_entries_to_run_eval(
    tmp_path: Path,
    make_entry,
) -> None:
    """The deprecated-filtering happens at the boundary
    (iter_active_retrieval_entries). Even if the events log contains
    deprecated entries, run_eval only ever sees active ones."""
    from query_index_eval.cli import main

    dataset = tmp_path / "events.jsonl"
    dataset.write_text("")

    active = make_entry(query="active query")
    make_entry(query="deprecated query", deprecated=True)  # not passed to iter

    captured_entries: list = []

    def fake_run_eval(*, entries, **_):
        captured_entries.extend(entries)
        from query_index_eval.schema import (
            AggregateMetrics,
            MetricsReport,
            OperationalMetrics,
            RunMetadata,
        )

        return MetricsReport(
            aggregate=AggregateMetrics(0, 0, 0, 0, 0, 0),
            operational=OperationalMetrics(0, 0, 0, 0, 0),
            metadata=RunMetadata("x", 0, 0, "", "", "", "", "2026-04-29T00:00:00Z", "indicative"),
            per_query=[],
        )

    # iter_active_retrieval_entries is the boundary that filters deprecated;
    # we simulate it returning only the active entry.
    with (
        patch("query_index_eval.cli.run_eval", side_effect=fake_run_eval),
        patch("query_index_eval.cli.iter_active_retrieval_entries", return_value=iter([active])),
        patch("query_index_eval.cli._write_report"),
        patch("query_index_eval.cli._print_summary"),
        patch("query_index_eval.cli.Config") as mock_cfg,
    ):
        mock_cfg.from_env.return_value = mock_cfg
        main(["eval", "--dataset", str(dataset)])

    assert len(captured_entries) == 1
    assert captured_entries[0].query == "active query"
