"""Public API for the query_index package.

Internal modules (client, schema_discovery, ingest helpers) are NOT re-exported.
"""

from query_index.chunks import get_chunk, sample_chunks
from query_index.config import Config
from query_index.embeddings import get_embedding
from query_index.search import hybrid_search
from query_index.types import Chunk, SearchHit

__all__ = [
    "Chunk",
    "Config",
    "SearchHit",
    "get_chunk",
    "get_embedding",
    "hybrid_search",
    "sample_chunks",
]
