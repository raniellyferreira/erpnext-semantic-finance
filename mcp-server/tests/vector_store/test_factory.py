"""Testes para a Factory de vector store.

Valida que a factory instancia o adapter correto baseado na configuração
VECTOR_STORE_PROVIDER, seguindo o princípio OCP.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.config import settings
from src.vector_store.factory import create_vector_store


class TestCreateVectorStore:
    """Testes para a função create_vector_store."""

    def test_retorna_qdrant_adapter_para_provider_qdrant(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Deve retornar QdrantAdapter quando VECTOR_STORE_PROVIDER=qdrant."""
        from src.vector_store.adapters.qdrant_adapter import QdrantAdapter

        monkeypatch.setattr(settings, "vector_store_provider", "qdrant")
        monkeypatch.setattr(settings, "qdrant_url", "http://localhost:6333")
        monkeypatch.setattr(settings, "qdrant_api_key", "")

        with patch("src.vector_store.adapters.qdrant_adapter.AsyncQdrantClient"):
            store = create_vector_store()

        assert isinstance(store, QdrantAdapter)

    def test_retorna_pinecone_adapter_para_provider_pinecone(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Deve retornar PineconeAdapter quando VECTOR_STORE_PROVIDER=pinecone."""
        from src.vector_store.adapters.pinecone_adapter import PineconeAdapter

        monkeypatch.setattr(settings, "vector_store_provider", "pinecone")
        monkeypatch.setattr(settings, "pinecone_api_key", "test-pinecone-key")
        monkeypatch.setattr(settings, "pinecone_index_name", "erpnext-finance")
        monkeypatch.setattr(settings, "pinecone_namespace", "default")
        monkeypatch.setattr(settings, "pinecone_environment", "")

        store = create_vector_store()

        assert isinstance(store, PineconeAdapter)

    def test_levanta_value_error_para_provider_desconhecido(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Deve levantar ValueError para provider não suportado."""
        monkeypatch.setattr(settings, "vector_store_provider", "weaviate")

        with pytest.raises(ValueError, match="não suportado"):
            create_vector_store()

    def test_provider_case_insensitive(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """O provider deve ser case-insensitive (QDRANT == qdrant)."""
        from src.vector_store.adapters.qdrant_adapter import QdrantAdapter

        monkeypatch.setattr(settings, "vector_store_provider", "QDRANT")
        monkeypatch.setattr(settings, "qdrant_url", "http://localhost:6333")
        monkeypatch.setattr(settings, "qdrant_api_key", "")

        with patch("src.vector_store.adapters.qdrant_adapter.AsyncQdrantClient"):
            store = create_vector_store()

        assert isinstance(store, QdrantAdapter)

    def test_qdrant_recebe_api_key_nula_quando_vazia(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """QdrantAdapter deve receber api_key=None quando configuração está vazia."""
        monkeypatch.setattr(settings, "vector_store_provider", "qdrant")
        monkeypatch.setattr(settings, "qdrant_url", "http://localhost:6333")
        monkeypatch.setattr(settings, "qdrant_api_key", "")

        with patch("src.vector_store.adapters.qdrant_adapter.AsyncQdrantClient") as mock_cls:
            create_vector_store()

        call_kwargs = mock_cls.call_args.kwargs
        assert call_kwargs["api_key"] is None

    def test_qdrant_recebe_api_key_quando_configurada(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """QdrantAdapter deve receber api_key quando configuração não está vazia."""
        monkeypatch.setattr(settings, "vector_store_provider", "qdrant")
        monkeypatch.setattr(settings, "qdrant_url", "https://cloud.qdrant.io")
        monkeypatch.setattr(settings, "qdrant_api_key", "my-qdrant-key")

        with patch("src.vector_store.adapters.qdrant_adapter.AsyncQdrantClient") as mock_cls:
            create_vector_store()

        call_kwargs = mock_cls.call_args.kwargs
        assert call_kwargs["api_key"] == "my-qdrant-key"

    def test_pinecone_recebe_environment_nulo_quando_vazio(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """PineconeAdapter deve receber environment=None quando configuração está vazia."""
        from src.vector_store.adapters.pinecone_adapter import PineconeAdapter

        monkeypatch.setattr(settings, "vector_store_provider", "pinecone")
        monkeypatch.setattr(settings, "pinecone_api_key", "key")
        monkeypatch.setattr(settings, "pinecone_index_name", "idx")
        monkeypatch.setattr(settings, "pinecone_namespace", "ns")
        monkeypatch.setattr(settings, "pinecone_environment", "")

        store = create_vector_store()

        assert isinstance(store, PineconeAdapter)
        assert store._environment is None
