"""Tests for tenant CRUD."""

from __future__ import annotations

from pathlib import Path  # noqa: TC003

import pytest
from local_pdf.auth.db import ensure_schema, open_auth_db
from local_pdf.auth.tenants import (
    create_tenant,
    get_tenant_by_id,
    get_tenant_by_slug,
    list_tenants,
    validate_slug,
)


def _conn_ctx(tmp_path: Path):
    return open_auth_db(tmp_path)


def test_create_and_lookup_tenant(tmp_path: Path) -> None:
    with _conn_ctx(tmp_path) as conn:
        ensure_schema(conn)
        t = create_tenant(conn, slug="default", name="Default")
        assert t.slug == "default"
        assert t.tenant_id.startswith("t-")
        assert get_tenant_by_slug(conn, "default").tenant_id == t.tenant_id
        assert get_tenant_by_id(conn, t.tenant_id).slug == "default"


def test_get_returns_none_when_missing(tmp_path: Path) -> None:
    with _conn_ctx(tmp_path) as conn:
        ensure_schema(conn)
        assert get_tenant_by_slug(conn, "nope") is None
        assert get_tenant_by_id(conn, "t-fake") is None


def test_duplicate_slug_raises(tmp_path: Path) -> None:
    with _conn_ctx(tmp_path) as conn:
        ensure_schema(conn)
        create_tenant(conn, slug="default", name="Default")
        with pytest.raises(ValueError, match="bereits vergeben"):
            create_tenant(conn, slug="default", name="Another")


def test_list_tenants_ordered_by_created_at(tmp_path: Path) -> None:
    with _conn_ctx(tmp_path) as conn:
        ensure_schema(conn)
        create_tenant(conn, slug="a", name="A")
        create_tenant(conn, slug="b", name="B")
        slugs = [t.slug for t in list_tenants(conn)]
    assert slugs == ["a", "b"]


def test_slug_validator_rejects_bad_input() -> None:
    with pytest.raises(ValueError):
        validate_slug("UPPER")
    with pytest.raises(ValueError):
        validate_slug("-leading-dash")
    with pytest.raises(ValueError):
        validate_slug("trailing-dash-")
    with pytest.raises(ValueError):
        validate_slug("contains_underscore")
    with pytest.raises(ValueError):
        validate_slug("")
    # Valid:
    assert validate_slug("a") == "a"
    assert validate_slug("gns-2026") == "gns-2026"


def test_empty_name_rejected(tmp_path: Path) -> None:
    with _conn_ctx(tmp_path) as conn:
        ensure_schema(conn)
        with pytest.raises(ValueError, match="leer"):
            create_tenant(conn, slug="x", name="   ")
