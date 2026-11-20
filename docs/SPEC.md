# Especificação técnica

Referências: [PRD](PRD.md) · [Arquitetura](ARCHITECTURE.md) · [TDD](TDD.md) · [Tarefas](TASKS.md)

## 1. Glossário

- **Aplicação** — uma planning application (ou caso do ABP) lida de uma fonte.
- **Rótulo** — par (**categoria**, **subcategoria**) escolhido pelo usuário, nessa ordem:
  primeiro `energy` | `not_energy`, depois uma subcategoria **daquela** categoria (tabela do
  §1.1). Rótulo humano incoerente não existe: a API e o banco recusam.
- **Pendente** — aplicação exibida ao usuário e ainda sem rótulo. Só existe em memória.
- **Modelo decisor** — modelo que, para uma descrição, devolve numa só chamada um percentual
  para cada uma das 11 subcategorias **e** um percentual para cada uma das 2 categorias. Há dois, em **slots** configuráveis: slot 1 = `gemini-decision-1`
  (API Gemini), slot 2 = `typesafe/jev-1.14` (via OpenRouter). Trocar o modelo de um slot é só
  configuração (§7).
- **Decisão** — a resposta de um modelo decisor: as duas distribuições, a subcategoria de
  maior percentual e a categoria de maior percentual. As duas escolhas são **independentes** e
  podem se contradizer (ex.: wind 60 % e not_energy 55 %); a contradição é mostrada, não corrigida.
- **Conselheiro** — o modelo do botão **Dúvida** (`gemini-3.5-flash-lite`), que dá uma
  opinião em texto quando o usuário pede.

### 1.1 Taxonomia (guia de rotulagem)

É o guia do rotulador humano e o conteúdo das perguntas feitas aos modelos (§4.2). A ordem da tabela
é a ordem canônica (desempate, teclado, exibição). Teclas: `E`/`N` escolhem a categoria;
os números escolhem a subcategoria **dentro** da categoria escolhida.

As descrições quase nunca dizem "wind farm" ou "solar farm". Um parque eólico aparece como
"N turbines", "permission for X years to install N turbines", aumento de altura de pá,
extensão de prazo da permissão etc.; um parque solar aparece como instalação de painéis
PV no solo ("ground-mounted solar PV panels/arrays", hectares de painéis) etc.

| Categoria | Subcategoria (`valor`) | Tecla | Quando usar |
|---|---|---|---|
| energy | hybrid | `1` | Duas ou mais entre wind / solar / bess na mesma aplicação, 1 MW ou mais no total. |
| energy | wind | `2` | Turbinas eólicas / parque eólico (onshore/offshore) de 1 MW ou mais: instalação de N turbinas, permissão (ou extensão de prazo) para N turbinas, troca de turbinas (repowering), ampliações. |
| energy | solar | `3` | Instalação de painéis fotovoltaicos no solo (parque solar) de 1 MW ou mais. |
| energy | bess | `4` | Armazenamento em baterias como empreendimento principal, de qualquer potência. |
| energy | hydro | `5` | Geração hidrelétrica, de qualquer potência. |
| energy | substation | `6` | Subestação elétrica (nova ou ampliada) da rede ou de geração. |
| energy | energy_support | `7` | **Obras** que dão suporte relevante a projetos de energia: estradas nacionais, cabos elétricos até subestações, ampliação de subestações para atender parques eólicos e solares (solar no solo). Tem de ser obra; o parque em si é `wind` ou `solar`. |
| energy | leu | `8` | Large energy user: fábricas, complexos industriais, construção de 200 ou mais casas num mesmo projeto. |
| energy | data_centre | `9` | Data centre. |
| not_energy | not_energy | `1` | Todo o resto. Inclui cercas, estacionamentos, prédios (que não sejam subestações), depósitos etc., **mesmo que façam parte** de parques eólicos e solares ou de LEUs. |
| not_energy | low_energy | `2` | Baixa energia: solar / wind / hybrid com menos de 1 MW; conjunto de menos de 200 casas; geração por **outras fontes** (biomassa, diesel, gás, CHP etc.), **sempre**, de qualquer potência; pequenas subestações dentro de casas, escolas, supermercados; painéis solares em telhados; pontos de carregamento de carros elétricos. |

Decisões do dono (2026-11-19): `bess` e `hydro` não seguem a regra de 1 MW (são energia
em qualquer potência); outras fontes (biomassa, diesel etc.) são sempre `low_energy`.

## 2. Fontes

