"""ERPNext API Client — Ports & Adapters.

Cliente HTTP assíncrono para a API REST do ERPNext, com modelos Pydantic
para DocTypes financeiros e exceções semânticas para tratamento de erros.
"""

from .client import ERPNextClient
from .exceptions import (
    ERPNextAuthError,
    ERPNextConnectionError,
    ERPNextError,
    ERPNextNotFoundError,
    ERPNextServerError,
    ERPNextValidationError,
)
from .models import (
    InvoiceItem,
    JournalEntry,
    JournalEntryAccount,
    PaymentEntry,
    PurchaseInvoice,
    SalesInvoice,
    Supplier,
)

__all__ = [
    # Client
    "ERPNextClient",
    # Exceções
    "ERPNextError",
    "ERPNextAuthError",
    "ERPNextNotFoundError",
    "ERPNextValidationError",
    "ERPNextServerError",
    "ERPNextConnectionError",
    # Modelos
    "PaymentEntry",
    "PurchaseInvoice",
    "SalesInvoice",
    "JournalEntry",
    "JournalEntryAccount",
    "InvoiceItem",
    "Supplier",
]
