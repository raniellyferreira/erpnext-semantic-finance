# -*- coding: utf-8 -*-
"""Testes unitários para o módulo ``embeddings/indexer.py``.

Todos os testes usam um mock de ``VectorStorePort`` — nenhum banco vetorial
real é necessário. A geração de embeddings também é mockada.
"""

from __future__ import annotations

import asyncio
import os
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

# ─── Configurar env vars ANTES de importar o indexer ──────────────────────────
# Sobrescreve explicitamente para garantir isolamento independente do ambiente.

os.environ["VECTOR_STORE_PROVIDER"] = "qdrant"
os.environ["EMBEDDING_PROVIDER"] = "ollama"
os.environ["EMBEDDING_DIMENSION"] = "768"
os.environ["QDRANT_URL"] = "http://localhost:6333"
os.environ["OLLAMA_URL"] = "http://localhost:11434"

from semantic_finance.embeddings import indexer  # noqa: E402
from src.vector_store.port import VectorDocument, VectorStorePort  # noqa: E402


# ─── Fixtures ─────────────────────────────────────────────────────────────────

FAKE_EMBEDDING = [0.1] * 768


@pytest.fixture(autouse=True)
def _reset_indexer_state():
    """Reseta o estado global do módulo entre testes."""
    indexer._vector_store = None
    indexer._collections_ensured = False
    indexer._executor = None
    yield
    indexer._vector_store = None
    indexer._collections_ensured = False
    indexer._executor = None


@pytest.fixture()
def mock_vector_store() -> AsyncMock:
    """Cria um mock completo de ``VectorStorePort``."""
    store = AsyncMock(spec=VectorStorePort)
    store.ensure_collection = AsyncMock()
    store.upsert = AsyncMock()
    store.delete = AsyncMock()
    store.count = AsyncMock(return_value=42)
    store.search = AsyncMock(return_value=[])
    return store


@pytest.fixture()
def _patch_store_and_embedding(mock_vector_store: AsyncMock):
    """Patcha a factory e a geração de embeddings."""
    with (
        patch(
            "semantic_finance.embeddings.indexer.create_vector_store",
            return_value=mock_vector_store,
        ),
        patch(
            "semantic_finance.embeddings.indexer._generate_embedding",
            return_value=FAKE_EMBEDDING,
        ),
    ):
        yield


# ─── Helpers para criar docs fake ─────────────────────────────────────────────


def _make_payment_entry(**overrides: Any) -> SimpleNamespace:
    return SimpleNamespace(
        name="PAY-00001",
        doctype="Payment Entry",
        payment_type="Pay",
        party_type="Supplier",
        party="Fornecedor ABC",
        paid_amount=1500.00,
        posting_date="2024-06-15",
        mode_of_payment="Transferência Bancária",
        cost_center="CC - Administrativo",
        reference_no="TED-123",
        remarks="Pagamento de serviço",
        references=[
            SimpleNamespace(reference_name="PINV-00001"),
        ],
        **overrides,
    )


def _make_purchase_invoice(**overrides: Any) -> SimpleNamespace:
    return SimpleNamespace(
        name="PINV-00001",
        doctype="Purchase Invoice",
        supplier_name="Fornecedor XYZ",
        tax_id="12.345.678/0001-99",
        grand_total=5000.00,
        posting_date="2024-06-10",
        bill_no="NF-4567",
        items=[
            SimpleNamespace(item_name="Consultoria TI", qty=1, amount=5000.00),
        ],
        taxes_and_charges="Impostos Padrão",
        remarks="NF de serviço",
        **overrides,
    )


def _make_sales_invoice(**overrides: Any) -> SimpleNamespace:
    return SimpleNamespace(
        name="SINV-00001",
        doctype="Sales Invoice",
        customer_name="Cliente Beta",
        grand_total=3000.00,
        posting_date="2024-07-01",
        items=[
            SimpleNamespace(item_name="Produto A", qty=10, amount=3000.00),
        ],
        remarks="Venda mensal",
        **overrides,
    )


def _make_journal_entry(**overrides: Any) -> SimpleNamespace:
    return SimpleNamespace(
        name="JV-00001",
        doctype="Journal Entry",
        voucher_type="Journal Entry",
        posting_date="2024-07-05",
        accounts=[
            SimpleNamespace(account="Caixa - ME", debit=1000.00, credit=0.00),
            SimpleNamespace(account="Banco - ME", debit=0.00, credit=1000.00),
        ],
        user_remark="Transferência entre contas",
        **overrides,
    )


