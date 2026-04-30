"""Curator profile (~/.config/goldens/identity.toml).

`load_identity()` returns None on first run (file absent) and raises
ValueError on any schema violation — identity is consent-bearing data,
silent defaults are wrong here. (D15.)

`prompt_and_save_identity()` is the first-run interactive prompt
(landed in Task 8).
"""

from __future__ import annotations

import os
import sys
import tempfile
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from goldens.creation._time import now_utc_iso
from goldens.creation._toml import dump_toml
from goldens.schemas import HumanActor

_VALID_LEVELS: frozenset[str] = frozenset({"expert", "phd", "masters", "bachelors", "other"})

Level = Literal["expert", "phd", "masters", "bachelors", "other"]

_INTRO_NOTE = (
    "Wir speichern ein Pseudonym, keinen Klarnamen. Niveau-Selbsteinschätzung "
    "dient nur dem Gewichten der Reviews."
)


@dataclass(frozen=True)
class Identity:
    schema_version: int
    pseudonym: str
    level: Level
    created_at_utc: str


def _config_dir() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME") or ""
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "goldens"


def _identity_path() -> Path:
    return _config_dir() / "identity.toml"


def load_identity() -> Identity | None:
    path = _identity_path()
    if not path.exists():
        return None
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as e:
        raise ValueError(f"corrupt identity.toml at {path}: {e}") from e
    if "schema_version" not in raw:
        raise ValueError(f"identity.toml missing schema_version (at {path})")
    if raw["schema_version"] != 1:
        raise ValueError(
            f"identity.toml schema_version {raw['schema_version']!r} not supported (at {path})"
        )
    for key in ("pseudonym", "level", "created_at_utc"):
        if key not in raw:
            raise ValueError(f"identity.toml missing {key!r} (at {path})")
    if raw["level"] not in _VALID_LEVELS:
        raise ValueError(
            f"identity.toml level {raw['level']!r} not in {sorted(_VALID_LEVELS)} (at {path})"
        )
    return Identity(
        schema_version=raw["schema_version"],
        pseudonym=raw["pseudonym"],
        level=raw["level"],
        created_at_utc=raw["created_at_utc"],
    )


def identity_to_human_actor(identity: Identity) -> HumanActor:
    return HumanActor(pseudonym=identity.pseudonym, level=identity.level)


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = tempfile.NamedTemporaryFile(  # noqa: SIM115
        "w",
        dir=str(path.parent),
        prefix=path.name + ".",
        suffix=".tmp",
        delete=False,
        encoding="utf-8",
    )
    try:
        tmp.write(text)
        tmp.flush()
        os.fsync(tmp.fileno())
    finally:
        tmp.close()
    os.replace(tmp.name, path)


def _prompt_pseudonym() -> str:
    raw = input("Pseudonym: ").strip()
    if raw:
        return raw
    raw = input("Pseudonym (nicht leer): ").strip()
    if raw:
        return raw
    print("leeres Pseudonym zweimal eingegeben — Abbruch", file=sys.stderr)
    raise SystemExit(2)


def _prompt_level() -> Level:
    options = "expert | phd | masters | bachelors | other"
    raw = input(f"Niveau [{options}]: ").strip()
    if raw in _VALID_LEVELS:
        return raw  # type: ignore[return-value]
    raw = input(f"Niveau (eines aus {options}): ").strip()
    if raw in _VALID_LEVELS:
        return raw  # type: ignore[return-value]
    print("ungültiges Level zweimal eingegeben — Abbruch", file=sys.stderr)
    raise SystemExit(2)


def prompt_and_save_identity() -> Identity:
    """First-run interactive prompt → write identity.toml → return Identity."""
    print(_INTRO_NOTE)
    pseudonym = _prompt_pseudonym()
    level = _prompt_level()
    identity = Identity(
        schema_version=1,
        pseudonym=pseudonym,
        level=level,
        created_at_utc=now_utc_iso(),
    )
    body = dump_toml(
        {
            "schema_version": identity.schema_version,
            "pseudonym": identity.pseudonym,
            "level": identity.level,
            "created_at_utc": identity.created_at_utc,
        }
    )
    _atomic_write(_identity_path(), body)
    return identity
