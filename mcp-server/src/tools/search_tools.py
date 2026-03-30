"""Ferramenta de busca semântica no banco vetorial.

Implementa a tool ``busca_semantica`` para o MCP Server, permitindo que
LLMs pesquisem documentos financeiros (despesas, notas fiscais,
lançamentos contábeis) usando linguagem natural com filtros híbridos.

A ferramenta segue o padrão Hexagonal Architecture — acessa o banco
vetorial exclusivamente via ``create_vector_store()`` e gera embeddings
via ``EmbeddingService``, sem acoplamento a implementações concretas.
"""

from __future__ import annotations

import asyncio
import json

import mcp.types as types
import structlog

from ..vector_store.embeddings import EmbeddingService
from ..vector_store.factory import create_vector_store
from ..vector_store.port import SearchFilter, VectorStorePort

logger = structlog.get_logger(__name__)

TOOL_NAMES: list[str] = ["busca_semantica"]

_DEFAULT_COLLECTIONS = ["despesas", "notas_fiscais", "lancamentos_contabeis"]

# Singletons de módulo — evita recriar conexões HTTP e clientes a cada chamada.
# Inicializados de forma lazy na primeira execução, protegidos por lock.
_embedding_service: EmbeddingService | None = None
_vector_store: VectorStorePort | None = None
_init_lock = asyncio.Lock()


async def _get_embedding_service() -> EmbeddingService:
    """Retorna a instância singleton do EmbeddingService (lazy init com lock)."""
    global _embedding_service  # noqa: PLW0603
    if _embedding_service is None:
        async with _init_lock:
            if _embedding_service is None:
                _embedding_service = EmbeddingService()
    return _embedding_service


async def _get_vector_store() -> VectorStorePort:
    """Retorna a instância singleton do VectorStore (lazy init com lock)."""
    global _vector_store  # noqa: PLW0603
    if _vector_store is None:
        async with _init_lock:
            if _vector_store is None:
                _vector_store = create_vector_store()
    return _vector_store


async def close() -> None:
    """Fecha os recursos dos singletons (embedding service e vector store).

    Deve ser chamado no shutdown do servidor para liberar conexões HTTP
    e sockets abertos, evitando resource warnings.
    """
    global _embedding_service, _vector_store  # noqa: PLW0603

    if _embedding_service is not None:
        await _embedding_service.close()
        _embedding_service = None
        logger.info("embedding_service_encerrado")

    _vector_store = None
    logger.info("search_tools_recursos_liberados")


def get_tools() -> list[types.Tool]:
    """Retorna a definição das tools de busca para registro no MCP Server."""
    return [
        types.Tool(
            name="busca_semantica",
            description=(
                "Realiza busca semântica em documentos financeiros do ERPNext. "
                "Pesquisa em despesas, notas fiscais e lançamentos contábeis "
                "usando linguagem natural, com filtros opcionais de data e valor."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": (
                            "Texto da busca em linguagem natural. "
                            "Ex: 'despesas com material de escritório acima de 500 reais'"
                        ),
                    },
                    "colecoes": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Coleções onde buscar. "
                            "Padrão: ['despesas', 'notas_fiscais', 'lancamentos_contabeis']"
                        ),
                    },
                    "limite": {
                        "type": "integer",
                        "description": "Número máximo de resultados por coleção. Padrão: 10",
                    },
                    "data_inicio": {
                        "type": "string",
                        "description": "Data inicial do filtro (ISO 8601). Ex: '2024-01-01'",
                    },
                    "data_fim": {
                        "type": "string",
                        "description": "Data final do filtro (ISO 8601). Ex: '2024-12-31'",
                    },
                    "valor_minimo": {
                        "type": "number",
                        "description": "Valor mínimo para filtro de valor monetário.",
                    },
                    "valor_maximo": {
                        "type": "number",
                        "description": "Valor máximo para filtro de valor monetário.",
                    },
                },
                "required": ["query"],
            },
        ),
    ]


async def execute(name: str, arguments: dict) -> str:
    """Despacha a execução da tool pelo nome.

    Args:
        name: Nome da tool a ser executada.
        arguments: Argumentos recebidos do LLM.

    Returns:
        Resultado serializado em JSON.

    Raises:
        ValueError: Se o nome da tool não for reconhecido.
    """
    if name == "busca_semantica":
        return await _busca_semantica(arguments)

    raise ValueError(f"Tool não implementada: {name}")


# ─── Implementação interna ──────────────────────────────────────────────────


async def _busca_semantica(arguments: dict) -> str:
    """Executa a busca semântica nas coleções configuradas.

    Gera o embedding da query, aplica filtros híbridos opcionais
    e busca em cada coleção solicitada.
    """
    query: str = arguments["query"]
    colecoes: list[str] = arguments.get("colecoes", _DEFAULT_COLLECTIONS)
    limite: int = arguments.get("limite", 10)
    data_inicio: str | None = arguments.get("data_inicio")
    data_fim: str | None = arguments.get("data_fim")
    valor_minimo: float | None = arguments.get("valor_minimo")
    valor_maximo: float | None = arguments.get("valor_maximo")

    logger.info(
        "busca_semantica_iniciada",
        query=query,
        colecoes=colecoes,
        limite=limite,
        data_inicio=data_inicio,
        data_fim=data_fim,
        valor_minimo=valor_minimo,
        valor_maximo=valor_maximo,
    )

    # Gera embedding da query
    embedding_service = await _get_embedding_service()
    query_vector = await embedding_service.embed(query)

    # Monta filtros híbridos (vetorial + metadados)
    search_filter = _build_search_filter(
        data_inicio=data_inicio,
        data_fim=data_fim,
        valor_minimo=valor_minimo,
        valor_maximo=valor_maximo,
    )

    # Busca em cada coleção via porta abstrata
    vector_store = await _get_vector_store()
    resultados: list[dict] = []

    for colecao in colecoes:
        results = await vector_store.search(
            collection=colecao,
            query_vector=query_vector,
            limit=limite,
            filters=search_filter,
        )

        for result in results:
            resultados.append({
                "colecao": colecao,
                "id": result.id,
                "score": result.score,
                "dados": result.payload,
            })

    logger.info(
        "busca_semantica_concluida",
        query=query,
        total_resultados=len(resultados),
    )

    return json.dumps(
        {"query": query, "total": len(resultados), "resultados": resultados},
        ensure_ascii=False,
        default=str,
    )


def _build_search_filter(
    *,
    data_inicio: str | None,
    data_fim: str | None,
    valor_minimo: float | None,
    valor_maximo: float | None,
) -> SearchFilter | None:
    """Constrói o ``SearchFilter`` a partir dos parâmetros da tool.

    Retorna ``None`` se nenhum filtro foi fornecido.
    """
    has_filters = (
        data_inicio is not None
        or data_fim is not None
        or valor_minimo is not None
        or valor_maximo is not None
    )

    if not has_filters:
        return None

    return SearchFilter(
        date_gte=data_inicio,
        date_lte=data_fim,
        amount_gte=valor_minimo,
        amount_lte=valor_maximo,
    )
