"""Tests for the audit-identity helper + HumanActor email guard."""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import pytest
from goldens.schemas.base import HumanActor
from local_pdf.auth.audit import pseudonym_for_audit


@dataclass(frozen=True)
class _StubIdent:
    pseudonym: str | None = None
    name: str | None = None


def test_audit_prefers_pseudonym() -> None:
    """When both pseudonym and name are set, pseudonym wins."""
    ident = _StubIdent(pseudonym="Klarer Wolf", name="alice")
    assert pseudonym_for_audit(ident) == "Klarer Wolf"


def test_audit_falls_back_to_name() -> None:
    """Legacy curator path may only have name populated."""
    ident = _StubIdent(pseudonym=None, name="alice")
    assert pseudonym_for_audit(ident) == "alice"


def test_audit_returns_anonymous_when_no_identity() -> None:
    """Endpoints without auth (e.g. /api/health) must not crash here."""
    assert pseudonym_for_audit(None) == "anonymous"
    request = SimpleNamespace(state=SimpleNamespace())
    assert pseudonym_for_audit(request) == "anonymous"


def test_audit_unwraps_request_state_identity() -> None:
    """The helper accepts both a Request and an AuthIdentity."""
    ident = _StubIdent(pseudonym="Stiller Fuchs")
    request = SimpleNamespace(state=SimpleNamespace(identity=ident))
    assert pseudonym_for_audit(request) == "Stiller Fuchs"


def test_human_actor_rejects_email_pseudonym() -> None:
    """Defensive: a code path that constructs HumanActor directly must
    not accidentally store an email as the audit identity."""
    with pytest.raises(ValueError, match="email shape"):
        HumanActor(pseudonym="alice@example.com", level="phd")


def test_human_actor_accepts_legit_pseudonym() -> None:
    a = HumanActor(pseudonym="Wachsamer Hirsch", level="expert")
    assert a.pseudonym == "Wachsamer Hirsch"
    assert a.kind == "human"


def test_human_actor_rejects_empty_pseudonym() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        HumanActor(pseudonym="", level="phd")
