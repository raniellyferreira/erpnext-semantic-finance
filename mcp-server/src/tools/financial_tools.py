"""Ferramentas de gestão financeira — despesas, fluxo de caixa e fornecedores.

Implementa as tools ``listar_despesas``, ``registrar_despesa``,
``consultar_fluxo_caixa`` e ``consultar_fornecedor`` para o MCP Server,
permitindo que LLMs consultem e registrem movimentações financeiras
no ERPNext via API REST.
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

TOOL_NAMES: list[str] = [
    "listar_despesas",
    "registrar_despesa",
    "consultar_fluxo_caixa",
    "consultar_fornecedor",
]

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
        logger.info("financial_tools_recursos_liberados")


def get_tools() -> list[types.Tool]:
    """Retorna a definição das tools financeiras para registro no MCP Server."""
    return [
        types.Tool(
            name="listar_despesas",
            description=(
                "Lista despesas (pagamentos a fornecedores) registradas no ERPNext. "
                "Filtra por período, fornecedor, centro de custo e valor mínimo."
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
                    "fornecedor": {
                        "type": "string",
                        "description": "Nome exato do fornecedor no ERPNext (opcional).",
                    },
                    "centro_custo": {
                        "type": "string",
                        "description": "Nome do centro de custo para filtrar (opcional).",
                    },
                    "valor_minimo": {
                        "type": "number",
                        "description": "Valor mínimo da despesa em reais (opcional).",
                    },
                    "limite": {
                        "type": "integer",
                        "description": "Número máximo de registros retornados. Padrão: 50.",
                    },
                },
                "required": ["data_inicio", "data_fim"],
            },
        ),
        types.Tool(
            name="registrar_despesa",
            description=(
                "Registra um novo pagamento a fornecedor no ERPNext (Payment Entry tipo Pay). "
                "Cria o documento em status Rascunho para revisão antes de submeter."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "fornecedor": {
                        "type": "string",
                        "description": "Nome exato do fornecedor cadastrado no ERPNext.",
                    },
                    "valor": {
                        "type": "number",
                        "description": "Valor do pagamento em reais.",
                    },
                    "data": {
                        "type": "string",
                        "description": "Data do pagamento (ISO 8601). Ex: '2024-03-15'",
                    },
                    "centro_custo": {
                        "type": "string",
                        "description": "Centro de custo para rateio da despesa.",
                    },
                    "conta_debito": {
                        "type": "string",
                        "description": (
                            "Conta bancária ou caixa de origem do pagamento (paid_from). "
                            "Ex: 'Caixa - XPTO'"
                        ),
                    },
                    "descricao": {
                        "type": "string",
                        "description": "Observações ou motivo do pagamento.",
                    },
                    "modo_pagamento": {
                        "type": "string",
                        "description": "Modo de pagamento. Padrão: 'Transferência Bancária'.",
                    },
                },
                "required": [
                    "fornecedor",
                    "valor",
                    "data",
                    "centro_custo",
                    "conta_debito",
                    "descricao",
                ],
            },
        ),
        types.Tool(
            name="consultar_fluxo_caixa",
            description=(
                "Calcula o fluxo de caixa de um período: total de entradas (recebimentos), "
                "saídas (pagamentos) e saldo líquido, agrupados por tipo de movimentação."
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
            name="consultar_fornecedor",
            description=(
                "Consulta dados de um fornecedor por CNPJ ou nome, incluindo histórico "
                "de pagamentos recentes e faturas pendentes."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "cnpj_ou_nome": {
                        "type": "string",
                        "description": (
                            "CNPJ (somente dígitos ou com máscara) ou parte do nome "
                            "do fornecedor."
                        ),
                    },
                },
                "required": ["cnpj_ou_nome"],
            },
        ),
    ]


async def execute(name: str, arguments: dict) -> str:
    """Despacha a execução da tool financeira pelo nome.

    Args:
        name: Nome da tool a ser executada.
        arguments: Argumentos recebidos do LLM.

    Returns:
        Resultado serializado em JSON.

    Raises:
        ValueError: Se o nome da tool não for reconhecido.
    """
    match name:
        case "listar_despesas":
            return await _listar_despesas(arguments)
        case "registrar_despesa":
            return await _registrar_despesa(arguments)
        case "consultar_fluxo_caixa":
            return await _consultar_fluxo_caixa(arguments)
        case "consultar_fornecedor":
            return await _consultar_fornecedor(arguments)
        case _:
            raise ValueError(f"Tool financeira não reconhecida: {name}")


# ─── Implementações internas ──────────────────────────────────────────────────


async def _listar_despesas(arguments: dict) -> str:
    """Lista Payment Entries do tipo Pay com filtros opcionais."""
    data_inicio: str = arguments["data_inicio"]
    data_fim: str = arguments["data_fim"]
    fornecedor: str | None = arguments.get("fornecedor")
    centro_custo: str | None = arguments.get("centro_custo")
    valor_minimo_raw = arguments.get("valor_minimo")
    valor_minimo: float | None = float(valor_minimo_raw) if valor_minimo_raw is not None else None
    limite: int = arguments.get("limite", 50)

    logger.info(
        "listar_despesas_iniciado",
        data_inicio=data_inicio,
        data_fim=data_fim,
        fornecedor=fornecedor,
        centro_custo=centro_custo,
        valor_minimo=valor_minimo,
        limite=limite,
    )

    filtros: list[list] = [
        ["payment_type", "=", "Pay"],
        ["docstatus", "=", 1],
        ["posting_date", ">=", data_inicio],
        ["posting_date", "<=", data_fim],
    ]
    if fornecedor:
        filtros.append(["party", "=", fornecedor])
    if centro_custo:
        filtros.append(["cost_center", "=", centro_custo])
    if valor_minimo is not None:
        filtros.append(["paid_amount", ">=", valor_minimo])

    campos = [
        "name",
        "posting_date",
        "party",
        "party_name",
        "paid_amount",
        "mode_of_payment",
        "cost_center",
        "remarks",
        "status",
        "paid_from",
        "reference_no",
    ]

    try:
        client = await _get_client()
        documentos = await client.list_docs(
            "Payment Entry",
            filters=filtros,
            fields=campos,
            limit=limite,
        )
    except ERPNextError as exc:
        return _tratar_erro_erpnext(exc, "listar despesas")

    logger.info("listar_despesas_concluido", total=len(documentos))

    return json.dumps(
        {"total": len(documentos), "despesas": documentos},
        ensure_ascii=False,
        default=str,
    )


async def _registrar_despesa(arguments: dict) -> str:
    """Cria um Payment Entry (tipo Pay) no ERPNext."""
    fornecedor: str = arguments["fornecedor"]
    data: str = arguments["data"]
    centro_custo: str = arguments["centro_custo"]
    conta_debito: str = arguments["conta_debito"]
    descricao: str = arguments["descricao"]
    modo_pagamento: str = arguments.get("modo_pagamento", "Transferência Bancária")

    try:
        valor: float = float(arguments["valor"])
    except (TypeError, ValueError) as exc:
        return json.dumps(
            {
                "erro": True,
                "tipo": "validacao",
                "mensagem": f"Valor inválido para despesa: '{arguments.get('valor')}'. "
                            f"Informe um número válido em reais. Detalhe: {exc}",
            },
            ensure_ascii=False,
        )

    logger.info(
        "registrar_despesa_iniciado",
        fornecedor=fornecedor,
        valor=valor,
        data=data,
    )

    try:
        client = await _get_client()
        paid_to = await _resolver_conta_fornecedor(client, fornecedor)

        payload = {
            "doctype": "Payment Entry",
            "payment_type": "Pay",
            "posting_date": data,
            "company": settings.erpnext_default_company,
            "party_type": "Supplier",
            "party": fornecedor,
            "paid_from": conta_debito,
            "paid_from_account_currency": "BRL",
            "paid_to": paid_to,
            "paid_to_account_currency": "BRL",
            "paid_amount": valor,
            "received_amount": valor,
            "source_exchange_rate": 1.0,
            "target_exchange_rate": 1.0,
            "mode_of_payment": modo_pagamento,
            "cost_center": centro_custo,
            "remarks": descricao,
        }

        documento_criado = await client.create_doc("Payment Entry", payload)

    except ERPNextError as exc:
        return _tratar_erro_erpnext(exc, "registrar despesa")

    nome_doc = documento_criado.get("name", "—")
    logger.info("registrar_despesa_concluido", documento=nome_doc)

    return json.dumps(
        {
            "sucesso": True,
            "mensagem": f"Despesa registrada com sucesso. ID: {nome_doc}",
            "documento": nome_doc,
            "status": documento_criado.get("docstatus", 0),
            "aviso": (
                "Documento criado em Rascunho (docstatus=0). "
                "Submeta no ERPNext para confirmar o lançamento."
            ),
        },
        ensure_ascii=False,
    )


async def _consultar_fluxo_caixa(arguments: dict) -> str:
    """Agrega Payment Entries por tipo para calcular entradas, saídas e saldo."""
    data_inicio: str = arguments["data_inicio"]
    data_fim: str = arguments["data_fim"]
    empresa: str = arguments.get("empresa") or settings.erpnext_default_company

    logger.info(
        "consultar_fluxo_caixa_iniciado",
        data_inicio=data_inicio,
        data_fim=data_fim,
        empresa=empresa,
    )

    filtros: list[list] = [
        ["docstatus", "=", 1],
        ["posting_date", ">=", data_inicio],
        ["posting_date", "<=", data_fim],
        ["company", "=", empresa],
    ]
    campos = [
        "name",
        "payment_type",
        "paid_amount",
        "posting_date",
        "party",
        "party_type",
    ]

    try:
        client = await _get_client()
        movimentacoes = await client.list_docs(
            "Payment Entry",
            filters=filtros,
            fields=campos,
            limit=5000,
        )
    except ERPNextError as exc:
        return _tratar_erro_erpnext(exc, "consultar fluxo de caixa")

    # ─── Agregação por tipo de movimentação ──────────────────────────────────
    total_entradas = 0.0
    total_saidas = 0.0
    total_transferencias = 0.0

    for mov in movimentacoes:
        valor = float(mov.get("paid_amount") or 0)
        tipo = mov.get("payment_type", "")
        if tipo == "Receive":
            total_entradas += valor
        elif tipo == "Pay":
            total_saidas += valor
        elif tipo == "Internal Transfer":
            total_transferencias += valor

    logger.info(
        "consultar_fluxo_caixa_concluido",
        empresa=empresa,
        total_movimentacoes=len(movimentacoes),
    )

    return json.dumps(
        {
            "periodo": {"inicio": data_inicio, "fim": data_fim},
            "empresa": empresa,
            "total_entradas": round(total_entradas, 2),
            "total_saidas": round(total_saidas, 2),
            "saldo_liquido": round(total_entradas - total_saidas, 2),
            "total_transferencias": round(total_transferencias, 2),
            "total_movimentacoes": len(movimentacoes),
        },
        ensure_ascii=False,
    )


async def _consultar_fornecedor(arguments: dict) -> str:
    """Consulta fornecedor por CNPJ ou nome, com histórico e pendências."""
    cnpj_ou_nome: str = arguments["cnpj_ou_nome"]

    logger.info("consultar_fornecedor_iniciado", cnpj_ou_nome=cnpj_ou_nome)

    try:
        client = await _get_client()
        supplier_name = await _localizar_fornecedor(client, cnpj_ou_nome)

        if not supplier_name:
            return json.dumps(
                {
                    "encontrado": False,
                    "mensagem": f"Fornecedor '{cnpj_ou_nome}' não encontrado no ERPNext.",
                },
                ensure_ascii=False,
            )

        dados_fornecedor = await client.get_doc("Supplier", supplier_name)

        historico_pagamentos = await client.list_docs(
            "Payment Entry",
            filters=[
                ["party_type", "=", "Supplier"],
                ["party", "=", supplier_name],
                ["docstatus", "=", 1],
            ],
            fields=[
                "name",
                "posting_date",
                "paid_amount",
                "mode_of_payment",
                "remarks",
            ],
            limit=10,
        )

        faturas_pendentes = await client.list_docs(
            "Purchase Invoice",
            filters=[
                ["supplier", "=", supplier_name],
                ["status", "in", ["Unpaid", "Overdue"]],
                ["docstatus", "=", 1],
            ],
            fields=[
                "name",
                "posting_date",
                "due_date",
                "grand_total",
                "status",
                "bill_no",
            ],
            limit=20,
        )

    except ERPNextError as exc:
        return _tratar_erro_erpnext(exc, "consultar fornecedor")

    valor_pendente = round(
        sum(float(f.get("grand_total") or 0) for f in faturas_pendentes),
        2,
    )

    logger.info(
        "consultar_fornecedor_concluido",
        supplier=supplier_name,
        pagamentos=len(historico_pagamentos),
        faturas_pendentes=len(faturas_pendentes),
    )

    return json.dumps(
        {
            "encontrado": True,
            "fornecedor": dados_fornecedor,
            "historico_pagamentos": {
                "total": len(historico_pagamentos),
                "registros": historico_pagamentos,
            },
            "faturas_pendentes": {
                "total": len(faturas_pendentes),
                "valor_total": valor_pendente,
                "registros": faturas_pendentes,
            },
        },
        ensure_ascii=False,
        default=str,
    )


# ─── Auxiliares internos ─────────────────────────────────────────────────────


async def _localizar_fornecedor(client: ERPNextClient, cnpj_ou_nome: str) -> str | None:
    """Localiza o name (ID) do fornecedor por CNPJ (tax_id) ou nome parcial.

    Tenta primeiro por tax_id com a string original; se o input tiver
    14 dígitos, tenta também a versão somente-dígitos. Cai em busca
    LIKE por nome como fallback final.

    Args:
        client: Instância do ERPNextClient.
        cnpj_ou_nome: CNPJ com ou sem máscara, ou parte do nome do fornecedor.

    Returns:
        Identificador interno do fornecedor (campo ``name``), ou ``None`` se
        não encontrado.
    """
    apenas_digitos = "".join(c for c in cnpj_ou_nome if c.isdigit())

    # ─── Tentativa por CNPJ (tax_id) ─────────────────────────────────────────
    if apenas_digitos and len(apenas_digitos) == 14:
        for valor_cnpj in {cnpj_ou_nome, apenas_digitos}:
            resultados = await client.list_docs(
                "Supplier",
                filters=[["tax_id", "=", valor_cnpj]],
                fields=["name"],
                limit=1,
            )
            if resultados:
                return resultados[0]["name"]

    # ─── Fallback: busca parcial por nome ────────────────────────────────────
    resultados = await client.list_docs(
        "Supplier",
        filters=[["supplier_name", "like", f"%{cnpj_ou_nome}%"]],
        fields=["name"],
        limit=1,
    )
    if resultados:
        return resultados[0]["name"]

    return None


async def _resolver_conta_fornecedor(client: ERPNextClient, fornecedor: str) -> str:
    """Resolve a conta contábil de crédito (Contas a Pagar) para o fornecedor.

    Consulta primeiro o campo ``default_payable_account`` do Supplier.
    Se não configurado, usa a conta padrão da empresa (``default_payable_account``
    no DocType Company).

    Args:
        client: Instância do ERPNextClient.
        fornecedor: Nome (ID) do fornecedor no ERPNext.

    Returns:
        Nome da conta contábil de Contas a Pagar.

    Raises:
        ERPNextValidationError: Se nenhuma conta padrão estiver configurada.
    """
    try:
        supplier = await client.get_doc("Supplier", fornecedor)
        conta = supplier.get("default_payable_account")
        if conta:
            return conta
    except ERPNextNotFoundError:
        pass

    company = await client.get_doc("Company", settings.erpnext_default_company)
    conta_padrao = company.get("default_payable_account")
    if not conta_padrao:
        raise ERPNextValidationError(
            "Conta padrão de fornecedores não configurada na empresa. "
            "Configure 'default_payable_account' no DocType Company no ERPNext.",
            status_code=None,
        )
    return conta_padrao


def _tratar_erro_erpnext(exc: ERPNextError, operacao: str) -> str:
    """Converte exceções do ERPNextClient em mensagens amigáveis em Português.

    Args:
        exc: Exceção capturada do ERPNextClient.
        operacao: Descrição da operação que falhou (ex: 'listar despesas').

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
            f"Registro não encontrado ao {operacao}. "
            f"Verifique se o ID ou nome está correto. Detalhe: {exc.message}"
        )
    elif isinstance(exc, ERPNextValidationError):
        tipo_erro = "validacao"
        mensagem = f"Dados inválidos ao {operacao}. Detalhe: {exc.message}"
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
        "financial_tools.erro",
        operacao=operacao,
        tipo=tipo_erro,
        exc_type=type(exc).__name__,
        status_code=exc.status_code,
    )

    return json.dumps(
        {"erro": True, "tipo": tipo_erro, "mensagem": mensagem},
        ensure_ascii=False,
    )

