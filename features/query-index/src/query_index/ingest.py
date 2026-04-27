"""Populate an Azure AI Search index from a directory of source documents.

This is the simplest possible ingestion: each file in `source_path` becomes
one chunk, with `chunk_id` derived from the filename stem. Logs are
metadata-only — chunk text is never printed, written, or otherwise emitted
to anything other than the Azure upload payload.

Real ingestion (chunking by paragraph, embedding metadata, deduplication)
is a separate concern handled outside this package.
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

from query_index.client import get_search_client
from query_index.config import Config
from query_index.embeddings import get_embedding

if TYPE_CHECKING:
    from pathlib import Path


def _normalize(text: str) -> str:
    return " ".join(text.split())


def _hash(text: str) -> str:
    return "sha256:" + hashlib.sha256(_normalize(text).encode("utf-8")).hexdigest()


def populate_index(source_path: Path, cfg: Config | None = None) -> None:
    if not source_path.exists():
        raise FileNotFoundError(f"source_path does not exist: {source_path}")
    if cfg is None:
        cfg = Config.from_env()

    documents = []
    for file in sorted(source_path.iterdir()):
        if not file.is_file():
            continue
        chunk_text = file.read_text(encoding="utf-8")
        embedding = get_embedding(chunk_text, cfg)
        chunk_id = file.stem
        documents.append(
            {
                "chunk_id": chunk_id,
                "title": file.name,
                "chunk": chunk_text,
                "text_vector": embedding,
            }
        )
        print(f"Prepared chunk_id={chunk_id} size={len(chunk_text)} hash={_hash(chunk_text)}")

    if not documents:
        print("No source files found; nothing to upload.")
        return

    client = get_search_client(cfg)
    client.upload_documents(documents=documents)
    print(f"Uploaded {len(documents)} documents to index {cfg.ai_search_index_name}")
