"""Testes de contrato para VectorStorePort.

Valida que os dois adapters (QdrantAdapter e PineconeAdapter) implementam
o contrato da VectorStorePort corretamente, rodando os mesmos testes
parametrizados contra ambas as implementações.

Segue o princípio de Liskov Substitution (LSP): qualquer adapter deve ser
intercambiável sem alterar o comportamento do código de negócio.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.vector_store.port import SearchFilter, SearchResult, VectorDocument, VectorStorePort

_PINECONE_PATH = "src.vector_store.adapters.pinecone_adapter.Pinecone"


# ─── Fixtures de adapters ─────────────────────────────────────────────────────


def _make_qdrant_adapter() -> VectorStorePort:
    """Cria QdrantAdapter com AsyncQdrantClient mockado."""
    from src.vector_store.adapters.qdrant_adapter import QdrantAdapter

    client = MagicMock()
    client.get_collections = AsyncMock(return_value=MagicMock(collections=[]))
    client.create_collection = AsyncMock()
    client.upsert = AsyncMock()
    client.search = AsyncMock(return_value=[])
    client.delete = AsyncMock()
    client.count = AsyncMock(return_value=MagicMock(count=0))

    with patch("src.vector_store.adapters.qdrant_adapter.AsyncQdrantClient", return_value=client):
        adapter = QdrantAdapter(url="http://localhost:6333")
    adapter._client = client
    return adapter


def _make_pinecone_adapter() -> tuple[VectorStorePort, object]:
    """Cria PineconeAdapter com pinecone.Index e Pinecone class mockados.

    Retorna o adapter e o patch ativo que deve ser encerrado após o uso.
    """
    from src.vector_store.adapters.pinecone_adapter import PineconeAdapter

    index = MagicMock()
    index.upsert = MagicMock()
    index.query = MagicMock(return_value=MagicMock(matches=[]))
    index.delete = MagicMock()
    index.describe_index_stats = MagicMock(return_value={"namespaces": {}})

    mock_pc = MagicMock()
    mock_idx = MagicMock()
    mock_idx.name = "test-index"
    mock_pc.list_indexes.return_value = [mock_idx]
    mock_pc.Index.return_value = index

    active_patch = patch(_PINECONE_PATH, return_value=mock_pc)
    active_patch.start()

    adapter = PineconeAdapter(api_key="key", index_name="test-index", namespace="test")
    adapter._index = index
    return adapter, active_patch


# ─── Parametrização ──────────────────────────────────────────────────────────


@pytest.fixture(params=["qdrant", "pinecone"])
def adapter(request: pytest.FixtureRequest):  # noqa: ANN201
    """Fixture parametrizada que retorna cada adapter para os testes de contrato."""
    active_patch = None
    if request.param == "qdrant":
        inst = _make_qdrant_adapter()
    else:
        inst, active_patch = _make_pinecone_adapter()

    yield inst

    if active_patch is not None:
        active_patch.stop()


# ─── Testes de contrato ───────────────────────────────────────────────────────


class TestContrato:
    """Testes de contrato que rodam contra ambos os adapters."""

    async def test_adapter_implementa_vector_store_port(
        self, adapter: VectorStorePort
    ) -> None:
        """Todo adapter deve ser uma instância de VectorStorePort."""
        assert isinstance(adapter, VectorStorePort)

    async def test_ensure_collection_aceita_collection_e_vector_size(
        self, adapter: VectorStorePort
    ) -> None:
        """ensure_collection deve aceitar nome de collection e tamanho do vetor."""
        # Não deve lançar exceção
        await adapter.ensure_collection("test_collection", 768)

    async def test_upsert_aceita_lista_de_documentos(
        self, adapter: VectorStorePort
    ) -> None:
        """upsert deve aceitar uma lista de VectorDocument sem lançar exceção."""
        docs = [
            VectorDocument(id="doc-1", vector=[0.1, 0.2, 0.3], payload={"text": "teste"}),
            VectorDocument(id="doc-2", vector=[0.4, 0.5, 0.6], payload={"text": "outro"}),
        ]
        # Não deve lançar exceção
        await adapter.upsert("test_collection", docs)

    async def test_upsert_lista_vazia_nao_levanta_excecao(
        self, adapter: VectorStorePort
    ) -> None:
        """upsert com lista vazia não deve lançar exceção."""
        await adapter.upsert("test_collection", [])

    async def test_search_retorna_lista(self, adapter: VectorStorePort) -> None:
        """search deve retornar uma lista (possivelmente vazia)."""
        results = await adapter.search("test_collection", [0.1, 0.2, 0.3])
        assert isinstance(results, list)

    async def test_search_retorna_search_results(self, adapter: VectorStorePort) -> None:
        """Cada item retornado por search deve ser SearchResult."""
        results = await adapter.search("test_collection", [0.1])
        for result in results:
            assert isinstance(result, SearchResult)

    async def test_search_aceita_limite(self, adapter: VectorStorePort) -> None:
        """search deve aceitar o parâmetro limit."""
        results = await adapter.search("test_collection", [0.1], limit=5)
        assert isinstance(results, list)

    async def test_search_aceita_filtros_nulos(self, adapter: VectorStorePort) -> None:
        """search deve aceitar filters=None."""
        results = await adapter.search("test_collection", [0.1], filters=None)
        assert isinstance(results, list)

    async def test_search_aceita_filtros_preenchidos(self, adapter: VectorStorePort) -> None:
        """search deve aceitar um SearchFilter com campos preenchidos."""
        filters = SearchFilter(
            date_gte="2024-01-01",
            date_lte="2024-12-31",
            amount_gte=100.0,
            supplier="Fornecedor ABC",
        )
        results = await adapter.search("test_collection", [0.1], filters=filters)
        assert isinstance(results, list)

    async def test_delete_aceita_collection_e_id(self, adapter: VectorStorePort) -> None:
        """delete deve aceitar collection e doc_id sem lançar exceção."""
        # Não deve lançar exceção
        await adapter.delete("test_collection", "doc-123")

    async def test_count_retorna_inteiro(self, adapter: VectorStorePort) -> None:
        """count deve retornar um inteiro."""
        result = await adapter.count("test_collection")
        assert isinstance(result, int)
        assert result >= 0

    async def test_count_retorna_zero_em_collection_vazia(
        self, adapter: VectorStorePort
    ) -> None:
        """count deve retornar 0 para uma collection sem documentos."""
        result = await adapter.count("colecao_vazia")
        assert result == 0


# ─── Testes de substituição (Liskov) ─────────────────────────────────────────


class TestSubstituicao:
    """Verifica que os adapters são intercambiáveis via VectorStorePort."""

    async def test_todos_os_metodos_abstratos_estao_implementados(
        self, adapter: VectorStorePort
    ) -> None:
        """Todos os métodos abstratos de VectorStorePort devem estar implementados."""
        metodos_abstratos = [
            "ensure_collection",
            "upsert",
            "search",
            "delete",
            "count",
        ]
        for metodo in metodos_abstratos:
            assert hasattr(adapter, metodo), f"Método '{metodo}' não encontrado"
            assert callable(getattr(adapter, metodo)), f"'{metodo}' não é callable"

    def test_nao_pode_instanciar_port_diretamente(self) -> None:
        """VectorStorePort não deve poder ser instanciada diretamente."""
        with pytest.raises(TypeError):
            VectorStorePort()  # type: ignore[abstract]
