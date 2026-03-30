"""Modelos Pydantic para DocTypes financeiros do ERPNext.

Define representações tipadas dos documentos retornados pela API REST,
permitindo validação automática e autocompletar no editor. Todos os
campos (exceto ``name``) são opcionais, pois a API pode retornar
dados parciais dependendo dos ``fields`` solicitados.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field

# ─── Modelos auxiliares (child tables) ────────────────────────────────────────


class InvoiceItem(BaseModel):
    """Item de uma fatura (Purchase Invoice / Sales Invoice)."""

    model_config = ConfigDict(populate_by_name=True)

    item_code: str | None = Field(default=None, alias="item_code")
    item_name: str | None = Field(default=None, alias="item_name")
    qty: float | None = Field(default=None, alias="qty")
    rate: float | None = Field(default=None, alias="rate")
    amount: float | None = Field(default=None, alias="amount")


class JournalEntryAccount(BaseModel):
    """Linha contábil de um lançamento (Journal Entry Account)."""

    model_config = ConfigDict(populate_by_name=True)

    account: str | None = Field(default=None, alias="account")
    debit: float | None = Field(default=None, alias="debit_in_account_currency")
    credit: float | None = Field(default=None, alias="credit_in_account_currency")


# ─── DocTypes financeiros ─────────────────────────────────────────────────────


class PaymentEntry(BaseModel):
    """Pagamento registrado no ERPNext (DocType: Payment Entry).

    Representa movimentações financeiras como recebimentos de clientes,
    pagamentos a fornecedores e transferências entre contas.
    """

    model_config = ConfigDict(populate_by_name=True)

    name: str
    posting_date: date | None = None
    party_type: str | None = None
    party: str | None = None
    paid_amount: float | None = None
    paid_from: str | None = None
    paid_to: str | None = None
    payment_type: str | None = Field(
        default=None, description="Receive / Pay / Internal Transfer"
    )
    mode_of_payment: str | None = None
    cost_center: str | None = None
    reference_no: str | None = None
    reference_date: date | None = None
    remarks: str | None = None


class PurchaseInvoice(BaseModel):
    """Nota fiscal de compra (DocType: Purchase Invoice).

    Representa faturas recebidas de fornecedores, incluindo
    impostos, itens e informações de vencimento.
    """

    model_config = ConfigDict(populate_by_name=True)

    name: str
    posting_date: date | None = None
    supplier: str | None = None
    supplier_name: str | None = None
    grand_total: float | None = None
    net_total: float | None = None
    taxes_and_charges: float | None = Field(
        default=None, alias="total_taxes_and_charges"
    )
    due_date: date | None = None
    bill_no: str | None = None
    bill_date: date | None = None
    items: list[InvoiceItem] | None = Field(default=None)
    status: str | None = None


class SalesInvoice(BaseModel):
    """Nota fiscal de venda (DocType: Sales Invoice).

    Representa faturas emitidas para clientes, incluindo
    itens, totais e informações de vencimento.
    """

    model_config = ConfigDict(populate_by_name=True)

    name: str
    posting_date: date | None = None
    customer: str | None = None
    customer_name: str | None = None
    grand_total: float | None = None
    net_total: float | None = None
    due_date: date | None = None
    items: list[InvoiceItem] | None = Field(default=None)
    status: str | None = None


class JournalEntry(BaseModel):
    """Lançamento contábil manual (DocType: Journal Entry).

    Usado para ajustes contábeis, reclassificações e outros
    lançamentos que não se enquadram em documentos específicos.
    """

    model_config = ConfigDict(populate_by_name=True)

    name: str
    posting_date: date | None = None
    voucher_type: str | None = None
    total_debit: float | None = None
    total_credit: float | None = None
    accounts: list[JournalEntryAccount] | None = Field(default=None)
    remark: str | None = None
    user_remark: str | None = None


class Supplier(BaseModel):
    """Fornecedor cadastrado (DocType: Supplier).

    Dados cadastrais de fornecedores utilizados em compras,
    pagamentos e relatórios financeiros.
    """

    model_config = ConfigDict(populate_by_name=True)

    name: str
    supplier_name: str | None = None
    supplier_type: str | None = None
    tax_id: str | None = None
    supplier_group: str | None = None
    country: str | None = None
    default_currency: str | None = None
