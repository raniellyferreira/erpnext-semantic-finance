"""Testes de integração para as ferramentas de busca semântica.

Valida a definição das tools, a construção de filtros, a execução
da busca semântica com mocks do VectorStorePort e EmbeddingService,
e o tratamento de nomes de tool desconhecidos.
"""

from __future__ import annotations

import json

import pytest

from src.tools import search_tools
from src.vector_store.port import SearchFilter, SearchResult

# ─── Mock classes ────────────────────────────────────────────────────────────


class _MockVectorStore:
    """Mock do VectorStorePort que retorna resultados pré-configurados."""

    def __init__(self, results: list[SearchResult] | None = None) -> None:
        self.results = results or []
        self.search_calls: list[dict] = []

    async def search(
        self,
        collection: str,
        query_vector: list[float],
        limit: int = 10,
        filters: SearchFilter | None = None,
    ) -> list[SearchResult]:
        self.search_calls.append({
            "collection": collection,
            "query_vector": query_vector,
            "limit": limit,
            "filters": filters,
        })
        return self.results


class _MockEmbeddingService:
    """Mock do EmbeddingService que retorna vetores determinísticos."""

    def __init__(self, embedding_dimension: int = 768) -> None:
        self._embedding_dimension = embedding_dimension
        self.embed_calls: list[str] = []

    async def embed(self, text: str) -> list[float]:
        self.embed_calls.append(text)
        return [0.1] * self._embedding_dimension


# ─── get_tools() ─────────────────────────────────────────────────────────────


class TestGetTools:
    """Testes para a definição das tools de busca."""

    def test_retorna_definicao_da_tool_busca_semantica(self) -> None:
        """Deve retornar a definição da tool 'busca_semantica'."""
        tools = search_tools.get_tools()

        assert len(tools) == 1
        tool = tools[0]
        assert tool.name == "busca_semantica"
        assert "busca semântica" in tool.description.lower()

    def test_input_schema_tem_query_obrigatoria(self) -> None:
        """O inputSchema deve exigir o campo 'query'."""
        tools = search_tools.get_tools()
        schema = tools[0].inputSchema

        assert "properties" in schema
        assert "query" in schema["properties"]
        assert "required" in schema
        assert "query" in schema["required"]

    def test_input_schema_campos_opcionais(self) -> None:
        """O inputSchema deve conter campos opcionais de filtro."""
        tools = search_tools.get_tools()
        schema = tools[0].inputSchema
        properties = schema["properties"]

        assert "colecoes" in properties
        assert "limite" in properties
        assert "data_inicio" in properties
        assert "data_fim" in properties
        assert "valor_minimo" in properties
        assert "valor_maximo" in properties


# ─── TOOL_NAMES ──────────────────────────────────────────────────────────────


class TestToolNames:
    """Testes para a constante TOOL_NAMES."""

    def test_contem_busca_semantica(self) -> None:
        """TOOL_NAMES deve conter 'busca_semantica'."""
        assert "busca_semantica" in search_tools.TOOL_NAMES

    def test_tamanho_correto(self) -> None:
        """TOOL_NAMES deve conter exatamente uma entrada."""
        assert len(search_tools.TOOL_NAMES) == 1


# ─── execute() ───────────────────────────────────────────────────────────────


