"""Hybrid (text + vector) search over the configured Azure AI Search index.

Reads the canonical notebook schema: `id`, `chunk`, `title`, `chunkVector`,
optional `section_heading`, optional `source_file`.
"""

from __future__ import annotations

from azure.search.documents.models import VectorizedQuery

from query_index.client import get_search_client
from query_index.config import Config
from query_index.embeddings import get_embedding
from query_index.types import SearchHit


def hybrid_search(
    query: str,
    top: int = 10,
    filter: str | None = None,
    cfg: Config | None = None,
) -> list[SearchHit]:
    if cfg is None:
        cfg = Config.from_env()
    vector = get_embedding(query, cfg)
    vector_query = VectorizedQuery(
        vector=vector,
        k_nearest_neighbors=top,
        fields="chunkVector",
    )
    search_client = get_search_client(cfg)
    results = search_client.search(
        search_text=query,
        vector_queries=[vector_query],
        top=top,
        filter=filter,
    )

    hits: list[SearchHit] = []
    for r in results:
        hits.append(
            SearchHit(
                chunk_id=r["id"],
                title=r["title"],
                chunk=r["chunk"],
                score=float(r.get("@search.score", 0.0)),
                section_heading=r.get("section_heading"),
                source_file=r.get("source_file"),
            )
        )
    return hits
