# TDD — estratégia e catálogo de testes

## 1. Regras do ciclo

1. **Red**: escrever o teste da tarefa (IDs abaixo) e vê-lo falhar pelo motivo certo.
2. **Green**: o mínimo de código para passar.
3. **Refactor**: limpar com a suíte verde.
4. Commit por ciclo concluído: `test: <ID>` + `feat: <ID>` (ou um só commit com ambos).
5. Nenhum teste de unidade/integração toca a rede real: HTTP é simulado com `respx`;
   tradutor, decisores e conselheiro são fakes. Testes contra a rede real ficam em `tests/live/`,
   marcados `@pytest.mark.live` e **fora** da suíte padrão.

## 2. Ferramentas

`pytest` · `pytest-cov` (mín. 90 % em `planlabel/`) · `respx` (mock do `httpx`) ·
`fastapi.testclient` · `playwright` (e2e, Chromium headless) · `ruff` (lint + format).

Fixtures-chave (`tests/conftest.py`):
- `tmp_db` — `Repository` num arquivo SQLite em `tmp_path`.
- `fake_sources` — fontes em memória com registros controlados (`FakeSource`).
- `rng` — `random.Random(42)`.
- `clock` — relógio controlável (avança minutos, cruza a meia-noite do Pacífico).
- `fake_deciders` — `FakeDecider` por slot com respostas programáveis (decisão, falha, lento).
- `fake_advisor` — `FakeAdvisor` com opinião, bloqueio (`rpm`/`tpm`/`rpd`) e falha programáveis.
- `client` — `TestClient` com app montado via
  `create_app(settings, sources, translator, deciders, advisor, rng, clock)`.
- `arcgis_fixtures/` — JSONs reais gravados (`abp_ids.json`, `abp_one.json`, `arcgis_error.json`, `epl_*`).
- `gemini_fixtures/` — respostas `generateContent` reais/gravadas (decisão válida, JSON inválido,
  distribuição incompleta, 429, 500, opinião do conselheiro com `usageMetadata`).
- `openrouter_fixtures/` — respostas `chat/completions` do jev (válida, `error` no corpo, 429).

## 3. Catálogo de testes

### 3.1 Domínio (`tests/unit/test_models.py`)
| ID | Caso |
|---|---|
| M-01 | `Label(category, subcategory)` é válido para cada uma das 11 subcategorias com a sua categoria (9 com `energy`, 2 com `not_energy`) |
| M-02 | subcategoria ou categoria fora da lista (`"nuclear"`) ou ausente → `ValidationError` |
| M-03 | rótulo humano incoerente (`energy` + `low_energy`, `not_energy` + `wind`) → `ValidationError` |
| M-04 | `Decision` com duas distribuições válidas: `subcategory`/`subcategory_pct` = maior das 11, `category`/`category_pct` = maior das 2, cada uma da sua distribuição; `stored()` devolve o JSON com essas quatro chaves |
| M-05 | probabilidades (soma 0,98–1,02) → percentuais inteiros que somam 100 (maior resto); soma fora da faixa, chave faltando, chave extra, valor < 0 ou > 1 → `ValidationError` |
| M-06 | `Application` com número ou descrição vazio/só espaços → `ValidationError`; `application_url` não vazio sem `https://` → `ValidationError` |
| M-07 | a escolha é o `choice` da API, mesmo quando o arredondamento empata percentuais |
| M-08 | decisão contraditória (wind 60 %, `not_energy` 55 %) é **válida**, com `consistent=False` e as duas escolhas preservadas |

