"""SQLite connection + idempotent schema migration for the auth store.

The DB file lives at ``{data_root}/_meta/auth.db`` and is chmod 0600 so
only the process owner can read it. WAL mode is enabled for concurrent
readers (the auth check runs on every request); a single writer at a
time is fine for the expected single-machine workload.

Schema version is tracked in PRAGMA user_version so future migrations
land in this module rather than on the operator's plate.
"""

from __future__ import annotations

import contextlib
import os
import sqlite3
from collections.abc import Iterator  # noqa: TC003
from contextlib import contextmanager
from pathlib import Path  # noqa: TC003

# Bumped on every schema change. ``ensure_schema`` no-ops when the DB
# is already at this version; future versions add migrations here.
_SCHEMA_VERSION = 1


def auth_db_path(data_root: Path) -> Path:
    """Return ``{data_root}/_meta/auth.db``.

    Pure path computation; does not touch the filesystem. Callers
    create the parent directory on first write.
    """
    return data_root / "_meta" / "auth.db"


@contextmanager
def open_auth_db(data_root: Path) -> Iterator[sqlite3.Connection]:
    """Open the auth DB at ``{data_root}/_meta/auth.db``.

    Ensures the parent directory exists, applies chmod 0600 to a
    freshly-created file, enables WAL + foreign keys, and yields a
    standard sqlite3 connection. Auto-commits and closes on exit.

    Row factory is :class:`sqlite3.Row` so callers can read columns by
    name (``row["username"]``) — robust against column reordering in
    later migrations.
    """
    path = auth_db_path(data_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    created = not path.exists()
    conn = sqlite3.connect(
        path,
        isolation_level=None,  # autocommit; explicit BEGIN/COMMIT via SQL
        detect_types=sqlite3.PARSE_DECLTYPES,
    )
    if created:
        # Best-effort: on non-POSIX file systems chmod can no-op or
        # raise. The DB still sits inside data_root which the operator
        # is expected to keep private.
        with contextlib.suppress(OSError):
            os.chmod(path, 0o600)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA synchronous = NORMAL")
        yield conn
    finally:
        conn.close()


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Idempotent schema-creation + migration.

    Reads ``PRAGMA user_version`` and applies whatever the gap is up
    to ``_SCHEMA_VERSION``. Today there's only one version; the
    structure below is so the next change ships as a clean migration
    rather than an in-place edit.
    """
    current = int(conn.execute("PRAGMA user_version").fetchone()[0])
    if current >= _SCHEMA_VERSION:
        return
    if current < 1:
        _migrate_to_v1(conn)
    conn.execute(f"PRAGMA user_version = {_SCHEMA_VERSION}")


def _migrate_to_v1(conn: sqlite3.Connection) -> None:
    """Initial schema: tenants, users, sessions, failed_logins."""
    conn.executescript(
        """
        BEGIN;

        CREATE TABLE tenants (
            tenant_id     TEXT PRIMARY KEY,
            slug          TEXT NOT NULL UNIQUE,
            name          TEXT NOT NULL,
            created_at    TEXT NOT NULL
        );

        CREATE TABLE users (
            user_id            TEXT PRIMARY KEY,
            tenant_id          TEXT NOT NULL,
            username           TEXT NOT NULL,
            password_hash      TEXT NOT NULL,
            pseudonym          TEXT NOT NULL,
            role               TEXT NOT NULL CHECK (role IN ('admin', 'reviewer', 'curator')),
            active             INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
            created_at         TEXT NOT NULL,
            last_login_at      TEXT,
            FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id) ON DELETE CASCADE,
            UNIQUE (tenant_id, username),
            UNIQUE (tenant_id, pseudonym)
        );
        CREATE INDEX idx_users_tenant ON users(tenant_id);

        CREATE TABLE sessions (
            session_id    TEXT PRIMARY KEY,
            user_id       TEXT NOT NULL,
            created_at    TEXT NOT NULL,
            expires_at    TEXT NOT NULL,
            revoked       INTEGER NOT NULL DEFAULT 0 CHECK (revoked IN (0, 1)),
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
        );
        CREATE INDEX idx_sessions_user ON sessions(user_id);
        CREATE INDEX idx_sessions_expires ON sessions(expires_at);

        -- Failed-login counter per (tenant, username). When the count
        -- crosses the threshold within the lockout window, login is
        -- temporarily refused. Window + threshold live in code, not
        -- schema, so they can be tuned without a migration.
        CREATE TABLE failed_logins (
            tenant_id     TEXT NOT NULL,
            username      TEXT NOT NULL,
            attempts      INTEGER NOT NULL DEFAULT 0,
            last_attempt  TEXT NOT NULL,
            lockout_until TEXT,
            PRIMARY KEY (tenant_id, username)
        );

        COMMIT;
        """
    )
