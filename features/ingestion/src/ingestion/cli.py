"""ingest CLI entry point. Four subcommands: analyze | chunk | embed | upload."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

from ingestion.analyze import analyze_pdf
from ingestion.chunk import chunk
from ingestion.embed import embed_chunks
from ingestion.upload import upload_chunks


def _load_env() -> None:
    """Load .env from repo root once. Walk up from this file to find it."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        env_path = parent / ".env"
        if env_path.exists():
            load_dotenv(env_path)
            return
    load_dotenv()


def _cmd_analyze(args: argparse.Namespace) -> int:
    out = Path(args.out) if args.out else None
    analyze_pdf(in_path=Path(args.in_path), out_path=out)
    return 0


def _cmd_chunk(args: argparse.Namespace) -> int:
    out = Path(args.out) if args.out else None
    chunk(in_path=Path(args.in_path), strategy=args.strategy, out_path=out)
    return 0


def _cmd_embed(args: argparse.Namespace) -> int:
    out = Path(args.out) if args.out else None
    embed_chunks(in_path=Path(args.in_path), out_path=out)
    return 0


def _cmd_upload(args: argparse.Namespace) -> int:
    upload_chunks(
        in_path=Path(args.in_path),
        index_name=args.index,
        force_recreate=args.force_recreate,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    _load_env()

    parser = argparse.ArgumentParser(prog="ingest")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_analyze = sub.add_parser("analyze", help="PDF → analyze JSON")
    p_analyze.add_argument("--in", dest="in_path", required=True)
    p_analyze.add_argument("--out", default=None)
    p_analyze.set_defaults(func=_cmd_analyze)

    p_chunk = sub.add_parser("chunk", help="analyze JSON → chunks JSONL")
    p_chunk.add_argument("--in", dest="in_path", required=True)
    p_chunk.add_argument("--strategy", default="section")
    p_chunk.add_argument("--out", default=None)
    p_chunk.set_defaults(func=_cmd_chunk)

    p_embed = sub.add_parser("embed", help="chunks JSONL → embedded JSONL")
    p_embed.add_argument("--in", dest="in_path", required=True)
    p_embed.add_argument("--out", default=None)
    p_embed.set_defaults(func=_cmd_embed)

    p_upload = sub.add_parser("upload", help="embedded JSONL → Azure AI Search")
    p_upload.add_argument("--in", dest="in_path", required=True)
    p_upload.add_argument("--index", default=None)
    p_upload.add_argument("--force-recreate", action="store_true")
    p_upload.set_defaults(func=_cmd_upload)

    try:
        args = parser.parse_args(argv)
    except SystemExit as e:
        return int(e.code or 2)

    try:
        return int(args.func(args) or 0)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
