# ingestion

PDF ingestion pipeline for the Azure AI Search index. Four stages, each its own CLI subcommand:

```bash
ingest analyze --in data/foo.pdf
ingest chunk   --in outputs/foo/analyze/{ts}.json --strategy section
ingest embed   --in outputs/foo/chunk/{ts}-section.jsonl
ingest upload  --in outputs/foo/embed/{ts}-section.jsonl
```

## Stages

- **analyze**: Document Intelligence `prebuilt-layout` extracts text + structure. Output: JSON.
- **chunk**: applies a chunker strategy (V1: `section`-based) to the analyze JSON. Output: text-only chunks JSONL.
- **embed**: calls Azure OpenAI to vectorise each chunk. Output: chunks + vectors JSONL.
- **upload**: pushes to Azure AI Search. Multi-doc cumulative — deletes only chunks for the given source_file before uploading.

## Outputs structure

All artefacts live under `outputs/{slug}/<stage>/{ts}-{strategy}.{ext}`. The slug is derived from the input filename (lowercased, hyphenated, sanitised).

## Tests

```bash
pytest features/pipelines/microsoft/ingestion/
```

All tests are mocked — they do not call Azure. Live verification is done by the user in their separate cloned workspace.