### 3.2 Repository (`tests/unit/test_repository.py`)
| ID | Caso |
|---|---|
| R-01 | schema criado em banco novo; reabrir não falha (idempotente) |
| R-02 | `save` + `exists` → True; outra autoridade com mesmo número → False; mesma fonte `eplanning` com outra camada (`epl_1`) e mesmo conselho + número → `exists` True e `save` → `DuplicateError` |
| R-03 | `save` duplicado → `DuplicateError`; total continua 1 |
| R-04 | INSERT SQL direto com `category='energy', subcategory='low_energy'` → `sqlite3.IntegrityError` |
| R-05 | INSERT SQL direto com `category='not_energy', subcategory='wind'` ou `subcategory='nuclear'` → `IntegrityError` |
| R-06 | `counts()` em banco vazio → zeros e as 11 subcategorias presentes |
| R-07 | `counts()` com dados mistos → total, energy, not_energy e by_subcategory corretos |
| R-08 | `labeled_at` gravado em ISO-8601 UTC |
| R-09 | `save` com dois `SlotResult` grava `m1_model`/`m1_decision` e `m2_model`/`m2_decision` (JSON com `category`, `category_pct`, `subcategory`, `subcategory_pct`, legível com `json_extract`); decisão contraditória é gravada como veio; slot sem decisão grava o nome do modelo em `mN_model` e `mN_decision` NULL; `application_url` gravado |
| R-10 | INSERT direto com `m1_model` ou `m2_model` NULL/vazio, ou `m1_decision` que não é JSON válido → `IntegrityError`; `mN_decision` NULL e JSON contraditório são aceitos |
| R-11 | `add_usage` 3× (com tokens) → `usage` = 3 requisições e soma dos tokens; outro dia ou outro modelo → zeros; reabrir o banco mantém os valores |

### 3.3 ArcGISSource (`tests/unit/test_arcgis_source.py`, com `respx`)
| ID | Caso |
|---|---|
| A-01 | `list_ids()` lê `objectIds` da resposta; com `exceededTransferLimit: true` pede a próxima página com `OBJECTID > maior ID` até acabar (400 000 + 112 860 → 512 860) |
| A-02 | `list_ids()` usa cache dentro do TTL (1 chamada HTTP para 2 invocações) e recarrega após o TTL (relógio injetado) |
| A-03 | `fetch(id)` monta a query correta (`objectIds`, `outFields`, `returnGeometry=false`) |
| A-04 | `fetch(id)` mapeia campos por fonte (`abp`: ABPCASEID/DEVDESC/PLANINGATY; `epl_*`: ApplicationNumber/…) |
| A-05 | normaliza texto (strip, colapsa espaços) |
| A-06 | `fetch` de registro sem descrição → `None` (inválido) |
| A-10 | `fetch` preenche `application_url` com `LINKABPWEB`/`LinkAppDetails`; link vazio → `''`; `http://` é aceito; `outFields` nunca contém campos `Applicant*` |
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
| S-11 | **nenhuma** escrita em `labeled_application` ocorre em `next_application` nem em `skip` (spy no repository) |
| S-12 | rotação de fontes: 6 chamadas seguidas (de tokens/sessões diferentes) servem `abp, eplanning, abp, eplanning, abp, eplanning`; fonte com `SourceError` ou sem registro novo em 10 tentativas é pulada e a rotação segue; chamadas concorrentes (threads) não repetem nem pulam posição |
| S-13 | limite de 100 pendentes: o mais antigo é descartado |

### 3.4.1 Decisor do slot 1 — `GeminiDecider` (`tests/unit/test_decider_gemini.py`, com `respx`)
| ID | Caso |
|---|---|
| G-01 | requisição `POST .../v1beta/decisions` com header `x-goog-api-key`, `model: "gemini-decision-1"`, a descrição em `input` e as perguntas `subcategory` (choice, 11 opções) e `category` (choice, 2 opções) |
| G-02 | resposta real gravada (`decision_wind_valid.json`) → `Decision(model="gemini-decision-1", subcategory=wind, subcategory_pct=99, category=energy, category_pct=100, consistent=True)`; os 11 percentuais somam 100 |
| G-03 | resposta contraditória (subcategory `wind`, category `not_energy`) → `Decision` válida com `consistent=False` (não vira erro) |
| G-04 | resposta sem uma das perguntas, opção desconhecida, probabilidades que não somam ~1, HTTP 400 de segurança → `decision=None`, `reason="error"` (não levanta) |
| G-05 | HTTP 429 → `reason="rate_limited"`; 500 e timeout → `reason="error"`; sem retry (1 chamada só) |
| G-06 | cache: mesma descrição → 1 chamada HTTP |
| G-07 | snapshot das perguntas compartilhadas pelos dois decisores (mudança exige atualizar o snapshot conscientemente); as perguntas contêm as 11 subcategorias e 2 categorias do §1.1 e as pistas de wind/solar |
| G-08 | sem `GEMINI_API_KEY` → nenhuma chamada HTTP, `decision=None`, `reason="no_key"`, `model="gemini-decision-1"`; `PLANLABEL_MODEL1_ID` troca o modelo da URL |
| G-09 | cada requisição enviada soma 1 em `model_usage` (200, 429, 500 e timeout); resposta do cache não soma |
| G-10 | 10 000 requisições no dia ou 200 no minuto → nenhuma chamada HTTP, `reason="quota_exhausted"` |
| G-11 | dia da cota no fuso do Pacífico (relógio injetado): 07:59 UTC e 08:00 UTC em novembro caem em dias diferentes; `resets_at` correto também no horário de verão |

