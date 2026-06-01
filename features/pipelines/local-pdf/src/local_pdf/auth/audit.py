"""Helpers for resolving the audit-safe identity at request time.

JSONL audit logs must NEVER carry the real username. Every write path
that records an actor goes through :func:`pseudonym_for_audit` so a
future refactor that accidentally reaches for ``ident.username`` is
visible in code review (the helper has no such return path).

Today the auth middleware mirrors ``pseudonym`` into ``name`` for
both cookie-mode and token-mode identities — calling
``pseudonym_for_audit`` on legacy callers returns the same value as
``ident.name`` and remains safe.
"""

from __future__ import annotations

from typing import Any


def pseudonym_for_audit(request_or_identity: Any) -> str:
    """Return the audit-safe identity string.

    Accepts either a FastAPI ``Request`` (read ``request.state.identity``)
    or an ``AuthIdentity`` directly. Resolution order:

      1. ``identity.pseudonym``   — preferred; set by both cookie + token
                                    middleware paths.
      2. ``identity.name``        — legacy fallback; mirrored from
                                    pseudonym today, kept as a safety net.
      3. ``"anonymous"``          — final fallback so callers never get a
                                    null actor in the JSONL.

    Never returns a real username because the middleware does not put
    one on the identity object in the first place. If a future change
    introduces a ``username`` field, this helper will still pick
    ``pseudonym`` thanks to the explicit attribute order.
    """
    ident = getattr(request_or_identity, "state", None)
    ident = getattr(ident, "identity", None) if ident is not None else request_or_identity
    if ident is None:
        return "anonymous"
    pseudonym = getattr(ident, "pseudonym", None)
    if pseudonym:
        return str(pseudonym)
    name = getattr(ident, "name", None)
    if name:
        return str(name)
    return "anonymous"
