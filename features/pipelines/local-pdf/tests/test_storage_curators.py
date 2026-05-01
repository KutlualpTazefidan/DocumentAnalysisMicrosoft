from __future__ import annotations

import hashlib
from pathlib import Path  # noqa: TC003


def test_read_curators_returns_empty_when_missing(tmp_path: Path) -> None:
    from local_pdf.storage.curators import read_curators

    out = read_curators(tmp_path)
    assert out.curators == []


def test_write_then_read_round_trip(tmp_path: Path) -> None:
    from local_pdf.api.schemas import Curator, CuratorsFile
    from local_pdf.storage.curators import read_curators, write_curators

    c = Curator(
        id="c-abc1",
        name="Doktor Müller",
        token_prefix="aabb1122",
        token_sha256=hashlib.sha256(b"raw-token").hexdigest(),
        assigned_slugs=["spec"],
        created_at="2026-05-01T12:00:00Z",
        last_seen_at=None,
        active=True,
    )
    write_curators(tmp_path, CuratorsFile(curators=[c]))
    out = read_curators(tmp_path)
    assert len(out.curators) == 1
    assert out.curators[0].id == "c-abc1"
    assert out.curators[0].assigned_slugs == ["spec"]


def test_curator_helpers(tmp_path: Path) -> None:
    from local_pdf.storage.curators import (
        find_by_token_hash,
        hash_token,
        new_curator_id,
        new_token,
        token_prefix,
    )

    raw = new_token()
    assert len(raw) == 32
    h = hash_token(raw)
    assert len(h) == 64
    pref = token_prefix(raw)
    assert pref == raw[-8:]
    cid = new_curator_id()
    assert cid.startswith("c-") and len(cid) == 6

    from local_pdf.api.schemas import Curator, CuratorsFile
    from local_pdf.storage.curators import write_curators

    c = Curator(
        id=cid,
        name="X",
        token_prefix=pref,
        token_sha256=h,
        assigned_slugs=[],
        created_at="t",
        last_seen_at=None,
        active=True,
    )
    write_curators(tmp_path, CuratorsFile(curators=[c]))
    found = find_by_token_hash(tmp_path, h)
    assert found is not None and found.id == cid
    assert find_by_token_hash(tmp_path, "0" * 64) is None
