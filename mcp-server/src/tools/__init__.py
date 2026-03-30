"""Tools MCP — ERPNext Semantic Finance.

Pacote que agrupa todas as ferramentas expostas pelo MCP Server.
Cada módulo encapsula um domínio funcional (busca, financeiro, fiscal, relatórios).
"""

from . import financial_tools, fiscal_tools, report_tools, search_tools

__all__ = [
    "search_tools",
    "financial_tools",
    "fiscal_tools",
    "report_tools",
]
