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


def cmd_serve(args: argparse.Namespace) -> int:  # pragma: no cover
    """Boot the goldens HTTP API via uvicorn. Reads config from env."""
    import os
    import sys

    if not os.environ.get("GOLDENS_API_TOKEN"):
        print(
            "ERROR: GOLDENS_API_TOKEN env var is required. "
            "Set it before running, e.g.:\n"
            "    export GOLDENS_API_TOKEN=$(uuidgen)\n"
            "    query-eval serve",
            file=sys.stderr,
        )
        return 2

    try:
        import uvicorn
        from goldens.api.app import create_app
    except ImportError as e:
        print(f"ERROR: {e}. Did you install features/goldens with the api extra?", file=sys.stderr)
        return 2

    app = create_app()
    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )
    return 0


def cmd_segment_serve(*, host: str, port: int, log_level: str) -> int:
    """Start the local-pdf FastAPI app via uvicorn."""
    import uvicorn
    from local_pdf.api import create_app

    app = create_app()
    uvicorn.run(app, host=host, port=port, log_level=log_level)
    return 0


def _resolve_data_root() -> Path:
    """Resolve the data_root the same way the FastAPI Config does.

    Reads LOCAL_PDF_DATA_ROOT (the env var the running server uses) so
    CLI invocations and the server share the same auth.db without an
    extra flag. Falls back to the Config default if unset.
    """
    import os
    from pathlib import Path

    root_str = os.environ.get("LOCAL_PDF_DATA_ROOT", "data/raw-pdfs")
    return Path(root_str).expanduser().resolve()


def cmd_segment_auth_init(
    *,
    tenant_slug: str,
    tenant_name: str,
    admin_username: str,
    admin_password: str,
    admin_pseudonym: str | None,
) -> int:
    """Bootstrap the local auth DB with one tenant + one admin user.

    Idempotent semantics:
      * Tenant slug already taken -> reuse existing tenant (warn).
      * Admin username already taken inside tenant -> abort with hint.

    On success, prints the pseudonym + the auth.db path so the operator
    sees exactly what was written.
    """
    from local_pdf.auth.db import auth_db_path, ensure_schema, open_auth_db
    from local_pdf.auth.tenants import create_tenant, get_tenant_by_slug
    from local_pdf.auth.users import create_user

    if not admin_password:
        print("ERROR: admin password must be non-empty.", file=sys.stderr)
        return 2

    data_root = _resolve_data_root()
    print(f"data_root: {data_root}")
    print(f"auth.db:   {auth_db_path(data_root)}")

    with open_auth_db(data_root) as conn:
        ensure_schema(conn)
        existing = get_tenant_by_slug(conn, tenant_slug)
        if existing is not None:
            print(f"tenant {tenant_slug!r} already exists (reusing).")
            tenant = existing
        else:
            try:
                tenant = create_tenant(conn, slug=tenant_slug, name=tenant_name)
            except ValueError as exc:
                print(f"ERROR: {exc}", file=sys.stderr)
                return 3
            print(f"created tenant: {tenant.slug} (id={tenant.tenant_id})")

        try:
            user = create_user(
                conn,
                tenant_id=tenant.tenant_id,
                username=admin_username,
                password=admin_password,
                role="admin",
                pseudonym=admin_pseudonym,
            )
        except ValueError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 4

    print(f"created admin user: {user.username}")
    print(f"  user_id:   {user.user_id}")
    print(f"  pseudonym: {user.pseudonym}  (lands in audit logs)")
    print(f"  role:      {user.role}")
    print()
    print("Next: login at /api/auth/login with tenant_slug + username + password.")
    print("(auth.db is chmod 0600 — keep data_root private.)")
    return 0


