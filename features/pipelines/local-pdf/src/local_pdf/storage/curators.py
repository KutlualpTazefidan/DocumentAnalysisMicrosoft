"""fcntl-locked read/write of `data/curators.json`.

Schema:
    {
      "curators": [
        {
          "id": "c-abc1",
          "name": "Doktor Müller",
          "token_prefix": "<last 8 chars of full token>",
          "token_sha256": "<hex hash>",
          "assigned_slugs": ["..."],
          "created_at": "ISO-8601",
          "last_seen_at": "ISO-8601 | None",
          "active": true
        }
      ]
    }
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import secrets
from pathlib import Path  # noqa: TC003

from local_pdf.api.schemas import Curator, CuratorsFile


def _path(data_root: Path) -> Path:
    return data_root / "curators.json"


def read_curators(data_root: Path) -> CuratorsFile:
    p = _path(data_root)
    if not p.exists():
        return CuratorsFile(curators=[])
    raw = p.read_text(encoding="utf-8")
    return CuratorsFile.model_validate(json.loads(raw))  # type: ignore[no-any-return]


def write_curators(data_root: Path, curators: CuratorsFile) -> None:
    p = _path(data_root)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(curators.model_dump(mode="json"), ensure_ascii=False, indent=2)
    tmp = p.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    os.replace(tmp, p)


def new_token() -> str:
    return secrets.token_hex(16)


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def token_prefix(raw: str) -> str:
    return raw[-8:]


def new_curator_id() -> str:
    return f"c-{secrets.token_hex(2)}"


def find_by_token_hash(data_root: Path, token_hash: str) -> Curator | None:
    cf = read_curators(data_root)
    for c in cf.curators:
        if c.active and c.token_sha256 == token_hash:
            return c
    return None
