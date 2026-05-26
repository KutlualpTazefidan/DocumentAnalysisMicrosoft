"""Tests for the legacy-data → tenants/{slug}/ migration helper."""

from __future__ import annotations

from pathlib import Path  # noqa: TC003

import pytest
from local_pdf.auth.migration import migrate_legacy_data


def _seed_legacy(root: Path) -> None:
    """Create a stub data_root with a couple of legacy slug directories
    plus the system dirs that must NOT migrate."""
    (root / "doc-alpha" / "datasets").mkdir(parents=True)
    (root / "doc-alpha" / "datasets" / "events.jsonl").write_text('{"x":1}\n')
    (root / "doc-alpha" / "source.pdf").write_bytes(b"%PDF-1.4\n%%EOF\n")
    (root / "doc-beta").mkdir(parents=True)
    (root / "doc-beta" / "mineru-out.json").write_text("{}")
    (root / "_meta").mkdir()
    (root / "_meta" / "auth.db").write_bytes(b"sqlite-header")
    (root / "tenants" / "already-there").mkdir(parents=True)


def test_copy_migration_creates_target_and_leaves_originals(tmp_path: Path) -> None:
    _seed_legacy(tmp_path)
    r = migrate_legacy_data(tmp_path, target_tenant="default", mode="copy")
    assert r.moved_count == 2
    assert (tmp_path / "tenants" / "default" / "doc-alpha" / "source.pdf").exists()
    assert (tmp_path / "tenants" / "default" / "doc-beta" / "mineru-out.json").exists()
    # Originals untouched.
    assert (tmp_path / "doc-alpha" / "source.pdf").exists()
    assert (tmp_path / "doc-beta" / "mineru-out.json").exists()


def test_skip_system_directories(tmp_path: Path) -> None:
    _seed_legacy(tmp_path)
    r = migrate_legacy_data(tmp_path, target_tenant="default", mode="copy")
    skipped_names = {p.name for p, _ in r.skipped_paths}
    assert "_meta" in skipped_names
    assert "tenants" in skipped_names
    # Auth DB untouched + no copy under target.
    assert (tmp_path / "_meta" / "auth.db").exists()
    assert not (tmp_path / "tenants" / "default" / "_meta").exists()


def test_idempotent_re_run(tmp_path: Path) -> None:
    """Second run skips already-migrated entries instead of overwriting."""
    _seed_legacy(tmp_path)
    migrate_legacy_data(tmp_path, target_tenant="default", mode="copy")
    r2 = migrate_legacy_data(tmp_path, target_tenant="default", mode="copy")
    assert r2.moved_count == 0
    # Every entry now appears in skipped_paths.
    skipped_names = {p.name for p, _ in r2.skipped_paths}
    assert "doc-alpha" in skipped_names
    assert "doc-beta" in skipped_names


def test_move_mode_removes_originals(tmp_path: Path) -> None:
    _seed_legacy(tmp_path)
    r = migrate_legacy_data(tmp_path, target_tenant="default", mode="move")
    assert r.moved_count == 2
    assert (tmp_path / "tenants" / "default" / "doc-alpha").exists()
    assert not (tmp_path / "doc-alpha").exists()
    assert not (tmp_path / "doc-beta").exists()
    # System dirs survive even in move mode.
    assert (tmp_path / "_meta" / "auth.db").exists()


def test_dry_run_does_not_touch_filesystem(tmp_path: Path) -> None:
    _seed_legacy(tmp_path)
    r = migrate_legacy_data(tmp_path, target_tenant="default", mode="copy", dry_run=True)
    assert r.dry_run is True
    assert r.moved_count == 2  # planned
    assert not (tmp_path / "tenants" / "default" / "doc-alpha").exists()


def test_invalid_mode_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="mode must be"):
        migrate_legacy_data(tmp_path, target_tenant="default", mode="symlink")
