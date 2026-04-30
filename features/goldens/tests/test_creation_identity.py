"""Tests for goldens.creation.identity."""

from __future__ import annotations

import builtins
from collections.abc import Iterator  # noqa: TC003
from pathlib import Path  # noqa: TC003

import pytest
from goldens.creation.identity import (
    Identity,
    identity_to_human_actor,
    load_identity,
    prompt_and_save_identity,
)


@pytest.fixture
def xdg_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    return tmp_path


def _write(xdg_home: Path, body: str) -> Path:
    cfg = xdg_home / "goldens"
    cfg.mkdir(parents=True, exist_ok=True)
    path = cfg / "identity.toml"
    path.write_text(body, encoding="utf-8")
    return path


def _scripted_input(answers: list[str], monkeypatch: pytest.MonkeyPatch) -> None:
    it: Iterator[str] = iter(answers)
    monkeypatch.setattr(builtins, "input", lambda _prompt="": next(it))


def test_load_returns_none_when_file_absent(xdg_home: Path) -> None:
    assert load_identity() is None


def test_load_round_trip_alice_no_special_chars(xdg_home: Path) -> None:
    _write(
        xdg_home,
        'schema_version = 1\npseudonym = "alice"\nlevel = "masters"\n'
        'created_at_utc = "2026-04-29T14:32:00Z"\n',
    )
    identity = load_identity()
    assert identity == Identity(
        schema_version=1,
        pseudonym="alice",
        level="masters",
        created_at_utc="2026-04-29T14:32:00Z",
    )


def test_load_raises_on_invalid_level(xdg_home: Path) -> None:
    _write(
        xdg_home,
        'schema_version = 1\npseudonym = "alice"\nlevel = "guru"\n'
        'created_at_utc = "2026-04-29T14:32:00Z"\n',
    )
    with pytest.raises(ValueError, match="level"):
        load_identity()


def test_load_raises_on_corrupt_toml(xdg_home: Path) -> None:
    _write(xdg_home, "this is not = valid = toml = at all\n[")
    with pytest.raises(ValueError, match="identity"):
        load_identity()


def test_load_raises_on_missing_schema_version(xdg_home: Path) -> None:
    _write(
        xdg_home,
        'pseudonym = "alice"\nlevel = "masters"\ncreated_at_utc = "2026-04-29T14:32:00Z"\n',
    )
    with pytest.raises(ValueError, match="schema_version"):
        load_identity()


def test_load_raises_on_wrong_schema_version(xdg_home: Path) -> None:
    _write(
        xdg_home,
        'schema_version = 99\npseudonym = "alice"\nlevel = "masters"\n'
        'created_at_utc = "2026-04-29T14:32:00Z"\n',
    )
    with pytest.raises(ValueError, match="schema_version"):
        load_identity()


def test_load_raises_on_missing_pseudonym(xdg_home: Path) -> None:
    _write(
        xdg_home,
        'schema_version = 1\nlevel = "masters"\ncreated_at_utc = "2026-04-29T14:32:00Z"\n',
    )
    with pytest.raises(ValueError, match="pseudonym"):
        load_identity()


def test_xdg_config_home_respected_when_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    cfg = tmp_path / "goldens"
    cfg.mkdir()
    (cfg / "identity.toml").write_text(
        'schema_version = 1\npseudonym = "x"\nlevel = "other"\n'
        'created_at_utc = "2026-04-29T14:32:00Z"\n',
        encoding="utf-8",
    )
    assert load_identity() is not None


def test_xdg_config_home_falls_back_to_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    cfg = tmp_path / ".config" / "goldens"
    cfg.mkdir(parents=True)
    (cfg / "identity.toml").write_text(
        'schema_version = 1\npseudonym = "x"\nlevel = "other"\n'
        'created_at_utc = "2026-04-29T14:32:00Z"\n',
        encoding="utf-8",
    )
    assert load_identity() is not None


def test_identity_to_human_actor() -> None:
    identity = Identity(
        schema_version=1,
        pseudonym="alice",
        level="phd",
        created_at_utc="2026-04-29T14:32:00Z",
    )
    actor = identity_to_human_actor(identity)
    assert actor.pseudonym == "alice"
    assert actor.level == "phd"
    assert actor.kind == "human"


def test_prompt_and_save_writes_atomically(xdg_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "goldens.creation.identity.now_utc_iso",
        lambda: "2026-04-29T14:32:00Z",
    )
    _scripted_input(["alice", "masters"], monkeypatch)
    identity = prompt_and_save_identity()
    assert identity.pseudonym == "alice"
    assert identity.level == "masters"
    on_disk = load_identity()
    assert on_disk == identity
    cfg_dir = xdg_home / "goldens"
    assert (cfg_dir / "identity.toml").exists()
    assert not list(cfg_dir.glob("*.tmp"))


def test_prompt_empty_pseudonym_re_prompts_once(
    xdg_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "goldens.creation.identity.now_utc_iso",
        lambda: "2026-04-29T14:32:00Z",
    )
    _scripted_input(["   ", "alice", "masters"], monkeypatch)
    identity = prompt_and_save_identity()
    assert identity.pseudonym == "alice"


def test_prompt_double_empty_pseudonym_exits_with_code_2(
    xdg_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _scripted_input(["", ""], monkeypatch)
    with pytest.raises(SystemExit) as excinfo:
        prompt_and_save_identity()
    assert excinfo.value.code == 2


def test_prompt_invalid_level_re_prompts_once(
    xdg_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "goldens.creation.identity.now_utc_iso",
        lambda: "2026-04-29T14:32:00Z",
    )
    _scripted_input(["alice", "guru", "phd"], monkeypatch)
    identity = prompt_and_save_identity()
    assert identity.level == "phd"


def test_prompt_double_invalid_level_exits_with_code_2(
    xdg_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _scripted_input(["alice", "guru", "wizard"], monkeypatch)
    with pytest.raises(SystemExit) as excinfo:
        prompt_and_save_identity()
    assert excinfo.value.code == 2
