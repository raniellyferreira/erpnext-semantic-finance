"""Ferramentas financeiras do ERPNext (stub).

Este módulo será implementado em uma tarefa futura com tools para
consulta e gestão de contas a pagar, contas a receber, fluxo de caixa, etc.
"""

import mcp.types as types

TOOL_NAMES: list[str] = []


def get_tools() -> list[types.Tool]:
    """Retorna as tools financeiras disponíveis (vazio por enquanto)."""
    return []


async def execute(name: str, arguments: dict) -> str:
    """Executa uma tool financeira pelo nome.

    Raises:
        ValueError: Sempre — nenhuma tool financeira implementada ainda.
    """
    raise ValueError(f"Tool não implementada: {name}")
