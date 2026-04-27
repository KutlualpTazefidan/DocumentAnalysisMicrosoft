"""Print the field definitions of a named Azure AI Search index.

Used at setup time to confirm field names (chunk_id, chunk, title, text_vector,
labels, ...) match what the rest of the pipeline expects.
"""

from __future__ import annotations

from query_index.client import get_search_index_client
from query_index.config import Config


def print_index_schema(index_name: str, cfg: Config | None = None) -> None:
    if cfg is None:
        cfg = Config.from_env()
    client = get_search_index_client(cfg)
    index = client.get_index(index_name)
    print(f"Index: {index_name}")
    print("-" * 60)
    for field in index.fields:
        flags = []
        if getattr(field, "searchable", False):
            flags.append("searchable")
        if getattr(field, "filterable", False):
            flags.append("filterable")
        if getattr(field, "retrievable", True):
            flags.append("retrievable")
        flag_str = f" [{', '.join(flags)}]" if flags else ""
        print(f"  {field.name}: {field.type}{flag_str}")
