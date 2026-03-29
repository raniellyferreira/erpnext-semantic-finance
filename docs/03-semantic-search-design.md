# 🔍 Design da Busca Semântica

## Visão Geral

A busca semântica permite consultas em linguagem natural sobre dados financeiros, como:

- _"Quais fornecedores tiveram maior volume de pagamentos em 2024?"_
- _"Mostre despesas relacionadas a serviços de TI acima de R$10.000"_
- _"Quais notas fiscais de entrada estão pendentes de conciliação?"_

## Stack de Embeddings

### Opção 1: Ollama (Recomendado - Local/Self-hosted)
```
Modelo: nomic-embed-text (768 dimensões)
Vantagem: 100% local, dados financeiros não saem da infraestrutura
Requisito: ~500MB RAM
```

### Opção 2: OpenAI
```
Modelo: text-embedding-3-small (1536 dimensões)
Vantagem: Maior qualidade
Desvantagem: Dados enviados para API externa (atenção à LGPD)
```

## Configuração via variável de ambiente
```bash
# .env
EMBEDDING_PROVIDER=ollama          # ou openai
OLLAMA_URL=http://ollama:11434
OLLAMA_MODEL=nomic-embed-text
OPENAI_API_KEY=sk-...              # se usar openai
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
```

## Banco Vetorial: Qdrant

### Collections a criar

```python
# despesas
{
    "name": "despesas",
    "vector_size": 768,
    "distance": "Cosine",
    "payload_schema": {
        "doctype": "string",       # Payment Entry, Purchase Invoice
        "name": "string",          # ID do documento no ERPNext
        "supplier": "string",      # Fornecedor
        "amount": "float",         # Valor
        "date": "string",          # Data
        "cost_center": "string",   # Centro de custo
        "category": "string",      # Categoria da despesa
        "description": "string",   # Descrição original
    }
}

# notas_fiscais
{
    "name": "notas_fiscais",
    "vector_size": 768,
    "distance": "Cosine",
    "payload_schema": {
        "doctype": "string",
        "nfe_number": "string",
        "supplier_cnpj": "string",
        "items_description": "string",  # texto concatenado dos itens
        "total_value": "float",
        "tax_icms": "float",
        "tax_pis": "float",
        "tax_cofins": "float",
        "issue_date": "string",
    }
}

# lancamentos_contabeis
{
    "name": "lancamentos_contabeis",
    "vector_size": 768,
    "distance": "Cosine",
    "payload_schema": {
        "account": "string",
        "debit": "float",
        "credit": "float",
        "remarks": "string",
        "posting_date": "string",
        "voucher_type": "string",
    }
}
```

## Pipeline de Indexação (Frappe Hooks)

```python
# semantic_finance/hooks.py

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
}
```

## Texto para Embedding

Cada documento deve gerar um texto rico para embedding:

```python
def build_payment_entry_text(doc) -> str:
    return f"""
    Pagamento para fornecedor {doc.party} no valor de R$ {doc.paid_amount:.2f}
    em {doc.posting_date}. Referência: {doc.reference_no}.
    Centro de custo: {doc.cost_center}.
    Modo de pagamento: {doc.mode_of_payment}.
    Observações: {doc.remarks or 'sem observações'}.
    """.strip()

def build_purchase_invoice_text(doc) -> str:
    items_text = ", ".join([f"{i.item_name} (qty: {i.qty}, valor: R${i.amount:.2f})" for i in doc.items])
    return f"""
    Nota fiscal de entrada do fornecedor {doc.supplier} ({doc.supplier_name})
    no valor total de R$ {doc.grand_total:.2f} em {doc.posting_date}.
    Itens: {items_text}.
    CNPJ fornecedor: {doc.tax_id}.
    Impostos: ICMS R${doc.total_taxes_and_charges:.2f}.
    """.strip()
```

## Busca Híbrida (Vetorial + Filtros)

```python
# Exemplo: busca semântica com filtro de data e valor
results = qdrant_client.search(
    collection_name="despesas",
    query_vector=embedding_da_query,
    query_filter=Filter(
        must=[
            FieldCondition(key="date", range=DatetimeRange(gte="2024-01-01")),
            FieldCondition(key="amount", range=Range(gte=1000.0)),
        ]
    ),
    limit=10
)
```
