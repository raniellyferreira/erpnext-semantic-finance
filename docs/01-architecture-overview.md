# 🏗️ Visão Geral da Arquitetura

## Diagrama Geral

```
┌─────────────────────────────────────────────────────────────────┐
│                        USUÁRIO / LLM                            │
│                  (Claude, GPT, Copilot, etc.)                   │
└────────────────────────────┬────────────────────────────────────┘
                             │ MCP Protocol
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                      MCP SERVER (Python)                        │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ Tools disponíveis:                                       │   │
│  │  • busca_semantica(query)                                │   │
│  │  • listar_despesas(filtros)                              │   │
│  │  • registrar_despesa(dados)                              │   │
│  │  • consultar_fluxo_caixa(periodo)                        │   │
│  │  • emitir_nota_fiscal(dados)                             │   │
│  │  • calcular_impostos(operacao)                           │   │
│  │  • consultar_fornecedor(nome_ou_cnpj)                    │   │
│  │  • gerar_dre(periodo)                                    │   │
│  └─────────────────────────────────────────────────────────┘   │
└──────────┬─────────────────────────────┬────────────────────────┘
           │ REST API                    │ Vector Search
           ▼                             ▼
┌──────────────────────┐   ┌─────────────────────────────────────┐
│   ERPNext / Frappe   │   │         Qdrant (Banco Vetorial)     │
│                      │   │                                     │
│  • Contas P/Pagar    │   │  Collections:                       │
│  • Contas P/Receber  │   │   • despesas                        │
│  • Fluxo de Caixa    │   │   • fornecedores                    │
│  • DRE / Balanço     │   │   • notas_fiscais                   │
│  • Fornecedores      │   │   • lancamentos_contabeis           │
│  • Clientes          │   │                                     │
│  • Estoque           │   └──────────────┬──────────────────────┘
│                      │                  │
│  [Frappe App]        │   ┌──────────────▼──────────────────────┐
│  semantic_finance    │──▶│     Pipeline de Embeddings          │
│  (hooks + indexação) │   │                                     │
│                      │   │  Frappe Hook (on_submit/on_update)  │
└──────────┬───────────┘   │       ↓                             │
           │               │  Ollama / OpenAI Embeddings         │
           │               │       ↓                             │
           │               │  Salva vetor no Qdrant              │
           │               └─────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────────────────────┐
│                   Integrações Fiscais BR                         │
│                                                                  │
│   Focus NF-e API          SEFAZ (via Focus/Webmania)            │
│   • Emissão NF-e          • Consulta de NFe                     │
│   • Emissão NFS-e         • Manifestação do destinatário        │
│   • Consulta status                                             │
└──────────────────────────────────────────────────────────────────┘
```

## Princípios Arquiteturais

### Hexagonal Architecture (Ports & Adapters)

```
         [MCP Tools]     [REST API]     [Web UI]
              │               │              │
              └───────────────┴──────────────┘
                              │
                        ┌─────▼──────┐
                        │  Use Cases  │  ← Application Core
                        │  (Domain)   │
                        └─────┬──────┘
                              │
              ┌───────────────┴──────────────┐
              │               │              │
         [ERPNext]        [Qdrant]      [Focus NFe]
         Adapter          Adapter        Adapter
```

### Domain-Driven Design (DDD)

Bounded Contexts identificados:

| Contexto | Responsabilidade |
|---|---|
| **Financeiro** | Contas a pagar/receber, fluxo de caixa |
| **Fiscal** | NF-e, NFS-e, impostos, SEFAZ |
| **Contábil** | DRE, Balanço, lançamentos |
| **Fornecedores** | Cadastro, histórico, avaliação |
| **Busca Semântica** | Indexação, embeddings, similarity search |

## Fluxo de Busca Semântica

```
Usuário: "Quais foram os maiores gastos com fornecedores de TI em 2024?"
                    │
                    ▼
            MCP Tool: busca_semantica()
                    │
                    ▼
        Gera embedding da query
        (Ollama nomic-embed-text)
                    │
                    ▼
        Busca por similaridade no Qdrant
        (collections: despesas + fornecedores)
                    │
                    ▼
        Retorna top-K documentos relevantes
                    │
                    ▼
        Enriquece com dados do ERPNext via API
                    │
                    ▼
        Retorna contexto estruturado ao LLM
                    │
                    ▼
        LLM gera resposta final para o usuário
```

## Decisões Arquiteturais (ADRs)

### ADR-001: Qdrant como banco vetorial
- **Decisão:** Usar Qdrant self-hosted
- **Motivo:** Open source, alta performance, suporte a filtros híbridos (vetorial + metadados), fácil deploy via Docker
- **Alternativas consideradas:** pgvector (menos recursos), Weaviate (mais complexo)

### ADR-002: Ollama para embeddings locais
- **Decisão:** Usar Ollama com modelo `nomic-embed-text`
- **Motivo:** Dados financeiros são sensíveis; embeddings locais evitam envio de dados para APIs externas
- **Alternativas:** OpenAI Embeddings (configurável via env var)

### ADR-003: Frappe App para hooks de indexação
- **Decisão:** Criar app Frappe `semantic_finance` para hooks de eventos
- **Motivo:** Integração nativa com ciclo de vida dos documentos ERPNext
- **Eventos monitorados:** `on_submit`, `on_update`, `on_cancel`

### ADR-004: MCP Server desacoplado
- **Decisão:** MCP Server como serviço independente (não dentro do Frappe)
- **Motivo:** Separação de responsabilidades; MCP pode evoluir independente do ERP
