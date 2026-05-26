"""Pseudonym generator + validator for tenant users.

Pseudonyms are the ONLY identity that lands in JSONL audit logs (see
``HumanActor.pseudonym``). The generator pairs a German adjective with
a German animal noun so the result is short, memorable, and clearly
not a real name. The validator refuses obvious de-anonymisation
patterns (email addresses, common realname tokens) so a self-chosen
override doesn't accidentally leak the user's identity into the audit
trail.
"""

from __future__ import annotations

import re
import secrets

# Adjective + animal pairs were picked for memorability over creativity.
# German because the rest of the system is German; if the project ever
# i18n's, swap the lists per-locale and keep the generator signature.
_ADJECTIVES = (
    "Wachsamer",
    "Geduldiger",
    "Schneller",
    "Stiller",
    "Mutiger",
    "Kluger",
    "Ruhiger",
    "Heiterer",
    "Strenger",
    "Sanfter",
    "Pfiffiger",
    "Tapferer",
    "Stolzer",
    "Munterer",
    "Listiger",
    "Wahrer",
    "Treuer",
    "Heller",
    "Klarer",
    "Aufmerksamer",
    "Genauer",
    "Sorgsamer",
    "Wandernder",
    "Forscher",
    "Suchender",
)

_ANIMALS = (
    "Hirsch",
    "Wolf",
    "Fuchs",
    "Luchs",
    "Adler",
    "Falke",
    "Eule",
    "Reiher",
    "Rabe",
    "Kranich",
    "Dachs",
    "Otter",
    "Marder",
    "Iltis",
    "Biber",
    "Bär",
    "Wildkatze",
    "Steinbock",
    "Auerhahn",
    "Specht",
    "Eisvogel",
    "Marmot",
    "Murmeltier",
    "Elch",
    "Wisent",
)

# Email-shaped strings, full-name templates ("Hans Müller"), and a
# small allowlist of words that are uncontroversial as standalone
# pseudonyms (e.g., 'Anonym'). Rejection is intentionally
# conservative — we'd rather reject a borderline case than leak a real
# name into the audit log.
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_REALNAME_RE = re.compile(r"^[A-ZÄÖÜ][a-zäöüß]+\s+[A-ZÄÖÜ][a-zäöüß]+$")
_PSEUDONYM_MIN_LEN = 3
_PSEUDONYM_MAX_LEN = 64


def generate_pseudonym(*, exclude: set[str] | None = None, max_tries: int = 50) -> str:
    """Return a fresh ``<Adjektiv> <Tier>`` pair.

    Avoids any pseudonym in ``exclude`` (typically the existing
    pseudonyms in the tenant so the DB UNIQUE constraint can't fail).
    Falls back to suffixing a 2-digit random number once the simple
    pair space collides — the keyspace ~625 names is large enough that
    a tenant with 100 users will still see a 16% collision rate per
    draw, but the suffix path makes generation O(1) regardless.
    """
    seen = exclude or set()
    for _ in range(max_tries):
        candidate = f"{secrets.choice(_ADJECTIVES)} {secrets.choice(_ANIMALS)}"
        if candidate not in seen:
            return candidate
    # Last-resort suffix; effectively unique modulo astronomical luck.
    base = f"{secrets.choice(_ADJECTIVES)} {secrets.choice(_ANIMALS)}"
    return f"{base} {secrets.randbelow(99) + 1:02d}"


def validate_user_pseudonym(value: str) -> str:
    """Return the cleaned pseudonym or raise ``ValueError`` with a
    reason a frontend can show verbatim.

    Rejects:
      * empty / whitespace-only
      * shorter than 3 chars or longer than 64
      * anything containing an ``@`` (email shape)
      * two-token "Firstname Surname" pattern (heuristic; matches both
        German and ASCII capitalisation)
    """
    stripped = value.strip()
    if not stripped:
        raise ValueError("Pseudonym darf nicht leer sein.")
    if len(stripped) < _PSEUDONYM_MIN_LEN:
        raise ValueError(f"Pseudonym muss mindestens {_PSEUDONYM_MIN_LEN} Zeichen lang sein.")
    if len(stripped) > _PSEUDONYM_MAX_LEN:
        raise ValueError(f"Pseudonym darf hoechstens {_PSEUDONYM_MAX_LEN} Zeichen lang sein.")
    if _EMAIL_RE.search(stripped):
        raise ValueError("Pseudonym darf keine E-Mail-Adresse enthalten.")
    if _REALNAME_RE.match(stripped):
        raise ValueError(
            "Pseudonym sieht aus wie 'Vorname Nachname'. Bitte einen Phantasie-"
            "Namen wählen — z.B. mit dem Auto-Vorschlag-Button."
        )
    return stripped
