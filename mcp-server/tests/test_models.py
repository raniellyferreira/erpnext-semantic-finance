"""Testes para os modelos Pydantic dos DocTypes financeiros do ERPNext.

Valida a construção, validação de tipos, campos opcionais, aliases
e serialização dos modelos que representam documentos financeiros.
"""

from __future__ import annotations

from datetime import date

import pytest

from src.erpnext_client.models import (
    InvoiceItem,
    JournalEntry,
    JournalEntryAccount,
    PaymentEntry,
    PurchaseInvoice,
    SalesInvoice,
    Supplier,
)


# ─── PaymentEntry ────────────────────────────────────────────────────────────


class TestPaymentEntry:
    """Testes para o modelo PaymentEntry."""

    def test_criacao_com_campos_obrigatorios(self) -> None:
        """Deve criar PaymentEntry com apenas o campo 'name'."""
        pe = PaymentEntry(name="PE-00001")

        assert pe.name == "PE-00001"
        assert pe.posting_date is None
        assert pe.party is None
        assert pe.paid_amount is None

    def test_criacao_com_todos_os_campos(self) -> None:
        """Deve criar PaymentEntry com todos os campos preenchidos."""
        pe = PaymentEntry(
            name="PE-00002",
            posting_date=date(2024, 6, 15),
            party_type="Supplier",
            party="Fornecedor ABC",
            paid_amount=5000.50,
            paid_from="Banco Itaú - CI",
            paid_to="Fornecedor ABC - CI",
            payment_type="Pay",
            mode_of_payment="Transferência Bancária",
            cost_center="Centro Principal - CI",
            reference_no="TED-12345",
            reference_date=date(2024, 6, 15),
            remarks="Pagamento de nota fiscal NF-001",
        )

        assert pe.name == "PE-00002"
        assert pe.posting_date == date(2024, 6, 15)
        assert pe.paid_amount == 5000.50
        assert pe.payment_type == "Pay"
        assert pe.remarks == "Pagamento de nota fiscal NF-001"


# ─── PurchaseInvoice ─────────────────────────────────────────────────────────


class TestPurchaseInvoice:
    """Testes para o modelo PurchaseInvoice."""

    def test_alias_total_taxes_and_charges(self) -> None:
        """Deve aceitar 'total_taxes_and_charges' como alias de 'taxes_and_charges'."""
        pi = PurchaseInvoice(
            name="PINV-00001",
            total_taxes_and_charges=250.0,
        )

        assert pi.taxes_and_charges == 250.0

    def test_campo_direto_taxes_and_charges(self) -> None:
        """Deve aceitar o campo direto 'taxes_and_charges' (populate_by_name=True)."""
        pi = PurchaseInvoice(
            name="PINV-00002",
            taxes_and_charges=180.0,
        )

        assert pi.taxes_and_charges == 180.0

    def test_com_itens(self) -> None:
        """Deve aceitar lista de InvoiceItem nos itens."""
        items = [
            InvoiceItem(item_code="ITEM-001", item_name="Caneta", qty=100, rate=2.5, amount=250.0),
            InvoiceItem(item_code="ITEM-002", item_name="Papel A4", qty=50, rate=25.0, amount=1250.0),
        ]

        pi = PurchaseInvoice(
            name="PINV-00003",
            posting_date=date(2024, 3, 10),
            supplier="SUP-001",
            supplier_name="Papelaria Central",
            grand_total=1500.0,
            net_total=1250.0,
            items=items,
            status="Submitted",
        )

        assert pi.name == "PINV-00003"
        assert len(pi.items) == 2
        assert pi.items[0].item_name == "Caneta"
        assert pi.items[1].amount == 1250.0
        assert pi.grand_total == 1500.0


# ─── JournalEntry ────────────────────────────────────────────────────────────


class TestJournalEntry:
    """Testes para o modelo JournalEntry."""

    def test_com_lista_de_accounts(self) -> None:
        """Deve criar JournalEntry com lista de JournalEntryAccount."""
        accounts = [
            JournalEntryAccount(
                account="Despesas Operacionais - CI",
                debit_in_account_currency=1000.0,
            ),
            JournalEntryAccount(
                account="Banco Itaú - CI",
                credit_in_account_currency=1000.0,
            ),
        ]

        je = JournalEntry(
            name="JE-00001",
            posting_date=date(2024, 7, 1),
            voucher_type="Journal Entry",
            total_debit=1000.0,
            total_credit=1000.0,
            accounts=accounts,
            remark="Reclassificação contábil",
        )

        assert je.name == "JE-00001"
        assert len(je.accounts) == 2
        assert je.accounts[0].debit == 1000.0
        assert je.accounts[1].credit == 1000.0
        assert je.total_debit == je.total_credit

    def test_journal_entry_account_alias_debit(self) -> None:
        """JournalEntryAccount deve aceitar 'debit_in_account_currency' como alias."""
        acc = JournalEntryAccount(debit_in_account_currency=500.0)

        assert acc.debit == 500.0
        assert acc.credit is None

    def test_journal_entry_account_alias_credit(self) -> None:
        """JournalEntryAccount deve aceitar 'credit_in_account_currency' como alias."""
        acc = JournalEntryAccount(credit_in_account_currency=750.0)

        assert acc.credit == 750.0
        assert acc.debit is None


# ─── Supplier ────────────────────────────────────────────────────────────────


class TestSupplier:
    """Testes para o modelo Supplier."""

    def test_com_todos_os_campos(self) -> None:
        """Deve criar Supplier com todos os campos preenchidos."""
        supplier = Supplier(
            name="SUP-00001",
            supplier_name="Distribuidora ABC Ltda",
            supplier_type="Company",
            tax_id="12.345.678/0001-90",
            supplier_group="Serviços",
            country="Brazil",
            default_currency="BRL",
        )

        assert supplier.name == "SUP-00001"
        assert supplier.supplier_name == "Distribuidora ABC Ltda"
        assert supplier.tax_id == "12.345.678/0001-90"
        assert supplier.country == "Brazil"
        assert supplier.default_currency == "BRL"

    def test_apenas_name(self) -> None:
        """Deve criar Supplier apenas com name, demais campos None."""
        supplier = Supplier(name="SUP-00002")

        assert supplier.name == "SUP-00002"
        assert supplier.supplier_name is None
        assert supplier.supplier_type is None
        assert supplier.tax_id is None
        assert supplier.supplier_group is None
        assert supplier.country is None
        assert supplier.default_currency is None


# ─── Dados parciais ──────────────────────────────────────────────────────────


class TestDadosParciais:
    """Testes para validar que modelos aceitam dados parciais (apenas 'name')."""

    @pytest.mark.parametrize(
        "model_class",
        [PaymentEntry, PurchaseInvoice, SalesInvoice, JournalEntry, Supplier],
    )
    def test_criacao_com_apenas_name(self, model_class: type) -> None:
        """Todos os modelos devem aceitar dados com apenas o campo 'name'."""
        instance = model_class(name="TEST-001")

        assert instance.name == "TEST-001"

    def test_sales_invoice_parcial(self) -> None:
        """SalesInvoice com dados parciais deve ter campos opcionais como None."""
        si = SalesInvoice(name="SINV-00001")

        assert si.name == "SINV-00001"
        assert si.customer is None
        assert si.grand_total is None
        assert si.items is None