### 3.4.2 Decisor do slot 2 — `OpenRouterDecider` (`tests/unit/test_decider_openrouter.py`, com `respx`)
| ID | Caso |
|---|---|
| O-01 | requisição `POST https://openrouter.ai/api/alpha/decisions` com `Authorization: Bearer`, `model: "typesafe/jev-1.14"`, a descrição em `state` e as mesmas perguntas do G-07; sem `user`, `session_id`, `trace` nem headers opcionais |
| O-02 | resposta real gravada (`jev_decision_wind.json`) → `Decision` com subcategory wind 100 %, category energy 100 %; `model` = snapshot da resposta (`typesafe/jev-1.14-20261014`), que vai para `m2_model`; sem decisão, `m2_model` = nome do `.env` |
| O-03 | resposta com `refusal`, sem uma das perguntas ou com `error` no corpo → `decision=None`, `reason="error"` |
| O-04 | 429 → `rate_limited`; 402 (sem créditos), 5xx e timeout → `error`; sem retry |
| O-05 | sem `OPENROUTER_API_KEY` → nenhuma chamada HTTP, `reason="no_key"`, `model="typesafe/jev-1.14"`; alias `~typesafe/jev-latest` é recusado na inicialização |
| O-07 | faltando qualquer um de `PLANLABEL_MODEL{1,2}_PROVIDER`/`_ID` → o app não sobe e a mensagem cita a variável que falta |
| O-06 | uso contado em `model_usage` por dia UTC (requisições e tokens de `usage.total_tokens`); limites `0` = sem bloqueio; limite > 0 atingido → `quota_exhausted` |

### 3.4.3 Conselheiro — `GeminiAdvisor` (`tests/unit/test_advisor.py`, com `respx` e `clock`)
| ID | Caso |
|---|---|
| H-01 | requisição para `.../models/<PLANLABEL_ADVISOR_ID>:generateContent` com a mesma `GEMINI_API_KEY`; saída JSON `{category, subcategory, text}` |
| H-02 | resposta válida → `Opinion`; inválida, 5xx ou timeout → `AdvisorError` |
| H-03 | 15 requisições em 60 s → `status.available=false`, `reason="rpm"`, `retry_at` = requisição mais antiga + 60 s; avançar o relógio além de `retry_at` → disponível |
| H-04 | tokens na janela (de `usageMetadata.totalTokenCount`) + estimativa > 25 000 → `reason="tpm"`; volta quando os tokens saem da janela |
| H-05 | 1 000 requisições no dia do Pacífico → `reason="rpd"` até a meia-noite do Pacífico; o contador sobrevive a reinício (lido de `model_usage`) |
| H-06 | HTTP 429 → bloqueado até `Retry-After` (ou 60 s), `reason="rate_limited"` |
| H-07 | cache: mesma descrição → nenhuma requisição nova e nada contado |
| H-08 | sem `GEMINI_API_KEY` → `NoneAdvisor` (`reason="disabled"`) |

