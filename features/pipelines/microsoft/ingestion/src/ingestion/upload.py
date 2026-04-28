"""CLI-stage handler for the upload pipeline step.

Reads an embedded JSONL, ensures the Azure AI Search index exists with the
canonical schema, deletes only the chunks for this file's source_file, and
uploads the new chunks. Multi-doc cumulative.
"""

from __future__ import annotations

import contextlib
import json
from typing import TYPE_CHECKING

from azure.core.exceptions import ResourceNotFoundError
from query_index import build_canonical_index_schema, get_search_client, get_search_index_client

if TYPE_CHECKING:
    from pathlib import Path

    from query_index import Config


_BATCH_SIZE = 100


def _escape_odata_string(s: str) -> str:
    """Per OData rules, single quotes inside a literal are doubled."""
    return s.replace("'", "''")


def _ensure_index_exists(index_client, index_name: str, embedding_dimensions: int) -> None:
    """Create the index if it does not exist; no-op otherwise."""
    try:
        index_client.get_index(index_name)
    except ResourceNotFoundError:
        index_client.create_index(build_canonical_index_schema(index_name, embedding_dimensions))


def _delete_existing_chunks_for_source(search_client, source_file: str) -> int:
    """Find all chunks where source_file == <given>, delete by their ids."""
    escaped = _escape_odata_string(source_file)
    results = search_client.search(
        search_text="*",
        filter=f"source_file eq '{escaped}'",
        select=["id"],
        top=10000,
    )
    ids = [{"id": r["id"]} for r in results]
    if ids:
        search_client.delete_documents(documents=ids)
    return len(ids)


def _embedded_to_index_doc(record: dict) -> dict:
    """Map the embedded-JSONL line shape to the Azure index document shape."""
    return {
        "id": record["chunk_id"],
        "title": record["title"],
        "section_heading": record["section_heading"],
        "chunk": record["chunk"],
        "source_file": record["source_file"],
        "chunkVector": record["vector"],
    }


def upload_chunks(
    in_path: Path,
    index_name: str | None = None,
    force_recreate: bool = False,
    cfg: Config | None = None,
) -> int:
    """Upload embedded chunks to the Azure AI Search index.

    - If `force_recreate`: drop the entire index, create fresh, upload.
    - Else: ensure index exists (create if not), delete existing chunks where
      source_file matches this file's source_file, then upload.

    Returns the number of chunks uploaded.
    """
    if cfg is None:
        from query_index import Config as _Cfg

        cfg = _Cfg.from_env()
    if index_name is None:
        index_name = cfg.ai_search_index_name

    # Load all records, determine source_file from first line
    records: list[dict] = []
    with in_path.open("r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if line:
                records.append(json.loads(line))

    if not records:
        print(f"No chunks in {in_path}; nothing uploaded.")
        return 0

    source_file = records[0]["source_file"]
    index_client = get_search_index_client(cfg)
    search_client = get_search_client(cfg)

    deleted = 0
    if force_recreate:
        with contextlib.suppress(ResourceNotFoundError):
            index_client.delete_index(index_name)
        index_client.create_index(
            build_canonical_index_schema(index_name, cfg.embedding_dimensions)
        )
    else:
        _ensure_index_exists(index_client, index_name, cfg.embedding_dimensions)
        deleted = _delete_existing_chunks_for_source(search_client, source_file)

    documents = [_embedded_to_index_doc(r) for r in records]
    for i in range(0, len(documents), _BATCH_SIZE):
        batch = documents[i : i + _BATCH_SIZE]
        search_client.upload_documents(documents=batch)

    print(f"Uploaded {len(documents)} chunks ({deleted} replaced) → {index_name}")
    return len(documents)
