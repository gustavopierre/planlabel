# TDD — estratégia e catálogo de testes

## 1. Regras do ciclo

1. **Red**: escrever o teste da tarefa (IDs abaixo) e vê-lo falhar pelo motivo certo.
2. **Green**: o mínimo de código para passar.
3. **Refactor**: limpar com a suíte verde.
4. Commit por ciclo concluído: `test: <ID>` + `feat: <ID>` (ou um só commit com ambos).
5. Nenhum teste de unidade/integração toca a rede real: HTTP é simulado com `respx`;
   tradutor é um fake. Testes contra a rede real ficam em `tests/live/`, marcados
   `@pytest.mark.live` e **fora** da suíte padrão.

## 2. Ferramentas

`pytest` · `pytest-cov` (mín. 90 % em `planlabel/`) · `respx` (mock do `httpx`) ·
`fastapi.testclient` · `playwright` (e2e, Chromium headless) · `ruff` (lint + format).

Fixtures-chave (`tests/conftest.py`):
- `tmp_db` — `Repository` num arquivo SQLite em `tmp_path`.
- `fake_sources` — fontes em memória com registros controlados (`FakeSource`).
- `rng` — `random.Random(42)`.
- `client` — `TestClient` com app montado via `create_app(settings, sources, translator, rng)`.
- `arcgis_fixtures/` — JSONs reais gravados (`abp_ids.json`, `abp_one.json`, `arcgis_error.json`, `epl_*`).

## 3. Catálogo de testes

### 3.1 Domínio (`tests/unit/test_models.py`)
| ID | Caso |
|---|---|
| M-01 | `Label(energy=False, category=None)` é válido |
| M-02 | `Label(energy=True, category="wind")` é válido para cada uma das 5 categorias |
| M-03 | `Label(energy=True, category=None)` → `ValidationError` |
| M-04 | `Label(energy=False, category="solar")` → `ValidationError` |
| M-05 | categoria fora da lista (`"hydro"`) → `ValidationError` |
| M-06 | `Application` com número ou descrição vazio/só espaços → `ValidationError` |

### 3.2 Repository (`tests/unit/test_repository.py`)
| ID | Caso |
|---|---|
| R-01 | schema criado em banco novo; reabrir não falha (idempotente) |
| R-02 | `save` + `exists` → True; outra autoridade com mesmo número → False |
| R-03 | `save` duplicado → `DuplicateError`; total continua 1 |
| R-04 | INSERT SQL direto com `energy=1, category NULL` → `sqlite3.IntegrityError` (constraint) |
| R-05 | INSERT SQL direto com `energy=0, category='wind'` → `IntegrityError` |
| R-06 | `counts()` em banco vazio → zeros e as 5 categorias presentes |
| R-07 | `counts()` com dados mistos → total, energy, not_energy e by_category corretos |
| R-08 | `labeled_at` gravado em ISO-8601 UTC |

### 3.3 ArcGISSource (`tests/unit/test_arcgis_source.py`, com `respx`)
| ID | Caso |
|---|---|
| A-01 | `list_ids()` lê `objectIds` da resposta |
| A-02 | `list_ids()` usa cache dentro do TTL (1 chamada HTTP para 2 invocações) e recarrega após o TTL (relógio injetado) |
| A-03 | `fetch(id)` monta a query correta (`objectIds`, `outFields`, `returnGeometry=false`) |
| A-04 | `fetch(id)` mapeia campos por fonte (`abp`: ABPCASEID/DEVDESC/PLANINGATY; `epl_*`: ApplicationNumber/…) |
| A-05 | normaliza texto (strip, colapsa espaços) |
| A-06 | `fetch` de registro sem descrição → `None` (inválido) |
| A-07 | corpo `{"error": ...}` com HTTP 200 → `SourceError` |
| A-08 | 503 duas vezes e 200 na terceira → sucesso (retry); 4 falhas → `SourceError` |
| A-09 | timeout → `SourceError` |

### 3.4 LabelingService (`tests/unit/test_service.py`, com `FakeSource`)
| ID | Caso |
|---|---|
| S-01 | `next_application` devolve token + aplicação válida |
| S-02 | aplicação já no banco é **descartada**; retorna outra |
| S-03 | registro inválido é pulado |
| S-04 | todas as aplicações já existem/ inválidas → `NoApplicationAvailable` após `MAX_ATTEMPTS` |
| S-05 | uma fonte com `SourceError` → usa as outras |
| S-06 | todas as fontes com erro → `NoApplicationAvailable` |
| S-07 | `confirm` grava exatamente os dados buscados + rótulo; remove o pendente |
| S-08 | `confirm` com token desconhecido → `UnknownToken`; nada gravado |
| S-09 | `confirm` quando outra sessão já gravou a mesma aplicação → `DuplicateError` |
| S-10 | `skip` não grava nada; o ID não é oferecido de novo na mesma execução |
| S-11 | **nenhuma** escrita no banco ocorre em `next_application` nem em `skip` (spy no repository) |
| S-12 | sorteio `by_size` e `uniform` respeitam pesos (distribuição em 10 000 sorteios com `rng` fixo, tolerância 3 %) |
| S-13 | limite de 100 pendentes: o mais antigo é descartado |

