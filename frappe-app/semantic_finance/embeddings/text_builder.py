# -*- coding: utf-8 -*-
"""Construtores de texto rico para geração de embeddings.

Cada função recebe um documento Frappe e retorna um texto
detalhado e semântico para ser transformado em embedding vetorial.
"""

from typing import Any


def build_payment_entry_text(doc: Any) -> str:
    """Gera texto semântico para Payment Entry (pagamentos)."""
    lines = [
        f"Pagamento {doc.payment_type} para {doc.party_type} {doc.party}",
        f"Valor pago: R$ {doc.paid_amount:,.2f}",
        f"Data do pagamento: {doc.posting_date}",
        f"Modo de pagamento: {doc.mode_of_payment}",
    ]
    if doc.cost_center:
        lines.append(f"Centro de custo: {doc.cost_center}")
    if doc.reference_no:
        lines.append(f"Referência/Cheque/TED: {doc.reference_no}")
    if doc.remarks:
        lines.append(f"Observações: {doc.remarks}")
    if hasattr(doc, "references") and doc.references:
        refs = ", ".join([r.reference_name for r in doc.references])
        lines.append(f"Documentos relacionados: {refs}")
    return "\n".join(lines)


def build_purchase_invoice_text(doc: Any) -> str:
    """Gera texto semântico para Purchase Invoice (NF de entrada)."""
    items_text = "; ".join([
        f"{item.item_name} (qtd: {item.qty}, valor: R${item.amount:,.2f})"
        for item in (doc.items or [])
    ])
    lines = [
        f"Nota fiscal de entrada do fornecedor {doc.supplier_name}",
        f"CNPJ do fornecedor: {getattr(doc, 'tax_id', 'não informado')}",
        f"Valor total: R$ {doc.grand_total:,.2f}",
        f"Data de emissão: {doc.posting_date}",
        f"Número da NF: {doc.bill_no or 'não informado'}",
        f"Itens: {items_text}",
    ]
    if doc.taxes_and_charges:
        lines.append(f"Template de impostos: {doc.taxes_and_charges}")
    if doc.remarks:
        lines.append(f"Observações: {doc.remarks}")
    return "\n".join(lines)


def build_sales_invoice_text(doc: Any) -> str:
    """Gera texto semântico para Sales Invoice (NF de saída)."""
    items_text = "; ".join([
        f"{item.item_name} (qtd: {item.qty}, valor: R${item.amount:,.2f})"
        for item in (doc.items or [])
    ])
    lines = [
        f"Nota fiscal de saída para cliente {doc.customer_name}",
        f"Valor total: R$ {doc.grand_total:,.2f}",
        f"Data: {doc.posting_date}",
        f"Itens vendidos: {items_text}",
    ]
    if doc.remarks:
        lines.append(f"Observações: {doc.remarks}")
    return "\n".join(lines)


def build_journal_entry_text(doc: Any) -> str:
    """Gera texto semântico para Journal Entry (lançamentos contábeis)."""
    accounts = "; ".join([
        f"{a.account} (débito: R${a.debit:,.2f}, crédito: R${a.credit:,.2f})"
        for a in (doc.accounts or [])
    ])
    lines = [
        f"Lançamento contábil do tipo {doc.voucher_type}",
        f"Data: {doc.posting_date}",
        f"Contas envolvidas: {accounts}",
    ]
    if doc.user_remark:
        lines.append(f"Histórico: {doc.user_remark}")
    return "\n".join(lines)


def build_supplier_text(doc: Any) -> str:
    """Gera texto semântico para Supplier (fornecedor)."""
    lines = [
        f"Fornecedor: {doc.supplier_name}",
        f"Tipo: {doc.supplier_type}",
        f"Grupo: {doc.supplier_group}",
        f"CNPJ/CPF: {getattr(doc, 'tax_id', 'não informado')}",
    ]
    if doc.country:
        lines.append(f"País: {doc.country}")
    return "\n".join(lines)
