"""Testes de integração para o ERPNextClient.

Valida operações CRUD com respostas HTTP mockadas via pytest-httpx,
incluindo mapeamento de erros HTTP para exceções semânticas e
gerenciamento do ciclo de vida (context manager).
"""

from __future__ import annotations

import json
import re

import pytest
from pytest_httpx import HTTPXMock

from src.erpnext_client.client import ERPNextClient
from src.erpnext_client.exceptions import (
    ERPNextAuthError,
    ERPNextNotFoundError,
    ERPNextServerError,
    ERPNextValidationError,
)

BASE_URL = "https://test.erpnext.com"
AUTH_HEADER = "token test-key:test-secret"


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _make_client() -> ERPNextClient:
    """Cria um ERPNextClient configurado para testes."""
    return ERPNextClient(base_url=BASE_URL, auth_header=AUTH_HEADER)


# ─── GET /api/resource/{doctype}/{name} ──────────────────────────────────────


class TestGetDoc:
    """Testes para ERPNextClient.get_doc()."""

    async def test_retorna_dados_para_resposta_200(self, httpx_mock: HTTPXMock) -> None:
        """Deve retornar os dados do documento para uma resposta 200."""
        expected_data = {
            "name": "SINV-00001",
            "grand_total": 1500.00,
            "customer": "Cliente Teste",
        }

        httpx_mock.add_response(
            url=re.compile(rf"{re.escape(BASE_URL)}/api/resource/Sales%20Invoice/SINV-00001"),
            json={"data": expected_data},
        )

        async with _make_client() as client:
            result = await client.get_doc("Sales Invoice", "SINV-00001")

        assert result == expected_data
        assert result["name"] == "SINV-00001"
        assert result["grand_total"] == 1500.00


# ─── GET /api/resource/{doctype} (list) ──────────────────────────────────────


class TestListDocs:
    """Testes para ERPNextClient.list_docs()."""

    async def test_retorna_lista_com_filtros(self, httpx_mock: HTTPXMock) -> None:
        """Deve retornar lista de documentos quando filtros são aplicados."""
        expected_data = [
            {"name": "PE-001", "paid_amount": 500.0},
            {"name": "PE-002", "paid_amount": 1200.0},
        ]

        httpx_mock.add_response(
            url=re.compile(rf"{re.escape(BASE_URL)}/api/resource/Payment%20Entry"),
            json={"data": expected_data},
        )

        async with _make_client() as client:
            result = await client.list_docs(
                "Payment Entry",
                filters={"status": "Submitted"},
                limit=10,
            )

        assert len(result) == 2
        assert result[0]["name"] == "PE-001"
        assert result[1]["paid_amount"] == 1200.0

    async def test_retorna_lista_vazia_quando_sem_resultados(self, httpx_mock: HTTPXMock) -> None:
        """Deve retornar lista vazia quando a API não encontra documentos."""
        httpx_mock.add_response(
            url=re.compile(rf"{re.escape(BASE_URL)}/api/resource/Payment%20Entry"),
            json={"data": []},
        )

        async with _make_client() as client:
            result = await client.list_docs("Payment Entry")

        assert result == []


# ─── POST /api/resource/{doctype} ────────────────────────────────────────────


class TestCreateDoc:
    """Testes para ERPNextClient.create_doc()."""

    async def test_envia_payload_correto(self, httpx_mock: HTTPXMock) -> None:
        """Deve enviar o payload correto e retornar os dados do documento criado."""
        created_doc = {
            "name": "JE-00001",
            "voucher_type": "Journal Entry",
            "total_debit": 1000.0,
        }

        httpx_mock.add_response(
            url=re.compile(rf"{re.escape(BASE_URL)}/api/resource/Journal%20Entry"),
            json={"data": created_doc},
            status_code=200,
        )

        payload = {
            "voucher_type": "Journal Entry",
            "accounts": [
                {"account": "Debit - TC", "debit_in_account_currency": 1000.0},
                {"account": "Credit - TC", "credit_in_account_currency": 1000.0},
            ],
        }

        async with _make_client() as client:
            result = await client.create_doc("Journal Entry", payload)

        assert result["name"] == "JE-00001"

        # Valida que a requisição enviou o payload correto
        request = httpx_mock.get_request()
        assert request is not None
        assert request.method == "POST"
        sent_body = json.loads(request.content)
        assert sent_body["voucher_type"] == "Journal Entry"
        assert len(sent_body["accounts"]) == 2


# ─── PUT /api/resource/{doctype}/{name} ──────────────────────────────────────


