"""Adapter Pinecone para o VectorStorePort.

Implementa a interface VectorStorePort usando Pinecone como backend.
Suporta tanto Pinecone Serverless (recomendado) quanto Pinecone legado (pod-based).

Nota sobre collections no Pinecone:
  O Pinecone não tem o conceito de "collection" igual ao Qdrant.
  Aqui usamos NAMESPACES dentro de um único index para simular collections,
  combinando: namespace = f"{self._namespace}_{collection}".
  Isso mantém a interface idêntica à do QdrantAdapter.

Nota sobre filtros no Pinecone:
  O Pinecone suporta metadata filtering nativo (Pinecone Serverless e pods p1/s1/p2).
  Os filtros são traduzidos para o formato de metadata filter do Pinecone.
"""

from typing import Any

from pinecone import Pinecone

from ..port import SearchFilter, SearchResult, VectorDocument, VectorStorePort


class PineconeAdapter(VectorStorePort):
    """Adapter que implementa VectorStorePort usando Pinecone."""

    def __init__(
        self,
        api_key: str,
        index_name: str,
        namespace: str = "default",
    ) -> None:
        self._api_key = api_key
        self._index_name = index_name
        self._base_namespace = namespace
        self._index: Any = None  # lazy init

    def _get_namespace(self, collection: str) -> str:
        """Gera namespace único combinando base namespace + collection."""
        return f"{self._base_namespace}_{collection}"

    async def _get_index(self) -> Any:
        """Lazy initialization do Pinecone index."""
        if self._index is None:
            pc = Pinecone(api_key=self._api_key)
            self._index = pc.Index(self._index_name)
        return self._index

    async def ensure_collection(self, collection: str, vector_size: int) -> None:
        """No Pinecone, o index deve ser criado manualmente ou via IaC.

        Este método valida que o index existe e tem a dimensão correta.
        A criação automática do index não é feita aqui para evitar custos
        inesperados — o index deve ser criado previamente.

        Raises:
            RuntimeError: Se o index não existir ou tiver dimensão incorreta.
        """
        pc = Pinecone(api_key=self._api_key)
        indexes = [i.name for i in pc.list_indexes()]
        if self._index_name not in indexes:
            raise RuntimeError(
                f"Pinecone index '{self._index_name}' não encontrado. "
                f"Crie o index manualmente no console Pinecone ou via IaC "
                f"com dimension={vector_size} e metric=cosine."
            )

    async def upsert(
        self, collection: str, documents: list[VectorDocument]
    ) -> None:
        """Insere ou atualiza vetores no Pinecone."""
        index = await self._get_index()
        namespace = self._get_namespace(collection)
        vectors = [
            {
                "id": doc.id,
                "values": doc.vector,
                "metadata": {**doc.payload, "_collection": collection},
            }
            for doc in documents
        ]
        # Upsert em batches de 100 (limite recomendado pelo Pinecone)
        for i in range(0, len(vectors), 100):
            batch = vectors[i : i + 100]
            index.upsert(vectors=batch, namespace=namespace)

    async def search(
        self,
        collection: str,
        query_vector: list[float],
        limit: int = 10,
        filters: SearchFilter | None = None,
    ) -> list[SearchResult]:
        """Busca no Pinecone com metadata filters opcionais."""
        index = await self._get_index()
        namespace = self._get_namespace(collection)
        pinecone_filter = _build_pinecone_filter(filters) if filters else None

        response = index.query(
            vector=query_vector,
            top_k=limit,
            namespace=namespace,
            filter=pinecone_filter,
            include_metadata=True,
        )

        return [
            SearchResult(
                id=match.id,
                score=match.score,
                payload={
                    k: v
                    for k, v in (match.metadata or {}).items()
                    if k != "_collection"
                },
            )
            for match in (response.matches or [])
        ]

    async def delete(self, collection: str, doc_id: str) -> None:
        """Remove vetor do Pinecone pelo ID."""
        index = await self._get_index()
        namespace = self._get_namespace(collection)
        index.delete(ids=[doc_id], namespace=namespace)

    async def count(self, collection: str) -> int:
        """Retorna total de vetores no namespace da collection."""
        index = await self._get_index()
        namespace = self._get_namespace(collection)
        stats = index.describe_index_stats()
        ns_stats = stats.get("namespaces", {}).get(namespace, {})
        return ns_stats.get("vector_count", 0)


def _build_pinecone_filter(filters: SearchFilter) -> dict | None:
    """Traduz SearchFilter genérico para o formato de metadata filter do Pinecone."""
    conditions: dict = {}

    if filters.date_gte or filters.date_lte:
        date_filter: dict = {}
        if filters.date_gte:
            date_filter["$gte"] = filters.date_gte
        if filters.date_lte:
            date_filter["$lte"] = filters.date_lte
        conditions["date"] = date_filter

    if filters.amount_gte or filters.amount_lte:
        amount_filter: dict = {}
        if filters.amount_gte:
            amount_filter["$gte"] = filters.amount_gte
        if filters.amount_lte:
            amount_filter["$lte"] = filters.amount_lte
        conditions["amount"] = amount_filter

    if filters.supplier:
        conditions["supplier"] = {"$eq": filters.supplier}

    if filters.cost_center:
        conditions["cost_center"] = {"$eq": filters.cost_center}

    return conditions if conditions else None
