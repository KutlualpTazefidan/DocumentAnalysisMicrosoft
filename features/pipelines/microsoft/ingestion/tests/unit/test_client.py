"""Tests for ingestion.client lazy-construction helpers."""

from __future__ import annotations

from unittest.mock import patch


def test_get_doc_intel_client_constructs_with_config(env_vars: dict[str, str]) -> None:
    from ingestion.client import get_doc_intel_client
    from ingestion.config import IngestionConfig

    cfg = IngestionConfig.from_env()
    with (
        patch("ingestion.client.DocumentIntelligenceClient") as mock_cls,
        patch("ingestion.client.AzureKeyCredential") as mock_cred,
    ):
        mock_cred.return_value = "credential-instance"
        get_doc_intel_client(cfg)
    mock_cred.assert_called_once_with(cfg.doc_intel_key)
    mock_cls.assert_called_once_with(
        endpoint=cfg.doc_intel_endpoint,
        credential="credential-instance",
    )
