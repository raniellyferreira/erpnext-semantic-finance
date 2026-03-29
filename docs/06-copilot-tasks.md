# 🤖 Tarefas para o GitHub Copilot

Este documento lista todas as tarefas de desenvolvimento organizadas por prioridade.
Cada issue pode ser criada no GitHub e atribuída ao Copilot.

---

## 🔴 Alta Prioridade

### TASK-001: Implementar Frappe App `semantic_finance`
**Descrição:**
Criar o app Frappe com a estrutura base e os hooks de eventos para indexação automática no Qdrant.

**Critérios de aceitação:**
- [ ] Estrutura do app criada com `bench new-app semantic_finance`
- [ ] `hooks.py` com doc_events para Payment Entry, Purchase Invoice, Sales Invoice, Journal Entry
- [ ] Módulo `embeddings/indexer.py` com funções `index_*` e `remove_from_index`
- [ ] Módulo `embeddings/text_builder.py` com funções que geram texto rico para cada doctype
- [ ] Conexão com Qdrant via variável de ambiente `QDRANT_URL`
- [ ] Suporte a Ollama e OpenAI via `EMBEDDING_PROVIDER`
- [ ] Testes unitários para text builders
- [ ] README de instalação

**Stack:** Python, Frappe Framework, Qdrant Client, httpx

---

### TASK-002: Implementar MCP Server base
**Descrição:**
Criar o servidor MCP com as tools de busca semântica e integração ERPNext.

**Critérios de aceitação:**
- [ ] `pyproject.toml` com dependências (mcp, httpx, qdrant-client, pydantic, python-dotenv)
- [ ] `config.py` com todas as configurações via env vars
- [ ] `erpnext_client/client.py` com métodos: `get`, `post`, `list_docs`, `get_doc`, `create_doc`
- [ ] `erpnext_client/models.py` com modelos Pydantic para PaymentEntry, PurchaseInvoice, SalesInvoice
- [ ] `vector_store/qdrant_client.py` com métodos: `search`, `upsert`, `delete`
- [ ] `vector_store/embeddings.py` com suporte a Ollama e OpenAI
- [ ] `tools/search_tools.py` com tool `busca_semantica`
- [ ] `main.py` inicializando o MCP Server
- [ ] `.env.example` completo
- [ ] Testes de integração

**Stack:** Python, MCP SDK, httpx, Qdrant, Pydantic

---

### TASK-003: Implementar tools financeiras no MCP
**Descrição:**
Implementar as tools de gestão financeira no MCP Server.

**Critérios de aceitação:**
- [ ] `tools/financial_tools.py` com:
  - [ ] `listar_despesas(data_inicio, data_fim, ...)`
  - [ ] `registrar_despesa(fornecedor, valor, data, ...)`
  - [ ] `consultar_fluxo_caixa(data_inicio, data_fim)`
  - [ ] `consultar_fornecedor(cnpj_ou_nome)`
- [ ] `tools/report_tools.py` com:
  - [ ] `gerar_dre(data_inicio, data_fim)`
  - [ ] `gerar_balancete(data_inicio, data_fim)`
- [ ] Tratamento de erros com mensagens em português
- [ ] Logging estruturado
- [ ] Testes unitários com mocks

---

## 🟡 Média Prioridade

### TASK-004: Integração Focus NF-e
**Descrição:**
Implementar a integração com a API Focus NF-e para emissão de notas fiscais.

**Critérios de aceitação:**
- [ ] `fiscal/focus_nfe.py` com métodos: `emitir_nfe`, `emitir_nfse`, `consultar_status`, `cancelar`
- [ ] Modelos Pydantic para payload de NF-e e NFS-e
- [ ] Suporte a ambiente de homologação e produção via env var
- [ ] Tool MCP `emitir_nota_fiscal` integrada
- [ ] Tratamento de erros da API Focus
- [ ] Testes com ambiente de homologação

**Referência:** https://focusnfe.com.br/doc/

---

### TASK-005: Calculadora de impostos brasileiros
**Descrição:**
Implementar lógica de cálculo de impostos por regime tributário.

**Critérios de aceitação:**
- [ ] `fiscal/tax_calculator.py` com:
  - [ ] `calcular_simples_nacional(receita_bruta, atividade, competencia)`
  - [ ] `calcular_lucro_presumido(receita, tipo_servico_ou_produto)`
  - [ ] `calcular_iss(valor_servico, municipio, item_lista_servico)`
  - [ ] `calcular_icms(valor_produto, uf_origem, uf_destino, ncm)`
- [ ] Tabelas do Simples Nacional (Anexos I a V) atualizadas
- [ ] Tool MCP `consultar_impostos` integrada
- [ ] Testes unitários com casos reais

---

### TASK-006: Docker Compose stack completa
**Descrição:**
Criar o `docker-compose.yml` com toda a stack necessária.

**Critérios de aceitação:**
- [ ] Serviços: `erpnext`, `mariadb`, `redis`, `qdrant`, `ollama`, `mcp-server`
- [ ] Health checks em todos os serviços
- [ ] Volumes persistentes para dados
- [ ] Variáveis de ambiente via `.env`
- [ ] Instruções de primeiro boot no README
- [ ] Script `setup.sh` para configuração inicial

---

## 🟢 Baixa Prioridade

### TASK-007: Script de indexação em batch
**Descrição:**
Script para indexar documentos históricos já existentes no ERPNext.

**Critérios de aceitação:**
- [ ] `scripts/batch_index.py` que indexa todos os documentos submetidos
- [ ] Suporte a `--doctype` para indexar tipo específico
- [ ] Barra de progresso (tqdm)
- [ ] Retry com backoff exponencial
- [ ] Relatório final de indexação

---

### TASK-008: Dashboard de monitoramento da busca semântica
**Descrição:**
Page no ERPNext com métricas da busca semântica.

**Critérios de aceitação:**
- [ ] Frappe Page `semantic-dashboard`
- [ ] Total de documentos indexados por collection
- [ ] Últimas indexações
- [ ] Botão para re-indexar documento específico
- [ ] Botão para testar busca semântica

---

## 📋 Como criar Issues no GitHub

```bash
# Instale o GitHub CLI
gh issue create --title "TASK-001: Implementar Frappe App semantic_finance" \
  --body "$(cat docs/06-copilot-tasks.md)" \
  --label "copilot"
```