| `source` | camada (`source_layer`) | URL base (`/query` acrescentado pelo cliente) | número | descrição | autoridade | link |
|---|---|---|---|---|---|---|
| `abp` | `abp_3` | `https://services-eu1.arcgis.com/o56BSnENmD5mYs3j/ArcGIS/rest/services/Cases_2016_Onwards/FeatureServer/3` | `ABPCASEID` | `DEVDESC` | `PLANINGATY` | `LINKABPWEB` |
| `eplanning` | `epl_0` | `https://services.arcgis.com/NzlPQPKn5QF9v2US/ArcGIS/rest/services/IrishPlanningApplications/FeatureServer/0` | `ApplicationNumber` | `DevelopmentDescription` | `PlanningAuthority` | `LinkAppDetails` |
| `eplanning` | `epl_1` | `https://services.arcgis.com/NzlPQPKn5QF9v2US/ArcGIS/rest/services/IrishPlanningApplications/FeatureServer/1` | `ApplicationNumber` | `DevelopmentDescription` | `PlanningAuthority` | `LinkAppDetails` |

`source` é a **fonte** (ABP ou ePlanning) e entra na chave de duplicata; `source_layer` é a
camada de onde o registro veio, só para rastreio. As camadas 0 e 1 do ePlanning formam
**uma só fonte** no rodízio (`LayeredSource`, decisão abaixo).

**Verificado na T00 (2026-11-19, VPS 2)** — esquemas em `tests/fixtures/arcgis/*_layer.json`:
- `abp` — "Cases", polígonos, 27 310 registros, `OBJECTID` como OID, `maxRecordCount` 2000.
  `LINKABPWEB` sempre preenchido (`https://www.pleanala.ie/en-ie/case/<ABPCASEID>`).
- `epl_1` — "Planning Application Sites" (polígonos dos terrenos), 512 624 registros.
- `epl_0` — "Planning Application Points" (pontos), 512 860 registros. Tem também campos
  pessoais do requerente (`ApplicantForename`, `ApplicantSurname`, `ApplicantAddress`):
  **nunca** pedir esses campos em `outFields`.
- **As camadas 0 e 1 são quase as mesmas aplicações** em geometrias diferentes (tabela abaixo).
- `LinkAppDetails` (ePlanning): 63 913 de 512 860 vazios; 235 788 começam com `http://`
  (sem s); o domínio varia por conselho (ex.: `eplanning.ie/CarlowCC/...`,
  `planning.agileapplications.ie/corkcoco/...`). Link aceito se começar com `http://` ou `https://`.
- `ApplicationNumber` pode vir com espaços à direita (ex.: `F19A/0014     `): a normalização
  (`strip()`) é obrigatória antes da checagem de duplicata.

O mapeamento fica num dicionário `FIELD_MAP` em `planlabel/sources/arcgis.py`; nenhum
nome de campo aparece em outro lugar do código. Sem link → `application_url` vazio (`''`),
sem bloquear a rotulagem.

**Decisão: camadas 0 e 1 do ePlanning juntas, como uma fonte** (2026-11-20, pedido do dono;
até então só a camada 0). Comparação completa feita na T00 (conselho + número normalizados,
todas as linhas das duas camadas):

| | camada 0 (pontos) | camada 1 (polígonos) |
|---|---|---|
| registros | 512 860 | 512 624 |
| aplicações distintas | 512 332 | 511 952 |
| repetidas dentro da própria camada | 400 | 494 |
| só nesta camada | **391** | **11** |
| nas duas | 511 941 | 511 941 |

O dono pediu que uma aplicação já no banco nunca seja rotulada de novo dentro da mesma fonte,
mesmo vinda de outra camada. Por isso a chave de duplicata usa a fonte (`eplanning`), não a
camada: uma aplicação que está nas duas camadas é rotulada uma vez só. A comparação é dentro de
cada fonte (ABP com ABP, ePlanning com ePlanning), nunca entre ABP e ePlanning.

**Como as camadas viram uma fonte** (`LayeredSource` em `planlabel/sources/arcgis.py`):
- `list_ids()` junta as listas das camadas numa **visão sem cópia**; os OBJECTIDs se repetem
  entre camadas, então o ID da visão é `oid × 2 + camada` (`fetch` decodifica e pede à camada
  certa). Grava-se o `oid` real em `source_object_id` e a camada em `source_layer`.
- O rodízio continua `abp → eplanning → abp …`: a camada 1 **não** ganha vez própria. Cada
  sorteio do ePlanning cai em qualquer uma das 1 025 484 entradas (≈ metade em cada camada).
- Uma camada fora do ar é ignorada enquanto a outra responder; as duas fora → `SourceError`.
- Custo medido (2026-11-20, VPS 2): +26 MB de memória e +0,2 s na carga da lista (a camada 0
  sozinha: 48 MB). Ganho: as 11 aplicações que só existem na camada 1.

**A chave inclui o conselho, não só o número:** 19 932 números de aplicação existem em mais
de um conselho (ex.: `2360178` aparece em 19 conselhos). Os formatos variam por conselho
(`99/9999` em Cork County, `A99A/9999` em Fingal e Dún Laoghaire, `9999/99` em Dublin City,
`99999` ou `9999999` em vários). Não há variações só de maiúsculas ou espaços internos; a
normalização é `strip()` + espaços internos colapsados.

