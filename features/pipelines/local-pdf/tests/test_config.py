from __future__ import annotations

from pathlib import Path

import pytest


def test_config_loads_from_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("GOLDENS_API_TOKEN", "tok-xyz")
    monkeypatch.setenv("LOCAL_PDF_DATA_ROOT", str(tmp_path / "raw-pdfs"))
    monkeypatch.setenv("LOCAL_PDF_LOG_LEVEL", "debug")
    monkeypatch.setenv("LOCAL_PDF_YOLO_WEIGHTS", str(tmp_path / "weights/doclayout.pt"))
    from local_pdf.api.config import ApiConfig

    cfg = ApiConfig()
    assert cfg.api_token == "tok-xyz"
    assert cfg.data_root == tmp_path / "raw-pdfs"
    assert cfg.log_level == "debug"
    assert cfg.yolo_weights == tmp_path / "weights/doclayout.pt"


def test_config_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOLDENS_API_TOKEN", "tok")
    monkeypatch.delenv("LOCAL_PDF_DATA_ROOT", raising=False)
    monkeypatch.delenv("LOCAL_PDF_LOG_LEVEL", raising=False)
    monkeypatch.delenv("LOCAL_PDF_YOLO_WEIGHTS", raising=False)
    from local_pdf.api.config import ApiConfig

    cfg = ApiConfig()
    assert cfg.data_root == Path("data/raw-pdfs")
    assert cfg.log_level == "info"
    assert cfg.yolo_weights is None


def test_config_missing_token_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GOLDENS_API_TOKEN", raising=False)
    from local_pdf.api.config import ApiConfig
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ApiConfig()
