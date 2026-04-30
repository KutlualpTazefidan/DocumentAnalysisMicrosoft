from __future__ import annotations

from pathlib import Path  # noqa: TC003

import pytest


def _seed_identity(tmp_xdg: Path, pseudonym: str = "alice", level: str = "phd") -> None:
    cfg = tmp_xdg / "goldens"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "identity.toml").write_text(
        f'schema_version = 1\npseudonym = "{pseudonym}"\nlevel = "{level}"\n'
        f'created_at_utc = "2026-04-30T08:00:00Z"\n',
        encoding="utf-8",
    )


def test_load_or_fail_returns_identity_when_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    _seed_identity(tmp_path)
    from goldens.api.identity import load_or_fail

    ident = load_or_fail()
    assert ident.pseudonym == "alice"
    assert ident.level == "phd"


def test_load_or_fail_raises_on_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    from goldens.api.identity import IdentityNotConfiguredError, load_or_fail

    with pytest.raises(IdentityNotConfiguredError, match=r"identity\.toml"):
        load_or_fail()
