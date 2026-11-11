# Conciliação Inteligente

Aplicação web para conciliação financeira automática entre quatro fontes: **sistema financeiro/ERP**, **extrato bancário**, **máquina de cartão** e **adquirente/liquidação**. O usuário carrega os arquivos, clica em **Processar conciliação** e recebe o dashboard, as divergências e os relatórios.

- Frontend: Next.js 15 + TypeScript + Tailwind CSS (pt-BR, BRL, DD/MM/AAAA)
- Backend: Python 3.12 + FastAPI + SQLAlchemy 2
- Banco: PostgreSQL (migrations Alembic)
- Deploy: Vercel (Next.js + função Python em `api/index.py`)

## Funcionalidades

| Área | O que faz |
|---|---|
| Upload | 4 áreas com arrastar e soltar; XLSX, XLS, CSV, OFX, TXT e PDF tabular; validação por conteúdo (assinatura binária), não pela extensão; limite de 10 MB |
| Leitura | OFX SGML 1.02 e XML 2.x (inclusive Windows-1252); CSV com preâmbulo, `;`/`,`/tab, campos multilinha; detecção automática de cabeçalho e colunas por sinônimos |
| Mapeamento | Quando as colunas obrigatórias não são reconhecidas, abre a tela de mapeamento manual; o modelo pode ser salvo e é reaplicado automaticamente pelo layout do cabeçalho |
| Motor | 5 níveis determinísticos (abaixo). Nunca concilia de forma ambígua: casos com mais de um candidato vão para análise manual |
| Resultado | 10 status por transação, com nível, regra, confiança e justificativa |
| Análise | Busca (nome, NSU, código, valor), filtros (data, origem, status), ordenação, detalhe com lançamentos relacionados, aprovação/rejeição de sugestões, observações |
| Relatórios | Excel com abas por status e trilha de vínculos, CSV, PDF executivo, PDF de divergências, resumo financeiro |
| Histórico | Cada processamento gravado com código, período, arquivos (hash SHA-256), totais e responsável; alerta de reprocessamento dos mesmos arquivos; versões |
| Configurações | Tolerâncias, regras, taxas por operadora/bandeira/modalidade/parcelas, bandeiras, descritores de adquirente no extrato, contas, modelos de importação, usuários, auditoria |
| Segurança | JWT + bcrypt, papéis admin/analista, isolamento por empresa, log de auditoria, cartões e contas mascarados, CPF removido de descrições, arquivos originais não armazenados |

### Níveis de correspondência

1. **Identificador único**: NSU, ID da venda/RRN, autorização (+data+bandeira), FITID/documento, ordem de pagamento.
2. **Valor e data exatos**, com unicidade mútua; empate desfeito pelo nome do favorecido/pagador quando existe um único melhor.
3. **Valor com tolerância de data** (configurável): gera *Divergência de data*.
4. **Valores agrupados**: soma das liquidações por data + bandeira + modalidade = um crédito no banco; N↔M; subconjunto **único** de lançamentos que soma o valor (busca exata em centavos).
5. **Valor líquido**: bruto − taxa esperada (configurada) = crédito no banco.

Divergências de valor (juros, multa, desconto, pagamento parcial) são apenas **sugeridas** e exigem aprovação. Taxas cobradas diferentes da tabela geram *Taxa divergente*. Estornos/cancelamentos abatidos na liquidação ficam como *Estorno/cancelamento*.

Todo cálculo usa `Decimal` (centavos exatos). Nenhuma IA é usada para criar ou confirmar conciliações.

## Validação com os arquivos reais (Sicoob/SIPAG, novembro/2026)

| Arquivo | Leitura |
|---|---|
| OFX Sicoob (SGML 1.02, CHARSET 1252) | 113 lançamentos, 01/11 a 11/11, total −R$ 3.037,05 |
| XLSX do mesmo extrato | 113 lançamentos (linhas "SALDO DO DIA" ignoradas), mesmos valores |
| Lançamentos financeiros (CSV Latin-1, `;`, multilinha) | 16 despesas |
| Relatório de vendas recebidas SIPAG (CSV com preâmbulo) | 71 parcelas (70 vendas + 1 estorno), líquido R$ 19.568,65 |

