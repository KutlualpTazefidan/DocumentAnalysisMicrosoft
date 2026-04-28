"""Public API for the query_index package.

Exports the search/chunk/embedding interface plus the Azure-client factories
needed by sibling packages (e.g., `ingestion`) under the strict-boundary rule.
The OpenAI client factory remains internal (no consumer outside this package
needs it directly).
"""

from query_index.chunks import get_chunk, sample_chunks
from query_index.client import get_search_client, get_search_index_client
from query_index.config import Config
from query_index.embeddings import get_embedding
from query_index.index_schema import build_canonical_index_schema
from query_index.search import hybrid_search
from query_index.types import Chunk, SearchHit

__all__ = [
    "Chunk",
    "Config",
    "SearchHit",
    "build_canonical_index_schema",
    "get_chunk",
    "get_embedding",
    "get_search_client",
    "get_search_index_client",
    "hybrid_search",
    "sample_chunks",
]
