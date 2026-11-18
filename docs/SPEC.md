# Especificação técnica

Referências: [PRD](PRD.md) · [Arquitetura](ARCHITECTURE.md) · [TDD](TDD.md) · [Tarefas](TASKS.md)

## 1. Glossário

- **Aplicação** — uma planning application (ou caso do ABP) lida de uma fonte.
- **Rótulo** — par (`energy`, `category`). Completo ⇔ `energy=False ∧ category=None`
  ou `energy=True ∧ category ∈ {hybrid, wind, solar, bess, leu}`.
- **Pendente** — aplicação exibida ao usuário e ainda sem rótulo completo. Só existe em memória.

## 2. Fontes

| `source` | URL base (`/query` acrescentado pelo cliente) | número | descrição | autoridade |
|---|---|---|---|---|
| `abp` | `https://services-eu1.arcgis.com/o56BSnENmD5mYs3j/ArcGIS/rest/services/Cases_2016_Onwards/FeatureServer/3` | `ABPCASEID` | `DEVDESC` | `PLANINGATY` |
| `epl_1` | `https://services.arcgis.com/NzlPQPKn5QF9v2US/ArcGIS/rest/services/IrishPlanningApplications/FeatureServer/1` | `ApplicationNumber` | `DevelopmentDescription` | `PlanningAuthority` |
| `epl_0` | `https://services.arcgis.com/NzlPQPKn5QF9v2US/ArcGIS/rest/services/IrishPlanningApplications/FeatureServer/0` | `ApplicationNumber`* | `DevelopmentDescription`* | `PlanningAuthority`* |

\* Confirmar na tarefa **T00** (que também confirma que o modelo `gemini-decision-1` existe na API Gemini) com `GET <url>?f=json`. Esquema do `abp` verificado em
2026-11-18 (27 310 registros, `maxRecordCount` 2000, `OBJECTID` como OID).
O mapeamento fica num dicionário `FIELD_MAP` em `planlabel/sources/arcgis.py`; nenhum
nome de campo aparece em outro lugar do código.

### 2.1 Chamadas ao ArcGIS

| Uso | Parâmetros de `GET <url>/query` |
|---|---|
| Lista de IDs | `where=1=1&returnIdsOnly=true&f=json` → `{"objectIds":[...]}` |
| Um registro | `objectIds=<id>&outFields=<num>,<desc>,<aut>&returnGeometry=false&f=json` |

- Timeout 15 s; até 3 tentativas com backoff exponencial (0,5 s, 1 s, 2 s) em erro de rede/5xx.
- Resposta com chave `error` (o ArcGIS devolve HTTP 200 com erro no corpo) é tratada como falha.
- Cache da lista de IDs: em memória, TTL 24 h (`PLANLABEL_IDS_TTL_S`).
- Normalização: `strip()` em todos os textos; espaços internos múltiplos colapsados na descrição.

## 3. Banco de dados (SQLite)

```sql
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS labeled_application (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    source              TEXT    NOT NULL CHECK (source IN ('abp','epl_0','epl_1')),
    application_number  TEXT    NOT NULL CHECK (length(trim(application_number)) > 0),
    planning_authority  TEXT    NOT NULL DEFAULT '',
    source_object_id    INTEGER NOT NULL,
    description         TEXT    NOT NULL CHECK (length(trim(description)) > 0),
    energy              INTEGER NOT NULL CHECK (energy IN (0,1)),
    category            TEXT    CHECK (category IN ('hybrid','wind','solar','bess','leu')),
    labeled_at          TEXT    NOT NULL,                 -- ISO-8601 UTC
    -- sugestão do modelo no momento do rótulo (nullable: modelo falhou ou desligado) [RF-19]
    suggested_energy    INTEGER CHECK (suggested_energy IN (0,1)),
    suggested_category  TEXT    CHECK (suggested_category IN ('hybrid','wind','solar','bess','leu')),
    suggestion_model    TEXT,
    CHECK ((energy = 1 AND category IS NOT NULL) OR (energy = 0 AND category IS NULL)),
    CHECK (suggested_energy IS NULL OR
           (suggested_energy = 1 AND suggested_category IS NOT NULL) OR
           (suggested_energy = 0 AND suggested_category IS NULL)),
    UNIQUE (source, planning_authority, application_number)
);
```

