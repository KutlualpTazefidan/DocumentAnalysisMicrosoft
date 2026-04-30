"""Tests for goldens.creation.positions — silent-degrade reads, atomic writes."""

from __future__ import annotations

import multiprocessing
import sys
import tomllib
from pathlib import Path  # noqa: TC003

import pytest
from goldens.creation.positions import read_position, write_position


@pytest.fixture
def xdg_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    return tmp_path


def test_read_returns_none_when_file_absent(xdg_home: Path) -> None:
    assert read_position("doc-a") is None


def test_read_returns_none_when_file_corrupt(xdg_home: Path) -> None:
    cfg = xdg_home / "goldens"
    cfg.mkdir()
    (cfg / "positions.toml").write_text("not = [valid toml", encoding="utf-8")
    assert read_position("doc-a") is None


def test_read_returns_none_when_slug_absent(xdg_home: Path) -> None:
    write_position("other-slug", "p1-deadbeef")
    assert read_position("doc-a") is None


def test_write_creates_file(xdg_home: Path) -> None:
    write_position("doc-a", "p1-deadbeef")
    assert read_position("doc-a") == "p1-deadbeef"


def test_write_updates_existing_slug(xdg_home: Path) -> None:
    write_position("doc-a", "p1-deadbeef")
    write_position("doc-a", "p47-cafebabe")
    assert read_position("doc-a") == "p47-cafebabe"


def test_write_preserves_other_slugs(xdg_home: Path) -> None:
    write_position("doc-a", "p1-deadbeef")
    write_position("doc-b", "p2-cafebabe")
    assert read_position("doc-a") == "p1-deadbeef"
    assert read_position("doc-b") == "p2-cafebabe"


def test_xdg_config_home_falls_back_to_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    write_position("doc-a", "p1-deadbeef")
    assert (tmp_path / ".config" / "goldens" / "positions.toml").exists()
    assert read_position("doc-a") == "p1-deadbeef"


def test_slug_with_hyphens_round_trips(xdg_home: Path) -> None:
    write_position("tragkorb-b-147-2001-rev-1", "p47-a3f8b2c1")
    assert read_position("tragkorb-b-147-2001-rev-1") == "p47-a3f8b2c1"
    body = (xdg_home / "goldens" / "positions.toml").read_text(encoding="utf-8")
    assert tomllib.loads(body) == {
        "schema_version": 1,
        "positions": {"tragkorb-b-147-2001-rev-1": "p47-a3f8b2c1"},
    }


def _writer_process(xdg_root: str, slug: str, element_id: str, n: int) -> None:
    import os as _os

    _os.environ["XDG_CONFIG_HOME"] = xdg_root
    from goldens.creation.positions import write_position as _wp

    for _ in range(n):
        _wp(slug, element_id)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX rename semantics required")
def test_write_atomic_under_concurrent_writers(xdg_home: Path) -> None:
    procs = [
        multiprocessing.Process(
            target=_writer_process, args=(str(xdg_home), "doc-a", "p1-aaaaaaaa", 30)
        ),
        multiprocessing.Process(
            target=_writer_process, args=(str(xdg_home), "doc-b", "p2-bbbbbbbb", 30)
        ),
    ]
    for p in procs:
        p.start()
    for p in procs:
        p.join(timeout=30)
        assert p.exitcode == 0, f"writer crashed: exit={p.exitcode}"
    body = (xdg_home / "goldens" / "positions.toml").read_text(encoding="utf-8")
    parsed = tomllib.loads(body)
    assert parsed["positions"]["doc-a"] == "p1-aaaaaaaa"
    assert parsed["positions"]["doc-b"] == "p2-bbbbbbbb"