### 2.1 Chamadas ao ArcGIS

| Uso | Parâmetros de `GET <url>/query` |
|---|---|
| Maior ID | `where=1=1&outStatistics=[{"statisticType":"max","onStatisticField":"OBJECTID","outStatisticFieldName":"mx"}]&f=json` |
| Lista de IDs | `where=OBJECTID>{lo} AND OBJECTID<={hi}&returnIdsOnly=true&f=json` — por faixas (abaixo) |
| Um registro | `objectIds=<id>&outFields=<num>,<desc>,<aut>[,<link>]&returnGeometry=false&f=json` |

- Timeout 15 s; até 3 tentativas com backoff exponencial (0,5 s, 1 s, 2 s) em erro de rede/5xx.
- Resposta com chave `error` (o ArcGIS devolve HTTP 200 com erro no corpo) é tratada como falha.
- **Lista de IDs por faixas:** acima do limite de transferência (400 000 no ePlanning) o ArcGIS
  devolve um subconjunto **arbitrário** dos IDs, com `exceededTransferLimit: true` — não os
  menores. Por isso a lista é pedida por faixas fixas de `OBJECTID` (250 000 por vez) até o
  maior ID da camada (`outStatistics` max); faixa ainda cortada é dividida ao meio. Achado no
  teste ao vivo da T07: paginar por "maior ID recebido" carregava só 400 033 dos 512 860 IDs;
  com faixas, carrega os 512 860 em ~4 s.
- Cache da lista de IDs: em memória, TTL 24 h (`PLANLABEL_IDS_TTL_S`).
- Normalização: `strip()` em todos os textos; espaços internos múltiplos colapsados na descrição.

## 3. Banco de dados (SQLite)

```sql
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS labeled_application (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    source              TEXT    NOT NULL CHECK (source IN ('abp','eplanning')),
    source_layer        TEXT    NOT NULL CHECK (source_layer IN ('abp_3','epl_0','epl_1')),
    application_number  TEXT    NOT NULL CHECK (length(trim(application_number)) > 0),
    planning_authority  TEXT    NOT NULL DEFAULT '',
    source_object_id    INTEGER NOT NULL,
    description         TEXT    NOT NULL CHECK (length(trim(description)) > 0),
    application_url     TEXT    NOT NULL DEFAULT '',      -- link da página pública da aplicação [RF-23]
    -- rótulo do usuário (decisão final; categoria escolhida primeiro)
    category            TEXT    NOT NULL CHECK (category IN ('energy','not_energy')),
    subcategory         TEXT    NOT NULL,
    labeled_at          TEXT    NOT NULL,                 -- ISO-8601 UTC
    -- decisão de cada modelo no momento do rótulo [RF-19]
    -- mN_model:    nome do modelo; sempre preenchido. Se a API devolve o nome na resposta, grava esse
    --              (ex.: 'typesafe/jev-1.14-20261014'); senão, o nome do .env (ex.: 'gemini-decision-1')
    -- mN_decision: texto JSON com as escolhas de maior percentual, sem checagem de coerência:
    --              {"category":"energy","category_pct":91,"subcategory":"wind","subcategory_pct":82}
    --              NULL (em branco) quando o modelo não entregou decisão, por qualquer motivo
    m1_model            TEXT    NOT NULL CHECK (length(trim(m1_model)) > 0),
    m1_decision         TEXT    CHECK (m1_decision IS NULL OR json_valid(m1_decision)),
    m2_model            TEXT    NOT NULL CHECK (length(trim(m2_model)) > 0),
    m2_decision         TEXT    CHECK (m2_decision IS NULL OR json_valid(m2_decision)),
    CHECK ((category = 'energy' AND subcategory IN
              ('hybrid','wind','solar','bess','hydro','substation','energy_support','leu','data_centre'))
        OR (category = 'not_energy' AND subcategory IN ('not_energy','low_energy'))),
    UNIQUE (source, planning_authority, application_number)
);

-- uso dos modelos por dia [RF-20, RF-21]; não guarda nada da aplicação nem do rótulo
CREATE TABLE IF NOT EXISTS model_usage (
    day       TEXT    NOT NULL,      -- AAAA-MM-DD no fuso da cota do provedor (§4.4)
    model     TEXT    NOT NULL,
    requests  INTEGER NOT NULL DEFAULT 0 CHECK (requests >= 0),
    tokens    INTEGER NOT NULL DEFAULT 0 CHECK (tokens >= 0),
    PRIMARY KEY (day, model)
);
```

