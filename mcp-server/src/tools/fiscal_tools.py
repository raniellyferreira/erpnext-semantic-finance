"""Ferramentas fiscais — NF-e, NFS-e, impostos (stub).

Este módulo será implementado em uma tarefa futura com tools para
emissão e consulta de notas fiscais via integração Focus NF-e.
"""

import mcp.types as types

TOOL_NAMES: list[str] = []


def get_tools() -> list[types.Tool]:
    """Retorna as tools fiscais disponíveis (vazio por enquanto)."""
    return []


async def execute(name: str, arguments: dict) -> str:
    """Executa uma tool fiscal pelo nome.

    Raises:
        ValueError: Sempre — nenhuma tool fiscal implementada ainda.
    """
    raise ValueError(f"Tool não implementada: {name}")