def cmd_segment_auth_create_user(
    *,
    tenant_slug: str,
    username: str,
    password: str,
    role: str,
    pseudonym: str | None,
) -> int:
    """Create an additional user inside an existing tenant."""
    from local_pdf.auth.db import ensure_schema, open_auth_db
    from local_pdf.auth.tenants import get_tenant_by_slug
    from local_pdf.auth.users import create_user

    if not password:
        print("ERROR: password must be non-empty.", file=sys.stderr)
        return 2

    data_root = _resolve_data_root()
    with open_auth_db(data_root) as conn:
        ensure_schema(conn)
        tenant = get_tenant_by_slug(conn, tenant_slug)
        if tenant is None:
            print(f"ERROR: tenant not found: {tenant_slug!r}", file=sys.stderr)
            print("Run 'auth init' first.", file=sys.stderr)
            return 3
        try:
            user = create_user(
                conn,
                tenant_id=tenant.tenant_id,
                username=username,
                password=password,
                role=role,  # type: ignore[arg-type]
                pseudonym=pseudonym,
            )
        except ValueError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 4

    print(f"created user: {user.username}")
    print(f"  user_id:   {user.user_id}")
    print(f"  pseudonym: {user.pseudonym}")
    print(f"  role:      {user.role}")
    return 0


def cmd_segment_tenant_migrate(*, tenant_slug: str, mode: str, dry_run: bool) -> int:
    """Migrate legacy slug-keyed data into ``tenants/{slug}/``.

    Default mode is ``copy`` so originals stay around as a backup;
    pass ``--mode=move`` once the new layout has been verified.
    """
    from local_pdf.auth.migration import migrate_legacy_data

    data_root = _resolve_data_root()
    report = migrate_legacy_data(data_root, target_tenant=tenant_slug, mode=mode, dry_run=dry_run)
    print(f"data_root: {data_root}")
    print(f"target:    {report.target_root}")
    print(f"mode:      {report.mode}" + (" [DRY-RUN]" if report.dry_run else ""))
    print()
    print(
        f"would move {report.moved_count} entries"
        if report.dry_run
        else f"migrated {report.moved_count} entries"
    )
    for p in report.moved_paths:
        marker = "WOULD" if report.dry_run else "OK   "
        print(f"  {marker} {p.name}")
    if report.skipped_paths:
        print()
        print(f"skipped {len(report.skipped_paths)} entries:")
        for path, reason in report.skipped_paths:
            print(f"  -- {path.name}: {reason}")
    if report.bytes_total:
        mb = report.bytes_total / (1024 * 1024)
        print(f"\nsize affected: ~{mb:.1f} MiB")
    return 0


def cmd_segment_auth_backup(*, dest: str) -> int:
    """Snapshot the auth DB to a gzipped file.

    Uses sqlite3 online-backup (no quiesce required). Prints the
    resulting path + compressed size so the operator can verify.
    """
    from pathlib import Path

    from local_pdf.auth.backup import backup_auth_db

    data_root = _resolve_data_root()
    dest_path = Path(dest).expanduser().resolve()
    try:
        info = backup_auth_db(data_root, dest_path)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 3
    print(f"backed up: {info['source']}")
    print(f"        -> {info['dest']}")
    print(f"  size:    {info['bytes_written']} bytes (gzipped)")
    print(f"  source:  {info['source_pages']} pages")
    return 0


def _prompt_password(label: str) -> str:
    """Read a password from stdin with no echo; called when --password
    flag is omitted to avoid leaving creds in shell history."""
    import getpass

    return getpass.getpass(f"{label}: ")