- O banco **recusa** rótulo humano inválido, subcategoria incoerente com a categoria e
  duplicata, mesmo que a camada de aplicação falhe (defesa em profundidade, RF-10).
- As decisões dos modelos **não** passam por checagem de coerência: categoria e subcategoria
  de um modelo podem se contradizer e são gravadas como vieram.
- Leitura das decisões: `json_extract(m1_decision, '$.subcategory')` etc.
- A regra "nada é gravado sem confirmação" vale para `labeled_application`. `model_usage`
  é só um contador de chamadas e é escrito quando um modelo é chamado (RF-20, RF-21).
- A opinião do conselheiro (botão Dúvida) **não** é gravada.
- Caminho: `PLANLABEL_DB_PATH` (padrão `data/labels.sqlite3`). Schema criado no startup.

### 3.1 Repository (contrato)

```python
class Repository:
    def exists(self, source: str, authority: str, number: str) -> bool: ...
    def save(self, app: Application, label: Label,
             slot1: SlotResult, slot2: SlotResult) -> int: ...   # levanta DuplicateError
    def counts(self) -> Counts: ...   # total, energy, not_energy, by_subcategory{11 chaves sempre}
    def add_usage(self, day: str, model: str, tokens: int = 0) -> Usage: ...  # +1 requisição, +tokens (UPSERT atômico)
    def usage(self, day: str, model: str) -> Usage: ...                       # zeros se não houver linha
```

## 4. Domínio

```python
class Category(StrEnum): ENERGY="energy"; NOT_ENERGY="not_energy"

class Subcategory(StrEnum):          # ordem canônica do §1.1
    HYBRID="hybrid"; WIND="wind"; SOLAR="solar"; BESS="bess"; HYDRO="hydro"
    SUBSTATION="substation"; ENERGY_SUPPORT="energy_support"; LEU="leu"; DATA_CENTRE="data_centre"
    NOT_ENERGY="not_energy"; LOW_ENERGY="low_energy"

CATEGORY_OF: dict[Subcategory, Category]   # tabela do §1.1; única fonte do mapeamento

class Application(BaseModel):
    source: Literal["abp","eplanning"]
    source_layer: Literal["abp_3","epl_0","epl_1"]
    source_object_id: int
    application_number: str   # não vazio
    planning_authority: str   # pode ser ""
    description: str          # não vazio
    application_url: str      # pode ser ""; se preenchido, começa com http:// ou https://

class Label(BaseModel):
    category: Category
    subcategory: Subcategory
    # model_validator: CATEGORY_OF[subcategory] == category, senão ValidationError

class Decision(BaseModel):
    model: str                                        # nome do modelo, ex.: "gemini-decision-1"
    subcategory_distribution: dict[Subcategory, int]  # 11 chaves, 0..100, soma 100 (após normalização)
    category_distribution: dict[Category, int]        # 2 chaves, 0..100, soma 100 (após normalização)
    # derivados, cada um da sua própria distribuição (independentes):
    subcategory: Subcategory              # o `choice` da API (maior probabilidade)
    subcategory_pct: int
    category: Category                    # o `choice` da API (maior probabilidade)
    category_pct: int
    consistent: bool                      # CATEGORY_OF[subcategory] == category
    def stored(self) -> str: ...          # JSON de mN_decision: category, category_pct, subcategory, subcategory_pct

class SlotResult(BaseModel):
    slot: Literal[1, 2]
    model: str                            # nome do modelo: o da resposta da API, se houver; senão o do .env
    decision: Decision | None
    reason: Literal["ok","error","rate_limited","quota_exhausted","no_key","not_requested"]
```

**Validação das distribuições** (cada uma separadamente): exatamente as chaves esperadas
(11 ou 2); probabilidades entre 0 e 1 com soma entre 0,98 e 1,02 → convertidas para
percentuais inteiros que somam 100 (maior resto); fora disso → resposta inválida.
Contradição entre as duas **não** invalida.

### 4.1 LabelingService

- `next_application() -> Pending` — usa **uma fonte por vez, alternando** na ordem fixa
  `abp → eplanning → abp …` (decisão do dono, 2026-11-19). A posição da rotação é
  **única no servidor**, compartilhada por todos os usuários e abas, e protegida por lock.
  Na fonte da vez: sorteia um ID não visto, busca, valida, verifica `exists()`; repete até
  `MAX_ATTEMPTS_PER_SOURCE = 10`. Se a fonte falhar (`SourceError`) ou esgotar as tentativas,
  passa para a próxima da rotação. A chamada seguinte começa na fonte depois da que serviu.
  Nenhuma fonte serve → `NoApplicationAvailable`. A rotação recomeça em `abp` ao reiniciar o app.
- `Pending = {token: UUID4, application: Application, slots: {1: SlotResult, 2: SlotResult}}`;
  guardado num dicionário em memória (máx. 100 pendentes, os mais antigos são descartados).