def _make_supplier(**overrides: Any) -> SimpleNamespace:
    return SimpleNamespace(
        name="SUPP-00001",
        doctype="Supplier",
        supplier_name="Fornecedor Delta",
        supplier_type="Company",
        supplier_group="Serviços",
        tax_id="98.765.432/0001-10",
        country="Brasil",
        **overrides,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# TESTES DE INDEXAÇÃO
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.usefixtures("_patch_store_and_embedding")
class TestIndexPaymentEntry:
    def test_indexes_successfully(self, mock_vector_store: AsyncMock):
        doc = _make_payment_entry()
        indexer.index_payment_entry(doc, "on_submit")

        mock_vector_store.upsert.assert_called_once()
        call_args = mock_vector_store.upsert.call_args
        assert call_args[0][0] == "despesas"
        documents = call_args[0][1]
        assert len(documents) == 1
        assert documents[0].id == "PAY-00001"
        assert documents[0].payload["doctype"] == "Payment Entry"
        assert documents[0].payload["amount"] == 1500.00

    def test_ensures_collections_on_first_call(
        self, mock_vector_store: AsyncMock
    ):
        doc = _make_payment_entry()
        indexer.index_payment_entry(doc, "on_submit")

        assert mock_vector_store.ensure_collection.call_count == 4

    def test_does_not_raise_on_failure(self, mock_vector_store: AsyncMock):
        mock_vector_store.upsert.side_effect = Exception("connection refused")
        doc = _make_payment_entry()
        # Não deve levantar exceção
        indexer.index_payment_entry(doc, "on_submit")


@pytest.mark.usefixtures("_patch_store_and_embedding")
class TestIndexPurchaseInvoice:
    def test_indexes_to_notas_fiscais(self, mock_vector_store: AsyncMock):
        doc = _make_purchase_invoice()
        indexer.index_purchase_invoice(doc, "on_submit")

        call_args = mock_vector_store.upsert.call_args
        assert call_args[0][0] == "notas_fiscais"
        documents = call_args[0][1]
        assert documents[0].id == "PINV-00001"
        assert documents[0].payload["doctype"] == "Purchase Invoice"
        assert documents[0].payload["total_value"] == 5000.00


@pytest.mark.usefixtures("_patch_store_and_embedding")
class TestIndexSalesInvoice:
    def test_indexes_to_notas_fiscais(self, mock_vector_store: AsyncMock):
        doc = _make_sales_invoice()
        indexer.index_sales_invoice(doc, "on_submit")

        call_args = mock_vector_store.upsert.call_args
        assert call_args[0][0] == "notas_fiscais"
        documents = call_args[0][1]
        assert documents[0].id == "SINV-00001"
        assert documents[0].payload["doctype"] == "Sales Invoice"
        assert documents[0].payload["total_value"] == 3000.00


@pytest.mark.usefixtures("_patch_store_and_embedding")
class TestIndexJournalEntry:
    def test_indexes_to_lancamentos_contabeis(
        self, mock_vector_store: AsyncMock
    ):
        doc = _make_journal_entry()
        indexer.index_journal_entry(doc, "on_submit")

        call_args = mock_vector_store.upsert.call_args
        assert call_args[0][0] == "lancamentos_contabeis"
        documents = call_args[0][1]
        assert documents[0].id == "JV-00001"
        assert documents[0].payload["doctype"] == "Journal Entry"
        assert len(documents[0].payload["accounts"]) == 2


@pytest.mark.usefixtures("_patch_store_and_embedding")
class TestIndexSupplier:
    def test_indexes_to_fornecedores(self, mock_vector_store: AsyncMock):
        doc = _make_supplier()
        indexer.index_supplier(doc, "after_insert")

        call_args = mock_vector_store.upsert.call_args
        assert call_args[0][0] == "fornecedores"
        documents = call_args[0][1]
        assert documents[0].id == "SUPP-00001"
        assert documents[0].payload["supplier_name"] == "Fornecedor Delta"
        assert documents[0].payload["tax_id"] == "98.765.432/0001-10"


# ═══════════════════════════════════════════════════════════════════════════════
# TESTES DE REMOÇÃO
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.usefixtures("_patch_store_and_embedding")
class TestRemoveFromIndex:
    def test_removes_payment_entry(self, mock_vector_store: AsyncMock):
        doc = _make_payment_entry()
        indexer.remove_from_index(doc, "on_cancel")

        mock_vector_store.delete.assert_called_once_with(
            "despesas", "PAY-00001"
        )

    def test_removes_purchase_invoice(self, mock_vector_store: AsyncMock):
        doc = _make_purchase_invoice()
        indexer.remove_from_index(doc, "on_cancel")

        mock_vector_store.delete.assert_called_once_with(
            "notas_fiscais", "PINV-00001"
        )

    def test_removes_journal_entry(self, mock_vector_store: AsyncMock):
        doc = _make_journal_entry()
        indexer.remove_from_index(doc, "on_cancel")

        mock_vector_store.delete.assert_called_once_with(
            "lancamentos_contabeis", "JV-00001"
        )

    def test_removes_supplier(self, mock_vector_store: AsyncMock):
        doc = _make_supplier()
        indexer.remove_from_index(doc, "on_cancel")

        mock_vector_store.delete.assert_called_once_with(
            "fornecedores", "SUPP-00001"
        )

    def test_skips_unmapped_doctype(self, mock_vector_store: AsyncMock):
        doc = SimpleNamespace(name="X-001", doctype="Unknown DocType")
        indexer.remove_from_index(doc, "on_cancel")

        mock_vector_store.delete.assert_not_called()

    def test_does_not_raise_on_failure(self, mock_vector_store: AsyncMock):
        mock_vector_store.delete.side_effect = Exception("timeout")
        doc = _make_payment_entry()
        # Não deve levantar exceção
        indexer.remove_from_index(doc, "on_cancel")


# ═══════════════════════════════════════════════════════════════════════════════
# TESTES DE ENSURE_COLLECTIONS
# ═══════════════════════════════════════════════════════════════════════════════


class TestEnsureCollections:
    def test_creates_all_four_collections(self):
        store = AsyncMock(spec=VectorStorePort)
        with patch(
            "semantic_finance.embeddings.indexer.create_vector_store",
            return_value=store,
        ):
            indexer._ensure_collections()

        assert store.ensure_collection.call_count == 4
        collection_names = [
            call[0][0] for call in store.ensure_collection.call_args_list
        ]
        assert set(collection_names) == {
            "despesas",
            "notas_fiscais",
            "lancamentos_contabeis",
            "fornecedores",
        }

    def test_uses_embedding_dimension_env_var(self):
        store = AsyncMock(spec=VectorStorePort)
        with (
            patch(
                "semantic_finance.embeddings.indexer.create_vector_store",
                return_value=store,
            ),
            patch.dict(os.environ, {"EMBEDDING_DIMENSION": "1536"}),
        ):
            indexer._ensure_collections()

        for call in store.ensure_collection.call_args_list:
            assert call[0][1] == 1536

    def test_only_runs_once(self):
        store = AsyncMock(spec=VectorStorePort)
        with patch(
            "semantic_finance.embeddings.indexer.create_vector_store",
            return_value=store,
        ):
            indexer._ensure_collections()
            indexer._ensure_collections()

        # Deve chamar apenas 4 vezes (uma por collection), não 8
        assert store.ensure_collection.call_count == 4

    def test_tolerates_partial_failure(self):
        store = AsyncMock(spec=VectorStorePort)
        call_count = 0

        async def _fail_on_second(collection, vector_size):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise ConnectionError("unavailable")

        store.ensure_collection = AsyncMock(side_effect=_fail_on_second)
        with patch(
            "semantic_finance.embeddings.indexer.create_vector_store",
            return_value=store,
        ):
            # Não deve levantar exceção mesmo com falha parcial
            indexer._ensure_collections()

        assert store.ensure_collection.call_count == 4
        # Partial failure: collections NOT marked as ensured — allows retry
        assert indexer._collections_ensured is False

    def test_retries_after_partial_failure(self):
        store = AsyncMock(spec=VectorStorePort)
        fail_first_round = True

        async def _fail_on_first_round(collection, vector_size):
            if fail_first_round and collection == "notas_fiscais":
                raise ConnectionError("transient error")

        store.ensure_collection = AsyncMock(side_effect=_fail_on_first_round)
        with patch(
            "semantic_finance.embeddings.indexer.create_vector_store",
            return_value=store,
        ):
            indexer._ensure_collections()
            assert indexer._collections_ensured is False

            # Second attempt after transient error is resolved
            fail_first_round = False
            store.ensure_collection = AsyncMock()
            indexer._ensure_collections()

        assert indexer._collections_ensured is True


# ═══════════════════════════════════════════════════════════════════════════════
# TESTES DE EMBEDDING PROVIDERS
# ═══════════════════════════════════════════════════════════════════════════════


class TestGenerateEmbedding:
    def test_ollama_provider(self):
        with (
            patch.dict(os.environ, {"EMBEDDING_PROVIDER": "ollama"}),
            patch(
                "semantic_finance.embeddings.indexer._generate_ollama_embedding",
                return_value=FAKE_EMBEDDING,
            ) as mock_ollama,
        ):
            result = indexer._generate_embedding("texto de teste")

        mock_ollama.assert_called_once_with("texto de teste")
        assert result == FAKE_EMBEDDING

    def test_openai_provider(self):
        with (
            patch.dict(os.environ, {"EMBEDDING_PROVIDER": "openai"}),
            patch(
                "semantic_finance.embeddings.indexer._generate_openai_embedding",
                return_value=FAKE_EMBEDDING,
            ) as mock_openai,
        ):
            result = indexer._generate_embedding("texto de teste")

        mock_openai.assert_called_once_with("texto de teste")
        assert result == FAKE_EMBEDDING

    def test_voyage_provider(self):
        with (
            patch.dict(os.environ, {"EMBEDDING_PROVIDER": "voyage"}),
            patch(
                "semantic_finance.embeddings.indexer._generate_voyage_embedding",
                return_value=FAKE_EMBEDDING,
            ) as mock_voyage,
        ):
            result = indexer._generate_embedding("texto de teste")

        mock_voyage.assert_called_once_with("texto de teste")
        assert result == FAKE_EMBEDDING

    def test_unsupported_provider_raises(self):
        with (
            patch.dict(os.environ, {"EMBEDDING_PROVIDER": "invalid"}),
            pytest.raises(ValueError, match="não suportado"),
        ):
            indexer._generate_embedding("texto de teste")


class TestOllamaEmbedding:
    def test_calls_ollama_api(self):
        mock_response = MagicMock()
        mock_response.json.return_value = {"embedding": FAKE_EMBEDDING}
        mock_response.raise_for_status = MagicMock()

        with (
            patch.dict(
                os.environ,
                {
                    "OLLAMA_URL": "http://ollama:11434",
                    "OLLAMA_EMBEDDING_MODEL": "nomic-embed-text",
                },
            ),
            patch("semantic_finance.embeddings.indexer.httpx.post", return_value=mock_response) as mock_post,
        ):
            result = indexer._generate_ollama_embedding("meu texto")

        mock_post.assert_called_once_with(
            "http://ollama:11434/api/embeddings",
            json={"model": "nomic-embed-text", "prompt": "meu texto"},
            timeout=httpx.Timeout(180.0, connect=5.0),
        )
        assert result == FAKE_EMBEDDING


class TestOpenAIEmbedding:
    def test_calls_openai_api(self):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": [{"embedding": FAKE_EMBEDDING}]
        }
        mock_response.raise_for_status = MagicMock()

        with (
            patch.dict(
                os.environ,
                {
                    "OPENAI_API_KEY": "sk-test-key",
                    "OPENAI_EMBEDDING_MODEL": "text-embedding-3-small",
                },
            ),
            patch("semantic_finance.embeddings.indexer.httpx.post", return_value=mock_response) as mock_post,
        ):
            result = indexer._generate_openai_embedding("meu texto")

        mock_post.assert_called_once_with(
            "https://api.openai.com/v1/embeddings",
            headers={"Authorization": "Bearer sk-test-key"},
            json={"model": "text-embedding-3-small", "input": "meu texto"},
            timeout=httpx.Timeout(180.0, connect=5.0),
        )
        assert result == FAKE_EMBEDDING