### 3.4.4 Serviço + modelos (`tests/unit/test_service.py`)
| ID | Caso |
|---|---|
| S-14 | `decide(token, slot)` **não** escreve em `labeled_application` (spy) |
| S-15 | `decide` chamado 2× no mesmo token e slot → decisor chamado 1× |
| S-16 | `confirm` com rótulo **diferente** das duas decisões grava o rótulo do usuário e o `stored()` de cada decisão como recebido |
| S-17 | `confirm` sem ter chamado `decide` (ou com um slot que falhou) grava `mN_decision` NULL e `mN_model` preenchido |
| S-18 | `decide` ou `doubt` com token desconhecido → `UnknownToken` |
| S-19 | `doubt` não escreve em `labeled_application` e a opinião não é gravada em lugar nenhum; conselheiro bloqueado → `AdvisorUnavailable` |

### 3.5 Tradutor (`tests/unit/test_translator.py`)
| ID | Caso |
|---|---|
| T-01 | `NoneTranslator` devolve o texto original |
| T-02 | cache: mesma entrada → backend chamado 1 vez |
| T-03 | falha do backend → `TranslationError` |
| T-04 | fábrica escolhe a implementação por `PLANLABEL_TRANSLATOR` (`none`, `google`, lista `google,mymemory`) |
| T-05 | reserva: primeiro tradutor falha → usa o seguinte; todos falham → `TranslationError` |

### 3.6 API (`tests/integration/test_api.py`)
| ID | Caso |
|---|---|
| I-01 | `GET /` → 200 HTML contendo `id="app"` |
| I-02 | `GET /api/stats` → formato `Counts` com as 11 subcategorias |
| I-03 | `GET /api/next` → 200 com `token`, `application` (incl. `application_url`), `stats`, `models` (2) e `advisor` |
| I-04 | `POST /api/labels` com `not_energy`/`low_energy` → 201; `stats.total` +1; `stats.not_energy` +1 |
| I-05 | `POST /api/labels` com `energy`/`data_centre` → 201; `stats.energy` +1; `by_subcategory.data_centre` +1 |
| I-06 | `category` ou `subcategory` ausente → 422; banco inalterado |
| I-07 | valor inválido (`"nuclear"`) ou par incoerente (`energy`/`low_energy`) → 422; banco inalterado |
| I-08 | token desconhecido → 404 |
| I-09 | mesmo token confirmado duas vezes → segunda 404; total +1 só |
| I-10 | `POST /api/skip` → 204; depois `labels` com o mesmo token → 404; banco inalterado |
| I-11 | fontes todas fora → `GET /api/next` 503 com `detail` |
| I-12 | `POST /api/translate` → 200; tradutor falhando → 502 |
| I-13 | registro gravado contém `source`, `application_number`, `description`, `application_url`, `category`, `subcategory` iguais aos exibidos/escolhidos |
| I-14 | após gravar uma aplicação, 50 chamadas a `/api/next` nunca a retornam |
| I-15 | `POST /api/decide` slot 1 e slot 2 → 200 com `decision` (11 + 2 percentuais, subcategoria, categoria, `consistent`, modelo); **banco de rótulos inalterado** |
| I-16 | decisor falhando → 200 `{"decision": null, "reason": "error"}`; banco inalterado |
| I-17 | `decide` nos dois slots + nenhum `labels` + `skip` → banco de rótulos inalterado |
| I-18 | `decide`/`doubt` com token desconhecido → 404; `slot` fora de {1, 2} → 422 |
| I-19 | o cliente não consegue forjar decisão: `m1_*`/`m2_*` ou outros campos extras enviados em `/api/labels` → 422 |
| I-20 | `GET /healthz` → 200 `{"status":"ok"}` sem tocar fontes, modelos nem banco |
| I-21 | `quota` de `/api/decide` e `models[].quota` de `/api/next` trazem `used_today`, `limit_day`, `used_minute`, `limit_minute`, `resets_at`; `used_today` sobe 1 a cada decisão nova; slot sem chave → `model` preenchido, `decision` null, `reason="no_key"` |
| I-22 | `POST /api/doubt` → 200 com `opinion` e `advisor`; conselheiro bloqueado → 429 com `advisor.reason` e `retry_at`; falha → 502; `GET /api/advisor` reflete o estado |

