"""Per-document curate-position cache (~/.config/goldens/positions.toml).

Reads silent-degrade: any failure path yields None, the caller restarts
at element 0. Writes are atomic (tmp + os.replace within the same
directory) so a crash mid-write cannot tear the file. (D15.)
"""

from __future__ import annotations

import os
import tempfile
import tomllib
from pathlib import Path

from goldens.creation._toml import dump_toml


def _config_dir() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME") or ""
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "goldens"


def _positions_path() -> Path:
    return _config_dir() / "positions.toml"


def _read_all() -> dict[str, str]:
    path = _positions_path()
    if not path.exists():
        return {}
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError:
        return {}
    positions = raw.get("positions")
    if not isinstance(positions, dict):
        return {}
    return {k: v for k, v in positions.items() if isinstance(v, str)}


def read_position(slug: str) -> str | None:
    return _read_all().get(slug)


def write_position(slug: str, element_id: str) -> None:
    positions = _read_all()
    positions[slug] = element_id
    body = dump_toml({"schema_version": 1, "positions": positions})
    path = _positions_path()
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
        tmp.write(body)
        tmp.flush()
        os.fsync(tmp.fileno())
    finally:
        tmp.close()
    os.replace(tmp.name, path)
