# query-index

Azure AI Search hybrid-query library. The **only** package in this repository allowed to import `azure.*` or `openai` — enforced by a pre-commit hook at the repo root.

## Public API

```python
from query_index import (
    Chunk,
    Config,
    SearchHit,
    get_chunk,
    get_embedding,
    hybrid_search,
    sample_chunks,
)
```

## Environment

See [`.env.example`](../../../../.env.example). Variables are loaded once at the entry point of any consuming CLI; this package itself does not call `load_dotenv()`.

## Tests

```bash
pytest features/pipelines/microsoft/retrieval/
```

All tests are mocked — they do not call Azure. Live verification is done by the user in their separate cloned workspace.
