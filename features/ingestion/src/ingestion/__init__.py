"""Public API for the ingestion package."""

from ingestion.analyze import analyze_pdf
from ingestion.chunk import chunk
from ingestion.chunkers.base import RawChunk
from ingestion.chunkers.registry import get_chunker, list_strategies
from ingestion.config import IngestionConfig
from ingestion.embed import embed_chunks
from ingestion.slug import slug_from_filename
from ingestion.upload import upload_chunks

__all__ = [
    "IngestionConfig",
    "RawChunk",
    "analyze_pdf",
    "chunk",
    "embed_chunks",
    "get_chunker",
    "list_strategies",
    "slug_from_filename",
    "upload_chunks",
]
