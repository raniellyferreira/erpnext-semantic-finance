# -*- coding: utf-8 -*-
"""Frappe App Hooks - semantic_finance

Este arquivo define os hooks de eventos do Frappe que disparam
a indexação automática de documentos no Qdrant para busca semântica.
"""

app_name = "semantic_finance"
app_title = "Semantic Finance"
app_publisher = "Ranielly Ferreira"
app_description = "Busca semântica e MCP para gestão financeira no ERPNext"
app_version = "0.1.0"
app_license = "MIT"

# ─── Hooks de Documentos ─────────────────────────────────────────────────────
# Disparados automaticamente quando documentos são submetidos/cancelados

doc_events = {
    "Payment Entry": {
        "on_submit": "semantic_finance.embeddings.indexer.index_payment_entry",
        "on_cancel": "semantic_finance.embeddings.indexer.remove_from_index",
    },
    "Purchase Invoice": {
        "on_submit": "semantic_finance.embeddings.indexer.index_purchase_invoice",
        "on_cancel": "semantic_finance.embeddings.indexer.remove_from_index",
    },
    "Sales Invoice": {
        "on_submit": "semantic_finance.embeddings.indexer.index_sales_invoice",
        "on_cancel": "semantic_finance.embeddings.indexer.remove_from_index",
    },
    "Journal Entry": {
        "on_submit": "semantic_finance.embeddings.indexer.index_journal_entry",
        "on_cancel": "semantic_finance.embeddings.indexer.remove_from_index",
    },
    "Supplier": {
        "after_insert": "semantic_finance.embeddings.indexer.index_supplier",
        "on_update": "semantic_finance.embeddings.indexer.index_supplier",
    },
}

# ─── Scheduler ──────────────────────────────────────────────────────────────
# Jobs agendados para manutenção do índice vetorial

scheduler_events = {
    "daily": [
        "semantic_finance.embeddings.indexer.sync_pending_documents",
    ],
    "weekly": [
        "semantic_finance.embeddings.indexer.rebuild_index_stats",
    ],
}
