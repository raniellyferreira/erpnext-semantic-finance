"""Cliente HTTP assíncrono para a API REST do ERPNext.

Implementa operações CRUD sobre DocTypes via httpx.AsyncClient,
com retry automático (exponential backoff) para erros transientes
e mapeamento de erros HTTP para exceções semânticas.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import structlog
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from ..config import settings
from .exceptions import (
    ERPNextAuthError,
    ERPNextConnectionError,
    ERPNextError,
    ERPNextNotFoundError,
    ERPNextServerError,
    ERPNextValidationError,
)

logger = structlog.get_logger(__name__)


def _should_retry(error: BaseException) -> bool:
    """Determina se o erro é transiente e elegível para retry.

    Retorna True apenas para erros de servidor (5xx) e de conexão.
    Erros de cliente (4xx) nunca são retentados.
    """
    if isinstance(error, ERPNextServerError):
        return True
    if isinstance(error, ERPNextConnectionError):
        return True
    return False


class ERPNextClient:
    """Cliente assíncrono para a API REST do ERPNext.

    Encapsula autenticação, serialização de parâmetros, tratamento de
    erros e retry automático. Deve ser utilizado como async context
    manager para garantir o fechamento correto do httpx.AsyncClient.

    Exemplo de uso::

        async with ERPNextClient() as client:
            doc = await client.get_doc("Sales Invoice", "SINV-00001")

    Attributes:
        _base_url: URL base da instância ERPNext (sem barra final).
        _http: Instância interna do httpx.AsyncClient.
    """

    def __init__(
        self,
        *,
        base_url: str | None = None,
        auth_header: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        """Inicializa o cliente com configurações do ambiente.

        Args:
            base_url: URL base do ERPNext. Padrão: ``settings.erpnext_url``.
            auth_header: Header de autenticação. Padrão: ``settings.erpnext_auth_header``.
            timeout: Timeout em segundos para requisições HTTP.
        """
        self._base_url = (base_url or settings.erpnext_url).rstrip("/")
        self._auth_header = auth_header or settings.erpnext_auth_header
        self._http = httpx.AsyncClient(
            base_url=self._base_url,
            headers={
                "Authorization": self._auth_header,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            timeout=httpx.Timeout(timeout),
        )

    # ─── Async Context Manager ────────────────────────────────────────────────

    async def __aenter__(self) -> ERPNextClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        await self.close()

    async def close(self) -> None:
        """Fecha o httpx.AsyncClient subjacente."""
        await self._http.aclose()

    # ─── CRUD Operations ─────────────────────────────────────────────────────

    @retry(
        retry=retry_if_exception_type((ERPNextServerError, ERPNextConnectionError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def get_doc(self, doctype: str, name: str) -> dict[str, Any]:
        """Busca um documento específico pelo DocType e nome.

        Args:
            doctype: Tipo do documento (ex: ``Sales Invoice``).
            name: Identificador único do documento (ex: ``SINV-00001``).

        Returns:
            Dicionário com os dados do documento.

        Raises:
            ERPNextNotFoundError: Documento não encontrado (404).
            ERPNextAuthError: Credenciais inválidas ou sem permissão (401/403).
            ERPNextServerError: Erro interno do servidor (5xx).
            ERPNextConnectionError: Falha de conexão ou timeout.
        """
        logger.debug("erpnext.get_doc", doctype=doctype, name=name)
        response = await self._request("GET", f"/api/resource/{doctype}/{name}")
        return response.get("data", response)

    @retry(
        retry=retry_if_exception_type((ERPNextServerError, ERPNextConnectionError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def list_docs(
        self,
        doctype: str,
        *,
        filters: dict[str, Any] | None = None,
        fields: list[str] | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Lista documentos de um DocType com filtros opcionais.

        Args:
            doctype: Tipo do documento (ex: ``Payment Entry``).
            filters: Filtros no formato ERPNext (ex: ``{"status": "Paid"}``).
            fields: Lista de campos a retornar (ex: ``["name", "grand_total"]``).
            limit: Número máximo de resultados. Padrão: 20.

        Returns:
            Lista de dicionários com os dados dos documentos.

        Raises:
            ERPNextValidationError: Filtros ou campos inválidos (400/422).
            ERPNextAuthError: Credenciais inválidas ou sem permissão (401/403).
            ERPNextServerError: Erro interno do servidor (5xx).
            ERPNextConnectionError: Falha de conexão ou timeout.
        """
        logger.debug("erpnext.list_docs", doctype=doctype, filters=filters, limit=limit)

        params: dict[str, Any] = {"limit_page_length": limit}
        if filters:
            params["filters"] = _serialize_value(filters)
        if fields:
            params["fields"] = _serialize_value(fields)

        response = await self._request("GET", f"/api/resource/{doctype}", params=params)
        return response.get("data", [])

    @retry(
        retry=retry_if_exception_type((ERPNextServerError, ERPNextConnectionError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def create_doc(self, doctype: str, data: dict[str, Any]) -> dict[str, Any]:
        """Cria um novo documento no ERPNext.

        Args:
            doctype: Tipo do documento a criar (ex: ``Journal Entry``).
            data: Dados do documento (campos e valores).

        Returns:
            Dicionário com os dados do documento criado.

        Raises:
            ERPNextValidationError: Dados inválidos (400/422).
            ERPNextAuthError: Credenciais inválidas ou sem permissão (401/403).
            ERPNextServerError: Erro interno do servidor (5xx).
            ERPNextConnectionError: Falha de conexão ou timeout.
        """
        logger.debug("erpnext.create_doc", doctype=doctype)
        response = await self._request("POST", f"/api/resource/{doctype}", json_data=data)
        return response.get("data", response)

    @retry(
        retry=retry_if_exception_type((ERPNextServerError, ERPNextConnectionError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def update_doc(
        self, doctype: str, name: str, data: dict[str, Any]
    ) -> dict[str, Any]:
        """Atualiza um documento existente no ERPNext.

        Args:
            doctype: Tipo do documento (ex: ``Purchase Invoice``).
            name: Identificador único do documento.
            data: Campos a atualizar (chave-valor).

        Returns:
            Dicionário com os dados atualizados do documento.

        Raises:
            ERPNextNotFoundError: Documento não encontrado (404).
            ERPNextValidationError: Dados inválidos (400/422).
            ERPNextAuthError: Credenciais inválidas ou sem permissão (401/403).
            ERPNextServerError: Erro interno do servidor (5xx).
            ERPNextConnectionError: Falha de conexão ou timeout.
        """
        logger.debug("erpnext.update_doc", doctype=doctype, name=name)
        response = await self._request(
            "PUT", f"/api/resource/{doctype}/{name}", json_data=data
        )
        return response.get("data", response)

    @retry(
        retry=retry_if_exception_type((ERPNextServerError, ERPNextConnectionError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def call_method(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """Invoca um método server-side do Frappe/ERPNext via POST.

        Utilizado para endpoints que não seguem o padrão REST de recursos,
        como relatórios gerenciais, utilitários e whitelisted methods.

        Endpoint alvo: ``POST /api/method/{method}``

        Args:
            method: Caminho do método Frappe (ex:
                ``frappe.desk.query_report.run``).
            params: Parâmetros enviados como corpo JSON da requisição.

        Returns:
            Dicionário com a chave ``message`` contendo o resultado do método,
            ou o corpo completo da resposta em caso de formatos alternativos.

        Raises:
            ERPNextValidationError: Parâmetros inválidos ou método com erro (400/422).
            ERPNextAuthError: Sem permissão para executar o método (401/403).
            ERPNextNotFoundError: Método não encontrado ou não registrado (404).
            ERPNextServerError: Erro interno do servidor (5xx).
            ERPNextConnectionError: Falha de conexão ou timeout.
        """
        logger.debug("erpnext.call_method", method=method)
        response = await self._request("POST", f"/api/method/{method}", json_data=params)
        return response.get("message", response)

    # ─── Internals ────────────────────────────────────────────────────────────

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Executa uma requisição HTTP e trata erros de forma unificada.

        Args:
            method: Método HTTP (GET, POST, PUT).
            path: Caminho relativo da API (ex: ``/api/resource/Sales Invoice``).
            params: Query parameters opcionais.
            json_data: Corpo JSON opcional para POST/PUT.

        Returns:
            Dicionário com a resposta JSON do ERPNext.

        Raises:
            ERPNextAuthError: Erro de autenticação (401/403).
            ERPNextNotFoundError: Recurso não encontrado (404).
            ERPNextValidationError: Erro de validação (400/422).
            ERPNextServerError: Erro interno (5xx).
            ERPNextConnectionError: Falha de conexão ou timeout.
        """
        try:
            response = await self._http.request(
                method,
                path,
                params=params,
                json=json_data,
            )
        except httpx.TimeoutException as exc:
            raise ERPNextConnectionError(
                f"Timeout ao conectar com ERPNext: {exc}",
                status_code=None,
            ) from exc
        except httpx.ConnectError as exc:
            raise ERPNextConnectionError(
                f"Falha de conexão com ERPNext: {exc}",
                status_code=None,
            ) from exc
        except httpx.HTTPError as exc:
            raise ERPNextConnectionError(
                f"Erro HTTP inesperado: {exc}",
                status_code=None,
            ) from exc

        if response.is_success:
            return response.json()

        self._raise_for_status(response, path)

        # Linha inalcançável — _raise_for_status sempre levanta exceção
        return {}  # pragma: no cover

    def _raise_for_status(self, response: httpx.Response, path: str) -> None:
        """Converte respostas HTTP de erro em exceções semânticas.

        Args:
            response: Resposta HTTP com status de erro.
            path: Caminho da requisição (para contexto no log).

        Raises:
            ERPNextAuthError: Para status 401 e 403.
            ERPNextNotFoundError: Para status 404.
            ERPNextValidationError: Para status 400 e 422.
            ERPNextServerError: Para status 5xx.
            ERPNextError: Para qualquer outro status de erro.
        """
        status = response.status_code
        detail = _extract_error_detail(response)

        # Extrai doctype/name do path quando possível
        doctype, name = _parse_resource_path(path)

        logger.warning(
            "erpnext.http_error",
            status=status,
            detail=detail,
            path=path,
        )

        kwargs: dict[str, Any] = {
            "status_code": status,
            "doctype": doctype,
            "name": name,
        }

        if status in (401, 403):
            raise ERPNextAuthError(detail, **kwargs)
        if status == 404:
            raise ERPNextNotFoundError(detail, **kwargs)
        if status in (400, 422):
            raise ERPNextValidationError(detail, **kwargs)
        if status >= 500:
            raise ERPNextServerError(detail, **kwargs)

        raise ERPNextError(detail, **kwargs)


# ─── Funções auxiliares (módulo-privadas) ─────────────────────────────────────


def _serialize_value(value: Any) -> str:
    """Serializa listas e dicts para o formato JSON esperado pela API ERPNext."""
    return json.dumps(value)


def _extract_error_detail(response: httpx.Response) -> str:
    """Extrai mensagem de erro legível da resposta HTTP do ERPNext.

    A API do ERPNext pode retornar erros em diferentes formatos.
    Esta função tenta extrair a mensagem mais informativa disponível.
    """
    try:
        body = response.json()
        # Formato padrão: {"exc_type": "...", "_server_messages": "..."}
        if "message" in body:
            return str(body["message"])
        if "exc_type" in body:
            return f"{body['exc_type']}: {body.get('exception', 'Sem detalhe')}"
        if "_server_messages" in body:
            return str(body["_server_messages"])
    except (ValueError, KeyError):
        pass

    return response.text[:500] if response.text else f"HTTP {response.status_code}"


def _parse_resource_path(path: str) -> tuple[str | None, str | None]:
    """Extrai doctype e name de um caminho ``/api/resource/{doctype}/{name}``.

    Returns:
        Tupla (doctype, name). Ambos podem ser None se o path não
        seguir o padrão esperado.
    """
    prefix = "/api/resource/"
    if not path.startswith(prefix):
        return None, None

    parts = path[len(prefix):].strip("/").split("/", maxsplit=1)

    doctype = parts[0] if len(parts) >= 1 else None
    name = parts[1] if len(parts) >= 2 else None
    return doctype, name
