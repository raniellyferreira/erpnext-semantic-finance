"""Ferramentas de relatórios e análises financeiras (stub).

Este módulo será implementado em uma tarefa futura com tools para
geração de relatórios, dashboards e análises financeiras.
"""

import mcp.types as types

TOOL_NAMES: list[str] = []


def get_tools() -> list[types.Tool]:
    """Retorna as tools de relatório disponíveis (vazio por enquanto)."""
    return []


async def execute(name: str, arguments: dict) -> str:
    """Executa uma tool de relatório pelo nome.

    Raises:
        ValueError: Sempre — nenhuma tool de relatório implementada ainda.
    """
    raise ValueError(f"Tool não implementada: {name}")
