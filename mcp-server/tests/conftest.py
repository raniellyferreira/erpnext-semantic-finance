"""Fixtures compartilhadas para os testes de integração do MCP Server.

Contém mocks reutilizáveis para VectorStorePort, EmbeddingService
e variáveis de ambiente de teste.
"""

from __future__ import annotations

import pytest

from src.vector_store.port import SearchFilter, SearchResult, VectorStorePort, VectorDocument


# ─── Mock VectorStorePort ────────────────────────────────────────────────────


class MockVectorStore(VectorStorePort):
    """Implementação em memória do VectorStorePort para testes.

    Registra as chamadas recebidas para permitir asserções sobre
    os argumentos passados pelo código sob teste.
    """

    def __init__(self, results: list[SearchResult] | None = None) -> None:
        self.results = results or []
        self.calls: list[dict] = []

    async def ensure_collection(self, collection: str, vector_size: int) -> None:
        self.calls.append({"method": "ensure_collection", "collection": collection, "vector_size": vector_size})

    async def upsert(self, collection: str, documents: list[VectorDocument]) -> None:
        self.calls.append({"method": "upsert", "collection": collection, "documents": documents})

    async def search(
        self,
        collection: str,
        query_vector: list[float],
        limit: int = 10,
        filters: SearchFilter | None = None,
    ) -> list[SearchResult]:
        self.calls.append({
            "method": "search",
            "collection": collection,
            "query_vector": query_vector,
            "limit": limit,
            "filters": filters,
        })
        return self.results

    async def delete(self, collection: str, doc_id: str) -> None:
        self.calls.append({"method": "delete", "collection": collection, "doc_id": doc_id})

    async def count(self, collection: str) -> int:
        self.calls.append({"method": "count", "collection": collection})
        return len(self.results)


# ─── Mock EmbeddingService ───────────────────────────────────────────────────


class MockEmbeddingService:
    """Mock do EmbeddingService que retorna vetores determinísticos."""

    def __init__(self, embedding_dimension: int = 768) -> None:
        self._embedding_dimension = embedding_dimension

    async def embed(self, text: str) -> list[float]:
        return [0.1] * self._embedding_dimension


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture()
def mock_vector_store() -> MockVectorStore:
    """Retorna um MockVectorStore sem resultados pré-configurados."""
    return MockVectorStore()


@pytest.fixture()
def mock_vector_store_with_results() -> MockVectorStore:
    """Retorna um MockVectorStore com resultados de exemplo."""
    return MockVectorStore(results=[
        SearchResult(id="doc-1", score=0.95, payload={"text": "Despesa com material", "amount": 150.0}),
        SearchResult(id="doc-2", score=0.82, payload={"text": "Nota fiscal escritório", "amount": 300.0}),
    ])


@pytest.fixture()
def mock_embedding_service() -> MockEmbeddingService:
    """Retorna um MockEmbeddingService com dimensão padrão."""
    return MockEmbeddingService()


@pytest.fixture()
def env_test_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Configura variáveis de ambiente de teste para o Settings."""
    monkeypatch.setenv("ERPNEXT_URL", "https://test.erpnext.com")
    monkeypatch.setenv("ERPNEXT_API_KEY", "test-key")
    monkeypatch.setenv("ERPNEXT_API_SECRET", "test-secret")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "ollama")
    monkeypatch.setenv("OLLAMA_URL", "http://localhost:11434")
    monkeypatch.setenv("VECTOR_STORE_PROVIDER", "qdrant")
    monkeypatch.setenv("QDRANT_URL", "http://localhost:6333")
