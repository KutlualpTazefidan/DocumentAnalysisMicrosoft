"""Boot-time identity loading for the API.

The API uses ONE identity for all event-writing — the curator running the
server. Fail loud if no identity.toml exists; the user must run
`query-eval curate` once first to bootstrap, or write the file manually.
"""

from __future__ import annotations

from goldens.creation.identity import Identity, load_identity


class IdentityNotConfiguredError(RuntimeError):
    """Raised at server boot when ~/.config/goldens/identity.toml is absent."""


def load_or_fail() -> Identity:
    ident = load_identity()
    if ident is None:
        raise IdentityNotConfiguredError(
            "identity.toml missing — run `query-eval curate` once to bootstrap, "
            "or write ~/.config/goldens/identity.toml manually."
        )
    return ident
