"""Port (interface abstrata) para o banco vetorial.

Seguindo Hexagonal Architecture, toda a lógica de negócio depende
apenas desta interface — nunca de um adapter concreto (Qdrant, Pinecone, etc.).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class VectorDocument:
    """Documento a ser indexado no banco vetorial."""
    id: str
    vector: list[float]
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class SearchResult:
    """Resultado de uma busca semântica."""
    id: str
    score: float
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class SearchFilter:
    """Filtros opcionais para busca híbrida (vetorial + metadados)."""
    date_gte: str | None = None       # data_inicio (ISO 8601)
    date_lte: str | None = None       # data_fim (ISO 8601)
    amount_gte: float | None = None   # valor_minimo
    amount_lte: float | None = None   # valor_maximo
    supplier: str | None = None       # fornecedor
    cost_center: str | None = None    # centro de custo


class VectorStorePort(ABC):
    """Interface abstrata para qualquer banco vetorial.

    Todos os adapters (QdrantAdapter, PineconeAdapter, etc.) devem
    implementar este contrato. O código de negócio nunca importa
    diretamente um adapter — usa apenas esta porta.
    """

    @abstractmethod
    async def ensure_collection(self, collection: str, vector_size: int) -> None:
        """Garante que a collection/index existe; cria se necessário."""
        ...

    @abstractmethod
    async def upsert(self, collection: str, documents: list[VectorDocument]) -> None:
        """Insere ou atualiza documentos na collection."""
        ...

    @abstractmethod
    async def search(
        self,
        collection: str,
        query_vector: list[float],
        limit: int = 10,
        filters: SearchFilter | None = None,
    ) -> list[SearchResult]:
        """Busca documentos semanticamente similares ao vetor da query."""
        ...

    @abstractmethod
    async def delete(self, collection: str, doc_id: str) -> None:
        """Remove um documento da collection pelo ID."""
        ...

    @abstractmethod
    async def count(self, collection: str) -> int:
        """Retorna o total de documentos na collection."""
        ...
