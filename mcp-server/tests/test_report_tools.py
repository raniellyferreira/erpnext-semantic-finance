"""Testes unitários para as ferramentas de relatórios financeiros.

Valida a definição das tools, os dispatchers e a execução das funções
de DRE e Balancete, usando mocks do ERPNextClient.
"""

from __future__ import annotations

import json

import pytest

from src.tools import report_tools
from src.erpnext_client.exceptions import (
    ERPNextAuthError,
    ERPNextConnectionError,
    ERPNextNotFoundError,
    ERPNextServerError,
    ERPNextValidationError,
)


# ─── Mock do ERPNextClient ────────────────────────────────────────────────────


class _MockERPNextClient:
    """Mock do ERPNextClient com suporte a call_method."""

    def __init__(
        self,
        call_method_result: dict | None = None,
        raise_on: type[Exception] | None = None,
    ) -> None:
        self._call_method_result = call_method_result or {}
        self._raise_on = raise_on
        self.call_method_calls: list[dict] = []

    async def call_method(self, method: str, params: dict) -> dict:
        self.call_method_calls.append({"method": method, "params": params})
        if self._raise_on:
            raise self._raise_on("Erro simulado", status_code=500)
        return self._call_method_result

    async def close(self):
        pass


# ─── get_tools() ─────────────────────────────────────────────────────────────


class TestGetTools:
    """Testes para a definição das tools de relatório."""

    def test_retorna_duas_tools(self) -> None:
        """Deve retornar exatamente 2 tools de relatório."""
        tools = report_tools.get_tools()
        assert len(tools) == 2

    def test_nomes_das_tools(self) -> None:
        """As tools devem ter os nomes 'gerar_dre' e 'gerar_balancete'."""
        nomes = [t.name for t in report_tools.get_tools()]
        assert "gerar_dre" in nomes
        assert "gerar_balancete" in nomes

    def test_gerar_dre_campos_obrigatorios(self) -> None:
        """gerar_dre deve exigir data_inicio e data_fim."""
        tools = {t.name: t for t in report_tools.get_tools()}
        schema = tools["gerar_dre"].inputSchema
        assert "data_inicio" in schema["required"]
        assert "data_fim" in schema["required"]

    def test_gerar_balancete_campos_obrigatorios(self) -> None:
        """gerar_balancete deve exigir data_inicio e data_fim."""
        tools = {t.name: t for t in report_tools.get_tools()}
        schema = tools["gerar_balancete"].inputSchema
        assert "data_inicio" in schema["required"]
        assert "data_fim" in schema["required"]

    def test_empresa_e_campo_opcional(self) -> None:
        """O campo 'empresa' deve existir mas não ser obrigatório."""
        for tool in report_tools.get_tools():
            assert "empresa" in tool.inputSchema["properties"]
            assert "empresa" not in tool.inputSchema["required"]


# ─── TOOL_NAMES ──────────────────────────────────────────────────────────────


class TestToolNames:
    """Testes para a constante TOOL_NAMES."""

    def test_contem_gerar_dre(self) -> None:
        """TOOL_NAMES deve conter 'gerar_dre'."""
        assert "gerar_dre" in report_tools.TOOL_NAMES

    def test_contem_gerar_balancete(self) -> None:
        """TOOL_NAMES deve conter 'gerar_balancete'."""
        assert "gerar_balancete" in report_tools.TOOL_NAMES

    def test_tamanho_correto(self) -> None:
        """TOOL_NAMES deve conter exatamente 2 entradas."""
        assert len(report_tools.TOOL_NAMES) == 2


# ─── execute() dispatcher ────────────────────────────────────────────────────


class TestExecute:
    """Testes para o dispatcher execute()."""

    async def test_tool_desconhecida_levanta_value_error(self) -> None:
        """Deve levantar ValueError para nome de tool desconhecido."""
        with pytest.raises(ValueError, match="Tool de relatório não reconhecida"):
            await report_tools.execute("tool_inexistente", {})


# ─── _gerar_dre ──────────────────────────────────────────────────────────────


