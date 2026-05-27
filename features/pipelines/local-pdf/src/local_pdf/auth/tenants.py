"""Tenant CRUD.

Tenants are independent workspaces inside the local data_root. Each
tenant has its own user table (UNIQUE on (tenant_id, username)) and
its own data partition under ``data_root/tenants/{slug}/``.

This module owns the SQLite write surface; callers go through these
functions rather than crafting SQL inline so future Postgres migration
has one place to refactor.
"""

from __future__ import annotations

import re
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime

# Slugs are used as URL path segments AND as directory names under
# data_root/tenants/, so the allowed character set is intentionally
# tight: lowercase ASCII + digits + dashes.
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$|^[a-z0-9]$")


@dataclass(frozen=True)
class Tenant:
    tenant_id: str
    slug: str
    name: str
    created_at: str


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _new_tenant_id() -> str:
    return f"t-{secrets.token_hex(4)}"


def validate_slug(slug: str) -> str:
    """Return the slug or raise ``ValueError`` with a UI-friendly hint."""
    if not _SLUG_RE.match(slug):
        raise ValueError(
            f"Ungueltiger Tenant-Slug: {slug!r}. Erlaubt: 1-64 Zeichen, nur "
            "Kleinbuchstaben/Ziffern/Bindestrich, weder am Anfang noch am Ende "
            "ein Bindestrich."
        )
    return slug


def create_tenant(conn: sqlite3.Connection, *, slug: str, name: str) -> Tenant:
    """Insert a new tenant. Raises ``ValueError`` on slug clash so the
    caller can surface a 409 rather than a generic 500.
    """
    slug = validate_slug(slug)
    if not name.strip():
        raise ValueError("Tenant-Name darf nicht leer sein.")
    tenant_id = _new_tenant_id()
    created_at = _now()
    try:
        conn.execute(
            "INSERT INTO tenants (tenant_id, slug, name, created_at) VALUES (?, ?, ?, ?)",
            (tenant_id, slug, name.strip(), created_at),
        )
    except sqlite3.IntegrityError as exc:
        raise ValueError(f"Tenant-Slug bereits vergeben: {slug!r}") from exc
    return Tenant(tenant_id=tenant_id, slug=slug, name=name.strip(), created_at=created_at)


def get_tenant_by_slug(conn: sqlite3.Connection, slug: str) -> Tenant | None:
    row = conn.execute(
        "SELECT tenant_id, slug, name, created_at FROM tenants WHERE slug = ?",
        (slug,),
    ).fetchone()
    if row is None:
        return None
    return Tenant(
        tenant_id=row["tenant_id"],
        slug=row["slug"],
        name=row["name"],
        created_at=row["created_at"],
    )


def get_tenant_by_id(conn: sqlite3.Connection, tenant_id: str) -> Tenant | None:
    row = conn.execute(
        "SELECT tenant_id, slug, name, created_at FROM tenants WHERE tenant_id = ?",
        (tenant_id,),
    ).fetchone()
    if row is None:
        return None
    return Tenant(
        tenant_id=row["tenant_id"],
        slug=row["slug"],
        name=row["name"],
        created_at=row["created_at"],
    )


def update_tenant_name(conn: sqlite3.Connection, *, slug: str, name: str) -> Tenant:
    """Update the display name. The slug is immutable — it partitions
    ``data_root/tenants/{slug}/`` and is referenced by every user row.
    """
    if not name.strip():
        raise ValueError("Tenant-Name darf nicht leer sein.")
    cur = conn.execute(
        "UPDATE tenants SET name = ? WHERE slug = ?",
        (name.strip(), slug),
    )
    if cur.rowcount == 0:
        raise ValueError(f"Tenant nicht gefunden: {slug!r}")
    out = get_tenant_by_slug(conn, slug)
    assert out is not None  # just-updated row must exist
    return out


def delete_tenant(conn: sqlite3.Connection, *, slug: str) -> None:
    """Hard-delete a tenant. Users + sessions cascade via FK
    ``ON DELETE CASCADE``. Files under ``data_root/tenants/{slug}/``
    are NOT touched — the caller can wipe them manually if desired.
    """
    cur = conn.execute("DELETE FROM tenants WHERE slug = ?", (slug,))
    if cur.rowcount == 0:
        raise ValueError(f"Tenant nicht gefunden: {slug!r}")


def list_tenants(conn: sqlite3.Connection) -> list[Tenant]:
    rows = conn.execute(
        "SELECT tenant_id, slug, name, created_at FROM tenants ORDER BY created_at"
    ).fetchall()
    return [
        Tenant(
            tenant_id=r["tenant_id"],
            slug=r["slug"],
            name=r["name"],
            created_at=r["created_at"],
        )
        for r in rows
    ]