- `energy` é exposto como `bool` na API (True/False).
- O banco **rejeita** rótulo incompleto e duplicata mesmo que a camada de aplicação falhe (defesa em profundidade, RF-10).
- Caminho: `PLANLABEL_DB_PATH` (padrão `data/labels.sqlite3`). Schema criado no startup.

### 3.1 Repository (contrato)

```python
class Repository:
    def exists(self, source: str, authority: str, number: str) -> bool: ...
    def save(self, app: Application, label: Label,
             suggestion: Suggestion | None = None) -> int: ...   # levanta DuplicateError
    def counts(self) -> Counts: ...  # total, energy, not_energy, by_category{5 chaves sempre}
```

## 4. Domínio

```python
class Category(StrEnum): HYBRID="hybrid"; WIND="wind"; SOLAR="solar"; BESS="bess"; LEU="leu"

class Application(BaseModel):
    source: Literal["abp","epl_0","epl_1"]
    source_object_id: int
    application_number: str   # não vazio
    planning_authority: str   # pode ser ""
    description: str          # não vazio

class Label(BaseModel):
    energy: bool
    category: Category | None
    # model_validator: energy=True ⇒ category obrigatória; energy=False ⇒ category deve ser None

class Suggestion(BaseModel):
    label: Label              # mesma validação do rótulo humano
    model: str                # ex.: "gemini-decision-1"
```

### 4.1 LabelingService

- `next_application() -> Pending` — sorteia fonte, sorteia ID não visto, busca, valida,
  verifica `exists()`; repete até `MAX_ATTEMPTS = 25`. Fontes com erro são excluídas do
  sorteio daquela chamada. Sem sucesso → `NoApplicationAvailable`.
- `Pending = {token: UUID4, application: Application}`; guardado num dicionário em memória
  (máx. 100 pendentes, os mais antigos são descartados).
- `confirm(token, label) -> Counts` — token desconhecido → `UnknownToken`; revalida
  `exists()` (corrida) → `DuplicateError`; grava; remove o pendente.
- `suggest(token) -> Suggestion | None` — token desconhecido → `UnknownToken`; chama o
  `Suggester` uma vez por token (chamadas repetidas devolvem o valor guardado), guarda o
  resultado no pendente. **Não** escreve no banco.
- `confirm` grava o rótulo do usuário + a sugestão guardada no pendente (se houver).
  Rótulo e sugestão podem divergir; vale sempre o rótulo do usuário.
- `skip(token)` — remove o pendente sem gravar; o ID fica no conjunto "visto nesta execução".
- O sorteio usa `random.Random` injetável (testes determinísticos).

### 4.2 Suggester (`gemini-decision-1`)

```python
class Suggester(Protocol):
    def suggest(self, app: Application) -> Suggestion | None: ...   # nunca levanta: falha ⇒ None
```

- `GeminiSuggester`: `POST https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent`,
  chave no header `x-goog-api-key` (de `GEMINI_API_KEY`), timeout 10 s, sem retry.
- `generationConfig`: `temperature: 0`, `responseMimeType: "application/json"`,
  `responseSchema`:
  `{"type":"OBJECT","properties":{"energy":{"type":"BOOLEAN"},"category":{"type":"STRING","enum":["hybrid","wind","solar","bess","leu"],"nullable":true}},"required":["energy","category"]}`
- Resposta validada com `Label`; qualquer erro (HTTP, JSON, validação) ⇒ `None` + log `WARNING`.
- Cache LRU (256) por `sha256(description)`.
- `NoneSuggester` devolve sempre `None` (padrão quando não há `GEMINI_API_KEY`).

**Prompt (system instruction) — definições [DECIDIR]:**

```
You classify Irish planning application descriptions for an energy dataset.
Return JSON {energy, category}. energy=false ⇒ category=null.
energy=true when the main purpose of the development is one of:
- wind:   wind turbines / wind farm (onshore or offshore), incl. repowering and extensions.
- solar:  solar PV farm or ground-mounted solar array (not rooftop panels on a house or building).
- bess:   battery energy storage system as the main development.
- hybrid: two or more of wind / solar / bess combined in the same application.
- leu:    large energy user — data centre, large industrial facility whose application is
          driven by high electricity demand.
Everything else is energy=false (houses, extensions, rooftop solar on a dwelling,
roads, retail, grid-only works, etc.).
```

O texto da descrição vai na mensagem do usuário, sem outros campos. O prompt fica em
`planlabel/suggester.py` como constante e é coberto por teste de snapshot (G-07).

## 5. API HTTP

Todas as respostas são JSON, exceto `/` (HTML).