Resultado: 70 de 70 recebimentos de cartão conciliados (14 créditos agrupados por dia/bandeira/modalidade e 10 diretos), com o estorno de R$ 99,90 abatido no crédito Maestro de 05/11. Taxas conferidas: débito 1,59%, crédito à vista 1,79%, parcelado 2,29% e Elo parcelado 3,19%. No ERP, 12 despesas foram conciliadas, 1 com divergência de data (D+1). Ficaram 2 divergências de valor sugeridas (R$ 1,16 e R$ 0,97) e 1 pagamento futuro como pendente. Seis créditos SIPAG no banco não têm venda no relatório da adquirente (R$ 216,63, 759,97, 261,55, 420,07, 374,34 e 848,59). Verifique se há outro estabelecimento/terminal ou ampliar o período do relatório.

> O arquivo da **máquina de cartão** não foi fornecido. O suporte é genérico (detecção de NSU, autorização, bandeira, tipo, parcelas, valor, status) e há um exemplo fictício em `public/demo/`.

## Executar localmente

Pré-requisitos: Python 3.12+, Node 20+, PostgreSQL 14+ (ou omita `DATABASE_URL` para usar SQLite só em testes).

```bash
cp .env.example .env               # ajuste DATABASE_URL e JWT_SECRET
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
cd backend && alembic upgrade head && cd ..
npm install
npm run dev                        # API em :8000 e web em :3000
```

Acesse http://localhost:3000, crie a conta da empresa e use os arquivos de `public/demo/` (também disponíveis em Relatórios → Arquivos de demonstração).

## Testes

```bash
cd backend
pytest -q                                   # parsers, motor e ponta a ponta (upload → relatório)
SAMPLES_DIR=/caminho/arquivos_reais pytest -q tests/test_real_samples.py
DATABASE_URL=postgresql://... pytest -q     # mesmo conjunto em PostgreSQL
```

Os dados de demonstração são regenerados com `python scripts/gerar_demo.py`.

## Deploy no Vercel

1. Importe o repositório no Vercel (framework detectado: Next.js; `api/index.py` vira função Python).
2. Em **Storage**, adicione um banco **Neon (Postgres)** ao projeto. Isso cria `DATABASE_URL`.
3. Opcional: em **Settings → Environment Variables**, defina `JWT_SECRET` (senão a aplicação gera um aleatório e guarda no banco) e `ALLOW_REGISTRATION=false` para bloquear novos cadastros.
4. Faça o deploy. As tabelas são criadas no primeiro acesso (`AUTO_CREATE_TABLES=true`). Para controle por migrations, rode `alembic upgrade head` com a `DATABASE_URL` de produção e defina `AUTO_CREATE_TABLES=false`.

Limites do Vercel: corpo da requisição de até 4,5 MB por arquivo e 60 s por processamento (configurado em `vercel.json`).

## Estrutura

```
api/index.py                 entrada da função Python no Vercel
backend/app/
  parsers/                   common (valores, datas, codificação), ofx, tabular (CSV/XLSX/XLS/PDF), mapping
  engine/                    matcher (5 níveis, status, justificativas), summary (indicadores)
  reports/exporters.py       XLSX, CSV, PDF executivo e de divergências
  routers/                   auth, files, reconciliations, settings
  models.py, security.py, defaults.py, main.py
backend/migrations/          Alembic
backend/tests/               pytest
app/, components/, lib/      frontend Next.js
public/demo/                 arquivos FICTÍCIOS de demonstração
scripts/gerar_demo.py        gerador dos dados de demonstração
```

## Decisões técnicas

- **Sem pandas no processamento**: os valores são lidos e somados como `Decimal`, evitando erros de ponto flutuante (por exemplo, 0,1 + 0,2), e o pacote da função serverless fica menor. A leitura usa `csv`, `openpyxl`, `xlrd` e `pdfplumber`.
- **Arquivos originais não são armazenados**: só os registros normalizados ficam temporariamente até o processamento. Depois ficam as transações conciliadas e o hash SHA-256 de cada arquivo (usado para detectar reprocessamento).
- **Período da conciliação** vem do extrato (DTSTART/DTEND do OFX ou datas mín./máx.). Liquidações e pagamentos posteriores viram *Pendente de liquidação*.