class TestExecute:
    """Testes para a execução da busca semântica."""

    async def test_busca_semantica_com_mocks(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Deve executar a busca semântica e retornar resultados formatados."""
        mock_store = _MockVectorStore(results=[
            SearchResult(id="doc-1", score=0.95, payload={"text": "Despesa material"}),
        ])
        mock_embed = _MockEmbeddingService()

        monkeypatch.setattr(search_tools, "_embedding_service", mock_embed)
        monkeypatch.setattr(search_tools, "_vector_store", mock_store)

        result_json = await search_tools.execute(
            "busca_semantica",
            {"query": "despesas com material", "colecoes": ["despesas"], "limite": 5},
        )

        result = json.loads(result_json)
        assert result["query"] == "despesas com material"
        assert result["total"] == 1
        assert len(result["resultados"]) == 1
        assert result["resultados"][0]["id"] == "doc-1"
        assert result["resultados"][0]["score"] == 0.95
        assert result["resultados"][0]["colecao"] == "despesas"

    async def test_busca_em_multiplas_colecoes(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Deve buscar em todas as coleções solicitadas."""
        mock_store = _MockVectorStore(results=[
            SearchResult(id="multi-1", score=0.88, payload={"text": "Resultado"}),
        ])
        mock_embed = _MockEmbeddingService()

        monkeypatch.setattr(search_tools, "_embedding_service", mock_embed)
        monkeypatch.setattr(search_tools, "_vector_store", mock_store)

        result_json = await search_tools.execute(
            "busca_semantica",
            {
                "query": "pagamento fornecedor",
                "colecoes": ["despesas", "notas_fiscais"],
            },
        )

        result = json.loads(result_json)
        # Deve retornar 1 resultado por coleção = 2 resultados totais
        assert result["total"] == 2

        # Verifica que buscou em ambas as coleções
        colecoes_buscadas = [call["collection"] for call in mock_store.search_calls]
        assert "despesas" in colecoes_buscadas
        assert "notas_fiscais" in colecoes_buscadas

    async def test_busca_com_filtros(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Deve passar filtros para o vector store quando fornecidos."""
        mock_store = _MockVectorStore(results=[])
        mock_embed = _MockEmbeddingService()

        monkeypatch.setattr(search_tools, "_embedding_service", mock_embed)
        monkeypatch.setattr(search_tools, "_vector_store", mock_store)

        await search_tools.execute(
            "busca_semantica",
            {
                "query": "consulta com filtros",
                "colecoes": ["despesas"],
                "data_inicio": "2024-01-01",
                "data_fim": "2024-12-31",
                "valor_minimo": 100.0,
                "valor_maximo": 5000.0,
            },
        )

        assert len(mock_store.search_calls) == 1
        search_filter = mock_store.search_calls[0]["filters"]
        assert search_filter is not None
        assert search_filter.date_gte == "2024-01-01"
        assert search_filter.date_lte == "2024-12-31"
        assert search_filter.amount_gte == 100.0
        assert search_filter.amount_lte == 5000.0

    async def test_colecoes_padrao_quando_nao_informadas(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Deve usar as coleções padrão quando não informadas."""
        mock_store = _MockVectorStore(results=[])
        mock_embed = _MockEmbeddingService()

        monkeypatch.setattr(search_tools, "_embedding_service", mock_embed)
        monkeypatch.setattr(search_tools, "_vector_store", mock_store)

        await search_tools.execute(
            "busca_semantica",
            {"query": "teste coleções padrão"},
        )

        colecoes_buscadas = [call["collection"] for call in mock_store.search_calls]
        assert "despesas" in colecoes_buscadas
        assert "notas_fiscais" in colecoes_buscadas
        assert "lancamentos_contabeis" in colecoes_buscadas

    async def test_tool_desconhecida_levanta_value_error(self) -> None:
        """Deve levantar ValueError para nome de tool desconhecido."""
        with pytest.raises(ValueError, match="Tool não implementada"):
            await search_tools.execute("tool_inexistente", {"query": "teste"})


# ─── _build_search_filter() ──────────────────────────────────────────────────


class TestBuildSearchFilter:
    """Testes para a função _build_search_filter()."""

    def test_retorna_none_sem_filtros(self) -> None:
        """Deve retornar None quando nenhum filtro é fornecido."""
        result = search_tools._build_search_filter(
            data_inicio=None,
            data_fim=None,
            valor_minimo=None,
            valor_maximo=None,
        )

        assert result is None

    def test_filtro_apenas_data_inicio(self) -> None:
        """Deve retornar SearchFilter com apenas date_gte."""
        result = search_tools._build_search_filter(
            data_inicio="2024-01-01",
            data_fim=None,
            valor_minimo=None,
            valor_maximo=None,
        )

        assert result is not None
        assert result.date_gte == "2024-01-01"
        assert result.date_lte is None
        assert result.amount_gte is None
        assert result.amount_lte is None

    def test_filtro_apenas_data_fim(self) -> None:
        """Deve retornar SearchFilter com apenas date_lte."""
        result = search_tools._build_search_filter(
            data_inicio=None,
            data_fim="2024-12-31",
            valor_minimo=None,
            valor_maximo=None,
        )

        assert result is not None
        assert result.date_lte == "2024-12-31"

    def test_filtro_intervalo_de_datas(self) -> None:
        """Deve retornar SearchFilter com date_gte e date_lte."""
        result = search_tools._build_search_filter(
            data_inicio="2024-01-01",
            data_fim="2024-06-30",
            valor_minimo=None,
            valor_maximo=None,
        )

        assert result is not None
        assert result.date_gte == "2024-01-01"
        assert result.date_lte == "2024-06-30"

    def test_filtro_apenas_valor_minimo(self) -> None:
        """Deve retornar SearchFilter com apenas amount_gte."""
        result = search_tools._build_search_filter(
            data_inicio=None,
            data_fim=None,
            valor_minimo=500.0,
            valor_maximo=None,
        )

        assert result is not None
        assert result.amount_gte == 500.0
        assert result.amount_lte is None

    def test_filtro_apenas_valor_maximo(self) -> None:
        """Deve retornar SearchFilter com apenas amount_lte."""
        result = search_tools._build_search_filter(
            data_inicio=None,
            data_fim=None,
            valor_minimo=None,
            valor_maximo=10000.0,
        )

        assert result is not None
        assert result.amount_lte == 10000.0

    def test_filtro_completo(self) -> None:
        """Deve retornar SearchFilter com todos os campos preenchidos."""
        result = search_tools._build_search_filter(
            data_inicio="2024-01-01",
            data_fim="2024-12-31",
            valor_minimo=100.0,
            valor_maximo=50000.0,
        )

        assert result is not None
        assert result.date_gte == "2024-01-01"
        assert result.date_lte == "2024-12-31"
        assert result.amount_gte == 100.0
        assert result.amount_lte == 50000.0

    def test_filtro_valor_zero_nao_eh_ignorado(self) -> None:
        """Deve criar SearchFilter quando valor_minimo=0.0 (falsy mas válido)."""
        result = search_tools._build_search_filter(
            data_inicio=None,
            data_fim=None,
            valor_minimo=0.0,
            valor_maximo=0.0,
        )

        assert result is not None
        assert result.amount_gte == 0.0
        assert result.amount_lte == 0.0

    def test_filtro_string_vazia_eh_tratada(self) -> None:
        """Deve criar SearchFilter quando data é string vazia (falsy mas presente)."""
        result = search_tools._build_search_filter(
            data_inicio="",
            data_fim=None,
            valor_minimo=None,
            valor_maximo=None,
        )

        assert result is not None
        assert result.date_gte == ""
