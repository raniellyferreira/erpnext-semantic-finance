"""Exceções customizadas para erros HTTP do ERPNext.

Hierarquia de exceções que mapeia códigos HTTP para tipos semânticos,
permitindo tratamento granular de erros no código de negócio sem acoplar
às bibliotecas HTTP subjacentes.
"""


class ERPNextError(Exception):
    """Exceção base para todos os erros da API ERPNext.

    Attributes:
        message: Descrição legível do erro.
        status_code: Código HTTP retornado (quando aplicável).
        doctype: DocType envolvido na operação (quando aplicável).
        name: Nome/ID do documento envolvido (quando aplicável).
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        doctype: str | None = None,
        name: str | None = None,
    ) -> None:
        self.message = message
        self.status_code = status_code
        self.doctype = doctype
        self.name = name
        super().__init__(self._format_message())

    def _format_message(self) -> str:
        """Formata a mensagem incluindo contexto quando disponível."""
        parts = [self.message]
        if self.status_code is not None:
            parts.append(f"status={self.status_code}")
        if self.doctype:
            parts.append(f"doctype={self.doctype}")
        if self.name:
            parts.append(f"name={self.name}")
        return " | ".join(parts)


class ERPNextAuthError(ERPNextError):
    """Erro de autenticação ou autorização (HTTP 401/403).

    Indica credenciais inválidas, token expirado ou permissão insuficiente
    para acessar o recurso solicitado no ERPNext.
    """


class ERPNextNotFoundError(ERPNextError):
    """Recurso não encontrado (HTTP 404).

    O DocType ou documento solicitado não existe no ERPNext.
    """


class ERPNextValidationError(ERPNextError):
    """Erro de validação nos dados enviados (HTTP 400/422).

    Os dados enviados não atendem às regras de validação do ERPNext,
    como campos obrigatórios ausentes ou valores inválidos.
    """


class ERPNextServerError(ERPNextError):
    """Erro interno do servidor ERPNext (HTTP 5xx).

    Indica falha no lado do servidor. Operações com este erro
    são candidatas a retry automático.
    """


class ERPNextConnectionError(ERPNextError):
    """Erro de conexão ou timeout com o ERPNext.

    O servidor ERPNext está inacessível, a conexão foi recusada
    ou o tempo limite foi excedido. Operações com este erro
    são candidatas a retry automático.
    """
