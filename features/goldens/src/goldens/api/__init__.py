"""HTTP API for goldens. See docs/superpowers/specs/2026-04-30-a-plus-1-backend-design.md."""

from __future__ import annotations

# create_app is implemented in app.py (Task 6); we forward-declare here so callers
# can `from goldens.api import create_app`.

__all__ = ["create_app"]


def create_app(*args, **kwargs):
    """Lazy proxy. Real implementation in goldens.api.app.create_app."""
    from goldens.api.app import create_app as real_create_app

    return real_create_app(*args, **kwargs)