class TestUpdateDoc:
    """Testes para ERPNextClient.update_doc()."""

    async def test_envia_payload_de_atualizacao(self, httpx_mock: HTTPXMock) -> None:
        """Deve enviar o payload de atualização e retornar os dados atualizados."""
        updated_doc = {
            "name": "PINV-00001",
            "status": "Paid",
            "grand_total": 2500.0,
        }

        httpx_mock.add_response(
            url=re.compile(rf"{re.escape(BASE_URL)}/api/resource/Purchase%20Invoice/PINV-00001"),
            json={"data": updated_doc},
        )

        async with _make_client() as client:
            result = await client.update_doc(
                "Purchase Invoice",
                "PINV-00001",
                {"status": "Paid"},
            )

        assert result["status"] == "Paid"

        request = httpx_mock.get_request()
        assert request is not None
        assert request.method == "PUT"
        sent_body = json.loads(request.content)
        assert sent_body["status"] == "Paid"


# ─── Mapeamento de erros HTTP → Exceções ─────────────────────────────────────


class TestErrorHandling:
    """Testes para o mapeamento de status HTTP em exceções semânticas."""

    async def test_401_levanta_auth_error(self, httpx_mock: HTTPXMock) -> None:
        """HTTP 401 deve levantar ERPNextAuthError."""
        httpx_mock.add_response(
            url=re.compile(rf"{re.escape(BASE_URL)}/api/resource/Sales%20Invoice/SINV-001"),
            json={"message": "Not authenticated"},
            status_code=401,
        )

        async with _make_client() as client:
            with pytest.raises(ERPNextAuthError) as exc_info:
                await client.get_doc("Sales Invoice", "SINV-001")

        assert exc_info.value.status_code == 401

    async def test_404_levanta_not_found_error(self, httpx_mock: HTTPXMock) -> None:
        """HTTP 404 deve levantar ERPNextNotFoundError."""
        httpx_mock.add_response(
            url=re.compile(rf"{re.escape(BASE_URL)}/api/resource/Sales%20Invoice/SINV-999"),
            json={"message": "Not found"},
            status_code=404,
        )

        async with _make_client() as client:
            with pytest.raises(ERPNextNotFoundError) as exc_info:
                await client.get_doc("Sales Invoice", "SINV-999")

        assert exc_info.value.status_code == 404
        assert exc_info.value.doctype == "Sales Invoice"
        assert exc_info.value.name == "SINV-999"

    async def test_400_levanta_validation_error(self, httpx_mock: HTTPXMock) -> None:
        """HTTP 400 deve levantar ERPNextValidationError."""
        httpx_mock.add_response(
            url=re.compile(rf"{re.escape(BASE_URL)}/api/resource/Journal%20Entry"),
            json={"message": "Missing mandatory fields"},
            status_code=400,
        )

        async with _make_client() as client:
            with pytest.raises(ERPNextValidationError) as exc_info:
                await client.create_doc("Journal Entry", {})

        assert exc_info.value.status_code == 400

    async def test_500_levanta_server_error(self, httpx_mock: HTTPXMock) -> None:
        """HTTP 500 deve levantar ERPNextServerError (com 3 tentativas de retry)."""
        # O decorator @retry tenta 3 vezes — precisamos registrar 3 respostas
        for _ in range(3):
            httpx_mock.add_response(
                url=re.compile(rf"{re.escape(BASE_URL)}/api/resource/Payment%20Entry/PE-001"),
                json={"message": "Internal server error"},
                status_code=500,
            )

        async with _make_client() as client:
            with pytest.raises(ERPNextServerError) as exc_info:
                await client.get_doc("Payment Entry", "PE-001")

        assert exc_info.value.status_code == 500


# ─── Context Manager ────────────────────────────────────────────────────────


class TestContextManager:
    """Testes para o ciclo de vida via async context manager."""

    async def test_abre_e_fecha_corretamente(self, httpx_mock: HTTPXMock) -> None:
        """O client deve funcionar como async context manager."""
        httpx_mock.add_response(
            url=f"{BASE_URL}/api/resource/Supplier/SUP-001",
            json={"data": {"name": "SUP-001", "supplier_name": "Fornecedor Teste"}},
        )

        async with _make_client() as client:
            result = await client.get_doc("Supplier", "SUP-001")
            assert result["supplier_name"] == "Fornecedor Teste"

    async def test_close_pode_ser_chamado_diretamente(self, httpx_mock: HTTPXMock) -> None:
        """close() deve poder ser chamado diretamente sem context manager."""
        httpx_mock.add_response(
            url=f"{BASE_URL}/api/resource/Supplier/SUP-002",
            json={"data": {"name": "SUP-002"}},
        )

        client = _make_client()
        try:
            result = await client.get_doc("Supplier", "SUP-002")
            assert result["name"] == "SUP-002"
        finally:
            await client.close()