- `decide(token, slot) -> SlotResult` — token desconhecido → `UnknownToken`; chama o modelo
  do slot uma vez por token (chamadas repetidas devolvem o valor guardado) e guarda o
  resultado no pendente. **Não** escreve em `labeled_application`.
- `doubt(token) -> Opinion` — token desconhecido → `UnknownToken`; conselheiro bloqueado →
  `AdvisorUnavailable(status)`; falha → `AdvisorError`. Nada é gravado (só `model_usage` sobe).
- `confirm(token, label) -> Counts` — token desconhecido → `UnknownToken`; revalida
  `exists()` (corrida) → `DuplicateError`; grava o rótulo do usuário + os dois `SlotResult`
  guardados no pendente (`mN_model` sempre preenchido com o nome do modelo; slot sem
  decisão → `mN_decision` NULL); remove o pendente. Rótulo e decisões podem divergir; vale sempre o rótulo do usuário.
- `skip(token)` — remove o pendente sem gravar; o ID fica no conjunto "visto nesta execução".
  Aplicações puladas **podem** voltar a aparecer depois de reiniciar o app (decisão do dono, 2026-11-19).
- O sorteio do ID dentro da fonte usa `random.Random` injetável (testes determinísticos).

### 4.2 Modelos decisores

Os dois modelos são **modelos de decisão**: não geram texto; recebem um texto e perguntas de
escolha fechada e devolvem, numa só passada, a opção escolhida e a **probabilidade de cada
opção** (soma 1). Os percentuais da tela são essas probabilidades × 100. Verificado na T00
com chamadas reais (fixtures em `tests/fixtures/gemini/` e `tests/fixtures/openrouter/`).

```python
class Decider(Protocol):
    slot: Literal[1, 2]
    model: str
    def decide(self, app: Application) -> SlotResult: ...   # nunca levanta: falha ⇒ decision=None + reason
    def quota(self) -> Quota: ...
```

**Perguntas (iguais para os dois provedores)** — constantes em `planlabel/deciders/questions.py`,
geradas da tabela do §1.1, cobertas por teste de snapshot (G-07). Cada pergunta é avaliada de
forma independente pelo modelo:

```json
{
  "subcategory": {
    "type": "choice",
    "instructions": "<pista> Which subcategory best describes the main purpose of this development?",
    "criteria": {"hybrid": "<definição>", "wind": "<definição>", … 11 opções …}
  },
  "category": {
    "type": "choice",
    "instructions": "<pista> Is this an energy development?",
    "criteria": {"energy": "<definição>", "not_energy": "<definição>"}
  }
}
```

- `<pista>`: "This is an Irish planning application description. Descriptions rarely say
  'wind farm' or 'solar farm': a wind farm appears as 'N turbines', permission for X years
  for N turbines, tip height changes; a solar farm appears as ground-mounted solar PV panels
  or arrays, hectares of panels."
- `<definição>` de cada subcategoria: a coluna "Quando usar" do §1.1, em inglês.
- A descrição da aplicação é o texto compartilhado, sem outros campos.
- Ordem: a API ordena as opções pelo nome; o desempate exato vai para a primeira em ordem
  alfabética. A tela usa a ordem canônica do §1.1.

**Slot 1 — `GeminiDecider` (`gemini-decision-1`):**
`POST https://generativelanguage.googleapis.com/v1beta/decisions`, header `x-goog-api-key`
(`GEMINI_API_KEY`), corpo `{"model": "gemini-decision-1", "input": <descrição>, "questions": …}`.
Resposta: `answers.<pergunta>.{choice, probabilities, confidence}` e `usage.total_input_tokens`.
Na T00: 386 ms, 647 tokens de entrada por aplicação. O modelo **não** aceita `generateContent`
(só o método de decisões). Bloqueio de segurança → HTTP 400 com `error` → `reason="error"`.

**Slot 2 — `OpenRouterDecider` (`typesafe/jev-1.14`):**
`POST https://openrouter.ai/api/alpha/decisions`, header `Authorization: Bearer <OPENROUTER_API_KEY>`,
corpo `{"model": "typesafe/jev-1.14", "state": <descrição>, "questions": …}` (mesmas perguntas;
o texto vai em `state`, não em `input`). Resposta: `answers.<pergunta>.{choice, probabilities,
confidence}` (resposta `refusal` → sem decisão), `model` (snapshot resolvido, ex.:
`typesafe/jev-1.14-20261014`, gravado em `m2_model` — decisão do dono, 2026-11-19), `usage.{input_tokens, output_tokens, cost}`. Na T00: 352 ms,
946 tokens, US$ 0,00004 por aplicação. O modelo **não** aceita `chat/completions`. Nunca usar o
alias `~typesafe/jev-latest`. Nenhum dado do dono vai nos campos opcionais `user`, `session_id`
ou `trace`, nem em headers opcionais do OpenRouter.

