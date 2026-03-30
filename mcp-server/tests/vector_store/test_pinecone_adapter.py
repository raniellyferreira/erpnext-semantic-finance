"""Testes para o PineconeAdapter.

Valida todos os métodos da VectorStorePort implementados no PineconeAdapter,
usando mocks do pinecone.Index para evitar dependência de infraestrutura real.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.vector_store.adapters.pinecone_adapter import (
    PineconeAdapter,
    _build_pinecone_filter,
)
from src.vector_store.port import SearchFilter, VectorDocument

# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture()
def mock_index() -> MagicMock:
    """Mock do pinecone.Index com métodos usados pelo adapter."""
    index = MagicMock()
    index.upsert = MagicMock()
    index.query = MagicMock(return_value=MagicMock(matches=[]))
    index.delete = MagicMock()
    index.describe_index_stats = MagicMock(return_value={"namespaces": {}})
    return index


@pytest.fixture()
def adapter(mock_index: MagicMock) -> PineconeAdapter:
    """PineconeAdapter com index mockado e lazy init ignorado."""
    inst = PineconeAdapter(
        api_key="test-key",
        index_name="erpnext-finance",
        namespace="default",
    )
    inst._index = mock_index
    return inst


# ─── ensure_collection ───────────────────────────────────────────────────────


class TestEnsureCollection:
    """Testes para o método ensure_collection."""

    async def test_nao_levanta_erro_quando_index_existe(self) -> None:
        """Deve aceitar sem erros quando o index já existe no Pinecone."""
        mock_idx = MagicMock()
        mock_idx.name = "erpnext-finance"

        mock_pc = MagicMock()
        mock_pc.list_indexes.return_value = [mock_idx]

        with patch("src.vector_store.adapters.pinecone_adapter.Pinecone", return_value=mock_pc):
            inst = PineconeAdapter(
                api_key="test-key",
                index_name="erpnext-finance",
                namespace="default",
            )
            # Não deve levantar exceção
            await inst.ensure_collection("invoices", 768)

    async def test_levanta_runtime_error_quando_index_nao_existe(self) -> None:
        """Deve levantar RuntimeError quando o index não existe."""
        mock_pc = MagicMock()
        mock_pc.list_indexes.return_value = []

        with patch("src.vector_store.adapters.pinecone_adapter.Pinecone", return_value=mock_pc):
            inst = PineconeAdapter(
                api_key="test-key",
                index_name="erpnext-finance",
                namespace="default",
            )
            with pytest.raises(RuntimeError, match="não encontrado"):
                await inst.ensure_collection("invoices", 768)


# ─── upsert ──────────────────────────────────────────────────────────────────


class TestUpsert:
    """Testes para o método upsert."""

    async def test_upsert_simples(
        self, adapter: PineconeAdapter, mock_index: MagicMock
    ) -> None:
        """Deve chamar index.upsert com vetores no namespace correto."""
        docs = [VectorDocument(id="INV-001", vector=[0.1, 0.2], payload={"amount": 100.0})]

        await adapter.upsert("invoices", docs)

        mock_index.upsert.assert_called_once()
        call_kwargs = mock_index.upsert.call_args.kwargs
        assert call_kwargs["namespace"] == "default_invoices"
        assert call_kwargs["vectors"][0]["id"] == "INV-001"

    async def test_upsert_salva_collection_no_metadata(
        self, adapter: PineconeAdapter, mock_index: MagicMock
    ) -> None:
        """O metadata deve conter _collection com o nome da collection."""
        docs = [VectorDocument(id="DOC-001", vector=[0.5], payload={"text": "teste"})]

        await adapter.upsert("transactions", docs)

        vectors = mock_index.upsert.call_args.kwargs["vectors"]
        assert vectors[0]["metadata"]["_collection"] == "transactions"
        assert vectors[0]["metadata"]["text"] == "teste"

    async def test_upsert_em_batches_de_100(
        self, adapter: PineconeAdapter, mock_index: MagicMock
    ) -> None:
        """Deve dividir documentos em batches de 100."""
        docs = [
            VectorDocument(id=f"DOC-{i}", vector=[float(i)], payload={})
            for i in range(250)
        ]

        await adapter.upsert("invoices", docs)

        # 250 docs → 3 batches: 100, 100, 50
        assert mock_index.upsert.call_count == 3

    async def test_upsert_namespace_correto(
        self, adapter: PineconeAdapter, mock_index: MagicMock
    ) -> None:
        """O namespace deve ser base_namespace + '_' + collection."""
        docs = [VectorDocument(id="X", vector=[0.1], payload={})]

        await adapter.upsert("payments", docs)

        call_kwargs = mock_index.upsert.call_args.kwargs
        assert call_kwargs["namespace"] == "default_payments"


# ─── search ──────────────────────────────────────────────────────────────────


class TestSearch:
    """Testes para o método search."""

    async def test_search_retorna_lista_vazia_sem_resultados(
        self, adapter: PineconeAdapter, mock_index: MagicMock
    ) -> None:
        """Deve retornar lista vazia quando não há resultados."""
        mock_index.query.return_value = MagicMock(matches=[])

        results = await adapter.search("invoices", [0.1, 0.2])

        assert results == []

    async def test_search_mapeia_resultados_corretamente(
        self, adapter: PineconeAdapter, mock_index: MagicMock
    ) -> None:
        """Deve mapear os matches para SearchResult corretamente."""
        match = MagicMock()
        match.id = "INV-001"
        match.score = 0.95
        match.metadata = {"amount": 200.0, "_collection": "invoices"}
        response = MagicMock()
        response.matches = [match]
        mock_index.query.return_value = response

        results = await adapter.search("invoices", [0.1])

        assert len(results) == 1
        assert results[0].id == "INV-001"
        assert results[0].score == 0.95
        assert results[0].payload == {"amount": 200.0}
        assert "_collection" not in results[0].payload

    async def test_search_sem_filtros_passa_filter_none(
        self, adapter: PineconeAdapter, mock_index: MagicMock
    ) -> None:
        """Sem filtros, filter deve ser None."""
        mock_index.query.return_value = MagicMock(matches=[])

        await adapter.search("invoices", [0.1], limit=5)

        call_kwargs = mock_index.query.call_args.kwargs
        assert call_kwargs["filter"] is None
        assert call_kwargs["top_k"] == 5

    async def test_search_com_filtros_passa_metadata_filter(
        self, adapter: PineconeAdapter, mock_index: MagicMock
    ) -> None:
        """Com filtros, deve passar metadata filter não-nulo."""
        mock_index.query.return_value = MagicMock(matches=[])
        filters = SearchFilter(supplier="Fornecedor ABC")

        await adapter.search("invoices", [0.1], filters=filters)

        call_kwargs = mock_index.query.call_args.kwargs
        assert call_kwargs["filter"] is not None

    async def test_search_usa_namespace_correto(
        self, adapter: PineconeAdapter, mock_index: MagicMock
    ) -> None:
        """Deve usar o namespace combinado da collection."""
        mock_index.query.return_value = MagicMock(matches=[])

        await adapter.search("expenses", [0.1])

        call_kwargs = mock_index.query.call_args.kwargs
        assert call_kwargs["namespace"] == "default_expenses"

    async def test_search_com_metadata_none_retorna_payload_vazio(
        self, adapter: PineconeAdapter, mock_index: MagicMock
    ) -> None:
        """Resultado com metadata None deve retornar payload vazio."""
        match = MagicMock()
        match.id = "DOC-1"
        match.score = 0.5
        match.metadata = None
        response = MagicMock()
        response.matches = [match]
        mock_index.query.return_value = response

        results = await adapter.search("invoices", [0.1])

        assert results[0].payload == {}


# ─── delete ──────────────────────────────────────────────────────────────────


class TestDelete:
    """Testes para o método delete."""

    async def test_delete_por_id_no_namespace_correto(
        self, adapter: PineconeAdapter, mock_index: MagicMock
    ) -> None:
        """Deve chamar index.delete com o ID e namespace corretos."""
        await adapter.delete("invoices", "INV-001")

        mock_index.delete.assert_called_once_with(ids=["INV-001"], namespace="default_invoices")


# ─── count ───────────────────────────────────────────────────────────────────


class TestCount:
    """Testes para o método count."""

    async def test_count_retorna_total_do_namespace(
        self, adapter: PineconeAdapter, mock_index: MagicMock
    ) -> None:
        """Deve retornar o vector_count do namespace correto."""
        mock_index.describe_index_stats.return_value = {
            "namespaces": {
                "default_invoices": {"vector_count": 150},
                "default_payments": {"vector_count": 50},
            }
        }

        result = await adapter.count("invoices")

        assert result == 150

    async def test_count_retorna_zero_quando_namespace_inexistente(
        self, adapter: PineconeAdapter, mock_index: MagicMock
    ) -> None:
        """Deve retornar 0 quando o namespace não existe nas stats."""
        mock_index.describe_index_stats.return_value = {"namespaces": {}}

        result = await adapter.count("collection_inexistente")

        assert result == 0


# ─── _get_namespace ──────────────────────────────────────────────────────────


class TestGetNamespace:
    """Testes para o método _get_namespace."""

    def test_namespace_combina_base_e_collection(self) -> None:
        """Deve retornar base_namespace + '_' + collection."""
        adapter = PineconeAdapter(
            api_key="key", index_name="idx", namespace="my_company"
        )
        assert adapter._get_namespace("invoices") == "my_company_invoices"

    def test_namespace_default(self) -> None:
        """Deve usar 'default' como base namespace quando não especificado."""
        adapter = PineconeAdapter(api_key="key", index_name="idx")
        assert adapter._get_namespace("payments") == "default_payments"


# ─── _get_index (lazy init) ──────────────────────────────────────────────────


class TestGetIndex:
    """Testes para o lazy initialization do Pinecone index."""

    async def test_lazy_init_cria_index_na_primeira_chamada(self) -> None:
        """O index deve ser criado apenas na primeira chamada de _get_index."""
        mock_index = MagicMock()
        mock_pc = MagicMock()
        mock_pc.Index.return_value = mock_index

        with patch("src.vector_store.adapters.pinecone_adapter.Pinecone", return_value=mock_pc):
            inst = PineconeAdapter(api_key="key", index_name="my-index", namespace="ns")
            assert inst._index is None
            index = await inst._get_index()

        assert index is mock_index
        mock_pc.Index.assert_called_once_with("my-index")

    async def test_lazy_init_reutiliza_index_em_chamadas_subsequentes(self) -> None:
        """O index deve ser criado uma única vez e reutilizado."""
        mock_index = MagicMock()
        mock_pc = MagicMock()
        mock_pc.Index.return_value = mock_index

        with patch("src.vector_store.adapters.pinecone_adapter.Pinecone", return_value=mock_pc):
            inst = PineconeAdapter(api_key="key", index_name="my-index", namespace="ns")
            await inst._get_index()
            await inst._get_index()

        assert mock_pc.Index.call_count == 1


# ─── _build_pinecone_filter ──────────────────────────────────────────────────


class TestBuildPineconeFilter:
    """Testes para a função auxiliar _build_pinecone_filter."""

    def test_retorna_none_com_filtro_vazio(self) -> None:
        """Deve retornar None quando não há condições de filtro."""
        result = _build_pinecone_filter(SearchFilter())
        assert result is None

    def test_filtro_por_date_gte(self) -> None:
        """Deve criar filtro com $gte para date_gte."""
        result = _build_pinecone_filter(SearchFilter(date_gte="2024-01-01"))
        assert result is not None
        assert result["date"]["$gte"] == "2024-01-01"

    def test_filtro_por_date_lte(self) -> None:
        """Deve criar filtro com $lte para date_lte."""
        result = _build_pinecone_filter(SearchFilter(date_lte="2024-12-31"))
        assert result is not None
        assert result["date"]["$lte"] == "2024-12-31"

    def test_filtro_intervalo_de_datas(self) -> None:
        """Deve criar filtro com $gte e $lte quando ambas as datas estão presentes."""
        result = _build_pinecone_filter(SearchFilter(date_gte="2024-01-01", date_lte="2024-12-31"))
        assert result is not None
        assert result["date"]["$gte"] == "2024-01-01"
        assert result["date"]["$lte"] == "2024-12-31"

    def test_filtro_por_amount(self) -> None:
        """Deve criar filtro numérico para amount."""
        result = _build_pinecone_filter(SearchFilter(amount_gte=100.0, amount_lte=500.0))
        assert result is not None
        assert result["amount"]["$gte"] == 100.0
        assert result["amount"]["$lte"] == 500.0

    def test_filtro_por_supplier(self) -> None:
        """Deve criar filtro de igualdade para supplier."""
        result = _build_pinecone_filter(SearchFilter(supplier="Fornecedor XYZ"))
        assert result is not None
        assert result["supplier"] == {"$eq": "Fornecedor XYZ"}

    def test_filtro_por_cost_center(self) -> None:
        """Deve criar filtro de igualdade para cost_center."""
        result = _build_pinecone_filter(SearchFilter(cost_center="TI"))
        assert result is not None
        assert result["cost_center"] == {"$eq": "TI"}

    def test_filtro_completo(self) -> None:
        """Deve criar filtro com todos os campos presentes."""
        filters = SearchFilter(
            date_gte="2024-01-01",
            amount_gte=100.0,
            supplier="ABC",
            cost_center="TI",
        )
        result = _build_pinecone_filter(filters)
        assert result is not None
        assert "date" in result
        assert "amount" in result
        assert "supplier" in result
        assert "cost_center" in result
