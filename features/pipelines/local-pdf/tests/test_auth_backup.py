"""Tests for the auth-DB online-backup helper."""

from __future__ import annotations

import gzip
import sqlite3
from pathlib import Path  # noqa: TC003

import pytest
from local_pdf.auth.backup import backup_auth_db
from local_pdf.auth.db import ensure_schema, open_auth_db
from local_pdf.auth.tenants import create_tenant
from local_pdf.auth.users import authenticate, create_user


def test_backup_creates_restorable_gzipped_file(tmp_path: Path) -> None:
    """End-to-end: seed an auth DB, back it up, gunzip the result,
    open the restored DB and verify the user can still authenticate
    against the snapshot."""
    src_root = tmp_path / "src"
    src_root.mkdir()
    with open_auth_db(src_root) as conn:
        ensure_schema(conn)
        tenant = create_tenant(conn, slug="default", name="Default")
        create_user(
            conn,
            tenant_id=tenant.tenant_id,
            username="alice",
            password="secret",
        )

    dest = tmp_path / "snapshots" / "auth.db.gz"
    info = backup_auth_db(src_root, dest)

    assert dest.exists()
    assert info["bytes_written"] > 0
    assert info["source_pages"] > 0

    # Restore: gunzip into a plain .db, open it, verify the user.
    restored = tmp_path / "restored.db"
    with gzip.open(dest, "rb") as gz, restored.open("wb") as out:
        out.write(gz.read())
    conn = sqlite3.connect(str(restored))
    conn.row_factory = sqlite3.Row
    try:
        # The schema columns survived the round-trip.
        u = conn.execute(
            "SELECT username, role, active FROM users WHERE username = ?",
            ("alice",),
        ).fetchone()
        assert u is not None
        assert u["username"] == "alice"
        # Use the production authenticate to confirm the hash is still
        # verifiable end-to-end. authenticate writes last_login_at via
        # the connection, so it must accept the restored DB.
        from local_pdf.auth.users import authenticate as _authenticate

        _ = _authenticate
        result = authenticate(conn, tenant_slug="default", username="alice", password="secret")
        assert result.username == "alice"
    finally:
        conn.close()


def test_backup_missing_source_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        backup_auth_db(tmp_path / "no-such-root", tmp_path / "out.gz")


def test_backup_overwrites_existing_dest(tmp_path: Path) -> None:
    src_root = tmp_path / "src"
    src_root.mkdir()
    with open_auth_db(src_root) as conn:
        ensure_schema(conn)
        create_tenant(conn, slug="default", name="Default")

    dest = tmp_path / "out.gz"
    dest.write_bytes(b"older content")
    info = backup_auth_db(src_root, dest)
    # Existing file replaced — content is now valid gzip.
    assert info["bytes_written"] != len(b"older content")
    with gzip.open(dest, "rb") as gz:
        head = gz.read(16)
    # SQLite file format magic header.
    assert head.startswith(b"SQLite format 3")
