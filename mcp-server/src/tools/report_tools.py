"""Ferramentas de relatórios financeiros — DRE e Balancete.

Implementa as tools ``gerar_dre`` e ``gerar_balancete`` para o MCP Server,
invocando os relatórios nativos do ERPNext via método Frappe
``frappe.desk.query_report.run``.
"""

from __future__ import annotations

import asyncio
import json

import mcp.types as types
import structlog

from ..config import settings
from ..erpnext_client.client import ERPNextClient
from ..erpnext_client.exceptions import (
    ERPNextAuthError,
    ERPNextConnectionError,
    ERPNextError,
    ERPNextNotFoundError,
    ERPNextServerError,
    ERPNextValidationError,
)

logger = structlog.get_logger(__name__)

TOOL_NAMES: list[str] = ["gerar_dre", "gerar_balancete"]

# Singleton do ERPNextClient — lazy init com double-checked locking
_client: ERPNextClient | None = None
_init_lock = asyncio.Lock()


async def _get_client() -> ERPNextClient:
    """Retorna o singleton do ERPNextClient (lazy init com double-checked locking)."""
    global _client  # noqa: PLW0603
    if _client is None:
        async with _init_lock:
            if _client is None:
                _client = ERPNextClient()
    return _client


async def close() -> None:
    """Fecha os recursos do singleton ERPNextClient.

    Deve ser chamado no shutdown do servidor para liberar conexões HTTP abertas.
    """
    global _client  # noqa: PLW0603
    if _client is not None:
        await _client.close()
        _client = None
        logger.info("report_tools_recursos_liberados")


def get_tools() -> list[types.Tool]:
    """Retorna a definição das tools de relatório para registro no MCP Server."""
    return [
        types.Tool(
            name="gerar_dre",
            description=(
                "Gera a Demonstração do Resultado do Exercício (DRE) do ERPNext. "
                "Exibe receitas, custos, despesas e lucro/prejuízo líquido do período."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "data_inicio": {
                        "type": "string",
                        "description": "Data inicial do período (ISO 8601). Ex: '2024-01-01'",
                    },
                    "data_fim": {
                        "type": "string",
                        "description": "Data final do período (ISO 8601). Ex: '2024-12-31'",
                    },
                    "empresa": {
                        "type": "string",
                        "description": "Nome da empresa. Usa o padrão do .env se omitido.",
                    },
                },
                "required": ["data_inicio", "data_fim"],
            },
        ),
        types.Tool(
            name="gerar_balancete",
            description=(
                "Gera o Balancete de Verificação do ERPNext. "
                "Lista todos os saldos de contas contábeis (débitos e créditos) do período."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "data_inicio": {
                        "type": "string",
                        "description": "Data inicial do período (ISO 8601). Ex: '2024-01-01'",
                    },
                    "data_fim": {
                        "type": "string",
                        "description": "Data final do período (ISO 8601). Ex: '2024-12-31'",
                    },
                    "empresa": {
                        "type": "string",
                        "description": "Nome da empresa. Usa o padrão do .env se omitido.",
                    },
                },
                "required": ["data_inicio", "data_fim"],
            },
        ),
    ]


async def execute(name: str, arguments: dict) -> str:
    """Despacha a execução da tool de relatório pelo nome.

    Args:
        name: Nome da tool a ser executada.
        arguments: Argumentos recebidos do LLM.

    Returns:
        Resultado serializado em JSON.

    Raises:
        ValueError: Se o nome da tool não for reconhecido.
    """
    match name:
        case "gerar_dre":
            return await _gerar_dre(arguments)
        case "gerar_balancete":
            return await _gerar_balancete(arguments)
        case _:
            raise ValueError(f"Tool de relatório não reconhecida: {name}")


# ─── Implementações internas ──────────────────────────────────────────────────


async def _gerar_dre(arguments: dict) -> str:
    """Gera a DRE via relatório 'Profit and Loss Statement' do ERPNext."""
    data_inicio: str = arguments["data_inicio"]
    data_fim: str = arguments["data_fim"]
    empresa: str = arguments.get("empresa") or settings.erpnext_default_company

    logger.info(
        "gerar_dre_iniciado",
        data_inicio=data_inicio,
        data_fim=data_fim,
        empresa=empresa,
    )

    params = {
        "report_name": "Profit and Loss Statement",
        "filters": {
            "company": empresa,
            "from_date": data_inicio,
            "to_date": data_fim,
        },
    }

    try:
        client = await _get_client()
        resultado = await client.call_method("frappe.desk.query_report.run", params)
    except ERPNextError as exc:
        return _tratar_erro_erpnext(exc, "gerar DRE")

    resposta = _processar_dre(resultado, empresa, data_inicio, data_fim)
    logger.info("gerar_dre_concluido", empresa=empresa, total_linhas=resposta["total_linhas"])

    return json.dumps(resposta, ensure_ascii=False, default=str)


