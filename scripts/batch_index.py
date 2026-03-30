#!/usr/bin/env python3
"""Indexação em lote de documentos históricos do ERPNext no vector store.

Busca documentos do ERPNext via API e indexa no banco vetorial configurado
(Qdrant ou Pinecone), usando a arquitetura hexagonal existente.

Uso:
    python scripts/batch_index.py
    python scripts/batch_index.py --doctype "Payment Entry"
    python scripts/batch_index.py --doctype "Purchase Invoice" --batch-size 50
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

# Adiciona o diretório mcp-server ao sys.path para importar módulos internos
_MCP_SERVER_DIR = str(Path(__file__).resolve().parent.parent / "mcp-server")
if _MCP_SERVER_DIR not in sys.path:
    sys.path.insert(0, _MCP_SERVER_DIR)

import structlog  # noqa: E402
from tenacity import retry, stop_after_attempt, wait_exponential  # noqa: E402

from src.config import settings  # noqa: E402
from src.erpnext_client.client import ERPNextClient  # noqa: E402
from src.vector_store.embeddings import EmbeddingService  # noqa: E402
from src.vector_store.factory import create_vector_store  # noqa: E402
from src.vector_store.port import VectorDocument, VectorStorePort  # noqa: E402

logger = structlog.get_logger(__name__)

# ─── DocTypes suportados e mapeamento para coleções ──────────────────────────

_DOCTYPE_COLLECTION_MAP: dict[str, str] = {
    "Payment Entry": "despesas",
    "Purchase Invoice": "notas_fiscais",
    "GL Entry": "lancamentos_contabeis",
    "Journal Entry": "lancamentos_contabeis",
    "Sales Invoice": "notas_fiscais",
}

_DEFAULT_DOCTYPES = list(_DOCTYPE_COLLECTION_MAP.keys())

_DEFAULT_FIELDS = {
    "Payment Entry": [
        "name", "posting_date", "payment_type", "party_type", "party",
        "party_name", "paid_amount", "paid_from", "paid_to", "reference_no",
        "remarks", "cost_center", "company",
    ],
    "Purchase Invoice": [
        "name", "posting_date", "supplier", "supplier_name", "grand_total",
        "net_total", "remarks", "cost_center", "company", "bill_no",
    ],
    "GL Entry": [
        "name", "posting_date", "account", "debit", "credit",
        "party_type", "party", "remarks", "cost_center", "company",
    ],
    "Journal Entry": [
        "name", "posting_date", "voucher_type", "total_debit",
        "total_credit", "remark", "company",
    ],
    "Sales Invoice": [
        "name", "posting_date", "customer", "customer_name", "grand_total",
        "net_total", "remarks", "cost_center", "company",
    ],
}


# ─── Funções auxiliares ──────────────────────────────────────────────────────


def _doc_to_text(doctype: str, doc: dict) -> str:
    """Converte um documento ERPNext em texto para embedding."""
    parts = [f"DocType: {doctype}"]
    for key, value in doc.items():
        if value is not None and value != "" and key != "name":
            parts.append(f"{key}: {value}")
    return " | ".join(parts)


def _doc_to_payload(doctype: str, doc: dict) -> dict:
    """Extrai metadados relevantes para armazenamento no vector store.

    Além de copiar todos os campos não vazios do documento original,
    normaliza as chaves ``date``, ``amount``, ``supplier`` e ``cost_center``
    para que os filtros híbridos (SearchFilter) funcionem de forma consistente
    entre diferentes fontes de indexação (QdrantAdapter / PineconeAdapter).
    """
    payload: dict = {"doctype": doctype}
    for key, value in doc.items():
        if value is not None and value != "":
            payload[key] = value

    # ─── Normalização de campos para filtros híbridos ────────────────────────

    # Normaliza data — chave esperada pelos adapters: "date"
    posting_date = doc.get("posting_date")
    if posting_date:
        payload.setdefault("date", posting_date)

    # Normaliza valor (amount) por DocType — chave esperada pelos adapters: "amount"
    amount_value: float | str | None = None
    if doctype == "Payment Entry":
        amount_value = doc.get("paid_amount")
    elif doctype in ("Purchase Invoice", "Sales Invoice"):
        amount_value = doc.get("grand_total") or doc.get("net_total")
    elif doctype == "Journal Entry":
        amount_value = doc.get("total_debit") or doc.get("total_credit")
    elif doctype == "GL Entry":
        amount_value = doc.get("debit") or doc.get("credit")

    if amount_value is not None and amount_value != "":
        payload.setdefault("amount", amount_value)

    # Normaliza contraparte da transação — chave esperada pelos adapters: "supplier"
    supplier_like = doc.get("supplier") or doc.get("customer") or doc.get("party")
    if supplier_like:
        payload.setdefault("supplier", supplier_like)

    # Garante cost_center como chave normalizada
    cost_center = doc.get("cost_center")
    if cost_center:
        payload.setdefault("cost_center", cost_center)

    return payload


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    reraise=True,
)
async def _embed_with_retry(service: EmbeddingService, text: str) -> list[float]:
    """Gera embedding com retry e backoff exponencial."""
    return await service.embed(text)


# ─── Indexação ────────────────────────────────────────────────────────────────


async def index_doctype(
    doctype: str,
    client: ERPNextClient,
    embedding_service: EmbeddingService,
    vector_store: VectorStorePort,
    batch_size: int = 100,
) -> tuple[int, int]:
    """Indexa todos os documentos de um DocType no vector store.

    Args:
        doctype: Tipo do documento ERPNext (ex: ``Payment Entry``).
        client: Instância do ERPNextClient para buscar documentos.
        embedding_service: Serviço de geração de embeddings.
        vector_store: Adapter de vector store já instanciado.
        batch_size: Tamanho do lote para paginação.

    Returns:
        Tupla (total_indexado, total_erros).
    """
    collection = _DOCTYPE_COLLECTION_MAP.get(doctype)
    if not collection:
        logger.warning("doctype_sem_colecao", doctype=doctype)
        return 0, 0

    await vector_store.ensure_collection(
        collection=collection,
        vector_size=settings.embedding_dimension,
    )

    fields = _DEFAULT_FIELDS.get(doctype, ["name"])

    # Busca documentos com paginação baseada em nome
    total_indexed = 0
    total_errors = 0
    last_name: str | None = None

    # Tenta importar tqdm para barra de progresso
    try:
        from tqdm import tqdm
        use_tqdm = True
    except ImportError:
        use_tqdm = False
        logger.info(
            "tqdm_nao_instalado",
            msg="Instale tqdm para barra de progresso: pip install tqdm",
        )

    pbar = None

    while True:
        # Paginação via filtro no campo name (ordem crescente padrão do ERPNext)
        filters: list[list] | None = None
        if last_name:
            filters = [["name", ">", last_name]]

        try:
            docs = await client.list_docs(
                doctype=doctype,
                fields=fields,
                filters=filters,
                limit=batch_size,
            )
        except Exception:
            logger.exception("erro_listando_docs", doctype=doctype, last_name=last_name)
            total_errors += 1
            break

        if not docs:
            break

        if use_tqdm and pbar is None:
            # Estimativa inicial — atualizada conforme busca
            pbar = tqdm(desc=f"Indexando {doctype}", unit="doc", dynamic_ncols=True)

        batch_docs: list[VectorDocument] = []

        for doc in docs:
            try:
                text = _doc_to_text(doctype, doc)
                vector = await _embed_with_retry(embedding_service, text)
                payload = _doc_to_payload(doctype, doc)

                batch_docs.append(VectorDocument(
                    id=f"{doctype}:{doc.get('name', '')}",
                    vector=vector,
                    payload=payload,
                ))
            except Exception:
                logger.exception("erro_embedding_doc", doctype=doctype, doc=doc.get("name"))
                total_errors += 1

        if batch_docs:
            try:
                await vector_store.upsert(collection=collection, documents=batch_docs)
                total_indexed += len(batch_docs)
            except Exception:
                logger.exception("erro_upsert_batch", doctype=doctype, batch_size=len(batch_docs))
                total_errors += len(batch_docs)

        if pbar:
            pbar.update(len(docs))

        # Atualiza cursor de paginação
        last_name = docs[-1].get("name") if docs else None

        if len(docs) < batch_size:
            break

    if pbar:
        pbar.close()

    return total_indexed, total_errors


# ─── Main ─────────────────────────────────────────────────────────────────────


async def run(args: argparse.Namespace) -> None:
    """Executa a indexação em lote."""
    start_time = time.monotonic()

    doctypes = [args.doctype] if args.doctype else _DEFAULT_DOCTYPES

    logger.info(
        "indexacao_iniciada",
        doctypes=doctypes,
        batch_size=args.batch_size,
        vector_store_provider=settings.vector_store_provider,
    )

    client = ERPNextClient()
    embedding_service = EmbeddingService()
    vector_store = create_vector_store()

    report: dict[str, dict] = {}

    try:
        for doctype in doctypes:
            logger.info("indexando_doctype", doctype=doctype)
            indexed, errors = await index_doctype(
                doctype=doctype,
                client=client,
                embedding_service=embedding_service,
                vector_store=vector_store,
                batch_size=args.batch_size,
            )
            report[doctype] = {"indexados": indexed, "erros": errors}
    finally:
        await embedding_service.close()
        await client.close()

    elapsed = time.monotonic() - start_time

    # ─── Relatório final ──────────────────────────────────────────────────────
    total_indexed = sum(r["indexados"] for r in report.values())
    total_errors = sum(r["erros"] for r in report.values())

    print("\n" + "=" * 60)
    print("  RELATÓRIO DE INDEXAÇÃO")
    print("=" * 60)
    print(f"  Provider:       {settings.vector_store_provider}")
    print(f"  Tempo total:    {elapsed:.1f}s")
    print(f"  Total indexado: {total_indexed}")
    print(f"  Total erros:    {total_errors}")
    print("-" * 60)

    for doctype, stats in report.items():
        status = "✓" if stats["erros"] == 0 else "✗"
        print(f"  {status} {doctype}: {stats['indexados']} indexados, {stats['erros']} erros")

    print("=" * 60)

    # Saída JSON para integração com CI/CD
    if args.json:
        output = {
            "provider": settings.vector_store_provider,
            "elapsed_seconds": round(elapsed, 1),
            "total_indexed": total_indexed,
            "total_errors": total_errors,
            "details": report,
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))


def main() -> None:
    """Entry point do script de indexação em lote."""
    parser = argparse.ArgumentParser(
        description="Indexa documentos históricos do ERPNext no vector store.",
    )
    parser.add_argument(
        "--doctype",
        type=str,
        default=None,
        help=(
            "DocType específico para indexar (ex: 'Payment Entry'). "
            "Sem este argumento, indexa todos."
        ),
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Tamanho do lote para buscar documentos da API ERPNext (padrão: 100).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Exibe relatório final em formato JSON.",
    )

    args = parser.parse_args()

    # Valida doctype se fornecido
    if args.doctype and args.doctype not in _DOCTYPE_COLLECTION_MAP:
        supported = ", ".join(sorted(_DOCTYPE_COLLECTION_MAP.keys()))
        parser.error(f"DocType '{args.doctype}' não suportado. Opções: {supported}")

    asyncio.run(run(args))


if __name__ == "__main__":
    main()
