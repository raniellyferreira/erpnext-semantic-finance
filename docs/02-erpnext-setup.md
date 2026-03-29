# ⚙️ Setup do ERPNext

## Pré-requisitos

- Docker e Docker Compose instalados
- Mínimo 4GB RAM, 20GB disco
- Python 3.11+

## 1. Subir ERPNext via Docker

```bash
# Clone o repositório
git clone https://github.com/raniellyferreira/erpnext-semantic-finance.git
cd erpnext-semantic-finance

# Suba a stack completa
docker compose -f docker/docker-compose.yml up -d
```

## 2. Acessar ERPNext

- URL: http://localhost:8080
- Usuário: `Administrator`
- Senha: definida no `docker-compose.yml`

## 3. Configuração Inicial do ERPNext

### 3.1 Empresa
```
Nome da empresa: [Sua Empresa Ltda]
País: Brazil
Moeda: BRL
Plano de Contas: Brazil - Chart of Accounts
```

### 3.2 Configurações Fiscais
```
Regime Tributário: Simples Nacional / Lucro Presumido / Lucro Real
CNPJ: [seu CNPJ]
Inscrição Estadual: [IE]
Inscrição Municipal: [IM]
```

### 3.3 Instalar o App semantic_finance

```bash
# Acessar o container do backend
docker exec -it erpnext-backend bash

# Instalar o app
bench get-app https://github.com/raniellyferreira/erpnext-semantic-finance --branch main
bench --site mysite.localhost install-app semantic_finance
bench restart
```

## 4. Configurar API Key do ERPNext

```bash
# No ERPNext UI:
# Settings → API Access → Gerar API Key e API Secret
# Salvar em .env:
ERPNEXT_URL=http://localhost:8080
ERPNEXT_API_KEY=seu_api_key
ERPNEXT_API_SECRET=seu_api_secret
```

## 5. Módulos ERPNext utilizados

| Módulo | Uso |
|---|---|
| **Accounts** | Plano de contas, lançamentos, DRE, Balanço |
| **Buying** | Fornecedores, ordens de compra |
| **Selling** | Clientes, pedidos de venda |
| **Stock** | Estoque (opcional) |
| **Payroll** | Folha de pagamento (opcional) |
| **ERPNext Brazil** | Localização fiscal brasileira |

## 6. API REST do ERPNext

### Autenticação
```bash
curl -X GET http://localhost:8080/api/resource/Expense
  -H "Authorization: token api_key:api_secret"
```

### Exemplos de endpoints relevantes

```bash
# Listar Payment Entries (pagamentos)
GET /api/resource/Payment Entry?filters=[["payment_type","=","Pay"]]

# Criar Purchase Invoice (NF de entrada)
POST /api/resource/Purchase Invoice

# Consultar General Ledger (lançamentos contábeis)
GET /api/resource/GL Entry

# Relatório DRE
GET /api/method/frappe.desk.reportview.get?report_name=Profit and Loss Statement
```

## 7. Referências

- [Documentação ERPNext](https://docs.erpnext.com)
- [Frappe Framework Docs](https://frappeframework.com/docs)
- [ERPNext Docker](https://github.com/frappe/frappe_docker)
