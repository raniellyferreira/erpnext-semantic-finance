# 🧠 ERPNext Semantic Finance

Estudo e arquitetura para implementação de **busca semântica** e **MCP (Model Context Protocol)** sobre **ERPNext** para gestão financeira empresarial brasileira.

## 📋 Objetivo

Criar um sistema que permita:
- Gerenciar finanças empresariais completas via ERPNext
- Adicionar busca semântica sobre dados financeiros (despesas, NF-e, fornecedores, etc.)
- Expor funcionalidades via MCP para integração com LLMs (Claude, GPT, etc.)
- Manter compliance fiscal brasileiro (NF-e, ICMS, ISS, Simples Nacional)

## 📁 Estrutura do Projeto

```
.
├── docs/
│   ├── 01-architecture-overview.md       # Visão geral da arquitetura
│   ├── 02-erpnext-setup.md               # Setup do ERPNext
│   ├── 03-semantic-search-design.md      # Design da busca semântica
│   ├── 04-mcp-server-design.md           # Design do servidor MCP
│   ├── 05-brazilian-fiscal-integration.md # Integração fiscal BR
│   └── 06-copilot-tasks.md               # Tarefas para o Copilot
├── frappe-app/
│   └── semantic_finance/                 # App Frappe customizado
│       ├── hooks.py                      # Hooks de eventos
│       ├── embeddings/                   # Pipeline de embeddings
│       └── api/                          # Endpoints REST customizados
├── mcp-server/
│   └── src/                             # Servidor MCP em Python
│       ├── tools/                       # Tools MCP
│       └── erpnext_client/              # Cliente da API ERPNext
└── docker/
    └── docker-compose.yml               # Stack completa
```

## 🚀 Quick Start

Veja [docs/02-erpnext-setup.md](docs/02-erpnext-setup.md) para instruções de setup.

## 🏗️ Arquitetura

Veja [docs/01-architecture-overview.md](docs/01-architecture-overview.md) para visão geral.

## 🤖 Tarefas para o GitHub Copilot

Veja [docs/06-copilot-tasks.md](docs/06-copilot-tasks.md) para a lista de tarefas prontas para o Copilot desenvolver.

## 🛠️ Stack Tecnológica

| Componente | Tecnologia |
|---|---|
| ERP | ERPNext / Frappe Framework |
| Linguagem backend | Python 3.11+ |
| Banco relacional | MariaDB / PostgreSQL |
| Banco vetorial | Qdrant (self-hosted) |
| Embeddings | Ollama (local) ou OpenAI |
| MCP Server | Python (mcp SDK) |
| Infraestrutura | Docker Compose |
| Fiscal BR | Focus NF-e API |

## 📜 Licença

MIT