class TestVoyageEmbedding:
    def test_calls_voyage_api(self):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": [{"embedding": FAKE_EMBEDDING}]
        }
        mock_response.raise_for_status = MagicMock()

        with (
            patch.dict(
                os.environ,
                {
                    "VOYAGE_API_KEY": "pa-test-key",
                    "VOYAGE_EMBEDDING_MODEL": "voyage-3-large",
                    "VOYAGE_API_URL": "https://api.voyageai.com",
                },
            ),
            patch("semantic_finance.embeddings.indexer.httpx.post", return_value=mock_response) as mock_post,
        ):
            result = indexer._generate_voyage_embedding("meu texto")

        mock_post.assert_called_once_with(
            "https://api.voyageai.com/v1/embeddings",
            headers={"Authorization": "Bearer pa-test-key"},
            json={"model": "voyage-3-large", "input": ["meu texto"]},
            timeout=httpx.Timeout(180.0, connect=5.0),
        )
        assert result == FAKE_EMBEDDING

    def test_supports_custom_base_url(self):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": [{"embedding": FAKE_EMBEDDING}]
        }
        mock_response.raise_for_status = MagicMock()

        with (
            patch.dict(
                os.environ,
                {
                    "VOYAGE_API_KEY": "pa-test-key",
                    "VOYAGE_EMBEDDING_MODEL": "voyage-3-large",
                    "VOYAGE_API_URL": "http://localhost:8787",
                },
            ),
            patch("semantic_finance.embeddings.indexer.httpx.post", return_value=mock_response) as mock_post,
        ):
            result = indexer._generate_voyage_embedding("meu texto")

        mock_post.assert_called_once_with(
            "http://localhost:8787/v1/embeddings",
            headers={"Authorization": "Bearer pa-test-key"},
            json={"model": "voyage-3-large", "input": ["meu texto"]},
            timeout=httpx.Timeout(180.0, connect=5.0),
        )
        assert result == FAKE_EMBEDDING