Comum aos dois:
- Timeout `PLANLABEL_DECIDER_TIMEOUT_S` (10 s), **sem retry**. HTTP 429 → `rate_limited`;
  outro erro HTTP, timeout, resposta sem as duas perguntas ou com opção desconhecida → `error`;
  log `WARNING`.
- Percentual = `round(probabilidade × 100)`; a distribuição é normalizada para somar 100 (maior
  resto). A escolha (`subcategory`, `category`) é o `choice` da API.
- Cache LRU (256) por `sha256(description)` em cada decisor.
- Os dois slots sempre existem e sempre têm nome de modelo. Slot sem a chave do seu provedor
  não chama a API e devolve `decision=None`, `reason="no_key"`.

### 4.3 Conselheiro (botão Dúvida)

```python
class Advisor(Protocol):
    def opinion(self, app: Application) -> Opinion: ...      # levanta AdvisorUnavailable / AdvisorError
    def status(self) -> AdvisorStatus: ...

Opinion = {model: str, category: Category, subcategory: Subcategory, text: str}   # text em português, até ~80 palavras
AdvisorStatus = {model: str | None, available: bool,
                 reason: "rpm" | "tpm" | "rpd" | "rate_limited" | "disabled" | None,
                 retry_at: ISO-8601 UTC | None,
                 rpm_used: int, rpm_limit: int, tpm_used: int, tpm_limit: int,
                 rpd_used: int, rpd_limit: int}
```

