# -*- coding: utf-8 -*-
"""Pipeline de indexação de documentos financeiros no banco vetorial.

Cada função é chamada automaticamente pelos hooks do Frappe (doc_events)
quando documentos são submetidos, cancelados ou atualizados.

O indexer usa exclusivamente a interface abstrata ``VectorStorePort``
instanciada via ``create_vector_store()`` — **nunca** importa um adapter
concreto (Qdrant, Pinecone, etc.).
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import os
from typing import Any

import httpx

from src.vector_store.factory import create_vector_store
from src.vector_store.port import VectorDocument, VectorStorePort

from .text_builder import (
    build_journal_entry_text,
    build_payment_entry_text,
    build_purchase_invoice_text,
    build_sales_invoice_text,
    build_supplier_text,
)

logger = logging.getLogger(__name__)

# ─── Mapeamentos de collections ────────────────────────────────────────────────

COLLECTIONS: list[str] = [
    "despesas",
    "notas_fiscais",
    "lancamentos_contabeis",
    "fornecedores",
]

DOCTYPE_COLLECTION_MAP: dict[str, str] = {
    "Payment Entry": "despesas",
    "Purchase Invoice": "notas_fiscais",
    "Sales Invoice": "notas_fiscais",
    "Journal Entry": "lancamentos_contabeis",
    "Supplier": "fornecedores",
}

# ─── Estado do módulo (lazy-init) ──────────────────────────────────────────────

_vector_store: VectorStorePort | None = None
_collections_ensured: bool = False
_executor: concurrent.futures.ThreadPoolExecutor | None = None


# ─── Funções auxiliares ────────────────────────────────────────────────────────


def _get_vector_store() -> VectorStorePort:
    """Retorna (e cacheia) a instância do vector store via factory."""
    global _vector_store  # noqa: PLW0603
    if _vector_store is None:
        _vector_store = create_vector_store()
    return _vector_store


def _run_async(coro: Any) -> Any:
    """Executa coroutine async a partir de contexto síncrono do Frappe."""
    global _executor  # noqa: PLW0603
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    # Se já existe loop rodando, reutiliza executor cacheado para evitar
    # overhead de criar/destruir ThreadPoolExecutor a cada chamada.
    if _executor is None:
        _executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    return _executor.submit(asyncio.run, coro).result(timeout=30)


def _ensure_collections() -> None:
    """Garante que todas as collections existem no vector store.

    Só marca como concluído quando TODAS as collections forem garantidas
    com sucesso, permitindo retry automático em caso de falha transitória.
    """
    global _collections_ensured  # noqa: PLW0603
    if _collections_ensured:
        return

    store = _get_vector_store()
    dimension = int(os.environ.get("EMBEDDING_DIMENSION", "768"))
    all_ensured = True

    for collection in COLLECTIONS:
        try:
            _run_async(store.ensure_collection(collection, dimension))
        except Exception:
            all_ensured = False
            logger.exception(
                "Falha ao garantir collection '%s' no vector store", collection
            )

    if all_ensured:
        _collections_ensured = True


def _generate_embedding(text: str) -> list[float]:
    """Gera embedding vetorial usando o provider configurado (Ollama, OpenAI ou Voyage)."""
    provider = os.environ.get("EMBEDDING_PROVIDER", "ollama").lower()

    if provider == "ollama":
        return _generate_ollama_embedding(text)
    if provider == "openai":
        return _generate_openai_embedding(text)
    if provider == "voyage":
        return _generate_voyage_embedding(text)

    raise ValueError(
        f"Embedding provider '{provider}' não suportado. "
        f"Opções disponíveis: ollama, openai, voyage"
    )


def _generate_ollama_embedding(text: str) -> list[float]:
    """Gera embedding usando Ollama (local/self-hosted)."""
    url = os.environ.get("OLLAMA_URL", "http://localhost:11434")
    model = os.environ.get("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text")

    response = httpx.post(
        f"{url}/api/embeddings",
        json={"model": model, "prompt": text},
        timeout=httpx.Timeout(30.0, connect=5.0),
    )
    response.raise_for_status()
    return response.json()["embedding"]


def _generate_openai_embedding(text: str) -> list[float]:
    """Gera embedding usando a API OpenAI."""
    api_key = os.environ.get("OPENAI_API_KEY", "")
    model = os.environ.get("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")

    response = httpx.post(
        "https://api.openai.com/v1/embeddings",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"model": model, "input": text},
        timeout=httpx.Timeout(30.0, connect=5.0),
    )
    response.raise_for_status()
    return response.json()["data"][0]["embedding"]


def _generate_voyage_embedding(text: str) -> list[float]:
    """Gera embedding usando a API Voyage AI."""
    api_key = os.environ.get("VOYAGE_API_KEY", "")
    model = os.environ.get("VOYAGE_EMBEDDING_MODEL", "voyage-3-large")
    base_url = os.environ.get("VOYAGE_API_URL", "https://api.voyageai.com")

    response = httpx.post(
        f"{base_url}/v1/embeddings",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"model": model, "input": [text]},
        timeout=httpx.Timeout(30.0, connect=5.0),
    )
    response.raise_for_status()
    return response.json()["data"][0]["embedding"]


def _index_document(
    collection: str,
    doc_id: str,
    text: str,
    payload: dict[str, Any],
) -> None:
    """Fluxo genérico de indexação: gera embedding e faz upsert."""
    _ensure_collections()

    embedding = _generate_embedding(text)
    document = VectorDocument(id=doc_id, vector=embedding, payload=payload)

    store = _get_vector_store()
    _run_async(store.upsert(collection, [document]))


# ─── Funções de indexação (chamadas pelos hooks) ───────────────────────────────


def index_payment_entry(doc: Any, method: str) -> None:
    """Indexa um Payment Entry na collection ``despesas``."""
    try:
        text = build_payment_entry_text(doc)
        payload: dict[str, Any] = {
            "doctype": "Payment Entry",
            "name": doc.name,
            "supplier": getattr(doc, "party", ""),
            "amount": float(doc.paid_amount),
            "date": str(doc.posting_date),
            "cost_center": getattr(doc, "cost_center", ""),
            "text": text,
        }
        _index_document("despesas", doc.name, text, payload)
        logger.info("Payment Entry '%s' indexado com sucesso", doc.name)
    except Exception:
        logger.exception("Falha ao indexar Payment Entry '%s'", doc.name)


def index_purchase_invoice(doc: Any, method: str) -> None:
    """Indexa uma Purchase Invoice na collection ``notas_fiscais``."""
    try:
        text = build_purchase_invoice_text(doc)
        payload: dict[str, Any] = {
            "doctype": "Purchase Invoice",
            "name": doc.name,
            "supplier_cnpj": getattr(doc, "tax_id", ""),
            "total_value": float(doc.grand_total),
            "issue_date": str(doc.posting_date),
            "text": text,
        }
        _index_document("notas_fiscais", doc.name, text, payload)
        logger.info("Purchase Invoice '%s' indexada com sucesso", doc.name)
    except Exception:
        logger.exception("Falha ao indexar Purchase Invoice '%s'", doc.name)


def index_sales_invoice(doc: Any, method: str) -> None:
    """Indexa uma Sales Invoice na collection ``notas_fiscais``."""
    try:
        text = build_sales_invoice_text(doc)
        payload: dict[str, Any] = {
            "doctype": "Sales Invoice",
            "name": doc.name,
            "total_value": float(doc.grand_total),
            "issue_date": str(doc.posting_date),
            "text": text,
        }
        _index_document("notas_fiscais", doc.name, text, payload)
        logger.info("Sales Invoice '%s' indexada com sucesso", doc.name)
    except Exception:
        logger.exception("Falha ao indexar Sales Invoice '%s'", doc.name)


def index_journal_entry(doc: Any, method: str) -> None:
    """Indexa um Journal Entry na collection ``lancamentos_contabeis``."""
    try:
        text = build_journal_entry_text(doc)
        accounts_summary = [
            {
                "account": a.account,
                "debit": float(a.debit),
                "credit": float(a.credit),
            }
            for a in (doc.accounts or [])
        ]
        payload: dict[str, Any] = {
            "doctype": "Journal Entry",
            "name": doc.name,
            "posting_date": str(doc.posting_date),
            "accounts": accounts_summary,
            "text": text,
        }
        _index_document("lancamentos_contabeis", doc.name, text, payload)
        logger.info("Journal Entry '%s' indexado com sucesso", doc.name)
    except Exception:
        logger.exception("Falha ao indexar Journal Entry '%s'", doc.name)


def index_supplier(doc: Any, method: str) -> None:
    """Indexa um Supplier na collection ``fornecedores``."""
    try:
        text = build_supplier_text(doc)
        payload: dict[str, Any] = {
            "doctype": "Supplier",
            "name": doc.name,
            "supplier_name": doc.supplier_name,
            "tax_id": getattr(doc, "tax_id", ""),
            "text": text,
        }
        _index_document("fornecedores", doc.name, text, payload)
        logger.info("Supplier '%s' indexado com sucesso", doc.name)
    except Exception:
        logger.exception("Falha ao indexar Supplier '%s'", doc.name)


def remove_from_index(doc: Any, method: str) -> None:
    """Remove um documento do índice vetorial (chamado no on_cancel)."""
    try:
        _ensure_collections()
        collection = DOCTYPE_COLLECTION_MAP.get(doc.doctype)
        if not collection:
            logger.warning(
                "DocType '%s' não possui collection mapeada para remoção",
                doc.doctype,
            )
            return

        store = _get_vector_store()
        _run_async(store.delete(collection, doc.name))
        logger.info(
            "Documento '%s' (%s) removido do índice",
            doc.name,
            doc.doctype,
        )
    except Exception:
        logger.exception(
            "Falha ao remover '%s' (%s) do índice",
            doc.name,
            doc.doctype,
        )


# ─── Scheduler jobs ───────────────────────────────────────────────────────────


def sync_pending_documents() -> None:
    """Sincroniza documentos pendentes de indexação (scheduler diário).

    Consulta documentos submetidos recentemente e re-indexa aqueles que
    possam ter sido perdidos por falha temporária do vector store.
    """
    try:
        import frappe

        _ensure_collections()

        doctype_handlers = {
            "Payment Entry": index_payment_entry,
            "Purchase Invoice": index_purchase_invoice,
            "Sales Invoice": index_sales_invoice,
            "Journal Entry": index_journal_entry,
        }

        for doctype, handler in doctype_handlers.items():
            docs = frappe.get_all(
                doctype,
                filters={"docstatus": 1},
                fields=["name"],
                order_by="modified desc",
                limit_page_length=100,
            )
            for row in docs:
                try:
                    doc = frappe.get_doc(doctype, row.name)
                    handler(doc, "sync")
                except Exception:
                    logger.exception(
                        "Falha ao sincronizar %s '%s'",
                        doctype,
                        row.name,
                    )

        # Fornecedores (não possuem docstatus)
        suppliers = frappe.get_all(
            "Supplier",
            fields=["name"],
            order_by="modified desc",
            limit_page_length=100,
        )
        for row in suppliers:
            try:
                doc = frappe.get_doc("Supplier", row.name)
                index_supplier(doc, "sync")
            except Exception:
                logger.exception(
                    "Falha ao sincronizar Supplier '%s'", row.name
                )

        logger.info("Sincronização de documentos pendentes concluída")
    except Exception:
        logger.exception("Falha na sincronização de documentos pendentes")


def rebuild_index_stats() -> None:
    """Reconstrói estatísticas do índice vetorial (scheduler semanal).

    Loga a contagem de documentos por collection para monitoramento.
    """
    try:
        _ensure_collections()
        store = _get_vector_store()

        stats: dict[str, int] = {}
        for collection in COLLECTIONS:
            try:
                count = _run_async(store.count(collection))
                stats[collection] = count
            except Exception:
                logger.exception(
                    "Falha ao obter contagem da collection '%s'", collection
                )
                stats[collection] = -1

        logger.info("Estatísticas do índice vetorial: %s", stats)
    except Exception:
        logger.exception("Falha ao reconstruir estatísticas do índice")