# ═══════════════════════════════════════════════════════════════════════════════
# TESTES DO REBUILD INDEX STATS
# ═══════════════════════════════════════════════════════════════════════════════


class TestRebuildIndexStats:
    def test_counts_all_collections(self):
        store = AsyncMock(spec=VectorStorePort)
        store.count = AsyncMock(return_value=42)

        with patch(
            "semantic_finance.embeddings.indexer.create_vector_store",
            return_value=store,
        ):
            indexer.rebuild_index_stats()

        assert store.count.call_count == 4

    def test_tolerates_count_failure(self):
        store = AsyncMock(spec=VectorStorePort)
        store.count = AsyncMock(side_effect=Exception("unavailable"))

        with patch(
            "semantic_finance.embeddings.indexer.create_vector_store",
            return_value=store,
        ):
            # Não deve levantar exceção
            indexer.rebuild_index_stats()


# ═══════════════════════════════════════════════════════════════════════════════
# TESTES DE RESILIÊNCIA (error handling)
# ═══════════════════════════════════════════════════════════════════════════════


class TestErrorHandling:
    """Verifica que nenhuma exceção escapa para o Frappe."""

    def test_embedding_failure_does_not_propagate(self):
        store = AsyncMock(spec=VectorStorePort)
        with (
            patch(
                "semantic_finance.embeddings.indexer.create_vector_store",
                return_value=store,
            ),
            patch(
                "semantic_finance.embeddings.indexer._generate_embedding",
                side_effect=ConnectionError("ollama offline"),
            ),
        ):
            doc = _make_payment_entry()
            # Não deve levantar exceção
            indexer.index_payment_entry(doc, "on_submit")

    def test_vector_store_unavailable_does_not_propagate(self):
        with patch(
            "semantic_finance.embeddings.indexer.create_vector_store",
            side_effect=Exception("cannot connect"),
        ):
            doc = _make_payment_entry()
            # Não deve levantar exceção
            indexer.index_payment_entry(doc, "on_submit")


