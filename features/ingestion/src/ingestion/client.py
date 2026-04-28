"""Factory for the Azure Document Intelligence SDK client.

Construction is parameterised on an IngestionConfig — callers pass the
config they have, no module-level singletons. Tests patch the SDK class here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.core.credentials import AzureKeyCredential

if TYPE_CHECKING:
    from ingestion.config import IngestionConfig


def get_doc_intel_client(cfg: IngestionConfig) -> DocumentIntelligenceClient:
    return DocumentIntelligenceClient(
        endpoint=cfg.doc_intel_endpoint,
        credential=AzureKeyCredential(cfg.doc_intel_key),
    )
