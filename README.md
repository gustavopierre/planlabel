# Plan Labeler — dados rotulados de Planning Applications da Irlanda

Web app minimalista para rotular, uma por vez, planning applications irlandesas
(An Bord Pleanála e ePlanning/LGMA) por **categoria** (energia / não energia) e
**subcategoria** (hybrid, wind, solar, bess, hydro, substation, energy support, leu,
data centre, não energia, baixa energia). Dois modelos de decisão — `gemini-decision-1` e
`typesafe/jev-1.14` — mostram o percentual de cada opção; o botão **Dúvida** pede a opinião
do `gemini-3.5-flash-lite`. **A decisão final é sempre do usuário**, e nada é gravado sem
a confirmação dele. O resultado (SQLite) alimenta treino e fine-tuning de modelos de IA.

**Status:** MVP implementado e testado no branch `develop` (VPS 2). Deploy de teste em
`https://planlabel-test.bundoran.tech` (VPS 3) preparado, aguardando a credencial OAuth do
Google — ver [runbook deploy-vps3](docs/runbooks/deploy-vps3.md).

## Instalar

Requer Python 3.12+ e [`uv`](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/gustavopierre/planlabel.git && cd planlabel
uv venv --python 3.12 && source .venv/bin/activate
uv pip install -e ".[dev]"
playwright install --with-deps chromium   # só para os testes E2E
```

## Configurar (`.env`)

Crie `.env` na raiz (já está no `.gitignore`), com `chmod 600`. Sem aspas e sem espaços em
volta do `=`. Modelo: [`.env.example`](.env.example).

```dotenv
GEMINI_API_KEY=<chave do Google AI Studio>
OPENROUTER_API_KEY=<chave do OpenRouter>
PLANLABEL_MODEL1_PROVIDER=gemini
PLANLABEL_MODEL1_ID=gemini-decision-1
PLANLABEL_MODEL2_PROVIDER=openrouter
PLANLABEL_MODEL2_ID=typesafe/jev-1.14
PLANLABEL_ADVISOR_ID=gemini-3.5-flash-lite
```

Os cinco `PLANLABEL_MODEL*`/`PLANLABEL_ADVISOR_ID` são **obrigatórios** (o app não sobe sem
eles e diz qual falta). Sem uma chave, o modelo correspondente só fica "sem sugestão" e o
app continua funcionando.

| Variável opcional | Padrão | Para quê |
|---|---|---|
| `PLANLABEL_DB_PATH` | `data/labels.sqlite3` | arquivo do dataset |
| `PLANLABEL_HOST` / `PLANLABEL_PORT` | `127.0.0.1` / `8000` | onde o app escuta |
| `PLANLABEL_TRANSLATOR` | `google,mymemory` | tradutores tentados em ordem (`none` desliga) |
| `PLANLABEL_MODEL1_RPM` / `_RPD` | `200` / `10000` | limites do `gemini-decision-1` (free tier) |
| `PLANLABEL_MODEL2_RPM` / `_RPD` | `0` / `0` | limites do jev (`0` = só contar) |
| `PLANLABEL_ADVISOR_RPM` / `_TPM` / `_RPD` | `15` / `25000` / `1000` | limites do botão Dúvida |
| `PLANLABEL_DECIDER_TIMEOUT_S` | `10` | tempo máximo de cada modelo decisor |
| `PLANLABEL_IDS_TTL_S` | `86400` | cache da lista de IDs das fontes |

Lista completa e regras: [SPEC §7](docs/SPEC.md#7-configuração-variáveis-de-ambiente).

## Rodar

```bash
python -m planlabel
```

O app fica em `http://127.0.0.1:8000` (sem login: **não** abra a porta no firewall). Para
usar a partir do seu PC, abra um túnel SSH e acesse `http://localhost:8000`:

```bash
ssh -L 8000:127.0.0.1:8000 dev-vps
```

Teclado: `E`/`N` categoria · `1`–`9` subcategoria · `D` dúvida · `T` traduzir ·
`Enter` confirmar · `Esc` cancelar.

**Verificado em 2026-11-19 (VPS 2):** `GET /api/next` trouxe aplicações reais do ABP
(Wicklow 302000) e do ePlanning (Meath 21209), alternando; os dois modelos responderam; a
tradução funcionou pela reserva MyMemory (o Google Translate não oficial bloqueia o IP da VPS).

## Testar

```bash
pytest                                      # unit + integração + E2E (sem rede)
pytest --cov=planlabel --cov-fail-under=90  # cobertura (95 % e 190 testes em 2026-11-19)
pytest -m live                              # contra as fontes e os modelos reais (gasta cota)
ruff check . && ruff format --check .
```

Os IDs dos testes (`test_R04_...`) seguem o catálogo do [TDD](docs/TDD.md).

## Exportar o dataset

O banco é um arquivo SQLite. Cada linha é um rótulo confirmado pelo usuário, com a decisão
de cada modelo no momento do rótulo (`m1_*`, `m2_*`). Exemplo de exportação para CSV
(precisa do cliente `sqlite3`: `sudo apt install -y sqlite3`):

```bash
sqlite3 -header -csv data/labels.sqlite3 "
SELECT source, source_layer, planning_authority, application_number, application_url,
       description, category, subcategory, labeled_at,
       m1_model,
       json_extract(m1_decision, '$.category')        AS m1_category,
       json_extract(m1_decision, '$.category_pct')    AS m1_category_pct,
       json_extract(m1_decision, '$.subcategory')     AS m1_subcategory,
       json_extract(m1_decision, '$.subcategory_pct') AS m1_subcategory_pct,
       m2_model,
       json_extract(m2_decision, '$.category')        AS m2_category,
       json_extract(m2_decision, '$.category_pct')    AS m2_category_pct,
       json_extract(m2_decision, '$.subcategory')     AS m2_subcategory,
       json_extract(m2_decision, '$.subcategory_pct') AS m2_subcategory_pct
FROM labeled_application ORDER BY id;" > dataset.csv
```

Concordância de cada modelo com o rótulo humano:

```sql
SELECT m1_model,
       AVG(json_extract(m1_decision, '$.subcategory') = subcategory) AS acerto_subcategoria,
       AVG(json_extract(m1_decision, '$.category') = category)       AS acerto_categoria
FROM labeled_application WHERE m1_decision IS NOT NULL GROUP BY m1_model;
```

## Documentação

| Documento | Conteúdo |
|---|---|
| [docs/HANDOFF.md](docs/HANDOFF.md) | **comece aqui** — estado atual, decisões, pendências |
| [docs/PRD.md](docs/PRD.md) | problema, fluxo, histórias de usuário, requisitos (RF/RNF) |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | arquitetura e decisões |
| [docs/SPEC.md](docs/SPEC.md) | taxonomia, fontes, schema SQLite, modelos, API, interface (normativa) |
| [docs/TDD.md](docs/TDD.md) | catálogo de testes, rastreabilidade, definição de pronto |
| [docs/TASKS.md](docs/TASKS.md) | tarefas T00–T12 |
| [docs/runbooks/](docs/runbooks/README.md) | procedimentos operacionais passo a passo |
| [GO_PROMPT.md](GO_PROMPT.md) | prompt de execução com critério de conclusão |
| [LEIA_ME_memoria_no_drive.md](LEIA_ME_memoria_no_drive.md) | onde está a memória das conversas |