async def _gerar_balancete(arguments: dict) -> str:
    """Gera o Balancete via relatório 'Trial Balance' do ERPNext."""
    data_inicio: str = arguments["data_inicio"]
    data_fim: str = arguments["data_fim"]
    empresa: str = arguments.get("empresa") or settings.erpnext_default_company

    logger.info(
        "gerar_balancete_iniciado",
        data_inicio=data_inicio,
        data_fim=data_fim,
        empresa=empresa,
    )

    params = {
        "report_name": "Trial Balance",
        "filters": {
            "company": empresa,
            "from_date": data_inicio,
            "to_date": data_fim,
        },
    }

    try:
        client = await _get_client()
        resultado = await client.call_method("frappe.desk.query_report.run", params)
    except ERPNextError as exc:
        return _tratar_erro_erpnext(exc, "gerar balancete")

    resposta = _processar_balancete(resultado, empresa, data_inicio, data_fim)
    logger.info(
        "gerar_balancete_concluido",
        empresa=empresa,
        total_contas=resposta["total_contas"],
    )

    return json.dumps(resposta, ensure_ascii=False, default=str)


# ─── Processadores de resultado ──────────────────────────────────────────────


def _processar_dre(
    resultado: dict, empresa: str, data_inicio: str, data_fim: str
) -> dict:
    """Estrutura a resposta do relatório 'Profit and Loss Statement' para o LLM.

    Args:
        resultado: Dicionário retornado pelo ``call_method``.
        empresa: Nome da empresa.
        data_inicio: Data inicial do período.
        data_fim: Data final do período.

    Returns:
        Dicionário estruturado com metadados, colunas, linhas e resumo.
    """
    linhas = resultado.get("result", [])
    colunas = resultado.get("columns", [])
    resumo = resultado.get("report_summary", [])

    return {
        "tipo": "DRE",
        "relatorio": "Demonstração do Resultado do Exercício",
        "empresa": empresa,
        "periodo": {"inicio": data_inicio, "fim": data_fim},
        "colunas": colunas,
        "linhas": linhas,
        "resumo": resumo,
        "total_linhas": len(linhas),
    }


def _processar_balancete(
    resultado: dict, empresa: str, data_inicio: str, data_fim: str
) -> dict:
    """Estrutura a resposta do relatório 'Trial Balance' para o LLM.

    Calcula os totais de débito e crédito e verifica o equilíbrio
    (diferença deve ser 0 em um balancete correto).

    Args:
        resultado: Dicionário retornado pelo ``call_method``.
        empresa: Nome da empresa.
        data_inicio: Data inicial do período.
        data_fim: Data final do período.

    Returns:
        Dicionário estruturado com metadados, colunas, linhas e totais.
    """
    linhas = resultado.get("result", [])
    colunas = resultado.get("columns", [])

    total_debito = sum(
        float(linha.get("debit") or 0)
        for linha in linhas
        if isinstance(linha, dict)
    )
    total_credito = sum(
        float(linha.get("credit") or 0)
        for linha in linhas
        if isinstance(linha, dict)
    )

    return {
        "tipo": "Balancete",
        "relatorio": "Balancete de Verificação",
        "empresa": empresa,
        "periodo": {"inicio": data_inicio, "fim": data_fim},
        "colunas": colunas,
        "linhas": linhas,
        "totais": {
            "total_debito": round(total_debito, 2),
            "total_credito": round(total_credito, 2),
            "diferenca": round(total_debito - total_credito, 2),
        },
        "total_contas": len([ln for ln in linhas if isinstance(ln, dict)]),
    }


# ─── Tratamento de Erros ─────────────────────────────────────────────────────


def _tratar_erro_erpnext(exc: ERPNextError, operacao: str) -> str:
    """Converte exceções do ERPNextClient em mensagens amigáveis em Português.

    Args:
        exc: Exceção capturada do ERPNextClient.
        operacao: Descrição da operação que falhou (ex: 'gerar DRE').

    Returns:
        JSON com ``{"erro": True, "tipo": ..., "mensagem": ...}``.
    """
    tipo_erro: str
    mensagem: str

    if isinstance(exc, ERPNextAuthError):
        tipo_erro = "autenticacao"
        mensagem = (
            f"Sem permissão para {operacao}. "
            "Verifique as credenciais da API do ERPNext (ERPNEXT_API_KEY / ERPNEXT_API_SECRET)."
        )
    elif isinstance(exc, ERPNextNotFoundError):
        tipo_erro = "nao_encontrado"
        mensagem = (
            f"Recurso não encontrado ao {operacao}. "
            f"Verifique se o relatório existe no ERPNext. Detalhe: {exc.message}"
        )
    elif isinstance(exc, ERPNextValidationError):
        tipo_erro = "validacao"
        mensagem = f"Parâmetros inválidos ao {operacao}. Detalhe: {exc.message}"
    elif isinstance(exc, ERPNextConnectionError):
        tipo_erro = "conexao"
        mensagem = (
            f"Não foi possível conectar ao ERPNext para {operacao}. "
            "Verifique se o servidor está acessível e tente novamente em instantes."
        )
    elif isinstance(exc, ERPNextServerError):
        tipo_erro = "servidor"
        mensagem = (
            f"Erro interno do ERPNext ao {operacao}. "
            "Tente novamente ou verifique os logs do servidor ERPNext."
        )
    else:
        tipo_erro = "desconhecido"
        mensagem = f"Erro inesperado ao {operacao}: {exc.message}"

    logger.error(
        "report_tools.erro",
        operacao=operacao,
        tipo=tipo_erro,
        exc_type=type(exc).__name__,
        status_code=exc.status_code,
    )

    return json.dumps(
        {"erro": True, "tipo": tipo_erro, "mensagem": mensagem},
        ensure_ascii=False,
    )