def _add_segment_subparser(subparsers) -> None:
    seg = subparsers.add_parser("segment", help="local-pdf pipeline commands")
    seg_sub = seg.add_subparsers(dest="segment_cmd", required=True)
    serve = seg_sub.add_parser("serve", help="run the local-pdf HTTP API")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8001)
    serve.add_argument("--log-level", default="info", choices=["debug", "info", "warning", "error"])
    serve.set_defaults(
        func=lambda args: cmd_segment_serve(
            host=args.host, port=args.port, log_level=args.log_level
        )
    )

    # ── auth: tenant + first-admin bootstrap, plus user-creation ─────────
    auth = seg_sub.add_parser("auth", help="local-pdf auth management")
    auth_sub = auth.add_subparsers(dest="auth_cmd", required=True)

    init = auth_sub.add_parser("init", help="bootstrap first tenant + first admin user")
    init.add_argument("--tenant-slug", required=True)
    init.add_argument("--tenant-name", required=True)
    init.add_argument("--admin-username", required=True)
    init.add_argument("--admin-password", default=None, help="omit to prompt")
    init.add_argument(
        "--admin-pseudonym",
        default=None,
        help="optional override; auto-generated when absent",
    )
    init.set_defaults(
        func=lambda args: cmd_segment_auth_init(
            tenant_slug=args.tenant_slug,
            tenant_name=args.tenant_name,
            admin_username=args.admin_username,
            admin_password=args.admin_password or _prompt_password("Admin password"),
            admin_pseudonym=args.admin_pseudonym,
        )
    )

    create_user = auth_sub.add_parser(
        "create-user", help="create an additional user in an existing tenant"
    )
    create_user.add_argument("--tenant-slug", required=True)
    create_user.add_argument("--username", required=True)
    create_user.add_argument("--password", default=None, help="omit to prompt")
    create_user.add_argument("--role", choices=["admin", "reviewer", "curator"], default="curator")
    create_user.add_argument("--pseudonym", default=None)
    create_user.set_defaults(
        func=lambda args: cmd_segment_auth_create_user(
            tenant_slug=args.tenant_slug,
            username=args.username,
            password=args.password or _prompt_password("Password"),
            role=args.role,
            pseudonym=args.pseudonym,
        )
    )

    backup = auth_sub.add_parser(
        "backup", help="snapshot the auth DB (sqlite online-backup + gzip)"
    )
    backup.add_argument(
        "--to",
        dest="dest",
        required=True,
        help="destination file path; .db.gz suffix recommended",
    )
    backup.set_defaults(func=lambda args: cmd_segment_auth_backup(dest=args.dest))

    migrate = seg_sub.add_parser(
        "tenant",
        help="multi-tenant data lifecycle (migrate legacy data into tenants/)",
    )
    migrate_sub = migrate.add_subparsers(dest="tenant_cmd", required=True)
    mig = migrate_sub.add_parser(
        "migrate",
        help="copy/move legacy slug-keyed data into tenants/{slug}/",
    )
    mig.add_argument(
        "--tenant-slug",
        default="default",
        help="target tenant for the legacy data (default: 'default')",
    )
    mig.add_argument(
        "--mode",
        choices=["copy", "move"],
        default="copy",
        help=(
            "copy: leave originals as backup (default). move: replace "
            "originals with the migrated tree."
        ),
    )
    mig.add_argument(
        "--dry-run",
        action="store_true",
        help="walk + plan without touching the filesystem",
    )
    mig.set_defaults(
        func=lambda args: cmd_segment_tenant_migrate(
            tenant_slug=args.tenant_slug,
            mode=args.mode,
            dry_run=args.dry_run,
        )
    )


def main(argv: list[str] | None = None) -> int:
    _load_env()
    parser = argparse.ArgumentParser(prog="query-eval")
    sub = parser.add_subparsers(dest="cmd", required=True)

    _add_segment_subparser(sub)

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

    p_serve = sub.add_parser("serve", help="Run the goldens HTTP API on 127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8000)
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--reload", action="store_true", help="auto-reload on code changes (dev)")
    p_serve.set_defaults(func=cmd_serve)

    try:
        args = parser.parse_args(argv)
    except SystemExit as e:
        return int(e.code if e.code is not None else 2)
    try:
        return int(args.func(args) or 0)
    except Exception as e:  # pragma: no cover
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