### 3.5 Tradutor (`tests/unit/test_translator.py`)
| ID | Caso |
|---|---|
| T-01 | `NoneTranslator` devolve o texto original |
| T-02 | cache: mesma entrada → backend chamado 1 vez |
| T-03 | falha do backend → `TranslationError` |
| T-04 | fábrica escolhe a implementação por `PLANLABEL_TRANSLATOR` |

### 3.6 API (`tests/integration/test_api.py`)
| ID | Caso |
|---|---|
| I-01 | `GET /` → 200 HTML contendo `id="app"` |
| I-02 | `GET /api/stats` → formato `Counts` |
| I-03 | `GET /api/next` → 200 com `token`, `application`, `stats` |
| I-04 | `POST /api/labels` válido (não energia) → 201; `stats.total` +1; `stats.not_energy` +1 |
| I-05 | `POST /api/labels` válido (energia/bess) → 201; `by_category.bess` +1 |
| I-06 | `energy=true` sem categoria → 422; banco inalterado |
| I-07 | `energy=false` com categoria → 422; banco inalterado |
| I-08 | token desconhecido → 404 |
| I-09 | mesmo token confirmado duas vezes → segunda 404; total +1 só |
| I-10 | `POST /api/skip` → 204; depois `labels` com o mesmo token → 404; banco inalterado |
| I-11 | fontes todas fora → `GET /api/next` 503 com `detail` |
| I-12 | `POST /api/translate` → 200; tradutor falhando → 502 |
| I-13 | registro gravado contém `source`, `application_number`, `description`, `energy`, `category` iguais aos exibidos |
| I-14 | após gravar uma aplicação, 50 chamadas a `/api/next` nunca a retornam |

### 3.7 E2E (`tests/e2e/test_ui.py`, Playwright, servidor com fontes fake)
| ID | Caso |
|---|---|
| E-01 | abrir → mostra número, fonte, descrição e contador "0 rotulados" |
| E-02 | Confirmar desabilitado até escolher; "Energia" sem categoria mantém desabilitado |
| E-03 | Energia + wind + Confirmar → contador vai a 1 e outra aplicação aparece |
| E-04 | trocar Energia→Não energia esconde e limpa categorias |
| E-05 | Traduzir mostra texto PT; "Ver original" volta |
| E-06 | Cancelar → Próxima → nova aplicação; contador inalterado |
| E-07 | Cancelar → Encerrar → tela final; banco inalterado |
| E-08 | atalhos de teclado `N` + `Enter` gravam não energia |
| E-09 | recarregar a página → nova aplicação, contador persiste |
| E-10 | erro 503 → mensagem + "Tentar de novo" funciona |

### 3.8 Live (`tests/live/`, opcional, `pytest -m live`)
| ID | Caso |
|---|---|
| L-01 | cada uma das 3 fontes responde `?f=json` e contém os campos do `FIELD_MAP` |
| L-02 | `list_ids()` e `fetch()` reais devolvem uma `Application` válida por fonte |

## 4. Matriz de rastreabilidade

| Requisito | Testes |
|---|---|
| RF-01 | S-01, S-12, A-03 |
| RF-02 / RF-03 | S-02, I-14, R-02 |
| RF-04 | M-06, A-06, S-03 |
| RF-05 | I-03, E-01 |
| RF-06 | T-01..04, I-12, E-05 |
| RF-07 / RF-08 | M-01..05, I-06, I-07, E-02, E-04 |
| RF-09 | S-07, I-04, I-05, I-13 |
| RF-10 | R-04, R-05, S-11, I-06, I-07, I-10, E-07 |
| RF-11 | S-10, I-10, E-06, E-07 |
| RF-12 | E-09 |
| RF-13 | R-06, R-07, I-02, I-04, I-05, E-03 |
| RF-14 | A-07..09, S-05, S-06, I-11, E-10 |
| RNF-03 | E-08 |
| RNF-04 | cobertura no CI (`--cov-fail-under=90`) |

## 5. Comandos

```bash
pytest                                   # unit + integration + e2e (sem rede)
pytest --cov=planlabel --cov-fail-under=90
pytest -m live                           # contra as fontes reais
ruff check . && ruff format --check .
```
