# Arquitetura — proposta para discussão

**Status:** proposta. Os pontos marcados com **[DECIDIR]** precisam de confirmação do
dono do produto antes de o `GO_PROMPT.md` ser executado.

## 1. Visão geral

```
┌──────────────┐  HTTP/JSON   ┌──────────────────────────── FastAPI (Python) ──────────────────────────┐
│ index.html   │ ───────────► │ api.py ──► LabelingService ──► SourceRegistry ──► ArcGISSource × 3      │──► ArcGIS REST
│ app.js       │ ◄─────────── │                │                                                        │
│ style.css    │              │                ├──► Repository (sqlite3) ──► data/labels.sqlite3        │
│ (vanilla)    │              │                └──► Translator (plugável) ─────────────────────────────│──► serviço de tradução
└──────────────┘              └────────────────────────────────────────────────────────────────────────┘
```

Um processo só (`uvicorn`), que serve a API **e** os arquivos estáticos do frontend.
Executa localmente com `python -m planlabel` (ou `make run`).

## 2. Decisões e alternativas

### 2.1 Backend — **FastAPI + sqlite3 (stdlib)**
- FastAPI dá validação de entrada com Pydantic (a regra "rótulo completo" vira um
  `model_validator`), `TestClient` para testes de API e serve estáticos.
- `sqlite3` da stdlib em vez de ORM: são 1–2 tabelas; menos dependências e SQL explícito
  (as `CHECK`/`UNIQUE` constraints ficam visíveis no schema).
- Alternativa considerada: Flask (equivalente, mas sem validação nativa) e Django (pesado demais).

### 2.2 Frontend — **HTML + CSS + JavaScript puro (sem build)**
- Uma única tela, 3 arquivos estáticos, zero `npm`. Combina com "interface minimalista".
- Alternativas: HTMX (bom, mas adiciona um paradigma para pouco ganho) e React/Vue
  (exagero para uma tela). **[DECIDIR]** Se preferir HTMX + Jinja2, a API muda pouco.

### 2.3 Banco — **SQLite**
Suficiente: um usuário, escrita sequencial, alguns milhares de linhas. O arquivo é o
próprio dataset (`data/labels.sqlite3`). Modo WAL ligado. Concordo com a sua avaliação.

### 2.4 Como buscar "um dado de cada vez" sem repetir
O ArcGIS permite pedir **só os IDs** de uma camada (`returnIdsOnly=true`; testado no ABP:
27 310 IDs numa resposta). Estratégia:

1. Na primeira necessidade, cada fonte baixa e guarda **em memória** a lista de
   `OBJECTID`s (cache com TTL de 24 h).
2. Para servir um registro: sorteia a fonte (peso proporcional ao nº de IDs **[DECIDIR]**:
   ou uniforme entre as três fontes), sorteia um `OBJECTID`, busca **só esse** registro
   (`objectIds=<id>&outFields=...&returnGeometry=false`).
3. Valida (número e descrição não vazios) e checa no banco pela chave natural
   (`source`, `planning_authority`, `application_number`). Se já existir ou for inválido,
   marca o ID como "visto nesta execução" e repete (até N = 25 tentativas).

Vantagens: uma requisição pequena por registro, aleatoriedade real, nada gravado antes
do rótulo. Alternativa rejeitada: paginar por offset (custa mais e enviesa para os
registros antigos).

### 2.5 O que acontece com o registro em exibição?
Fica **no servidor, em memória**, numa "sessão de rotulagem" identificada por um
`token` (UUID) devolvido ao frontend. O `POST /api/labels` envia o `token` + rótulo; o
servidor grava os dados **que ele mesmo buscou** — o cliente não consegue alterar número,
fonte ou descrição. Pendências não vão para o banco (RF-10).

### 2.6 Tradução — interface `Translator` plugável **[DECIDIR]**
| Opção | Custo | Qualidade | Observação |
|---|---|---|---|
| `deep-translator` (Google Translate não oficial) | grátis | boa | sem chave; pode sofrer limite de uso |
| DeepL API Free | grátis até 500 mil caracteres/mês | muito boa | precisa de chave |
| Claude API (`claude-haiku-5-5`) | baixo | muito boa, entende jargão de planning | precisa de chave |

Proposta: padrão `deep-translator`, configurável por `PLANLABEL_TRANSLATOR`. Traduções
são cacheadas em memória (LRU) e **não** são gravadas no dataset.

### 2.7 Esquema de dados — campos além dos pedidos **[DECIDIR]**
O pedido lista: número, fonte, descrição, energia, categoria. Proponho acrescentar:
- `planning_authority` — **necessário**: `ApplicationNumber` se repete entre conselhos.
- `source_object_id` — rastreabilidade até o registro original.
- `labeled_at` (UTC) — auditoria e divisão treino/validação por tempo.

### 2.8 Interpretação do "Cancelar"
Leitura adotada: Cancelar → diálogo **Encerrar | Próxima**. "Próxima" pula o registro
(sem gravar); "Encerrar" termina a sessão e mostra a tela final. Registros pulados podem
reaparecer numa execução futura (não são gravados, por RF-10). **[DECIDIR]** Se quiser
que pulados nunca voltem, é preciso uma tabela separada `skipped`, fora do dataset.

## 3. Estrutura de pastas

```
planlabel/
  __init__.py  __main__.py   # python -m planlabel
  config.py                  # Settings via env (PLANLABEL_*)
  models.py                  # Application, Label, Category (Enum) — Pydantic
  sources/
    base.py                  # Protocol Source
    arcgis.py                # ArcGISSource (httpx) + mapeamento de campos
    registry.py              # sorteio entre fontes, fallback
  repository.py              # sqlite3: schema, exists(), save(), counts()
  translator.py              # Protocol Translator + implementações
  service.py                 # LabelingService (regras de negócio)
  api.py                     # FastAPI app + rotas
  static/ index.html app.js style.css
tests/
  unit/ integration/ e2e/ fixtures/
data/                        # labels.sqlite3 (gitignored)
```

## 4. Dependências

Runtime: `fastapi`, `uvicorn`, `httpx`, `pydantic-settings`, `deep-translator`.
Dev: `pytest`, `pytest-cov`, `respx`, `playwright`, `ruff`.
