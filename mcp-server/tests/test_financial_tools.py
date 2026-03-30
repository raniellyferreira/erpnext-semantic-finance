"""Testes unitários para as ferramentas financeiras do ERPNext.

Valida a definição das tools, os dispatchers e a execução das funções
de listagem, registro, fluxo de caixa e consulta de fornecedor,
usando mocks do ERPNextClient para isolar do servidor ERPNext.
"""

from __future__ import annotations

import json

import pytest

from src.tools import financial_tools
from src.erpnext_client.exceptions import (
    ERPNextAuthError,
    ERPNextConnectionError,
    ERPNextNotFoundError,
    ERPNextServerError,
    ERPNextValidationError,
)


# ─── Mock do ERPNextClient ────────────────────────────────────────────────────


class _MockERPNextClient:
    """Mock do ERPNextClient com respostas pré-configuradas."""

    def __init__(
        self,
        list_docs_results: list | None = None,
        get_doc_result: dict | None = None,
        get_doc_results_by_doctype: dict[str, dict] | None = None,
        create_doc_result: dict | None = None,
        raise_on: type[Exception] | None = None,
    ) -> None:
        self._list_docs_results = list_docs_results or []
        self._get_doc_result = get_doc_result or {}
        self._get_doc_results_by_doctype = get_doc_results_by_doctype or {}
        self._create_doc_result = create_doc_result or {}
        self._raise_on = raise_on
        self.list_docs_calls: list[dict] = []
        self.get_doc_calls: list[dict] = []
        self.create_doc_calls: list[dict] = []

    async def list_docs(self, doctype, *, filters=None, fields=None, limit=20):
        self.list_docs_calls.append({"doctype": doctype, "filters": filters, "limit": limit})
        if self._raise_on:
            raise self._raise_on("Erro simulado", status_code=500)
        if isinstance(self._list_docs_results, list) and self._list_docs_results:
            return self._list_docs_results
        return self._list_docs_results

    async def get_doc(self, doctype, name):
        self.get_doc_calls.append({"doctype": doctype, "name": name})
        if self._raise_on:
            raise self._raise_on("Erro simulado", status_code=500)
        if doctype in self._get_doc_results_by_doctype:
            return self._get_doc_results_by_doctype[doctype]
        return self._get_doc_result

    async def create_doc(self, doctype, data):
        self.create_doc_calls.append({"doctype": doctype, "data": data})
        if self._raise_on:
            raise self._raise_on("Erro simulado", status_code=500)
        return self._create_doc_result

    async def close(self):
        pass


# ─── get_tools() ─────────────────────────────────────────────────────────────


class TestGetTools:
    """Testes para a definição das tools financeiras."""

    def test_retorna_quatro_tools(self) -> None:
        """Deve retornar exatamente 4 tools financeiras."""
        tools = financial_tools.get_tools()
        assert len(tools) == 4

    def test_nomes_das_tools(self) -> None:
        """As tools devem ter os nomes corretos."""
        nomes = [t.name for t in financial_tools.get_tools()]
        assert "listar_despesas" in nomes
        assert "registrar_despesa" in nomes
        assert "consultar_fluxo_caixa" in nomes
        assert "consultar_fornecedor" in nomes

    def test_listar_despesas_campos_obrigatorios(self) -> None:
        """listar_despesas deve exigir data_inicio e data_fim."""
        tools = {t.name: t for t in financial_tools.get_tools()}
        schema = tools["listar_despesas"].inputSchema
        assert "data_inicio" in schema["required"]
        assert "data_fim" in schema["required"]

    def test_registrar_despesa_campos_obrigatorios(self) -> None:
        """registrar_despesa deve exigir todos os campos obrigatórios."""
        tools = {t.name: t for t in financial_tools.get_tools()}
        schema = tools["registrar_despesa"].inputSchema
        for campo in ["fornecedor", "valor", "data", "centro_custo", "conta_debito", "descricao"]:
            assert campo in schema["required"], f"Campo '{campo}' deveria ser obrigatório"

    def test_consultar_fornecedor_requer_cnpj_ou_nome(self) -> None:
        """consultar_fornecedor deve exigir cnpj_ou_nome."""
        tools = {t.name: t for t in financial_tools.get_tools()}
        schema = tools["consultar_fornecedor"].inputSchema
        assert "cnpj_ou_nome" in schema["required"]


