"""Adapter Qdrant para o VectorStorePort.

Implementa a interface VectorStorePort usando o Qdrant como backend.
Suporta tanto Qdrant self-hosted quanto Qdrant Cloud.
"""

import uuid
from typing import Any

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    Filter,
    FieldCondition,
    Range,
    MatchValue,
)

from ..port import VectorStorePort, VectorDocument, SearchResult, SearchFilter


class QdrantAdapter(VectorStorePort):
    """Adapter que implementa VectorStorePort usando Qdrant."""

    def __init__(self, url: str, api_key: str | None = None) -> None:
        self._client = AsyncQdrantClient(url=url, api_key=api_key)

    async def ensure_collection(self, collection: str, vector_size: int) -> None:
        """Cria a collection no Qdrant se ainda não existir."""
        collections = await self._client.get_collections()
        names = [c.name for c in collections.collections]
        if collection not in names:
            await self._client.create_collection(
                collection_name=collection,
                vectors_config=VectorParams(
                    size=vector_size,
                    distance=Distance.COSINE,
                ),
            )

    async def upsert(
        self, collection: str, documents: list[VectorDocument]
    ) -> None:
        """Insere ou atualiza documentos no Qdrant."""
        points = [
            PointStruct(
                id=doc.id if _is_uuid(doc.id) else str(uuid.uuid5(uuid.NAMESPACE_DNS, doc.id)),
                vector=doc.vector,
                payload={**doc.payload, "_original_id": doc.id},
            )
            for doc in documents
        ]
        await self._client.upsert(collection_name=collection, points=points)

    async def search(
        self,
        collection: str,
        query_vector: list[float],
        limit: int = 10,
        filters: SearchFilter | None = None,
    ) -> list[SearchResult]:
        """Busca no Qdrant com filtros híbridos opcionais."""
        qdrant_filter = _build_qdrant_filter(filters) if filters else None
        results = await self._client.search(
            collection_name=collection,
            query_vector=query_vector,
            query_filter=qdrant_filter,
            limit=limit,
            with_payload=True,
        )
        return [
            SearchResult(
                id=r.payload.get("_original_id", str(r.id)),
                score=r.score,
                payload={k: v for k, v in (r.payload or {}).items() if k != "_original_id"},
            )
            for r in results
        ]

    async def delete(self, collection: str, doc_id: str) -> None:
        """Remove documento do Qdrant pelo ID original."""
        from qdrant_client.models import Filter, FieldCondition, MatchValue
        await self._client.delete(
            collection_name=collection,
            points_selector=Filter(
                must=[FieldCondition(key="_original_id", match=MatchValue(value=doc_id))]
            ),
        )

    async def count(self, collection: str) -> int:
        """Retorna total de pontos na collection."""
        result = await self._client.count(collection_name=collection)
        return result.count


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
        return True
    except ValueError:
        return False


def _build_qdrant_filter(filters: SearchFilter) -> Filter | None:
    """Constrói o filtro Qdrant a partir do SearchFilter genérico."""
    conditions: list[Any] = []

    if filters.date_gte or filters.date_lte:
        date_range: dict[str, Any] = {}
        if filters.date_gte:
            date_range["gte"] = filters.date_gte
        if filters.date_lte:
            date_range["lte"] = filters.date_lte
        conditions.append(FieldCondition(key="date", range=Range(**date_range)))

    if filters.amount_gte or filters.amount_lte:
        amount_range: dict[str, Any] = {}
        if filters.amount_gte:
            amount_range["gte"] = filters.amount_gte
        if filters.amount_lte:
            amount_range["lte"] = filters.amount_lte
        conditions.append(FieldCondition(key="amount", range=Range(**amount_range)))

    if filters.supplier:
        conditions.append(FieldCondition(key="supplier", match=MatchValue(value=filters.supplier)))

    if filters.cost_center:
        conditions.append(FieldCondition(key="cost_center", match=MatchValue(value=filters.cost_center)))

    return Filter(must=conditions) if conditions else None
