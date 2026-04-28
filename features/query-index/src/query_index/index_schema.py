"""Build the canonical Azure AI Search index definition for the ingestion pipeline.

This function is the single source of truth for the index schema used by both
the ingestion pipeline (upload stage) and any tooling that needs to re-create
the index from scratch.
"""

from __future__ import annotations

from azure.search.documents.indexes.models import (
    HnswAlgorithmConfiguration,
    SearchableField,
    SearchField,
    SearchFieldDataType,
    SearchIndex,
    SemanticConfiguration,
    SemanticField,
    SemanticPrioritizedFields,
    SemanticSearch,
    SimpleField,
    VectorSearch,
    VectorSearchProfile,
)


def build_canonical_index_schema(index_name: str, embedding_dimensions: int) -> SearchIndex:
    """Construct the canonical index definition matching the notebook schema.

    Fields:
        id             — key field (mapped from chunk_id)
        title          — document title, German Lucene analyser
        section_heading — section heading, German Lucene analyser
        chunk          — body text, German Lucene analyser
        source_file    — filterable / facetable filename
        chunkVector    — dense vector for hybrid search
    """
    fields = [
        SimpleField(
            name="id",
            type=SearchFieldDataType.String,
            key=True,
            filterable=True,
        ),
        SearchableField(
            name="title",
            type=SearchFieldDataType.String,
            analyzer_name="de.lucene",
        ),
        SearchableField(
            name="section_heading",
            type=SearchFieldDataType.String,
            analyzer_name="de.lucene",
        ),
        SearchableField(
            name="chunk",
            type=SearchFieldDataType.String,
            analyzer_name="de.lucene",
        ),
        SimpleField(
            name="source_file",
            type=SearchFieldDataType.String,
            filterable=True,
            facetable=True,
        ),
        SearchField(
            name="chunkVector",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            searchable=True,
            vector_search_dimensions=embedding_dimensions,
            vector_search_profile_name="default-vector-profile",
        ),
    ]
    vector_search = VectorSearch(
        algorithms=[HnswAlgorithmConfiguration(name="default-hnsw")],
        profiles=[
            VectorSearchProfile(
                name="default-vector-profile",
                algorithm_configuration_name="default-hnsw",
            )
        ],
    )
    semantic_search = SemanticSearch(
        configurations=[
            SemanticConfiguration(
                name="default-semantic-config",
                prioritized_fields=SemanticPrioritizedFields(
                    title_field=SemanticField(field_name="section_heading"),
                    content_fields=[SemanticField(field_name="chunk")],
                ),
            ),
        ]
    )
    return SearchIndex(
        name=index_name,
        fields=fields,
        vector_search=vector_search,
        semantic_search=semantic_search,
    )
