from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING

from local_pdf.auth.db import _migrate_to_v1, ensure_schema, open_auth_db

if TYPE_CHECKING:
    from pathlib import Path


def test_migration_adds_level_column_to_existing_v1_db(tmp_path: Path):
    """Simulate an existing v1 install — directly build a v1 DB,
    seed a user, then re-open via open_auth_db which triggers
    ensure_schema → _migrate_to_v2."""
    db_path = tmp_path / "_meta" / "auth.db"
    db_path.parent.mkdir(parents=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    _migrate_to_v1(conn)
    conn.execute("PRAGMA user_version = 1")
    # Seed minimal tenant + user using v1 schema.
    conn.execute(
        "INSERT INTO tenants VALUES (?, ?, ?, ?)",
        ("t1", "default", "Default", "2026-01-01T00:00:00Z"),
    )
    conn.execute(
        "INSERT INTO users"
        " (user_id, tenant_id, username, password_hash, pseudonym, role, active, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, 1, ?)",
        ("u1", "t1", "alice", "h", "Alpha-Adler", "curator", "2026-01-01T00:00:00Z"),
    )
    conn.commit()
    conn.close()

    with open_auth_db(tmp_path) as conn:
        ensure_schema(conn)
        row = conn.execute("SELECT level FROM users WHERE user_id = 'u1'").fetchone()
        assert row["level"] == "other"


def test_new_user_default_level(tmp_path: Path):
    from local_pdf.auth.tenants import create_tenant
    from local_pdf.auth.users import create_user

    with open_auth_db(tmp_path) as conn:
        ensure_schema(conn)
        tenant = create_tenant(conn, slug="default", name="Default")
        user = create_user(conn, tenant_id=tenant.tenant_id, username="bob", password="pw")
        assert user.level == "other"


def test_create_user_with_explicit_level(tmp_path: Path):
    from local_pdf.auth.tenants import create_tenant
    from local_pdf.auth.users import create_user

    with open_auth_db(tmp_path) as conn:
        ensure_schema(conn)
        tenant = create_tenant(conn, slug="default", name="Default")
        user = create_user(
            conn, tenant_id=tenant.tenant_id, username="erin", password="pw", level="expert"
        )
        assert user.level == "expert"