# ═══════════════════════════════════════════════════════════════════════════════
# TESTES DO SYNC PENDING DOCUMENTS
# ═══════════════════════════════════════════════════════════════════════════════


class TestSyncPendingDocuments:
    """Testa o scheduler job sync_pending_documents com frappe mockado."""

    def _make_frappe_mock(
        self,
        docs_per_doctype: int = 1,
        supplier_count: int = 1,
    ) -> MagicMock:
        frappe = MagicMock()
        frappe.get_all.return_value = [
            SimpleNamespace(name=f"DOC-{i:05d}") for i in range(docs_per_doctype)
        ]
        frappe.get_doc.side_effect = lambda doctype, name: SimpleNamespace(
            name=name,
            doctype=doctype,
            payment_type="Pay",
            party_type="Supplier",
            party="Fornecedor ABC",
            paid_amount=100.00,
            posting_date="2024-01-01",
            mode_of_payment="TED",
            cost_center="",
            reference_no="",
            remarks="",
            references=[],
            supplier_name="Forn",
            tax_id="",
            grand_total=100.0,
            bill_no="",
            items=[],
            taxes_and_charges="",
            voucher_type="Journal Entry",
            accounts=[],
            user_remark="",
            supplier_type="Company",
            supplier_group="Serviços",
            country="Brasil",
        )
        return frappe

    def test_processes_all_doctypes(self):
        store = AsyncMock(spec=VectorStorePort)
        frappe_mock = self._make_frappe_mock()

        with (
            patch(
                "semantic_finance.embeddings.indexer.create_vector_store",
                return_value=store,
            ),
            patch(
                "semantic_finance.embeddings.indexer._generate_embedding",
                return_value=FAKE_EMBEDDING,
            ),
            patch.dict(
                "sys.modules",
                {"frappe": frappe_mock},
            ),
        ):
            indexer.sync_pending_documents()

        # get_all called once for each of the 4 transactional doctypes + Supplier
        assert frappe_mock.get_all.call_count == 5
        called_doctypes = [call[0][0] for call in frappe_mock.get_all.call_args_list]
        assert set(called_doctypes) == {
            "Payment Entry",
            "Purchase Invoice",
            "Sales Invoice",
            "Journal Entry",
            "Supplier",
        }

    def test_doctype_failure_does_not_stop_others(self):
        """Erro ao processar um doctype não interrompe os demais."""
        store = AsyncMock(spec=VectorStorePort)
        frappe_mock = self._make_frappe_mock()

        processed: list[str] = []
        original_get_doc = frappe_mock.get_doc.side_effect

        def _get_doc_with_failure(doctype, name):
            if doctype == "Payment Entry":
                raise RuntimeError("simulated error")
            processed.append(doctype)
            return original_get_doc(doctype, name)

        frappe_mock.get_doc.side_effect = _get_doc_with_failure

        with (
            patch(
                "semantic_finance.embeddings.indexer.create_vector_store",
                return_value=store,
            ),
            patch(
                "semantic_finance.embeddings.indexer._generate_embedding",
                return_value=FAKE_EMBEDDING,
            ),
            patch.dict("sys.modules", {"frappe": frappe_mock}),
        ):
            # Não deve levantar exceção
            indexer.sync_pending_documents()

        # Os outros doctypes devem ter sido processados
        assert "Purchase Invoice" in processed
        assert "Sales Invoice" in processed
        assert "Journal Entry" in processed
        assert "Supplier" in processed

    def test_supplier_is_processed_independently(self):
        """Suppliers são processados mesmo se os doctypes transacionais falharem."""
        store = AsyncMock(spec=VectorStorePort)
        frappe_mock = self._make_frappe_mock()

        upserted_collections: list[str] = []

        async def _capture_upsert(collection, documents):
            upserted_collections.append(collection)

        store.upsert = AsyncMock(side_effect=_capture_upsert)

        # Só retorna docs para Supplier
        def _selective_get_all(doctype, **kwargs):
            if doctype == "Supplier":
                return [SimpleNamespace(name="SUPP-00001")]
            return []

        frappe_mock.get_all.side_effect = _selective_get_all

        with (
            patch(
                "semantic_finance.embeddings.indexer.create_vector_store",
                return_value=store,
            ),
            patch(
                "semantic_finance.embeddings.indexer._generate_embedding",
                return_value=FAKE_EMBEDDING,
            ),
            patch.dict("sys.modules", {"frappe": frappe_mock}),
        ):
            indexer.sync_pending_documents()

        assert "fornecedores" in upserted_collections

    def test_does_not_raise_on_frappe_import_failure(self):
        """Falha ao importar frappe não deve propagar exceção."""
        import sys

        original = sys.modules.get("frappe")
        sys.modules["frappe"] = None  # simula ImportError

        try:
            # Não deve levantar exceção
            indexer.sync_pending_documents()
        finally:
            if original is None:
                sys.modules.pop("frappe", None)
            else:
                sys.modules["frappe"] = original
