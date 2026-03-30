"""Testes para a hierarquia de exceções do ERPNext.

Valida que cada exceção armazena corretamente os atributos de contexto
(message, status_code, doctype, name) e que a formatação da mensagem
inclui as informações disponíveis.
"""

import pytest

from src.erpnext_client.exceptions import (
    ERPNextAuthError,
    ERPNextConnectionError,
    ERPNextError,
    ERPNextNotFoundError,
    ERPNextServerError,
    ERPNextValidationError,
)


# ─── ERPNextError base ───────────────────────────────────────────────────────


class TestERPNextError:
    """Testes para a exceção base ERPNextError."""

    def test_armazena_atributos_basicos(self) -> None:
        """Deve armazenar message, status_code, doctype e name."""
        error = ERPNextError(
            "Erro de teste",
            status_code=418,
            doctype="Sales Invoice",
            name="SINV-00001",
        )

        assert error.message == "Erro de teste"
        assert error.status_code == 418
        assert error.doctype == "Sales Invoice"
        assert error.name == "SINV-00001"

    def test_atributos_opcionais_none(self) -> None:
        """Atributos opcionais devem ser None quando não informados."""
        error = ERPNextError("Erro simples")

        assert error.message == "Erro simples"
        assert error.status_code is None
        assert error.doctype is None
        assert error.name is None

    def test_format_message_sem_contexto(self) -> None:
        """_format_message deve retornar apenas a mensagem quando sem contexto."""
        error = ERPNextError("Apenas mensagem")

        assert str(error) == "Apenas mensagem"

    def test_format_message_com_status_code(self) -> None:
        """_format_message deve incluir status_code quando disponível."""
        error = ERPNextError("Erro HTTP", status_code=500)

        assert "status=500" in str(error)
        assert "Erro HTTP" in str(error)

    def test_format_message_com_doctype(self) -> None:
        """_format_message deve incluir doctype quando disponível."""
        error = ERPNextError("Erro no doc", doctype="Payment Entry")

        assert "doctype=Payment Entry" in str(error)

    def test_format_message_com_name(self) -> None:
        """_format_message deve incluir name quando disponível."""
        error = ERPNextError("Erro no doc", name="PE-00001")

        assert "name=PE-00001" in str(error)

    def test_format_message_completo(self) -> None:
        """_format_message deve incluir todos os campos separados por ' | '."""
        error = ERPNextError(
            "Documento inválido",
            status_code=404,
            doctype="Purchase Invoice",
            name="PINV-00005",
        )

        formatted = str(error)
        assert formatted == (
            "Documento inválido | status=404 | doctype=Purchase Invoice | name=PINV-00005"
        )

    def test_eh_instancia_de_exception(self) -> None:
        """ERPNextError deve ser subclasse de Exception."""
        error = ERPNextError("teste")
        assert isinstance(error, Exception)


# ─── Subclasses ──────────────────────────────────────────────────────────────


class TestSubclasses:
    """Testes para verificar que cada subclasse herda de ERPNextError."""

    @pytest.mark.parametrize(
        "exc_class",
        [
            ERPNextAuthError,
            ERPNextNotFoundError,
            ERPNextValidationError,
            ERPNextServerError,
            ERPNextConnectionError,
        ],
    )
    def test_subclasse_eh_instancia_de_erpnext_error(
        self, exc_class: type[ERPNextError]
    ) -> None:
        """Cada subclasse deve ser instância de ERPNextError."""
        error = exc_class("Mensagem de teste", status_code=400)

        assert isinstance(error, ERPNextError)
        assert isinstance(error, Exception)

    @pytest.mark.parametrize(
        "exc_class",
        [
            ERPNextAuthError,
            ERPNextNotFoundError,
            ERPNextValidationError,
            ERPNextServerError,
            ERPNextConnectionError,
        ],
    )
    def test_subclasse_herda_atributos(self, exc_class: type[ERPNextError]) -> None:
        """Cada subclasse deve herdar os atributos da classe base."""
        error = exc_class(
            "Erro da subclasse",
            status_code=500,
            doctype="Journal Entry",
            name="JE-00001",
        )

        assert error.message == "Erro da subclasse"
        assert error.status_code == 500
        assert error.doctype == "Journal Entry"
        assert error.name == "JE-00001"

    def test_auth_error_pode_ser_capturada_como_base(self) -> None:
        """ERPNextAuthError deve ser capturada por 'except ERPNextError'."""
        with pytest.raises(ERPNextError):
            raise ERPNextAuthError("Sem permissão", status_code=403)

    def test_not_found_error_pode_ser_capturada_como_base(self) -> None:
        """ERPNextNotFoundError deve ser capturada por 'except ERPNextError'."""
        with pytest.raises(ERPNextError):
            raise ERPNextNotFoundError("Não encontrado", status_code=404)

    def test_server_error_pode_ser_capturada_como_base(self) -> None:
        """ERPNextServerError deve ser capturada por 'except ERPNextError'."""
        with pytest.raises(ERPNextError):
            raise ERPNextServerError("Erro interno", status_code=500)
