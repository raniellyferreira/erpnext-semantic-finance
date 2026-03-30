"""Testes de integração para o EmbeddingService.

Valida cada provedor de embeddings (Ollama, OpenAI, Voyage) com respostas
HTTP mockadas via pytest-httpx, incluindo tratamento de erros e
gerenciamento do ciclo de vida.
"""

from __future__ import annotations

import pytest
from pytest_httpx import HTTPXMock

from src.config import settings
from src.vector_store.embeddings import EmbeddingService


# ─── Ollama ──────────────────────────────────────────────────────────────────


class TestEmbedOllama:
    """Testes para o provedor Ollama."""

    async def test_embed_retorna_vetor(
        self, monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
    ) -> None:
        """Deve retornar o vetor de embedding do Ollama."""
        monkeypatch.setattr(settings, "embedding_provider", "ollama")
        monkeypatch.setattr(settings, "ollama_url", "http://localhost:11434")
        monkeypatch.setattr(settings, "ollama_embedding_model", "nomic-embed-text")

        expected_vector = [0.1, 0.2, 0.3, 0.4, 0.5]

        httpx_mock.add_response(
            url="http://localhost:11434/api/embeddings",
            json={"embedding": expected_vector},
        )

        async with EmbeddingService() as service:
            result = await service.embed("Despesas com material de escritório")

        assert result == expected_vector

    async def test_embed_envia_payload_correto(
        self, monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
    ) -> None:
        """Deve enviar model e prompt no payload para o Ollama."""
        monkeypatch.setattr(settings, "embedding_provider", "ollama")
        monkeypatch.setattr(settings, "ollama_url", "http://localhost:11434")
        monkeypatch.setattr(settings, "ollama_embedding_model", "nomic-embed-text")

        httpx_mock.add_response(
            url="http://localhost:11434/api/embeddings",
            json={"embedding": [0.1]},
        )

        async with EmbeddingService() as service:
            await service.embed("texto de teste")

        request = httpx_mock.get_request()
        assert request is not None
        body = request.read()
        import json
        payload = json.loads(body)
        assert payload["model"] == "nomic-embed-text"
        assert payload["prompt"] == "texto de teste"


# ─── OpenAI ──────────────────────────────────────────────────────────────────


class TestEmbedOpenAI:
    """Testes para o provedor OpenAI."""

    async def test_embed_retorna_vetor(
        self, monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
    ) -> None:
        """Deve retornar o vetor de embedding da OpenAI."""
        monkeypatch.setattr(settings, "embedding_provider", "openai")
        monkeypatch.setattr(settings, "openai_api_key", "sk-test-key-123")
        monkeypatch.setattr(settings, "openai_embedding_model", "text-embedding-3-small")

        expected_vector = [0.5, 0.6, 0.7]

        httpx_mock.add_response(
            url="https://api.openai.com/v1/embeddings",
            json={"data": [{"embedding": expected_vector}]},
        )

        async with EmbeddingService() as service:
            result = await service.embed("Pagamento fornecedor")

        assert result == expected_vector

    async def test_sem_api_key_levanta_value_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Deve levantar ValueError se OPENAI_API_KEY não estiver configurada."""
        monkeypatch.setattr(settings, "embedding_provider", "openai")
        monkeypatch.setattr(settings, "openai_api_key", "")

        async with EmbeddingService() as service:
            with pytest.raises(ValueError, match="OPENAI_API_KEY"):
                await service.embed("teste")


# ─── Voyage AI ───────────────────────────────────────────────────────────────


class TestEmbedVoyage:
    """Testes para o provedor Voyage AI."""

    async def test_embed_retorna_vetor(
        self, monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
    ) -> None:
        """Deve retornar o vetor de embedding do Voyage AI."""
        monkeypatch.setattr(settings, "embedding_provider", "voyage")
        monkeypatch.setattr(settings, "voyage_api_key", "voyage-test-key")
        monkeypatch.setattr(settings, "voyage_embedding_model", "voyage-3-large")
        monkeypatch.setattr(settings, "voyage_api_url", "https://api.voyageai.com")

        expected_vector = [0.9, 0.8, 0.7, 0.6]

        httpx_mock.add_response(
            url="https://api.voyageai.com/v1/embeddings",
            json={"data": [{"embedding": expected_vector}]},
        )

        async with EmbeddingService() as service:
            result = await service.embed("Nota fiscal de serviço")

        assert result == expected_vector

    async def test_sem_api_key_levanta_value_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Deve levantar ValueError se VOYAGE_API_KEY não estiver configurada."""
        monkeypatch.setattr(settings, "embedding_provider", "voyage")
        monkeypatch.setattr(settings, "voyage_api_key", "")

        async with EmbeddingService() as service:
            with pytest.raises(ValueError, match="VOYAGE_API_KEY"):
                await service.embed("teste")


# ─── Provedor inválido ───────────────────────────────────────────────────────


class TestProvedorInvalido:
    """Testes para provedores não suportados."""

    def test_provedor_invalido_levanta_value_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Deve levantar ValueError ao instanciar com provedor inexistente."""
        monkeypatch.setattr(settings, "embedding_provider", "provedor_fantasma")

        with pytest.raises(ValueError, match="não suportado"):
            EmbeddingService()


# ─── Context Manager ────────────────────────────────────────────────────────


class TestContextManager:
    """Testes para o ciclo de vida do EmbeddingService via async context manager."""

    async def test_abre_e_fecha_corretamente(
        self, monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
    ) -> None:
        """O service deve funcionar como async context manager sem erros."""
        monkeypatch.setattr(settings, "embedding_provider", "ollama")
        monkeypatch.setattr(settings, "ollama_url", "http://localhost:11434")
        monkeypatch.setattr(settings, "ollama_embedding_model", "nomic-embed-text")

        httpx_mock.add_response(
            url="http://localhost:11434/api/embeddings",
            json={"embedding": [0.1, 0.2]},
        )

        async with EmbeddingService() as service:
            result = await service.embed("teste context manager")
            assert result == [0.1, 0.2]