| Método e rota | Corpo | Sucesso | Erros |
|---|---|---|---|
| `GET /` | — | `index.html` | — |
| `GET /api/stats` | — | `200 Counts` | — |
| `GET /api/next` | — | `200 {token, application, stats}` | `503 {"detail": "..."}` se nenhuma fonte responder |
| `POST /api/labels` | `{token, energy, category}` | `201 {stats}` | `422` rótulo incompleto/inválido · `404` token desconhecido · `409` duplicado |
| `POST /api/skip` | `{token}` | `204` | `404` token desconhecido |
| `POST /api/suggest` | `{token}` | `200 {"suggestion": {"energy": bool, "category": str\|null, "model": str} \| null}` | `404` token desconhecido |
| `POST /api/translate` | `{text}` (≤ 4000 chars) | `200 {translation}` | `502` tradutor falhou |

`Counts` = `{"total": int, "energy": int, "not_energy": int, "by_category": {"hybrid":int,"wind":int,"solar":int,"bess":int,"leu":int}}`

`application` exibido = `{source, source_label, application_number, planning_authority, description}`.

## 6. Interface

### 6.1 Layout (uma coluna, máx. 720 px, fonte do sistema, sem imagens)

```
Plan Labeler                                  1.284 rotulados · 312 energia
────────────────────────────────────────────────────────────────────────
ABP · Laois County Council · 318799
112 structures associated with uprate of existing line. A Natura …
                                                         [Traduzir]
( ) Energia   ( ) Não energia               sugestão do gemini-decision-1
    ( ) hybrid ( ) wind ( ) solar ( ) bess ( ) leu      ← só se Energia
                                         [Cancelar]  [Confirmar]
```

### 6.2 Estados e regras
- **Carregando** → texto "Buscando…"; botões desabilitados.
- **Sugestão:** após exibir, o frontend chama `/api/suggest`. Enquanto espera: "sugerindo…"
  (as opções continuam clicáveis). Ao chegar, marca as opções sugeridas **somente se o
  usuário ainda não escolheu nada** e mostra o selo "sugestão do gemini-decision-1".
  Se o usuário alterar qualquer opção, o selo muda para "alterado por você". Sem sugestão
  (falha/`null`): selo "sem sugestão" e opções vazias. Resposta que chega depois de o
  usuário passar para outra aplicação é ignorada (comparar token).
- **Confirmar** habilitado somente com rótulo completo (vindo da sugestão ou do usuário);
  nada é gravado sem o clique em Confirmar / `Enter`. Trocar para "Não energia" limpa a categoria.
- **Traduzir** alterna entre original e tradução ("Ver original"); erro de tradução aparece em linha e não bloqueia.
- **Cancelar** → diálogo nativo `<dialog>`: "Encerrar" / "Próxima".
- **Encerrado** → "Sessão encerrada. N registros rotulados." + botão "Recomeçar" (= recarregar).
- **Erro de fonte (503)** → mensagem + "Tentar de novo".
- Contador atualizado com o `stats` da resposta de confirmação (sem chamada extra).

### 6.3 Teclado
`E` energia · `N` não energia · `1–5` categoria (hybrid, wind, solar, bess, leu) · `T` traduzir ·
`Enter` confirmar · `Esc` cancelar.

## 7. Configuração (variáveis de ambiente)

| Variável | Padrão |
|---|---|
| `PLANLABEL_DB_PATH` | `data/labels.sqlite3` |
| `PLANLABEL_TRANSLATOR` | `google` (`google` \| `deepl` \| `claude` \| `none`) |
| `PLANLABEL_SOURCE_WEIGHTING` | `by_size` (`by_size` \| `uniform`) |
| `PLANLABEL_IDS_TTL_S` | `86400` |
| `PLANLABEL_HOST` / `PLANLABEL_PORT` | `127.0.0.1` / `8000` |

| `PLANLABEL_SUGGESTER` | `gemini` se `GEMINI_API_KEY` existir, senão `none` |
| `PLANLABEL_SUGGESTER_MODEL` | `gemini-decision-1` |
| `PLANLABEL_SUGGESTER_TIMEOUT_S` | `10` |

Chaves de API (`GEMINI_API_KEY`, DeepL, Anthropic) apenas via ambiente; nunca no repositório.

## 8. Rastreabilidade requisito → teste

Ver tabela em [TDD.md §4](TDD.md#4-matriz-de-rastreabilidade).
