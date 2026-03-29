# 🇧🇷 Integração Fiscal Brasileira

## Visão Geral

O sistema tributário brasileiro é complexo e requer integrações específicas. Esta documentação descreve como integrar o ERPNext com as obrigações fiscais brasileiras.

## Regimes Tributários Suportados

| Regime | Impostos | Observação |
|---|---|---|
| **Simples Nacional** | DAS (unificado) | Faturamento até R$4,8M/ano |
| **Lucro Presumido** | IRPJ, CSLL, PIS, COFINS, ISS/ICMS | Faturamento até R$78M/ano |
| **Lucro Real** | IRPJ, CSLL, PIS, COFINS, ISS/ICMS | Qualquer faturamento |

## Impostos por Tipo de Operação

### Venda de Mercadorias (Comércio/Indústria)
```
- ICMS: 4% a 18% (varia por estado)
- PIS: 0,65% (presumido) ou 1,65% (real - não cumulativo)
- COFINS: 3% (presumido) ou 7,6% (real - não cumulativo)
- IPI: variável por NCM (indústria)
- IRPJ + CSLL: sobre lucro
```

### Prestação de Serviços
```
- ISS: 2% a 5% (varia por município)
- PIS: 0,65% ou 1,65%
- COFINS: 3% ou 7,6%
- INSS (retenção): 11% sobre alguns serviços
- IR Fonte: 1,5% sobre alguns serviços
- CSLL Fonte: 1% sobre alguns serviços
```

## Integração com Focus NF-e

### Por que Focus NF-e?
- API REST moderna e bem documentada
- Plano gratuito disponível para desenvolvimento/baixo volume
- Suporte a NF-e (produto), NFS-e (serviço) e NFC-e (consumidor)
- Homologação e produção
- Suporte a todos os municípios do Brasil

### Endpoints principais

```bash
# Emitir NF-e
POST https://api.focusnfe.com.br/v2/nfe

# Consultar status da NF-e
GET https://api.focusnfe.com.br/v2/nfe/{referencia}

# Cancelar NF-e
DELETE https://api.focusnfe.com.br/v2/nfe/{referencia}

# Emitir NFS-e
POST https://api.focusnfe.com.br/v2/nfse
```

### Exemplo de payload NF-e

```json
{
  "natureza_operacao": "Venda de produto",
  "forma_pagamento": "0",
  "emitente": {
    "cnpj": "00000000000000",
    "nome": "Minha Empresa Ltda",
    "logradouro": "Rua Exemplo, 100",
    "municipio": "São Paulo",
    "uf": "SP",
    "cep": "01310100",
    "regime_tributario": "1"
  },
  "destinatario": {
    "cnpj": "11111111000191",
    "nome": "Cliente Exemplo SA",
    "email": "financeiro@cliente.com.br"
  },
  "itens": [
    {
      "numero_item": "1",
      "codigo_produto": "PROD001",
      "descricao": "Produto Exemplo",
      "ncm": "84713012",
      "quantidade_comercial": 1.0,
      "valor_unitario_comercial": 1000.00,
      "valor_bruto": 1000.00,
      "icms_origem": "0",
      "icms_modalidade": "3",
      "pis_modalidade": "07",
      "cofins_modalidade": "07"
    }
  ]
}
```

## Obrigações Acessórias

| Obrigação | Periodicidade | Observação |
|---|---|---|
| **SPED Fiscal** | Mensal | EFD-ICMS/IPI |
| **SPED Contribuições** | Mensal | EFD-PIS/COFINS |
| **SPED Contábil** | Anual | ECD |
| **ECF** | Anual | Escrituração Contábil Fiscal |
| **DCTF** | Mensal | Débitos e Créditos Tributários Federais |
| **DAS (Simples)** | Mensal | Guia única do Simples Nacional |

## Tabela de CNAE e ISS por Município

Para cálculo correto do ISS, é necessário cruzar:
1. CNAE da empresa (atividade)
2. Item da Lista de Serviços (LC 116/2003)
3. Alíquota do município

Repositório de referência para alíquotas: `docs/fiscal/iss_municipios.json` (a ser criado)

## ERPNext Brazil (Módulo OCA)

Repositório: https://github.com/OCA/l10n-brazil

Funcionalidades disponíveis:
- Plano de Contas Brasileiro
- Configuração de impostos (ICMS, PIS, COFINS, ISS)
- Emissão de NF-e integrada
- SPED Fiscal (parcial)
- Boleto Bancário

### Instalação
```bash
bench get-app https://github.com/OCA/l10n-brazil
bench --site mysite.localhost install-app l10n_br_account
```
