"""Hybrid (text + vector) search over the configured Azure AI Search index."""

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
    """Run a hybrid (text + vector) search.

    Returns up to `top` SearchHits ranked by Azure's hybrid scoring. The
    `filter` argument, if given, is passed through as an OData filter
    expression. The chunk text is included in each SearchHit but is
    repr-suppressed (see types.py).
    """
    if cfg is None:
        cfg = Config.from_env()
    vector = get_embedding(query, cfg)
    vector_query = VectorizedQuery(
        vector=vector,
        k_nearest_neighbors=top,
        fields="text_vector",
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
                chunk_id=r["chunk_id"],
                title=r["title"],
                chunk=r["chunk"],
                score=float(r.get("@search.score", 0.0)),
            )
        )
    return hits