### 3.7 E2E (`tests/e2e/test_ui.py`, Playwright, servidor com fontes e modelos fake)
| ID | Caso |
|---|---|
| E-01 | abrir → mostra número, fonte, descrição e contador "0 rotulados" |
| E-02 | Confirmar desabilitado até marcar categoria **e** subcategoria |
| E-03 | marcar Energia + wind + Confirmar → contador vai a 1 e outra aplicação aparece |
| E-04 | sem categoria, nenhuma subcategoria aparece; Energia mostra só as 9 de energia; Não energia mostra só não energia e baixa energia; trocar a categoria limpa a subcategoria |
| E-05 | Traduzir mostra texto PT; "Ver original" volta |
| E-06 | Cancelar → Próxima → nova aplicação; contador inalterado |
| E-07 | Cancelar → Encerrar → tela final; banco inalterado |
| E-08 | teclado: `N` `1` `Enter` grava não energia/não energia; `E` `9` marca data centre; `N` `2` marca baixa energia; número sem categoria não faz nada |
| E-09 | recarregar a página → nova aplicação, contador persiste |
| E-10 | erro 503 → mensagem + "Tentar de novo" funciona |
| E-11 | as duas decisões chegam → dois painéis com os 11 + 2 percentuais; maior subcategoria e maior categoria em destaque em cada painel; decisão contraditória mostra "⚠ contradição"; contador **não** muda até Confirmar |
| E-12 | com as decisões exibidas, Cancelar → Encerrar → banco inalterado |
| E-13 | os dois modelos escolhem energia + wind → Energia e wind pré-marcados com selo "sugestão dos dois modelos"; usuário troca para bess e confirma → grava energia/bess; selo "alterado por você" |
| E-14 | usuário escolhe antes de as decisões chegarem (decisor lento) → escolha do usuário não é sobrescrita |
| E-15 | um modelo falha → seu painel mostra só "sem sugestão" e o outro aparece normalmente; os dois falham → nada pré-marcado, rotulagem manual funciona |
| E-16 | linha de cotas mostra "gemini-decision-1 hoje N/10.000", "jev-1.14 hoje N" e "Dúvida N/1.000" e sobe após as decisões; slot 1 no limite → painel "limite diário atingido" |
| E-17 | Dúvida (botão ou `D`) mostra a opinião do conselheiro sem marcar opção; conselheiro bloqueado → botão desabilitado com motivo e horário na dica; ao voltar ao normal (relógio fake) o botão é reabilitado sem recarregar |
| E-18 | modelos concordam só na categoria (energia: wind × hybrid) → só Energia pré-marcada, subcategoria em branco; divergem na categoria → nada pré-marcado; os dois dizem energia + low_energy (contraditório) → só Energia pré-marcada |
| E-19 | link "abrir aplicação ↗" aparece com o `application_url` e abre em nova aba (`rel="noopener noreferrer"`); sem URL, o link não aparece |

### 3.8 Live (`tests/live/`, opcional, `pytest -m live`)
| ID | Caso |
|---|---|
| L-01 | cada uma das 3 fontes responde `?f=json` e contém os campos do `FIELD_MAP` |
| L-02 | `list_ids()` e `fetch()` reais devolvem uma `Application` válida por fonte |
| L-03 | com `GEMINI_API_KEY`, `gemini-decision-1` devolve decisão válida para 3 descrições conhecidas (wind farm, house extension, BESS) |
| L-04 | com `OPENROUTER_API_KEY`, `typesafe/jev-1.14` devolve decisão válida para as mesmas 3 descrições |
| L-05 | com `GEMINI_API_KEY`, `gemini-3.5-flash-lite` devolve opinião válida e `usageMetadata` com tokens |