- `GeminiAdvisor`: modelo `PLANLABEL_ADVISOR_ID` (`gemini-3.5-flash-lite`), **mesma**
  `GEMINI_API_KEY`, endpoint `generateContent`. Na T00, `gemini-2.5-flash-lite` respondeu 404 ("no longer
  available to new users"); o dono escolheu `gemini-3.5-flash-lite`, que funcionou (1,2 s, ~210 tokens). Prompt: a taxonomia do §1.1 + "explique
  em português, em até 80 palavras, qual categoria e qual subcategoria você escolheria e por quê, citando o
  trecho da descrição que decide". Saída JSON `{category, subcategory, text}`.
- Limites (configuráveis): **15 requisições/min**, **25 000 tokens/min**, **1 000 requisições/dia**.
  - Minuto: janela deslizante de 60 s em memória (horários das requisições e tokens de cada uma,
    lidos de `usageMetadata.totalTokenCount`).
  - Antes de chamar: bloqueia se `rpm_used >= rpm_limit`, se `tpm_used + estimativa >
    tpm_limit` (estimativa = `len(prompt_completo)/4 + 300`) ou se `rpd_used >= rpd_limit`.
  - Dia: `model_usage` (sobrevive a reinícios), fuso `America/Los_Angeles`.
  - HTTP 429 → bloqueado até `Retry-After` (ou 60 s), `reason="rate_limited"`.
  - `retry_at` = quando a condição deixa de valer (requisição mais antiga sai da janela,
    tokens saem da janela ou meia-noite do Pacífico).
- Cache LRU (128) por `sha256(description)`: repetir a dúvida da mesma aplicação não chama a API.
- Sem `GEMINI_API_KEY` → `NoneAdvisor` (`available=false`, `reason="disabled"`).

### 4.4 Cotas e contadores

| Modelo | Conta | Limites | Fuso do dia |
|---|---|---|---|
| slot 1 `gemini-decision-1` | requisições | **200/min** e **10 000/dia** (free tier, dados oficiais do dono em 2026-11-19) | `America/Los_Angeles` |
| slot 2 `typesafe/jev-1.14` | requisições e tokens | sem limite padrão (`0` = só contar) | `UTC` |
| conselheiro `gemini-3.5-flash-lite` | requisições e tokens | 15/min, 25 000 tokens/min, 1 000/dia (valores do 2.5, provisórios até o dono conferir os do 3.5 no AI Studio) | `America/Los_Angeles` |

- Cada requisição HTTP **enviada** soma 1 em `model_usage` antes do envio, qualquer que seja
  o resultado; os tokens da resposta são somados depois. Resposta de cache não conta.
- Decisor no limite (por minuto ou por dia) → não chama a API e devolve `reason="quota_exhausted"`.
- O dia é calculado com `zoneinfo`; relógio injetável em todos os componentes.
- `Quota = {"model": str, "used_today": int, "limit_day": int, "used_minute": int,
  "limit_minute": int, "resets_at": ISO-8601 UTC}` (limite `0` = sem limite).

## 5. API HTTP

Todas as respostas são JSON, exceto `/` (HTML).

| Método e rota | Corpo | Sucesso | Erros |
|---|---|---|---|
| `GET /` | — | `index.html` | — |
| `GET /healthz` | — | `200 {"status":"ok"}` (não chama fontes, modelos nem banco) | — |
| `GET /api/stats` | — | `200 Counts` | — |
| `GET /api/next` | — | `200 {token, application, stats, models: [ModelInfo, ModelInfo], advisor: AdvisorStatus}` | `503 {"detail": "..."}` se nenhuma fonte responder |
| `POST /api/decide` | `{token, slot: 1\|2}` | `200 {slot, model, decision: Decision\|null, reason, quota: Quota\|null}` | `404` token desconhecido · `422` slot inválido |
| `POST /api/doubt` | `{token}` | `200 {opinion: Opinion, advisor: AdvisorStatus}` | `404` token desconhecido · `429 {advisor}` bloqueado · `502 {advisor}` falha do modelo |
| `GET /api/advisor` | — | `200 AdvisorStatus` | — |
| `POST /api/labels` | `{token, category, subcategory}` (campos extras proibidos) | `201 {stats}` | `422` categoria/subcategoria ausente, inválida ou incoerente, ou campo extra · `404` token desconhecido · `409` duplicado |
| `POST /api/skip` | `{token}` | `204` | `404` token desconhecido |
| `POST /api/translate` | `{text}` (≤ 4000 chars) | `200 {translation}` | `502` tradutor falhou |

- `Counts` = `{"total": int, "energy": int, "not_energy": int, "by_subcategory": {<11 chaves>: int}}`.
- `ModelInfo` = `{slot, model: str, quota: Quota}`.
- `Decision` serializado = `{model, subcategory, subcategory_pct, category, category_pct, consistent,
  subcategory_distribution: {<11 chaves>: int}, category_distribution: {"energy": int, "not_energy": int}}`
  (as distribuições completas vão para a tela; no banco fica só o `stored()`).
- `application` exibido = `{source, source_label, application_number, planning_authority, description, application_url}`.
- A decisão dos modelos nunca vem do cliente; o servidor grava a que ele recebeu.

## 6. Interface

### 6.1 Layout (uma coluna, máx. 960 px, fonte do sistema, sem imagens)

```
Plan Labeler                                       1.284 rotulados · 312 energia
gemini-decision-1 hoje 37/10.000 · jev-1.14 hoje 37 · Dúvida 3/1.000
──────────────────────────────────────────────────────────────────────────────
ABP · Laois County Council · 318799                        [abrir aplicação ↗]
112 structures associated with uprate of existing line. A Natura …     [Traduzir]

Modelo 1 · gemini-decision-1            Modelo 2 · typesafe/jev-1.14
ENERGIA 91 %   não energia 9 %          energia 45 %   NÃO ENERGIA 55 %  ⚠ contradição
 hybrid 4  WIND 82  solar 2  bess 0      hybrid 5  WIND 60  solar 1  bess 0
 hydro 0  substation 1  support 2        hydro 0  substation 1  support 1
 leu 0  data centre 0                    leu 0  data centre 0
 não energia 6  baixa energia 3          não energia 20  baixa energia 12

Sua decisão
 Categoria     ( ) Energia E   ( ) Não energia N
 Subcategoria  (só as da categoria escolhida)
               ( ) hybrid 1 ( ) wind 2 ( ) solar 3 ( ) bess 4 ( ) hydro 5
               ( ) substation 6 ( ) energy support 7 ( ) leu 8 ( ) data centre 9
                                         [Dúvida]  [Cancelar]  [Confirmar]
 Opinião do gemini-3.5-flash-lite: "…"                     ← só depois de clicar em Dúvida
```

- Em cada painel de modelo: a categoria de maior percentual e a subcategoria de maior
  percentual em destaque (negrito/realce), escolhidas de forma independente; as demais em
  fonte pequena. Os 11 + 2 percentuais sempre visíveis. Se a subcategoria destacada não
  pertence à categoria destacada, o painel mostra "⚠ contradição".
- Link "abrir aplicação ↗" (nova aba, `rel="noopener noreferrer"`) quando houver `application_url`.
- Em tela estreita os dois painéis ficam um abaixo do outro.

### 6.2 Estados e regras
- **Carregando** → texto "Buscando…"; botões desabilitados.
- **Decisões:** após exibir, o frontend chama `POST /api/decide` para o slot 1 e o slot 2 **em
  paralelo**. Cada painel mostra "analisando…" até a sua resposta. Painel de modelo que não
  entregou decisão (qualquer motivo) mostra só "sem sugestão" em cinza, sem mensagem de erro;
  com `quota_exhausted`: "limite diário atingido". Os dois painéis aparecem sempre, com o nome do modelo.
- **Pré-marcação** (decisão do dono, 2026-11-19), só com os **dois** modelos respondendo:
  - concordam na categoria **e** na subcategoria, e a subcategoria pertence a essa categoria
    → pré-marca as duas, selo "sugestão dos dois modelos";
  - concordam só na categoria → pré-marca só a categoria (subcategoria em branco);
  - caso contrário → nada pré-marcado.
  Nunca sobrescreve uma escolha já feita pelo usuário. Se o usuário mudar o que veio
  pré-marcado, o selo vira "alterado por você".
- **Escolha:** primeiro a categoria (Energia / Não energia); só então aparecem as
  subcategorias **daquela** categoria. Trocar a categoria limpa a subcategoria.
  **Confirmar** habilitado somente com categoria e subcategoria marcadas; nada é gravado sem
  o clique em Confirmar / `Enter`.
- **Dúvida:** chama `POST /api/doubt` e mostra a opinião abaixo dos botões (não marca
  nenhuma opção). Desabilitado quando `advisor.available = false`, com dica (`title`) do
  motivo e do horário de retorno (`retry_at`). Enquanto desabilitado, o frontend consulta
  `GET /api/advisor` no horário `retry_at` (ou a cada 10 s, o que vier primeiro) e reabilita
  quando `available` volta a `true`. Erro 502: "o conselheiro não respondeu", em linha.
- **Traduzir** alterna entre original e tradução ("Ver original"); erro de tradução aparece em linha e não bloqueia.
- **Cancelar** → diálogo nativo `<dialog>`: "Encerrar" / "Próxima". Serve também quando o
  usuário fica em dúvida, com ou sem ajuda dos modelos.
- **Encerrado** → "Sessão encerrada. N registros rotulados." + botão "Recomeçar" (= recarregar).
- **Erro de fonte (503)** → mensagem + "Tentar de novo".
- **Contadores:** o total rotulado é atualizado com o `stats` da confirmação; a linha de cotas
  com o `quota` de cada `/api/decide` e o `advisor` de `/api/next`, `/api/doubt` e `/api/advisor`.
  Contador a partir de 80 % do limite fica em destaque. Respostas que chegam depois de o
  usuário passar para outra aplicação são ignoradas (comparar token).

### 6.3 Teclado
`E` energia · `N` não energia · `1`–`9` subcategoria da categoria escolhida (energia: ordem
do §1.1; não energia: `1` não energia, `2` baixa energia; números sem categoria escolhida
não fazem nada) · `D` dúvida · `T` traduzir · `Enter` confirmar · `Esc` cancelar.

## 7. Configuração (variáveis de ambiente)

| Variável | Padrão |
|---|---|
| `PLANLABEL_DB_PATH` | `data/labels.sqlite3` |
| `PLANLABEL_TRANSLATOR` | `google,mymemory` (lista tentada em ordem; `google`, `mymemory` ou `none`) |
| `PLANLABEL_IDS_TTL_S` | `86400` |
| `PLANLABEL_HOST` / `PLANLABEL_PORT` | `127.0.0.1` / `8000` (no container: `0.0.0.0`) |
| `PLANLABEL_MODEL1_PROVIDER` / `PLANLABEL_MODEL1_ID` | **obrigatório, sem padrão** (hoje: `gemini` / `gemini-decision-1`) |
| `PLANLABEL_MODEL1_RPM` / `PLANLABEL_MODEL1_RPD` | `200` / `10000` |
| `PLANLABEL_MODEL2_PROVIDER` / `PLANLABEL_MODEL2_ID` | **obrigatório, sem padrão** (hoje: `openrouter` / `typesafe/jev-1.14`) |
| `PLANLABEL_MODEL2_RPM` / `PLANLABEL_MODEL2_RPD` | `0` / `0` (só contar) |
| `PLANLABEL_DECIDER_TIMEOUT_S` | `10` |
| `PLANLABEL_ADVISOR_ID` | **obrigatório, sem padrão** (hoje: `gemini-3.5-flash-lite`) |
| `PLANLABEL_ADVISOR_RPM` / `PLANLABEL_ADVISOR_TPM` / `PLANLABEL_ADVISOR_RPD` | `15` / `25000` / `1000` |

Provedores aceitos em `PLANLABEL_MODEL{1,2}_PROVIDER`: `gemini`, `openrouter`. Os dois slots
são obrigatórios: os quatro `PLANLABEL_MODEL{1,2}_PROVIDER`/`_ID` ficam no `.env` (decisão do
dono, 2026-11-19) e o app **não sobe** se faltar algum, com mensagem dizendo qual. Slot sem a
chave do seu provedor funciona sem decisões (painel "sem sugestão", `mN_decision` NULL). Chaves de API (`GEMINI_API_KEY`,
`OPENROUTER_API_KEY`, DeepL, Anthropic) apenas via ambiente; nunca no repositório.

## 8. Rastreabilidade requisito → teste

Ver tabela em [TDD.md §4](TDD.md#4-matriz-de-rastreabilidade).