# ─── TOOL_NAMES ──────────────────────────────────────────────────────────────


class TestToolNames:
    """Testes para a constante TOOL_NAMES."""

    def test_contem_todas_as_tools(self) -> None:
        """TOOL_NAMES deve conter todas as tools financeiras."""
        for name in [
            "listar_despesas",
            "registrar_despesa",
            "consultar_fluxo_caixa",
            "consultar_fornecedor",
        ]:
            assert name in financial_tools.TOOL_NAMES

    def test_tamanho_correto(self) -> None:
        """TOOL_NAMES deve conter exatamente 4 entradas."""
        assert len(financial_tools.TOOL_NAMES) == 4


# ─── execute() dispatcher ────────────────────────────────────────────────────


class TestExecute:
    """Testes para o dispatcher execute()."""

    async def test_tool_desconhecida_levanta_value_error(self) -> None:
        """Deve levantar ValueError para nome de tool desconhecido."""
        with pytest.raises(ValueError, match="Tool financeira não reconhecida"):
            await financial_tools.execute("tool_inexistente", {})


# ─── _listar_despesas ─────────────────────────────────────────────────────────


class TestListarDespesas:
    """Testes para a tool listar_despesas."""

    async def test_retorna_despesas_no_periodo(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Deve retornar a lista de despesas para o período informado."""
        mock_docs = [
            {"name": "PE-001", "paid_amount": 500.0, "party": "Fornecedor A"},
            {"name": "PE-002", "paid_amount": 1200.0, "party": "Fornecedor B"},
        ]
        mock_client = _MockERPNextClient(list_docs_results=mock_docs)
        monkeypatch.setattr(financial_tools, "_client", mock_client)

        result_json = await financial_tools.execute(
            "listar_despesas",
            {"data_inicio": "2024-01-01", "data_fim": "2024-12-31"},
        )

        result = json.loads(result_json)
        assert result["total"] == 2
        assert len(result["despesas"]) == 2
        assert result["despesas"][0]["name"] == "PE-001"

    async def test_filtros_sao_passados_corretamente(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Deve incluir filtros de fornecedor, centro de custo e valor mínimo."""
        mock_client = _MockERPNextClient(list_docs_results=[])
        monkeypatch.setattr(financial_tools, "_client", mock_client)

        await financial_tools.execute(
            "listar_despesas",
            {
                "data_inicio": "2024-01-01",
                "data_fim": "2024-06-30",
                "fornecedor": "Fornecedor Teste",
                "centro_custo": "CC-01",
                "valor_minimo": 100.0,
                "limite": 10,
            },
        )

        assert len(mock_client.list_docs_calls) == 1
        call = mock_client.list_docs_calls[0]
        filtros = call["filters"]
        assert call["limit"] == 10
        # Verifica presença dos filtros
        assert any(f[0] == "party" and f[2] == "Fornecedor Teste" for f in filtros)
        assert any(f[0] == "cost_center" and f[2] == "CC-01" for f in filtros)
        assert any(f[0] == "paid_amount" and f[2] == 100.0 for f in filtros)

    async def test_retorna_apenas_payment_type_pay(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Deve filtrar apenas Payment Entries do tipo Pay."""
        mock_client = _MockERPNextClient(list_docs_results=[])
        monkeypatch.setattr(financial_tools, "_client", mock_client)

        await financial_tools.execute(
            "listar_despesas",
            {"data_inicio": "2024-01-01", "data_fim": "2024-12-31"},
        )

        filtros = mock_client.list_docs_calls[0]["filters"]
        assert any(f[0] == "payment_type" and f[2] == "Pay" for f in filtros)

    async def test_erro_erpnext_retorna_json_de_erro(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Deve retornar JSON de erro quando o ERPNextClient falha."""
        mock_client = _MockERPNextClient(raise_on=ERPNextAuthError)
        monkeypatch.setattr(financial_tools, "_client", mock_client)

        result_json = await financial_tools.execute(
            "listar_despesas",
            {"data_inicio": "2024-01-01", "data_fim": "2024-12-31"},
        )

        result = json.loads(result_json)
        assert result["erro"] is True
        assert result["tipo"] == "autenticacao"


# ─── _registrar_despesa ───────────────────────────────────────────────────────


class TestRegistrarDespesa:
    """Testes para a tool registrar_despesa."""

    async def test_cria_payment_entry_com_campos_corretos(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Deve criar Payment Entry com todos os campos obrigatórios."""
        mock_client = _MockERPNextClient(
            get_doc_results_by_doctype={
                "Supplier": {"default_payable_account": "Credores - TC"},
                "Company": {"default_currency": "BRL"},
            },
            create_doc_result={"name": "PE-NEW-001", "docstatus": 0},
        )
        monkeypatch.setattr(financial_tools, "_client", mock_client)

        result_json = await financial_tools.execute(
            "registrar_despesa",
            {
                "fornecedor": "Fornecedor Teste",
                "valor": 1500.0,
                "data": "2024-03-15",
                "centro_custo": "Principal",
                "conta_debito": "Caixa - TC",
                "descricao": "Pagamento de serviço",
            },
        )

        result = json.loads(result_json)
        assert result["sucesso"] is True
        assert result["documento"] == "PE-NEW-001"
        assert "Rascunho" in result["aviso"]

        # Valida campos enviados ao ERPNext
        assert len(mock_client.create_doc_calls) == 1
        payload = mock_client.create_doc_calls[0]["data"]
        assert payload["payment_type"] == "Pay"
        assert payload["party_type"] == "Supplier"
        assert payload["party"] == "Fornecedor Teste"
        assert payload["paid_amount"] == 1500.0
        assert payload["received_amount"] == 1500.0
        assert payload["paid_to"] == "Credores - TC"
        assert payload["paid_from_account_currency"] == "BRL"
        assert payload["paid_to_account_currency"] == "BRL"
        # exchange_rate não deve ser enviado (ERPNext calcula automaticamente)
        assert "source_exchange_rate" not in payload
        assert "target_exchange_rate" not in payload

    async def test_usa_conta_padrao_da_empresa_quando_fornecedor_sem_conta(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Deve usar conta padrão da empresa se fornecedor não tiver conta configurada."""
        call_count = 0

        class _MockClientComFallback:
            async def get_doc(self, doctype, name):
                nonlocal call_count
                call_count += 1
                if doctype == "Supplier":
                    return {"name": name}  # sem default_payable_account
                if doctype == "Company":
                    return {
                        "default_payable_account": "Fornecedores - TC",
                        "default_currency": "BRL",
                    }
                return {}

            async def list_docs(self, *a, **kw):
                return []

            async def create_doc(self, doctype, data):
                return {"name": "PE-FALLBACK-001", "docstatus": 0}

            async def close(self):
                pass

        monkeypatch.setattr(financial_tools, "_client", _MockClientComFallback())

        result_json = await financial_tools.execute(
            "registrar_despesa",
            {
                "fornecedor": "Novo Fornecedor",
                "valor": 500.0,
                "data": "2024-04-01",
                "centro_custo": "CC-01",
                "conta_debito": "Caixa - TC",
                "descricao": "Teste fallback",
            },
        )

        result = json.loads(result_json)
        assert result["sucesso"] is True

    async def test_modo_pagamento_padrao(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Deve usar 'Transferência Bancária' como modo de pagamento padrão."""
        mock_client = _MockERPNextClient(
            get_doc_results_by_doctype={
                "Supplier": {"default_payable_account": "Credores - TC"},
                "Company": {"default_currency": "BRL"},
            },
            create_doc_result={"name": "PE-DEFAULT-001", "docstatus": 0},
        )
        monkeypatch.setattr(financial_tools, "_client", mock_client)

        await financial_tools.execute(
            "registrar_despesa",
            {
                "fornecedor": "Fornecedor X",
                "valor": 100.0,
                "data": "2024-01-10",
                "centro_custo": "CC-01",
                "conta_debito": "Caixa - TC",
                "descricao": "Teste modo padrão",
            },
        )

        payload = mock_client.create_doc_calls[0]["data"]
        assert payload["mode_of_payment"] == "Transferência Bancária"

    async def test_erro_validacao_retorna_json_de_erro(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Deve retornar JSON de erro de validação."""
        mock_client = _MockERPNextClient(raise_on=ERPNextValidationError)
        monkeypatch.setattr(financial_tools, "_client", mock_client)

        result_json = await financial_tools.execute(
            "registrar_despesa",
            {
                "fornecedor": "Fornecedor Inválido",
                "valor": 100.0,
                "data": "2024-01-10",
                "centro_custo": "CC-01",
                "conta_debito": "Caixa - TC",
                "descricao": "Teste erro",
            },
        )

        result = json.loads(result_json)
        assert result["erro"] is True
        assert result["tipo"] == "validacao"


# ─── _consultar_fluxo_caixa ───────────────────────────────────────────────────


class TestConsultarFluxoCaixa:
    """Testes para a tool consultar_fluxo_caixa."""

    async def test_agrega_entradas_e_saidas_corretamente(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Deve somar entradas (Receive) e saídas (Pay) corretamente."""
        movimentacoes = [
            {"name": "PE-001", "payment_type": "Receive", "paid_amount": 5000.0},
            {"name": "PE-002", "payment_type": "Receive", "paid_amount": 3000.0},
            {"name": "PE-003", "payment_type": "Pay",     "paid_amount": 2000.0},
            {"name": "PE-004", "payment_type": "Pay",     "paid_amount": 800.0},
        ]
        mock_client = _MockERPNextClient(list_docs_results=movimentacoes)
        monkeypatch.setattr(financial_tools, "_client", mock_client)

        result_json = await financial_tools.execute(
            "consultar_fluxo_caixa",
            {"data_inicio": "2024-01-01", "data_fim": "2024-12-31"},
        )

        result = json.loads(result_json)
        assert result["total_entradas"] == 8000.0
        assert result["total_saidas"] == 2800.0
        assert result["saldo_liquido"] == 5200.0
        assert result["total_movimentacoes"] == 4

    async def test_inclui_transferencias_internas(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Deve separar transferências internas das entradas e saídas."""
        movimentacoes = [
            {"payment_type": "Internal Transfer", "paid_amount": 1000.0},
        ]
        mock_client = _MockERPNextClient(list_docs_results=movimentacoes)
        monkeypatch.setattr(financial_tools, "_client", mock_client)

        result_json = await financial_tools.execute(
            "consultar_fluxo_caixa",
            {"data_inicio": "2024-01-01", "data_fim": "2024-01-31"},
        )

        result = json.loads(result_json)
        assert result["total_transferencias"] == 1000.0
        assert result["total_entradas"] == 0.0
        assert result["total_saidas"] == 0.0
        assert result["saldo_liquido"] == 0.0

    async def test_fluxo_vazio_retorna_zeros(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Deve retornar zeros quando não há movimentações no período."""
        mock_client = _MockERPNextClient(list_docs_results=[])
        monkeypatch.setattr(financial_tools, "_client", mock_client)

        result_json = await financial_tools.execute(
            "consultar_fluxo_caixa",
            {"data_inicio": "2024-01-01", "data_fim": "2024-01-31"},
        )

        result = json.loads(result_json)
        assert result["total_entradas"] == 0.0
        assert result["total_saidas"] == 0.0
        assert result["saldo_liquido"] == 0.0
        assert result["total_movimentacoes"] == 0

    async def test_periodo_e_empresa_no_resultado(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """O resultado deve conter o período e a empresa consultados."""
        mock_client = _MockERPNextClient(list_docs_results=[])
        monkeypatch.setattr(financial_tools, "_client", mock_client)

        result_json = await financial_tools.execute(
            "consultar_fluxo_caixa",
            {
                "data_inicio": "2024-03-01",
                "data_fim": "2024-03-31",
                "empresa": "Empresa Teste LTDA",
            },
        )

        result = json.loads(result_json)
        assert result["periodo"]["inicio"] == "2024-03-01"
        assert result["periodo"]["fim"] == "2024-03-31"
        assert result["empresa"] == "Empresa Teste LTDA"

    async def test_erro_conexao_retorna_json_de_erro(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Deve retornar JSON de erro de conexão."""
        mock_client = _MockERPNextClient(raise_on=ERPNextConnectionError)
        monkeypatch.setattr(financial_tools, "_client", mock_client)

        result_json = await financial_tools.execute(
            "consultar_fluxo_caixa",
            {"data_inicio": "2024-01-01", "data_fim": "2024-12-31"},
        )

        result = json.loads(result_json)
        assert result["erro"] is True
        assert result["tipo"] == "conexao"


# ─── _consultar_fornecedor ────────────────────────────────────────────────────


class TestConsultarFornecedor:
    """Testes para a tool consultar_fornecedor."""

    async def test_retorna_dados_do_fornecedor_encontrado(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Deve retornar dados cadastrais filtrados do fornecedor quando encontrado."""

        class _MockFornecedorClient:
            async def list_docs(self, doctype, *, filters=None, fields=None, limit=20):
                if doctype == "Supplier":
                    # Busca por nome
                    if any("like" in f for f in (filters or []) if isinstance(f, list)):
                        return [{"name": "SUP-001"}]
                    return []
                if doctype == "Payment Entry":
                    return [{"name": "PE-001", "paid_amount": 500.0}]
                if doctype == "Purchase Invoice":
                    return []
                return []

            async def get_doc(self, doctype, name):
                return {
                    "name": "SUP-001",
                    "supplier_name": "Fornecedor Teste",
                    "tax_id": "12345678000199",
                    "supplier_type": "Company",
                    "creation": "2024-01-01 00:00:00",
                    "owner": "admin@example.com",
                    "_user_tags": "",
                }

            async def close(self):
                pass

        monkeypatch.setattr(financial_tools, "_client", _MockFornecedorClient())

        result_json = await financial_tools.execute(
            "consultar_fornecedor",
            {"cnpj_ou_nome": "Fornecedor Teste"},
        )

        result = json.loads(result_json)
        assert result["encontrado"] is True
        assert result["fornecedor"]["supplier_name"] == "Fornecedor Teste"
        assert result["historico_pagamentos"]["total"] == 1
        assert result["faturas_pendentes"]["total"] == 0

        # Verifica que campos internos não são expostos
        assert "creation" not in result["fornecedor"]
        assert "owner" not in result["fornecedor"]
        assert "_user_tags" not in result["fornecedor"]

    async def test_retorna_nao_encontrado_quando_inexistente(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Deve retornar encontrado=False quando o fornecedor não existe."""
        mock_client = _MockERPNextClient(list_docs_results=[])
        monkeypatch.setattr(financial_tools, "_client", mock_client)

        result_json = await financial_tools.execute(
            "consultar_fornecedor",
            {"cnpj_ou_nome": "Fornecedor Inexistente"},
        )

        result = json.loads(result_json)
        assert result["encontrado"] is False
        assert "não encontrado" in result["mensagem"]

    async def test_busca_por_cnpj_com_14_digitos(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Deve tentar buscar por tax_id quando entrada tem 14 dígitos."""

        class _MockClientCNPJ:
            def __init__(self):
                self.calls: list[dict] = []

            async def list_docs(self, doctype, *, filters=None, fields=None, limit=20):
                self.calls.append({"doctype": doctype, "filters": filters})
                if doctype == "Supplier":
                    for f in (filters or []):
                        if isinstance(f, list) and f[0] == "tax_id":
                            return [{"name": "SUP-CNPJ-001"}]
                    return []
                if doctype == "Payment Entry":
                    return []
                if doctype == "Purchase Invoice":
                    return []
                return []

            async def get_doc(self, doctype, name):
                return {"name": name, "supplier_name": "Fornecedor CNPJ"}

            async def close(self):
                pass

        mock = _MockClientCNPJ()
        monkeypatch.setattr(financial_tools, "_client", mock)

        result_json = await financial_tools.execute(
            "consultar_fornecedor",
            {"cnpj_ou_nome": "12345678000199"},
        )

        result = json.loads(result_json)
        assert result["encontrado"] is True

        # Verifica que buscou por tax_id
        tax_id_calls = [
            c for c in mock.calls
            if c["doctype"] == "Supplier"
            and any(
                isinstance(f, list) and f[0] == "tax_id"
                for f in (c["filters"] or [])
            )
        ]
        assert len(tax_id_calls) > 0

    async def test_erro_server_retorna_json_de_erro(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Deve retornar JSON de erro de servidor."""
        mock_client = _MockERPNextClient(raise_on=ERPNextServerError)
        monkeypatch.setattr(financial_tools, "_client", mock_client)

        result_json = await financial_tools.execute(
            "consultar_fornecedor",
            {"cnpj_ou_nome": "Fornecedor Qualquer"},
        )

        result = json.loads(result_json)
        assert result["erro"] is True
        assert result["tipo"] == "servidor"


# ─── _tratar_erro_erpnext ─────────────────────────────────────────────────────


class TestTratarErroErpnext:
    """Testes para a função de tratamento de erros em Português."""

    def test_auth_error_retorna_tipo_autenticacao(self) -> None:
        """ERPNextAuthError deve retornar tipo 'autenticacao'."""
        exc = ERPNextAuthError("Unauthorized", status_code=401)
        result = json.loads(financial_tools._tratar_erro_erpnext(exc, "teste"))
        assert result["tipo"] == "autenticacao"
        assert result["erro"] is True

    def test_not_found_error_retorna_tipo_nao_encontrado(self) -> None:
        """ERPNextNotFoundError deve retornar tipo 'nao_encontrado'."""
        exc = ERPNextNotFoundError("Not found", status_code=404)
        result = json.loads(financial_tools._tratar_erro_erpnext(exc, "teste"))
        assert result["tipo"] == "nao_encontrado"

    def test_validation_error_retorna_tipo_validacao(self) -> None:
        """ERPNextValidationError deve retornar tipo 'validacao'."""
        exc = ERPNextValidationError("Invalid", status_code=400)
        result = json.loads(financial_tools._tratar_erro_erpnext(exc, "teste"))
        assert result["tipo"] == "validacao"

    def test_connection_error_retorna_tipo_conexao(self) -> None:
        """ERPNextConnectionError deve retornar tipo 'conexao'."""
        exc = ERPNextConnectionError("Timeout", status_code=None)
        result = json.loads(financial_tools._tratar_erro_erpnext(exc, "teste"))
        assert result["tipo"] == "conexao"

    def test_server_error_retorna_tipo_servidor(self) -> None:
        """ERPNextServerError deve retornar tipo 'servidor'."""
        exc = ERPNextServerError("Internal error", status_code=500)
        result = json.loads(financial_tools._tratar_erro_erpnext(exc, "teste"))
        assert result["tipo"] == "servidor"

    def test_mensagens_em_portugues(self) -> None:
        """Todas as mensagens de erro devem estar em Português."""
        for exc_class, status in [
            (ERPNextAuthError, 401),
            (ERPNextNotFoundError, 404),
            (ERPNextValidationError, 400),
            (ERPNextConnectionError, None),
            (ERPNextServerError, 500),
        ]:
            exc = exc_class("Mensagem original", status_code=status)
            result = json.loads(financial_tools._tratar_erro_erpnext(exc, "operação"))
            # Deve conter palavras em Português
            assert any(
                palavra in result["mensagem"]
                for palavra in ["permissão", "encontrado", "inválidos", "conectar", "Erro"]
            ), (
                f"Mensagem não está em Português para {exc_class.__name__}: "
                f"{result['mensagem']}"
            )