### 3.9 Deploy (pós-deploy na VPS 3)
| ID | Caso |
|---|---|
| D-01 | `curl -sI https://planlabel-test.bundoran.tech/` sem cookie → 302 para `/oauth2/start` (e daí para `accounts.google.com`) |
| D-02 | `curl -s https://planlabel-test.bundoran.tech/api/next` sem cookie → **não** 200 (302/401); nenhum dado exposto |
| D-03 | (manual) login com e-mail autorizado → app abre, `/api/next` traz aplicação real, rotular grava |
| D-04 | (manual) login com conta Google **fora** da lista → 403 do oauth2-proxy |
| D-05 | `curl --max-time 5 http://31.97.113.166:8000/` e `:4180` falham (portas não publicadas) |
| D-06 | `docker compose restart` não perde registros (volume persistente) |

## 4. Matriz de rastreabilidade

| Requisito | Testes |
|---|---|
| RF-01 | S-01, S-12, A-03 |
| RF-02 / RF-03 | S-02, I-14, R-02 |
| RF-04 | M-06, A-06, S-03 |
| RF-23 | A-10, M-06, R-09, I-03, I-13, E-19 |
| RF-05 | I-03, E-01 |
| RF-06 | T-01..04, I-12, E-05 |
| RF-07 / RF-08 | M-01..M-03, I-06, I-07, E-02, E-04 |
| RF-09 | S-07, I-04, I-05, I-13 |
| RF-10 | R-04, R-05, S-11, I-06, I-07, I-10, I-19, E-07 |
| RF-11 | S-10, I-10, E-06, E-07 |
| RF-12 | E-09 |
| RF-13 | R-06, R-07, I-02, I-04, I-05, E-03 |
| RF-14 | A-07..09, S-05, S-06, I-11, E-10 |
| RF-15 | M-04, M-05, M-07, M-08, G-01..G-03, G-07, O-01, O-02, I-15, E-11 |
| RF-16 | S-14, I-15, I-17, E-11, E-12 |
| RF-17 | S-16, E-13, E-14, E-18 |
| RF-18 | G-04, G-05, O-03, O-04, I-16, E-15 |
| RF-19 | R-09, R-10, S-16, S-17, I-19 |
| RF-20 | R-11, G-09..G-11, O-06, I-21, E-16 |
| RF-21 | H-01..H-08, S-19, I-22, E-17 |
| RF-22 | G-08, O-05, O-07, I-21 |
| RNF-03 | E-08 |
| RNF-04 | cobertura no CI (`--cov-fail-under=90`) |
| RNF-07 | I-20, D-01..D-06 |

## 5. Comandos

```bash
pytest                                   # unit + integration + e2e (sem rede)
pytest --cov=planlabel --cov-fail-under=90
pytest -m live                           # contra as fontes e modelos reais
ruff check . && ruff format --check .
```

## 6. Definição de pronto

Três níveis; cada um inclui o anterior.

**Tarefa** (cada linha de [TASKS.md](TASKS.md))
- [ ] Testes listados na tarefa escritos antes do código (red visto), com o ID no nome (`test_R04_...`).
- [ ] `pytest` verde, sem `skip` fora de `live`.
- [ ] `ruff check .` e `ruff format --check .` limpos.
- [ ] Cobertura de `planlabel/` não caiu abaixo de 90 %.
- [ ] Nenhum segredo, `.env` ou `data/` no commit.
- [ ] SPEC atualizada se o comportamento mudou em relação a ela.
- [ ] Commit feito (`test:`/`feat:` com o ID) e enviado ao `develop`.

**História** (US-01..US-15 do [PRD §5.1](PRD.md#51-histórias-de-usuário))
- [ ] Todas as tarefas que a implementam estão prontas.
- [ ] Todos os testes listados na história estão verdes, incluindo os E2E.
- [ ] Critérios de aceite conferidos no app rodando (`python -m planlabel`), uma vez, pelo dono ou na sessão.
- [ ] Nenhum `[DECIDIR]` pendente na história, ou a opção proposta foi registrada na SPEC.

**Produto (release)**
- [ ] Todas as histórias prontas.
- [ ] Critério C1–C16 do [GO_PROMPT.md](../GO_PROMPT.md) marcado, com evidência.
- [ ] README e runbooks atualizados; memória da conversa atualizada.
