"""Serviço de geração de embeddings multi-provider.

Suporta três provedores de embedding (Ollama, OpenAI, Voyage AI),
selecionados via configuração. Cada provedor é encapsulado em uma
estratégia interna, seguindo o princípio OCP — adicionar um novo
provedor exige apenas uma nova função de estratégia e o registro
no dicionário ``_PROVIDERS``.

A comunicação HTTP é feita via ``httpx.AsyncClient`` para manter
consistência e evitar dependências de SDKs específicos.
"""

from __future__ import annotations

import httpx
import structlog

from ..config import settings

logger = structlog.get_logger(__name__)


# ─── Estratégias por provedor ────────────────────────────────────────────────


async def _embed_ollama(text: str, client: httpx.AsyncClient) -> list[float]:
    """Gera embedding usando Ollama (100 % local)."""
    url = f"{settings.ollama_url}/api/embeddings"
    payload = {"model": settings.ollama_embedding_model, "prompt": text}

    response = await client.post(url, json=payload)
    response.raise_for_status()

    data = response.json()
    embedding: list[float] = data["embedding"]
    return embedding


async def _embed_openai(text: str, client: httpx.AsyncClient) -> list[float]:
    """Gera embedding usando a API da OpenAI."""
    if not settings.openai_api_key:
        raise ValueError(
            "OPENAI_API_KEY não configurada. "
            "Defina a variável de ambiente para usar o provedor OpenAI."
        )

    url = "https://api.openai.com/v1/embeddings"
    headers = {"Authorization": f"Bearer {settings.openai_api_key}"}
    payload = {"model": settings.openai_embedding_model, "input": text}

    response = await client.post(url, json=payload, headers=headers)
    response.raise_for_status()

    data = response.json()
    embedding: list[float] = data["data"][0]["embedding"]
    return embedding


async def _embed_voyage(text: str, client: httpx.AsyncClient) -> list[float]:
    """Gera embedding usando a API do Voyage AI."""
    if not settings.voyage_api_key:
        raise ValueError(
            "VOYAGE_API_KEY não configurada. "
            "Defina a variável de ambiente para usar o provedor Voyage AI."
        )

    url = f"{settings.voyage_api_url}/v1/embeddings"
    headers = {"Authorization": f"Bearer {settings.voyage_api_key}"}
    payload = {"model": settings.voyage_embedding_model, "input": [text]}

    response = await client.post(url, json=payload, headers=headers)
    response.raise_for_status()

    data = response.json()
    embedding: list[float] = data["data"][0]["embedding"]
    return embedding


# Registro de provedores suportados — OCP-friendly
_PROVIDER_STRATEGIES = {
    "ollama": _embed_ollama,
    "openai": _embed_openai,
    "voyage": _embed_voyage,
}


# ─── EmbeddingService ───────────────────────────────────────────────────────


class EmbeddingService:
    """Serviço de embeddings multi-provider.

    Lê a configuração do provider via ``settings.embedding_provider``
    e delega a geração do embedding para a estratégia correspondente.

    Pode ser usado como async context manager para gerenciamento
    automático do ciclo de vida do cliente HTTP::

        async with EmbeddingService() as service:
            vector = await service.embed("texto de exemplo")

    Ou manualmente, chamando ``close()`` ao final::

        service = EmbeddingService()
        try:
            vector = await service.embed("texto de exemplo")
        finally:
            await service.close()
    """

    def __init__(self) -> None:
        provider = settings.embedding_provider.lower()

        if provider not in _PROVIDER_STRATEGIES:
            supported = ", ".join(sorted(_PROVIDER_STRATEGIES))
            raise ValueError(
                f"Provedor de embedding '{provider}' não suportado. "
                f"Opções disponíveis: {supported}"
            )

        self._provider = provider
        self._strategy = _PROVIDER_STRATEGIES[provider]
        self._client = httpx.AsyncClient(timeout=30.0)

        logger.info(
            "embedding_service_inicializado",
            provider=self._provider,
            dimension=settings.embedding_dimension,
        )

    async def embed(self, text: str) -> list[float]:
        """Gera o vetor de embedding para o texto fornecido.

        Args:
            text: Texto a ser convertido em vetor de embedding.

        Returns:
            Lista de floats representando o vetor de embedding.

        Raises:
            httpx.HTTPStatusError: Se a API do provedor retornar erro HTTP.
            ValueError: Se o provedor não estiver configurado corretamente.
        """
        logger.debug(
            "gerando_embedding",
            provider=self._provider,
            text_length=len(text),
        )

        embedding = await self._strategy(text, self._client)

        logger.debug(
            "embedding_gerado",
            provider=self._provider,
            dimension=len(embedding),
        )

        return embedding

    async def close(self) -> None:
        """Fecha o cliente HTTP, liberando recursos de rede."""
        await self._client.aclose()
        logger.debug("embedding_service_fechado", provider=self._provider)

    async def __aenter__(self) -> EmbeddingService:
        """Suporte a ``async with``."""
        return self

    async def __aexit__(self, *_exc: object) -> None:
        """Fecha o cliente HTTP ao sair do context manager."""
        await self.close()
