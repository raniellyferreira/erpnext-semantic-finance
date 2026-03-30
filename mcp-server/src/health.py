"""Servidor HTTP leve para health check do container Docker.

Expõe um endpoint GET /health que retorna status 200 quando o serviço
está ativo. Roda em uma task asyncio separada do MCP Server principal.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread

import structlog

from .config import settings

logger = structlog.get_logger(__name__)


class _HealthHandler(BaseHTTPRequestHandler):
    """Handler HTTP mínimo para health check."""

    def do_GET(self) -> None:  # noqa: N802
        """Responde GET /health com status 200."""
        if self.path == "/health":
            body = json.dumps({"status": "ok", "service": "erpnext-mcp-server"})
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.write_safe(body.encode())
        else:
            self.send_response(404)
            self.end_headers()

    def write_safe(self, data: bytes) -> None:
        """Escreve dados no socket de forma segura."""
        try:
            self.wfile.write(data)
        except BrokenPipeError:
            pass

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        """Silencia logs do BaseHTTPRequestHandler (usa structlog)."""


def start_health_server() -> HTTPServer | None:
    """Inicia o servidor de health check em uma thread separada.

    Returns:
        Instância do HTTPServer (para shutdown posterior) ou None em caso de erro.
    """
    port = settings.mcp_server_port

    try:
        httpd = HTTPServer(("0.0.0.0", port), _HealthHandler)  # noqa: S104
        thread = Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        logger.info("health_server_iniciado", port=port, endpoint="/health")
        return httpd
    except OSError:
        logger.warning(
            "health_server_porta_em_uso",
            port=port,
            msg=f"Porta {port} já em uso — health check desabilitado.",
        )
        return None
