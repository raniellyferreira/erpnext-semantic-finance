# 🤖 Design do Servidor MCP

## Visão Geral

O MCP Server expõe **Tools** que permitem LLMs interagirem com o ERPNext e a busca semântica via protocolo MCP.

## Estrutura do Projeto

```
mcp-server/
├── pyproject.toml
├── .env.example
└── src/
    ├── main.py                    # Entry point do MCP Server
    ├── config.py                  # Configurações via env vars
    ├── erpnext_client/
    │   ├── __init__.py
    │   ├── client.py              # Cliente HTTP para API ERPNext
    │   ├── models.py              # Modelos de dados (Pydantic)
    │   └── exceptions.py         # Exceções customizadas
    ├── vector_store/
    │   ├── __init__.py
    │   ├── qdrant_client.py       # Cliente Qdrant
    │   └── embeddings.py         # Geração de embeddings
    ├── fiscal/
    │   ├── __init__.py
    │   ├── focus_nfe.py           # Integração Focus NF-e
    │   └── tax_calculator.py     # Cálculo de impostos BR
    └── tools/
        ├── __init__.py
        ├── search_tools.py        # Busca semântica
        ├── financial_tools.py     # Despesas, fluxo de caixa
        ├── fiscal_tools.py        # NF-e, impostos
        └── report_tools.py        # DRE, Balanço
```

## Tools MCP definidas

### 1. busca_semantica
```python
@mcp.tool()
async def busca_semantica(
    query: str,
    colecoes: list[str] = ["despesas", "notas_fiscais", "lancamentos_contabeis"],
    limite: int = 10,
    data_inicio: str | None = None,
    data_fim: str | None = None,
    valor_minimo: float | None = None,
    valor_maximo: float | None = None,
) -> list[dict]:
    """
    Realiza busca semântica em linguagem natural sobre os dados financeiros.
    Retorna documentos relevantes do ERPNext com base na similaridade semântica.
    """
```

### 2. listar_despesas
```python
@mcp.tool()
async def listar_despesas(
    data_inicio: str,
    data_fim: str,
    fornecedor: str | None = None,
    centro_custo: str | None = None,
    valor_minimo: float | None = None,
    limite: int = 50,
) -> list[dict]:
    """
    Lista despesas/pagamentos do ERPNext com filtros.
    """
```

### 3. registrar_despesa
```python
@mcp.tool()
async def registrar_despesa(
    fornecedor: str,
    valor: float,
    data: str,
    centro_custo: str,
    conta_debito: str,
    descricao: str,
    modo_pagamento: str = "Transferência Bancária",
) -> dict:
    """
    Registra uma despesa/pagamento no ERPNext.
    Cria um Payment Entry com os dados fornecidos.
    """
```

### 4. consultar_fluxo_caixa
```python
@mcp.tool()
async def consultar_fluxo_caixa(
    data_inicio: str,
    data_fim: str,
    empresa: str | None = None,
) -> dict:
    """
    Consulta o fluxo de caixa do período.
    Retorna entradas, saídas e saldo.
    """
```

### 5. gerar_dre
```python
@mcp.tool()
async def gerar_dre(
    data_inicio: str,
    data_fim: str,
    empresa: str | None = None,
) -> dict:
    """
    Gera o Demonstrativo de Resultado do Exercício (DRE).
    """
```

### 6. emitir_nota_fiscal
```python
@mcp.tool()
async def emitir_nota_fiscal(
    tipo: str,                    # nfe ou nfse
    cnpj_destinatario: str,
    nome_destinatario: str,
    itens: list[dict],            # [{descricao, quantidade, valor_unitario, ncm}]
    natureza_operacao: str,
    forma_pagamento: str = "01",  # 01 = dinheiro
) -> dict:
    """
    Emite Nota Fiscal Eletrônica (NF-e) ou Nota Fiscal de Serviço (NFS-e)
    via API Focus NF-e.
    """
```

### 7. consultar_impostos
```python
@mcp.tool()
async def consultar_impostos(
    regime_tributario: str,       # simples_nacional, lucro_presumido, lucro_real
    receita_bruta_anual: float,
    tipo_atividade: str,          # comercio, servicos, industria
    competencia: str,             # YYYY-MM
) -> dict:
    """
    Calcula estimativa de impostos brasileiros com base no regime tributário.
    Retorna alíquotas de IRPJ, CSLL, PIS, COFINS, ISS/ICMS.
    """
```

### 8. consultar_fornecedor
```python
@mcp.tool()
async def consultar_fornecedor(
    cnpj_ou_nome: str,
) -> dict:
    """
    Consulta dados de um fornecedor no ERPNext.
    Retorna histórico de compras, pagamentos pendentes e avaliação.
    """
```

## Configuração do MCP Server

```bash
# .env.example
ERPNEXT_URL=http://localhost:8080
ERPNEXT_API_KEY=sua_api_key
ERPNEXT_API_SECRET=seu_api_secret
ERPNEXT_SITE_NAME=mysite.localhost

QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=                    # opcional se local

EMBEDDING_PROVIDER=ollama          # ollama ou openai
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=nomic-embed-text
OPENAI_API_KEY=                    # se usar openai

FOCUS_NFE_TOKEN=seu_token_focus
FOCUS_NFE_URL=https://homologacao.focusnfe.com.br  # ou producao

MCP_SERVER_HOST=0.0.0.0
MCP_SERVER_PORT=8000
```

## Instalação e Execução

```bash
cd mcp-server
pip install -e .

# Desenvolvimento
python src/main.py

# Via Docker
docker compose up mcp-server
```

## Integração com Claude Desktop

```json
// claude_desktop_config.json
{
  "mcpServers": {
    "erpnext-finance": {
      "command": "python",
      "args": ["/path/to/mcp-server/src/main.py"],
      "env": {
        "ERPNEXT_URL": "http://localhost:8080",
        "ERPNEXT_API_KEY": "sua_key"
      }
    }
  }
}
```
