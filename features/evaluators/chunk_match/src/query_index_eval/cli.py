"""query-eval CLI entry point."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from dotenv import load_dotenv
from goldens import GOLDEN_EVENTS_V1_FILENAME, cmd_curate, iter_active_retrieval_entries
from goldens.creation.synthetic import cmd_synthesise
from query_index import Config
from query_index.schema_discovery import print_index_schema

from query_index_eval.runner import run_eval

if TYPE_CHECKING:
    from query_index_eval.schema import MetricsReport


DEFAULT_DATASET = Path("outputs") / "datasets" / GOLDEN_EVENTS_V1_FILENAME
DEFAULT_REPORTS_DIR = Path("outputs") / "reports"


def _write_report(
    report: MetricsReport,
    out_dir: Path,
    strategy: str = "unspecified",
) -> Path:  # pragma: no cover
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out_path = out_dir / f"{timestamp}-{strategy}.json"
    out_path.write_text(json.dumps(asdict(report), indent=2, ensure_ascii=False))
    return out_path


def _print_summary(report: MetricsReport, out_path: Path) -> None:  # pragma: no cover
    a = report.aggregate
    md = report.metadata
    if md.size_status == "indicative":
        banner = "INDICATIVE — n < 30, results NOT statistically reliable"
    elif md.size_status == "preliminary":
        banner = "PRELIMINARY — 30 ≤ n < 100, treat with caution"
    else:
        banner = "REPORTABLE — n ≥ 100"
    print()
    print(f"=== {banner} ===")
    print(f"dataset:      {md.dataset_path}")
    print(f"active:       {md.dataset_size_active}    deprecated: {md.dataset_size_deprecated}")
    print(f"index:        {md.search_index_name}")
    print(f"embedding:    {md.embedding_deployment_name} v{md.embedding_model_version}")
    print(f"timestamp:    {md.run_timestamp_utc}")
    print()
    print(f"Recall@5:     {a.recall_at_5:.3f}")
    print(f"Recall@10:    {a.recall_at_10:.3f}")
    print(f"Recall@20:    {a.recall_at_20:.3f}")
    print(f"MAP:          {a.map_score:.3f}")
    print(f"Hit Rate@1:   {a.hit_rate_at_1:.3f}")
    print(f"MRR:          {a.mrr:.3f}")
    print()
    print(f"report file:  {out_path}")


def _load_env() -> None:
    """Load .env from repo root once. Walk up from this file to find it."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        env_path = parent / ".env"
        if env_path.exists():
            load_dotenv(env_path)
            return
    load_dotenv()  # fallback to default search


def _cmd_eval(args: argparse.Namespace) -> int:
    if args.doc is not None:
        dataset_path = Path("outputs") / args.doc / "datasets" / GOLDEN_EVENTS_V1_FILENAME
        out_dir = Path("outputs") / args.doc / "reports"
    else:
        dataset_path = Path(args.dataset)
        out_dir = DEFAULT_REPORTS_DIR

    if not dataset_path.exists():
        print(f"ERROR: events log not found at {dataset_path}", file=sys.stderr)
        return 2

    cfg = Config.from_env()
    entries = iter_active_retrieval_entries(dataset_path)
    report = run_eval(
        entries=entries,
        dataset_path=str(dataset_path),
        top_k_max=args.top,
        cfg=cfg,
    )
    out_path = _write_report(report, out_dir, strategy=args.strategy)
    _print_summary(report, out_path)
    return 0


def _cmd_report(args: argparse.Namespace) -> int:  # pragma: no cover
    a = json.loads(Path(args.compare[0]).read_text())
    b = json.loads(Path(args.compare[1]).read_text())
    a_md = a["metadata"]
    b_md = b["metadata"]
    drift = []
    for key in (
        "embedding_deployment_name",
        "embedding_model_version",
        "azure_openai_api_version",
        "search_index_name",
    ):
        if a_md[key] != b_md[key]:
            drift.append(f"{key}: A={a_md[key]!r}  B={b_md[key]!r}")
    if drift:
        print("WARNING: reports differ in run-defining metadata; comparison may be misleading:")
        for d in drift:
            print(f"  {d}")
        print()
    print(f"{'metric':<14} {'A':>10} {'B':>10} {'B-A':>10}")
    for key in ("recall_at_5", "recall_at_10", "recall_at_20", "map_score", "hit_rate_at_1", "mrr"):
        av = a["aggregate"][key]
        bv = b["aggregate"][key]
        print(f"{key:<14} {av:>10.3f} {bv:>10.3f} {bv - av:>+10.3f}")
    return 0


def _cmd_schema_discovery(args: argparse.Namespace) -> int:  # pragma: no cover
    cfg = Config.from_env()
    print_index_schema(args.index_name or cfg.ai_search_index_name, cfg)
    return 0


def main(argv: list[str] | None = None) -> int:
    _load_env()
    parser = argparse.ArgumentParser(prog="query-eval")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_eval = sub.add_parser("eval", help="Run evaluation, write report")
    p_eval.add_argument("--dataset", default=str(DEFAULT_DATASET))
    p_eval.add_argument("--top", type=int, default=20)
    p_eval.add_argument(
        "--doc",
        default=None,
        help="Per-doc slug; if given, defaults --dataset and --out under outputs/<slug>/",
    )
    p_eval.add_argument(
        "--strategy",
        default="unspecified",
        help="Chunker strategy name; used in the report filename",
    )
    p_eval.set_defaults(func=_cmd_eval)

    p_report = sub.add_parser("report", help="Compare two metric reports")
    p_report.add_argument("--compare", nargs=2, required=True, metavar=("A", "B"))
    p_report.set_defaults(func=_cmd_report)

    p_schema = sub.add_parser("schema-discovery", help="Print the configured index schema")
    p_schema.add_argument("--index-name", default=None)
    p_schema.set_defaults(func=_cmd_schema_discovery)

    p_curate = sub.add_parser("curate", help="Interactive goldset curation")
    p_curate.add_argument(
        "--doc",
        default=None,
        help="Document slug; auto-pick if exactly one exists under outputs/",
    )
    p_curate.add_argument(
        "--start-from",
        default=None,
        help="Element id (or prefix) to resume from",
    )
    p_curate.set_defaults(func=cmd_curate)

    p_synth = sub.add_parser("synthesise", help="Generate synthetic golden entries via LLM")
    p_synth.add_argument("--doc", required=True)
    p_synth.add_argument("--start-from", default=None)
    p_synth.add_argument("--limit", type=int, default=None)
    p_synth.add_argument("--llm-base-url", default=None)
    p_synth.add_argument("--llm-model", default=None)
    p_synth.add_argument("--embedding-model", default=None)
    p_synth.add_argument("--prompt-template-version", default="v1")
    p_synth.add_argument("--max-questions-per-element", type=int, default=20)
    p_synth.add_argument("--temperature", type=float, default=0.0)
    p_synth.add_argument("--max-prompt-tokens", type=int, default=8000)
    p_synth.add_argument("--dry-run", action="store_true")
    p_synth.add_argument("--resume", action="store_true")
    p_synth.add_argument("--language", default="de")
    p_synth.set_defaults(func=cmd_synthesise)

    try:
        args = parser.parse_args(argv)
    except SystemExit as e:
        return int(e.code or 2)
    try:
        return int(args.func(args) or 0)
    except Exception as e:  # pragma: no cover
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
