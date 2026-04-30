from __future__ import annotations

from pathlib import Path

import pytest


def test_api_config_loads_from_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("GOLDENS_API_TOKEN", "tok-test")
    monkeypatch.setenv("GOLDENS_DATA_ROOT", str(tmp_path / "outputs"))
    monkeypatch.setenv("GOLDENS_LOG_LEVEL", "debug")
    from goldens.api.config import ApiConfig

    cfg = ApiConfig()
    assert cfg.api_token == "tok-test"
    assert cfg.data_root == tmp_path / "outputs"
    assert cfg.log_level == "debug"


def test_api_config_default_data_root_and_log_level(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOLDENS_API_TOKEN", "tok")
    monkeypatch.delenv("GOLDENS_DATA_ROOT", raising=False)
    monkeypatch.delenv("GOLDENS_LOG_LEVEL", raising=False)
    from goldens.api.config import ApiConfig

    cfg = ApiConfig()
    assert cfg.data_root == Path("outputs")
    assert cfg.log_level == "info"


def test_api_config_missing_token_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GOLDENS_API_TOKEN", raising=False)
    from goldens.api.config import ApiConfig
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ApiConfig()
