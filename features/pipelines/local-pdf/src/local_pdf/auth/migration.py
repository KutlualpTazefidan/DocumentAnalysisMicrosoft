"""One-shot migration of legacy single-tenant data into tenants/{slug}/.

Pre-Phase-7 deployments wrote all slug-keyed data directly under
``data_root``. After the multi-tenant rollout, a non-default tenant
must live under ``data_root/tenants/{slug}/``. This module walks
``data_root`` for legacy slug-keyed entries and copies / moves them
into the chosen target tenant subtree.

Safety:
  * ``mode='copy'`` (default) leaves the originals in place so a
    failed migration loses nothing.
  * ``_meta/`` (auth DB) and ``tenants/`` (already-migrated data) are
    skipped — they're cross-tenant by design.
  * Files already present in the destination are NOT overwritten;
    re-running the migration is a no-op for those.
"""

from __future__ import annotations

import contextlib
import shutil
from dataclasses import dataclass, field
from pathlib import Path  # noqa: TC003

# Names that are NOT slug-keyed and must never migrate into a tenant
# subtree. Order matters: ``tenants`` is the destination itself; if we
# included it the migration would infinite-recurse.
_SKIP_TOP_LEVEL = {"_meta", "tenants"}


@dataclass
class MigrationReport:
    """Counts + per-entry detail for the CLI to render."""

    target_tenant: str
    mode: str  # "copy" | "move"
    dry_run: bool
    target_root: Path
    moved_paths: list[Path] = field(default_factory=list)
    skipped_paths: list[tuple[Path, str]] = field(default_factory=list)
    bytes_total: int = 0

    @property
    def moved_count(self) -> int:
        return len(self.moved_paths)


def _dir_size_bytes(path: Path) -> int:
    """Sum of file sizes under ``path``. Best-effort: unreadable files
    are silently skipped (size = 0)."""
    total = 0
    for f in path.rglob("*"):
        if f.is_file():
            with contextlib.suppress(OSError):
                total += f.stat().st_size
    return total


def migrate_legacy_data(
    data_root: Path,
    *,
    target_tenant: str,
    mode: str = "copy",
    dry_run: bool = False,
) -> MigrationReport:
    """Move/copy legacy slug-keyed directories into the target tenant.

    Parameters
    ----------
    data_root
        The shared root containing legacy slugs and the auth DB.
    target_tenant
        Slug of the tenant that should own the legacy data. Typically
        ``"default"`` — most installs run as one workspace until
        someone calls ``auth init`` for a second one.
    mode
        ``"copy"`` (default) preserves originals as a backup;
        ``"move"`` replaces them. Idempotent in both modes: existing
        destinations are skipped.
    dry_run
        Walk + plan but do not touch the filesystem.
    """
    if mode not in ("copy", "move"):
        raise ValueError(f"mode must be 'copy' or 'move', got {mode!r}")
    target_root = data_root / "tenants" / target_tenant
    if not dry_run:
        target_root.mkdir(parents=True, exist_ok=True)

    report = MigrationReport(
        target_tenant=target_tenant,
        mode=mode,
        dry_run=dry_run,
        target_root=target_root,
    )

    if not data_root.exists():
        return report

    for entry in sorted(data_root.iterdir()):
        if not entry.is_dir():
            continue
        if entry.name in _SKIP_TOP_LEVEL:
            report.skipped_paths.append((entry, "system directory"))
            continue
        dest = target_root / entry.name
        if dest.exists():
            report.skipped_paths.append((entry, f"destination already exists: {dest}"))
            continue

        report.bytes_total += _dir_size_bytes(entry)
        if dry_run:
            report.moved_paths.append(entry)
            continue
        if mode == "copy":
            shutil.copytree(entry, dest)
        else:
            shutil.move(str(entry), str(dest))
        report.moved_paths.append(entry)

    return report
