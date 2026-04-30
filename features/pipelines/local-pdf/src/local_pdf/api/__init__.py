"""HTTP API for local-pdf. See docs/superpowers/specs/2026-04-30-local-pdf-pipeline-design.md."""

from __future__ import annotations

__all__ = ["create_app"]


def create_app(*args, **kwargs):
    from local_pdf.api.app import create_app as real

    return real(*args, **kwargs)
