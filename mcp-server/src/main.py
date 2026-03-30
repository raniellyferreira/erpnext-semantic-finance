"""Entry point do MCP Server - ERPNext Semantic Finance."""

import asyncio

import mcp.server.stdio
import mcp.types as types
from mcp.server import Server
from mcp.server.models import InitializationOptions

from .health import start_health_server
from .tools import financial_tools, fiscal_tools, report_tools, search_tools

# Inicializa o servidor MCP
server = Server("erpnext-semantic-finance")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    """Lista todas as tools disponíveis no MCP Server."""
    return [
        *search_tools.get_tools(),
        *financial_tools.get_tools(),
        *fiscal_tools.get_tools(),
        *report_tools.get_tools(),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    """Executa a tool solicitada pelo LLM."""
    # Roteamento das tools
    if name in search_tools.TOOL_NAMES:
        result = await search_tools.execute(name, arguments)
    elif name in financial_tools.TOOL_NAMES:
        result = await financial_tools.execute(name, arguments)
    elif name in fiscal_tools.TOOL_NAMES:
        result = await fiscal_tools.execute(name, arguments)
    elif name in report_tools.TOOL_NAMES:
        result = await report_tools.execute(name, arguments)
    else:
        raise ValueError(f"Tool desconhecida: {name}")

    return [types.TextContent(type="text", text=str(result))]


async def main() -> None:
    """Inicializa e executa o MCP Server via stdio."""
    # Inicia health check HTTP para Docker (thread separada)
    health_server = start_health_server()

    try:
        async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                InitializationOptions(
                    server_name="erpnext-semantic-finance",
                    server_version="0.1.0",
                    capabilities=server.get_capabilities(
                        notification_options=None,
                        experimental_capabilities={},
                    ),
                ),
            )
    finally:
        if health_server:
            health_server.shutdown()
        await search_tools.close()
        await financial_tools.close()
        await report_tools.close()


if __name__ == "__main__":
    asyncio.run(main())
