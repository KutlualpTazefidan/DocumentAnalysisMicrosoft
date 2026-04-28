"""Tests for ingestion.config.IngestionConfig.from_env()."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest


def test_from_env_loads_required_fields(env_vars: dict[str, str]) -> None:
    from ingestion.config import IngestionConfig

    cfg = IngestionConfig.from_env()
    assert cfg.doc_intel_endpoint == env_vars["DOC_INTEL_ENDPOINT"]
    assert cfg.doc_intel_key == env_vars["DOC_INTEL_KEY"]


def test_from_env_is_frozen(env_vars: dict[str, str]) -> None:
    from ingestion.config import IngestionConfig

    cfg = IngestionConfig.from_env()
    with pytest.raises(FrozenInstanceError):
        cfg.doc_intel_endpoint = "x"  # type: ignore[misc]


@pytest.mark.parametrize("missing_var", ["DOC_INTEL_ENDPOINT", "DOC_INTEL_KEY"])
def test_from_env_raises_when_required_missing(
    env_vars: dict[str, str], monkeypatch: pytest.MonkeyPatch, missing_var: str
) -> None:
    from ingestion.config import IngestionConfig

    monkeypatch.delenv(missing_var, raising=False)
    with pytest.raises(KeyError) as excinfo:
        IngestionConfig.from_env()
    assert missing_var in str(excinfo.value)