class TestGerarDre:
    """Testes para a tool gerar_dre."""

    async def test_chama_relatorio_correto(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Deve invocar o relatório 'Profit and Loss Statement' no ERPNext."""
        resultado_api = {
            "result": [{"account": "Receita", "total": 100000.0}],
            "columns": [{"fieldname": "account"}, {"fieldname": "total"}],
            "report_summary": [{"value": 100000.0, "label": "Total Receita"}],
        }
        mock_client = _MockERPNextClient(call_method_result=resultado_api)
        monkeypatch.setattr(report_tools, "_client", mock_client)

        result_json = await report_tools.execute(
            "gerar_dre",
            {"data_inicio": "2024-01-01", "data_fim": "2024-12-31"},
        )

        # Verifica que chamou o método correto
        assert len(mock_client.call_method_calls) == 1
        call = mock_client.call_method_calls[0]
        assert call["method"] == "frappe.desk.query_report.run"
        assert call["params"]["report_name"] == "Profit and Loss Statement"
        assert call["params"]["filters"]["from_date"] == "2024-01-01"
        assert call["params"]["filters"]["to_date"] == "2024-12-31"

        result = json.loads(result_json)
        assert result["tipo"] == "DRE"
        assert result["relatorio"] == "Demonstração do Resultado do Exercício"
        assert result["total_linhas"] == 1

    async def test_periodo_e_empresa_no_resultado(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """O resultado deve conter o período e a empresa."""
        mock_client = _MockERPNextClient(call_method_result={"result": [], "columns": []})
        monkeypatch.setattr(report_tools, "_client", mock_client)

        result_json = await report_tools.execute(
            "gerar_dre",
            {
                "data_inicio": "2024-01-01",
                "data_fim": "2024-06-30",
                "empresa": "Empresa Teste LTDA",
            },
        )

        result = json.loads(result_json)
        assert result["periodo"]["inicio"] == "2024-01-01"
        assert result["periodo"]["fim"] == "2024-06-30"
        assert result["empresa"] == "Empresa Teste LTDA"

    async def test_erro_auth_retorna_json_de_erro(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Deve retornar JSON de erro de autenticação."""
        mock_client = _MockERPNextClient(raise_on=ERPNextAuthError)
        monkeypatch.setattr(report_tools, "_client", mock_client)

        result_json = await report_tools.execute(
            "gerar_dre",
            {"data_inicio": "2024-01-01", "data_fim": "2024-12-31"},
        )

        result = json.loads(result_json)
        assert result["erro"] is True
        assert result["tipo"] == "autenticacao"

    async def test_resultado_vazio_retorna_zero_linhas(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Deve retornar total_linhas=0 quando relatório não tem dados."""
        mock_client = _MockERPNextClient(
            call_method_result={"result": [], "columns": [], "report_summary": []}
        )
        monkeypatch.setattr(report_tools, "_client", mock_client)

        result_json = await report_tools.execute(
            "gerar_dre",
            {"data_inicio": "2024-01-01", "data_fim": "2024-12-31"},
        )

        result = json.loads(result_json)
        assert result["total_linhas"] == 0
        assert result["resumo"] == []


# ─── _gerar_balancete ────────────────────────────────────────────────────────


class TestGerarBalancete:
    """Testes para a tool gerar_balancete."""

    async def test_chama_relatorio_trial_balance(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Deve invocar o relatório 'Trial Balance' no ERPNext."""
        resultado_api = {
            "result": [
                {"account": "Caixa", "debit": 5000.0, "credit": 0.0},
                {"account": "Receitas", "debit": 0.0, "credit": 5000.0},
            ],
            "columns": [],
        }
        mock_client = _MockERPNextClient(call_method_result=resultado_api)
        monkeypatch.setattr(report_tools, "_client", mock_client)

        result_json = await report_tools.execute(
            "gerar_balancete",
            {"data_inicio": "2024-01-01", "data_fim": "2024-12-31"},
        )

        call = mock_client.call_method_calls[0]
        assert call["params"]["report_name"] == "Trial Balance"

        result = json.loads(result_json)
        assert result["tipo"] == "Balancete"
        assert result["totais"]["total_debito"] == 5000.0
        assert result["totais"]["total_credito"] == 5000.0
        assert result["totais"]["diferenca"] == 0.0

    async def test_calcula_totais_corretamente(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Deve calcular corretamente os totais de débito e crédito."""
        resultado_api = {
            "result": [
                {"account": "Conta A", "debit": 1000.0, "credit": 0.0},
                {"account": "Conta B", "debit": 2000.0, "credit": 0.0},
                {"account": "Conta C", "debit": 0.0, "credit": 3000.0},
            ],
            "columns": [],
        }
        mock_client = _MockERPNextClient(call_method_result=resultado_api)
        monkeypatch.setattr(report_tools, "_client", mock_client)

        result_json = await report_tools.execute(
            "gerar_balancete",
            {"data_inicio": "2024-01-01", "data_fim": "2024-12-31"},
        )

        result = json.loads(result_json)
        assert result["totais"]["total_debito"] == 3000.0
        assert result["totais"]["total_credito"] == 3000.0
        assert result["totais"]["diferenca"] == 0.0
        assert result["total_contas"] == 3

    async def test_ignora_linhas_nao_dict_no_calculo(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Deve ignorar linhas separadoras (não-dict) no cálculo dos totais."""
        resultado_api = {
            "result": [
                {"account": "Conta A", "debit": 500.0, "credit": 0.0},
                "--- Separador ---",  # linha não-dict (separador do ERPNext)
                {"account": "Conta B", "debit": 0.0, "credit": 500.0},
            ],
            "columns": [],
        }
        mock_client = _MockERPNextClient(call_method_result=resultado_api)
        monkeypatch.setattr(report_tools, "_client", mock_client)

        result_json = await report_tools.execute(
            "gerar_balancete",
            {"data_inicio": "2024-01-01", "data_fim": "2024-12-31"},
        )

        result = json.loads(result_json)
        assert result["totais"]["total_debito"] == 500.0
        assert result["totais"]["total_credito"] == 500.0
        assert result["total_contas"] == 2  # apenas dicts contam

    async def test_erro_conexao_retorna_json_de_erro(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Deve retornar JSON de erro de conexão."""
        mock_client = _MockERPNextClient(raise_on=ERPNextConnectionError)
        monkeypatch.setattr(report_tools, "_client", mock_client)

        result_json = await report_tools.execute(
            "gerar_balancete",
            {"data_inicio": "2024-01-01", "data_fim": "2024-12-31"},
        )

        result = json.loads(result_json)
        assert result["erro"] is True
        assert result["tipo"] == "conexao"


# ─── _tratar_erro_erpnext ─────────────────────────────────────────────────────


class TestTratarErroErpnextReports:
    """Testes para a função de tratamento de erros em Português (report_tools)."""

    def test_todos_os_tipos_de_erro_cobertos(self) -> None:
        """Todos os tipos de exceção ERPNext devem ter tipo de erro mapeado."""
        casos = [
            (ERPNextAuthError(   "err", status_code=401), "autenticacao"),
            (ERPNextNotFoundError("err", status_code=404), "nao_encontrado"),
            (ERPNextValidationError("err", status_code=400), "validacao"),
            (ERPNextConnectionError("err", status_code=None), "conexao"),
            (ERPNextServerError("err", status_code=500), "servidor"),
        ]
        for exc, tipo_esperado in casos:
            result = json.loads(report_tools._tratar_erro_erpnext(exc, "teste"))
            assert result["tipo"] == tipo_esperado, (
                f"Tipo incorreto para {type(exc).__name__}: "
                f"esperado '{tipo_esperado}', obtido '{result['tipo']}'"
            )

    def test_resultado_sempre_tem_campo_erro_true(self) -> None:
        """O campo 'erro' deve ser sempre True no resultado."""
        exc = ERPNextServerError("Erro", status_code=500)
        result = json.loads(report_tools._tratar_erro_erpnext(exc, "gerar relatório"))
        assert result["erro"] is True
