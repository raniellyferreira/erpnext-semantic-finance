"""Testes para o QdrantAdapter.

Valida todos os métodos da VectorStorePort implementados no QdrantAdapter,
usando mocks do AsyncQdrantClient para evitar dependência de infraestrutura real.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.vector_store.adapters.qdrant_adapter import (
    QdrantAdapter,
    _build_qdrant_filter,
    _is_uuid,
)
from src.vector_store.port import SearchFilter, VectorDocument

_QDRANT_CLIENT_PATH = "src.vector_store.adapters.qdrant_adapter.AsyncQdrantClient"

# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture()
def mock_qdrant_client() -> MagicMock:
    """Mock do AsyncQdrantClient com todos os métodos como AsyncMock."""
    client = MagicMock()
    client.get_collections = AsyncMock()
    client.create_collection = AsyncMock()
    client.upsert = AsyncMock()
    client.search = AsyncMock(return_value=[])
    client.delete = AsyncMock()
    client.count = AsyncMock()
    return client


@pytest.fixture()
def adapter(mock_qdrant_client: MagicMock) -> QdrantAdapter:
    """QdrantAdapter com client mockado."""
    with patch(_QDRANT_CLIENT_PATH, return_value=mock_qdrant_client):
        inst = QdrantAdapter(url="http://localhost:6333")
    inst._client = mock_qdrant_client
    return inst


# ─── ensure_collection ───────────────────────────────────────────────────────


class TestEnsureCollection:
    """Testes para o método ensure_collection."""

    async def test_cria_collection_se_nao_existir(
        self, adapter: QdrantAdapter, mock_qdrant_client: MagicMock
    ) -> None:
        """Deve criar a collection quando ela não existe."""
        collections_response = MagicMock()
        collections_response.collections = []
        mock_qdrant_client.get_collections.return_value = collections_response

        await adapter.ensure_collection("invoices", 768)

        mock_qdrant_client.create_collection.assert_awaited_once()
        call_kwargs = mock_qdrant_client.create_collection.call_args
        assert call_kwargs.kwargs["collection_name"] == "invoices"

    async def test_nao_cria_collection_se_ja_existir(
        self, adapter: QdrantAdapter, mock_qdrant_client: MagicMock
    ) -> None:
        """Não deve chamar create_collection se a collection já existir."""
        existing = MagicMock()
        existing.name = "invoices"
        collections_response = MagicMock()
        collections_response.collections = [existing]
        mock_qdrant_client.get_collections.return_value = collections_response

        await adapter.ensure_collection("invoices", 768)

        mock_qdrant_client.create_collection.assert_not_awaited()

    async def test_usa_distance_cosine(
        self, adapter: QdrantAdapter, mock_qdrant_client: MagicMock
    ) -> None:
        """Deve criar a collection com Distance.COSINE."""
        from qdrant_client.models import Distance

        collections_response = MagicMock()
        collections_response.collections = []
        mock_qdrant_client.get_collections.return_value = collections_response

        await adapter.ensure_collection("transactions", 1536)

        call_kwargs = mock_qdrant_client.create_collection.call_args
        vectors_config = call_kwargs.kwargs["vectors_config"]
        assert vectors_config.distance == Distance.COSINE
        assert vectors_config.size == 1536


# ─── upsert ──────────────────────────────────────────────────────────────────


class TestUpsert:
    """Testes para o método upsert."""

    async def test_upsert_converte_id_nao_uuid_para_uuid5(
        self, adapter: QdrantAdapter, mock_qdrant_client: MagicMock
    ) -> None:
        """IDs não-UUID devem ser convertidos para UUID5 determinístico."""
        docs = [VectorDocument(id="INV-001", vector=[0.1, 0.2], payload={})]

        await adapter.upsert("invoices", docs)

        mock_qdrant_client.upsert.assert_awaited_once()
        points = mock_qdrant_client.upsert.call_args.kwargs["points"]
        expected_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, "INV-001"))
        assert str(points[0].id) == expected_uuid

    async def test_upsert_mantem_id_uuid_valido(
        self, adapter: QdrantAdapter, mock_qdrant_client: MagicMock
    ) -> None:
        """IDs que já são UUID devem ser mantidos sem conversão."""
        valid_uuid = str(uuid.uuid4())
        docs = [VectorDocument(id=valid_uuid, vector=[0.5], payload={})]

        await adapter.upsert("invoices", docs)

        points = mock_qdrant_client.upsert.call_args.kwargs["points"]
        assert str(points[0].id) == valid_uuid

    async def test_upsert_salva_original_id_no_payload(
        self, adapter: QdrantAdapter, mock_qdrant_client: MagicMock
    ) -> None:
        """O payload deve conter _original_id com o ID original do documento."""
        docs = [VectorDocument(id="NF-2024-001", vector=[0.1], payload={"amount": 100.0})]

        await adapter.upsert("invoices", docs)

        points = mock_qdrant_client.upsert.call_args.kwargs["points"]
        assert points[0].payload["_original_id"] == "NF-2024-001"
        assert points[0].payload["amount"] == 100.0

    async def test_upsert_multiplos_documentos(
        self, adapter: QdrantAdapter, mock_qdrant_client: MagicMock
    ) -> None:
        """Deve processar lista de múltiplos documentos em uma única chamada."""
        docs = [
            VectorDocument(id="DOC-001", vector=[0.1], payload={}),
            VectorDocument(id="DOC-002", vector=[0.2], payload={}),
        ]

        await adapter.upsert("collection", docs)

        points = mock_qdrant_client.upsert.call_args.kwargs["points"]
        assert len(points) == 2


# ─── search ──────────────────────────────────────────────────────────────────


class TestSearch:
    """Testes para o método search."""

    async def test_search_retorna_lista_vazia_sem_resultados(
        self, adapter: QdrantAdapter, mock_qdrant_client: MagicMock
    ) -> None:
        """Deve retornar lista vazia se Qdrant não retornar resultados."""
        mock_qdrant_client.search.return_value = []

        results = await adapter.search("invoices", [0.1, 0.2])

        assert results == []

    async def test_search_retorna_search_results_corretos(
        self, adapter: QdrantAdapter, mock_qdrant_client: MagicMock
    ) -> None:
        """Deve mapear corretamente os resultados do Qdrant para SearchResult."""
        raw = MagicMock()
        raw.id = uuid.uuid5(uuid.NAMESPACE_DNS, "INV-001")
        raw.score = 0.95
        raw.payload = {"_original_id": "INV-001", "amount": 200.0}
        mock_qdrant_client.search.return_value = [raw]

        results = await adapter.search("invoices", [0.1])

        assert len(results) == 1
        assert results[0].id == "INV-001"
        assert results[0].score == 0.95
        assert results[0].payload == {"amount": 200.0}
        assert "_original_id" not in results[0].payload

    async def test_search_sem_filtros_nao_passa_query_filter(
        self, adapter: QdrantAdapter, mock_qdrant_client: MagicMock
    ) -> None:
        """Sem filtros, query_filter deve ser None."""
        await adapter.search("invoices", [0.1], limit=5)

        call_kwargs = mock_qdrant_client.search.call_args.kwargs
        assert call_kwargs["query_filter"] is None
        assert call_kwargs["limit"] == 5

    async def test_search_com_filtros_passa_query_filter(
        self, adapter: QdrantAdapter, mock_qdrant_client: MagicMock
    ) -> None:
        """Com filtros preenchidos, query_filter não deve ser None."""
        filters = SearchFilter(supplier="Fornecedor ABC")

        await adapter.search("invoices", [0.1], filters=filters)

        call_kwargs = mock_qdrant_client.search.call_args.kwargs
        assert call_kwargs["query_filter"] is not None

    async def test_search_usa_id_uuid_quando_nao_tem_original_id(
        self, adapter: QdrantAdapter, mock_qdrant_client: MagicMock
    ) -> None:
        """Deve usar o ID do ponto como fallback quando não há _original_id."""
        raw = MagicMock()
        raw.id = "some-uuid"
        raw.score = 0.7
        raw.payload = {}
        mock_qdrant_client.search.return_value = [raw]

        results = await adapter.search("invoices", [0.1])

        assert results[0].id == "some-uuid"


# ─── delete ──────────────────────────────────────────────────────────────────


class TestDelete:
    """Testes para o método delete."""

    async def test_delete_por_original_id(
        self, adapter: QdrantAdapter, mock_qdrant_client: MagicMock
    ) -> None:
        """Deve chamar delete com filtro por _original_id."""
        await adapter.delete("invoices", "INV-001")

        mock_qdrant_client.delete.assert_awaited_once()
        call_kwargs = mock_qdrant_client.delete.call_args.kwargs
        assert call_kwargs["collection_name"] == "invoices"
        # Verifica que o filtro foi construído com o ID correto
        points_selector = call_kwargs["points_selector"]
        condition = points_selector.must[0]
        assert condition.key == "_original_id"
        assert condition.match.value == "INV-001"


# ─── count ───────────────────────────────────────────────────────────────────


class TestCount:
    """Testes para o método count."""

    async def test_count_retorna_total_de_pontos(
        self, adapter: QdrantAdapter, mock_qdrant_client: MagicMock
    ) -> None:
        """Deve retornar o total de pontos da collection."""
        count_result = MagicMock()
        count_result.count = 42
        mock_qdrant_client.count.return_value = count_result

        result = await adapter.count("invoices")

        assert result == 42
        mock_qdrant_client.count.assert_awaited_with(collection_name="invoices")


# ─── _is_uuid ────────────────────────────────────────────────────────────────


class TestIsUuid:
    """Testes para a função auxiliar _is_uuid."""

    def test_retorna_true_para_uuid_valido(self) -> None:
        """Deve retornar True para um UUID v4 válido."""
        assert _is_uuid(str(uuid.uuid4())) is True

    def test_retorna_false_para_string_arbitraria(self) -> None:
        """Deve retornar False para strings que não são UUID."""
        assert _is_uuid("INV-001") is False
        assert _is_uuid("NF-2024-001") is False
        assert _is_uuid("") is False


# ─── _build_qdrant_filter ────────────────────────────────────────────────────


class TestBuildQdrantFilter:
    """Testes para a função auxiliar _build_qdrant_filter."""

    def test_retorna_none_com_filtro_vazio(self) -> None:
        """Deve retornar None quando não há condições de filtro."""
        result = _build_qdrant_filter(SearchFilter())
        assert result is None

    def test_filtro_por_date_gte(self) -> None:
        """Deve criar condição de DatetimeRange para date_gte."""
        from datetime import date

        result = _build_qdrant_filter(SearchFilter(date_gte="2024-01-01"))
        assert result is not None
        assert len(result.must) == 1
        assert result.must[0].key == "date"
        assert result.must[0].range.gte == date(2024, 1, 1)

    def test_filtro_por_date_lte(self) -> None:
        """Deve criar condição de DatetimeRange para date_lte."""
        from datetime import date

        result = _build_qdrant_filter(SearchFilter(date_lte="2024-12-31"))
        assert result is not None
        assert result.must[0].range.lte == date(2024, 12, 31)

    def test_filtro_intervalo_de_datas(self) -> None:
        """Deve criar DatetimeRange com gte e lte quando ambos estão presentes."""
        from datetime import date

        result = _build_qdrant_filter(SearchFilter(date_gte="2024-01-01", date_lte="2024-12-31"))
        assert result is not None
        assert result.must[0].range.gte == date(2024, 1, 1)
        assert result.must[0].range.lte == date(2024, 12, 31)

    def test_filtro_por_amount(self) -> None:
        """Deve criar condição de range para amount_gte e amount_lte."""
        result = _build_qdrant_filter(SearchFilter(amount_gte=100.0, amount_lte=500.0))
        assert result is not None
        cond = result.must[0]
        assert cond.key == "amount"
        assert cond.range.gte == 100.0
        assert cond.range.lte == 500.0

    def test_filtro_por_supplier(self) -> None:
        """Deve criar condição de match para supplier."""
        result = _build_qdrant_filter(SearchFilter(supplier="Fornecedor XYZ"))
        assert result is not None
        cond = result.must[0]
        assert cond.key == "supplier"
        assert cond.match.value == "Fornecedor XYZ"

    def test_filtro_por_cost_center(self) -> None:
        """Deve criar condição de match para cost_center."""
        result = _build_qdrant_filter(SearchFilter(cost_center="TI - CC001"))
        assert result is not None
        cond = result.must[0]
        assert cond.key == "cost_center"
        assert cond.match.value == "TI - CC001"

    def test_filtro_completo_com_multiplas_condicoes(self) -> None:
        """Deve criar múltiplas condições quando todos os campos estão preenchidos."""
        filters = SearchFilter(
            date_gte="2024-01-01",
            date_lte="2024-12-31",
            amount_gte=100.0,
            amount_lte=500.0,
            supplier="Fornecedor ABC",
            cost_center="Financeiro",
        )
        result = _build_qdrant_filter(filters)
        assert result is not None
        assert len(result.must) == 4  # date, amount, supplier, cost_center


# ─── Suporte a Qdrant Cloud ──────────────────────────────────────────────────


class TestQdrantCloud:
    """Testes para suporte ao Qdrant Cloud com api_key."""

    def test_inicializa_com_api_key(self) -> None:
        """Deve aceitar api_key para conexão com Qdrant Cloud."""
        with patch(_QDRANT_CLIENT_PATH) as mock_cls:
            QdrantAdapter(url="https://cloud.qdrant.io", api_key="my-api-key")
            mock_cls.assert_called_once_with(url="https://cloud.qdrant.io", api_key="my-api-key")

    def test_inicializa_sem_api_key(self) -> None:
        """Deve funcionar sem api_key para Qdrant self-hosted."""
        with patch(_QDRANT_CLIENT_PATH) as mock_cls:
            QdrantAdapter(url="http://localhost:6333")
            mock_cls.assert_called_once_with(url="http://localhost:6333", api_key=None)
