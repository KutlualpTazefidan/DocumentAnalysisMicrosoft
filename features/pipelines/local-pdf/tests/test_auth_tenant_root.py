"""Tests for the tenant-scoped data_root helper."""

from __future__ import annotations

from pathlib import Path  # noqa: TC003
from types import SimpleNamespace

from local_pdf.auth.tenant_root import (
    tenant_data_root,
    tenant_slug_from_request,
)


def test_legacy_slug_aliases_return_data_root(tmp_path: Path) -> None:
    """None / '' / 'default' all collapse to the bare data_root so
    legacy callers see no change in path layout."""
    for slug in (None, "", "default"):
        assert tenant_data_root(tmp_path, slug) == tmp_path


def test_real_slug_routes_under_tenants_subdir(tmp_path: Path) -> None:
    out = tenant_data_root(tmp_path, "gns-2026")
    assert out == tmp_path / "tenants" / "gns-2026"
    assert out.exists()  # auto-created


def test_two_tenants_get_isolated_dirs(tmp_path: Path) -> None:
    a = tenant_data_root(tmp_path, "alpha")
    b = tenant_data_root(tmp_path, "beta")
    assert a != b
    assert a.parent == b.parent  # both under data_root/tenants/


def test_tenant_slug_from_request_handles_missing() -> None:
    """No identity on the request -> returns None (= legacy alias)."""
    assert tenant_slug_from_request(None) is None
    blank = SimpleNamespace(state=SimpleNamespace())
    assert tenant_slug_from_request(blank) is None


def test_tenant_slug_from_request_pulls_off_identity() -> None:
    ident = SimpleNamespace(tenant_slug="gns-2026")
    request = SimpleNamespace(state=SimpleNamespace(identity=ident))
    assert tenant_slug_from_request(request) == "gns-2026"


def test_tenant_slug_from_request_returns_none_for_empty() -> None:
    """Legacy token-mode AuthIdentity has tenant_slug=None — must not
    be coerced to the string 'None'."""
    ident = SimpleNamespace(tenant_slug=None)
    request = SimpleNamespace(state=SimpleNamespace(identity=ident))
    assert tenant_slug_from_request(request) is None
