"""
Hybrid query against the 'github-issues' index in Azure AI Search,
filtered on labels containing 'csp:azure'.

Uses text + vector search with DefaultAzureCredential for auth.

Prerequisites:
    pip install azure-search-documents azure-identity openai
"""

import os

from dotenv import load_dotenv
from azure.core.credentials import AzureKeyCredential
from azure.identity import DefaultAzureCredential
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizedQuery
from openai import AzureOpenAI

load_dotenv()

# ── Configuration ──────────────────────────────────────────────────────────────
SEARCH_SERVICE_NAME = "pocaisearchbam"
SEARCH_ENDPOINT = f"https://{SEARCH_SERVICE_NAME}.search.windows.net"
INDEX_NAME = "wizard-1"

AI_FOUNDRY_ENDPOINT = "https://poc-sweden-ai-plattform.services.ai.azure.com"
EMBEDDING_MODEL = "text-embedding-3-large"
AI_FOUNDRY_KEY = os.environ["AI_FOUNDRY_KEY"]
AI_SEARCH_KEY = os.environ["AI_SEARCH_KEY"]
EMBEDDING_DIMENSIONS = 3072

# ── Authentication ─────────────────────────────────────────────────────────────

openai_client = AzureOpenAI(
    api_version="2024-02-01",
    azure_endpoint=AI_FOUNDRY_ENDPOINT,
    api_key=AI_FOUNDRY_KEY,
)

search_client = SearchClient(
    endpoint=SEARCH_ENDPOINT,
    index_name=INDEX_NAME,
    credential=AzureKeyCredential(AI_SEARCH_KEY),
)


def get_embedding(text: str) -> list[float]:
    """Get embedding vector for a query string."""
    response = openai_client.embeddings.create(input=[text], model=EMBEDDING_MODEL)
    return response.data[0].embedding


def hybrid_search(query: str, top: int = 5):
    """
    Run a hybrid (text + vector) search on the github-issues index,
    filtered to documents where labels contains 'csp:azure'.
    """
    query_vector = get_embedding(query)

    vector_query = VectorizedQuery(
        vector=query_vector,
        k_nearest_neighbors=top,
        fields="text_vector",
    )

    results = search_client.search(
        search_text=query,
        vector_queries=[vector_query],
        top=top,
    )

    print(f"Query: {query}")
    print("-" * 80)

    for result in results:
        score = result.get("@search.score", "N/A")
        print(f"  {result['chunk_id']}  (score: {score})")
        print(f"    Title: {result['title']}")
        print(f"    Chunk: {result['chunk'][:200]}...")
        print()


if __name__ == "__main__":
    hybrid_search("Wo ist die Änderung des Tragkorbdurchmessers aufgeführt?")
