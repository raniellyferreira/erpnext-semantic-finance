# 🔍 Design da Busca Semântica

## Visão Geral

A busca semântica permite consultas em linguagem natural sobre dados financeiros, como:

- _"Quais fornecedores tiveram maior volume de pagamentos em 2024?"_
- _"Mostre despesas relacionadas a serviços de TI acima de R$10.000"_
- _"Quais notas fiscais de entrada estão pendentes de conciliação?"_

---

## Stack de Embeddings

### Opção 1: Ollama (Recomendado — Local/Self-hosted)
```
Modelo: nomic-embed-text (768 dimensões)
Vantagem: 100% local, dados financeiros não saem da infraestrutura
Requisito: ~500MB RAM
```

### Opção 2: OpenAI
```
Modelo: text-embedding-3-small (1536 dimensões)
Vantagem: Maior qualidade semântica
Desvantagem: Dados enviados para API externa (atenção à LGPD)
```

### Configuração via variável de ambiente
```bash
# .env
EMBEDDING_PROVIDER=ollama          # ou openai
EMBEDDING_DIMENSION=768            # 768 (Ollama) ou 1536 (OpenAI)
OLLAMA_URL=http://ollama:11434
OLLAMA_EMBEDDING_MODEL=nomic-embed-text
OPENAI_API_KEY=sk-...              # se usar openai
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
```

---

## Bancos Vetoriais Suportados

O sistema usa **Ports & Adapters (Hexagonal Architecture)**: o código de negócio
depende apenas da interface abstrata `VectorStorePort`. O adapter concreto é
injetado via factory baseada na env var `VECTOR_STORE_PROVIDER`.

```
VectorStorePort (interface abstrata)
    ├── QdrantAdapter   → VECTOR_STORE_PROVIDER=qdrant
    └── PineconeAdapter → VECTOR_STORE_PROVIDER=pinecone
```

### Qdrant (self-hosted ou Qdrant Cloud)
```bash
VECTOR_STORE_PROVIDER=qdrant
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=          # vazio para instância local
```

| Característica | Detalhe |
|---|---|
| Tipo | Self-hosted (Docker) ou Cloud |
| Collections | Criadas automaticamente pelo adapter |
| Filtros híbridos | ✅ Suportados nativamente |
| Melhor para | Infraestrutura própria / on-premise / dados sensíveis |

### Pinecone (Serverless ou Pod-based)
```bash
VECTOR_STORE_PROVIDER=pinecone
PINECONE_API_KEY=sua_api_key
PINECONE_INDEX_NAME=erpnext-finance   # index deve ser criado previamente
PINECONE_NAMESPACE=default            # útil para multi-tenancy
PINECONE_ENVIRONMENT=                 # vazio para Serverless (recomendado)
```

| Característica | Detalhe |
|---|---|
| Tipo | Managed cloud (SaaS) |
| Collections | Simuladas via **namespaces** dentro de um único index |
| Filtros híbridos | ✅ Metadata filtering nativo |
| Melhor para | Escala gerenciada, sem ops de infraestrutura |
| ⚠️ LGPD | Dados enviados para servidores Pinecone — avaliar conformidade |

> **Importante (Pinecone):** O index deve ser criado manualmente no console
> Pinecone (ou via Terraform/IaC) com `metric=cosine` e `dimension` igual
> ao `EMBEDDING_DIMENSION` configurado **antes** de subir o serviço.

---

## Arquitetura do Vector Store

```
mcp-server/src/vector_store/
├── port.py                    # VectorStorePort (interface abstrata)
├── factory.py                 # Instancia o adapter correto via env var
├── __init__.py                # Exports públicos
└── adapters/
    ├── qdrant_adapter.py      # Adapter Qdrant
    └── pinecone_adapter.py    # Adapter Pinecone
```

### Interface `VectorStorePort`

```python
class VectorStorePort(ABC):
    async def ensure_collection(collection, vector_size) -> None: ...
    async def upsert(collection, documents: list[VectorDocument]) -> None: ...
    async def search(collection, query_vector, limit, filters) -> list[SearchResult]: ...
    async def delete(collection, doc_id) -> None: ...
    async def count(collection) -> int: ...
```

---

## Collections / Namespaces

| Nome | Documentos indexados | Campos de payload principais |
|---|---|---|
| `despesas` | Payment Entry | supplier, amount, date, cost_center |
| `notas_fiscais` | Purchase Invoice, Sales Invoice | supplier_cnpj, total_value, tax_icms, issue_date |
| `lancamentos_contabeis` | Journal Entry | account, debit, credit, posting_date |
| `fornecedores` | Supplier | supplier_name, tax_id (CNPJ) |

---

## Pipeline de Indexação (Frappe Hooks)

```python
# semantic_finance/hooks.py
doc_events = {
    "Payment Entry":    {"on_submit": "...index_payment_entry",   "on_cancel": "...remove_from_index"},
    "Purchase Invoice": {"on_submit": "...index_purchase_invoice", "on_cancel": "...remove_from_index"},
    "Sales Invoice":    {"on_submit": "...index_sales_invoice",    "on_cancel": "...remove_from_index"},
    "Journal Entry":    {"on_submit": "...index_journal_entry",    "on_cancel": "...remove_from_index"},
    "Supplier":         {"after_insert": "...index_supplier",      "on_update": "...index_supplier"},
}
```

---

## Busca Híbrida (Vetorial + Filtros)

Ambos os adapters suportam filtros de metadados combinados com busca vetorial:

```python
results = await vector_store.search(
    collection="despesas",
    query_vector=embedding_da_query,
    limit=10,
    filters=SearchFilter(
        date_gte="2024-01-01",
        date_lte="2024-12-31",
        amount_gte=1000.0,
        supplier="Fornecedor XYZ",
    ),
)
```

### Tradução dos filtros por adapter

| Filtro | Qdrant | Pinecone |
|---|---|---|
| `date_gte` | `FieldCondition(range=Range(gte=...))` | `{"date": {"$gte": ...}}` |
| `amount_lte` | `FieldCondition(range=Range(lte=...))` | `{"amount": {"$lte": ...}}` |
| `supplier` | `FieldCondition(match=MatchValue(...))` | `{"supplier": {"$eq": ...}}` |
