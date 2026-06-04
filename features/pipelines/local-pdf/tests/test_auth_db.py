"""Tests for the auth DB connection + idempotent schema migration."""

from __future__ import annotations

from pathlib import Path  # noqa: TC003

from local_pdf.auth.db import auth_db_path, ensure_schema, open_auth_db


def test_auth_db_path_pure(tmp_path: Path) -> None:
    """auth_db_path is a pure function — no filesystem side effect."""
    p = auth_db_path(tmp_path)
    assert p == tmp_path / "_meta" / "auth.db"
    assert not p.exists()


def test_open_auth_db_creates_meta_dir(tmp_path: Path) -> None:
    with open_auth_db(tmp_path) as conn:
        ensure_schema(conn)
    assert (tmp_path / "_meta" / "auth.db").exists()


def test_ensure_schema_creates_all_tables(tmp_path: Path) -> None:
    with open_auth_db(tmp_path) as conn:
        ensure_schema(conn)
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        }
    assert tables == {"tenants", "users", "sessions", "failed_logins"}


def test_ensure_schema_idempotent(tmp_path: Path) -> None:
    """Running ensure_schema twice must not raise or duplicate tables."""
    with open_auth_db(tmp_path) as conn:
        ensure_schema(conn)
        ensure_schema(conn)
        ensure_schema(conn)
        version = conn.execute("PRAGMA user_version").fetchone()[0]
    assert version == 2


def test_foreign_keys_enabled(tmp_path: Path) -> None:
    """FK enforcement is essential so deleting a tenant cascades to its users."""
    with open_auth_db(tmp_path) as conn:
        ensure_schema(conn)
        fk_on = conn.execute("PRAGMA foreign_keys").fetchone()[0]
    assert int(fk_on) == 1
