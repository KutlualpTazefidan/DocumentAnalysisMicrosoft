"""Resolve a per-tenant data root inside the shared ``data_root``.

Layout::

    {data_root}/                       # legacy / default-tenant root
    ├── _meta/auth.db                  # shared across tenants
    ├── curators.json                  # legacy single-tenant store
    ├── <slug>/...                     # default-tenant document slugs
    └── tenants/
        ├── {tenant-slug}/             # additional tenants
        │   ├── <slug>/...
        │   └── ...
        └── ...

Resolution rules:
  * ``tenant_slug in (None, "default")`` → returns ``data_root``. This
    keeps every existing path stable for token-mode (legacy) callers
    and for users who never created more than one tenant.
  * Any other slug → returns ``data_root / "tenants" / slug``. The
    directory is created on first access (idempotent).

Callers that need tenant isolation use :func:`tenant_data_root` in
place of ``cfg.data_root``. Routes that don't yet thread tenant
identity through their handlers keep working unchanged thanks to the
legacy fall-through.
"""

from __future__ import annotations

from pathlib import Path  # noqa: TC003

_LEGACY_SLUGS = (None, "", "default")


def tenant_data_root(data_root: Path, tenant_slug: str | None) -> Path:
    """Return the per-tenant root under ``data_root``.

    Creates the directory on first access — write paths under it are
    free to ``mkdir(parents=True, exist_ok=True)`` regardless.
    """
    if tenant_slug in _LEGACY_SLUGS:
        return data_root
    out = data_root / "tenants" / str(tenant_slug)
    out.mkdir(parents=True, exist_ok=True)
    return out


def tenant_slug_from_request(request: object) -> str | None:
    """Pull the active tenant slug off ``request.state.identity``.

    Returns ``None`` for legacy callers (token-mode) and for endpoints
    that bypass auth (e.g. ``/api/health``). Callers feed the result
    into :func:`tenant_data_root` which treats ``None`` as the
    default-tenant alias.
    """
    state = getattr(request, "state", None)
    ident = getattr(state, "identity", None) if state is not None else None
    if ident is None:
        return None
    slug = getattr(ident, "tenant_slug", None)
    return str(slug) if slug else None
