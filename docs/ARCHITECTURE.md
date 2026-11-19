# Arquitetura — proposta para discussão

**Status:** proposta. Os pontos marcados com **[DECIDIR]** precisam de confirmação do
dono do produto antes de o `GO_PROMPT.md` ser executado.

## 1. Visão geral

```
┌──────────────┐  HTTP/JSON   ┌──────────────────────────── FastAPI (Python) ──────────────────────────┐
│ index.html   │ ───────────► │ api.py ──► LabelingService ──► SourceRegistry ──► ArcGISSource × 3      │──► ArcGIS REST
│ app.js       │ ◄─────────── │                │                                                        │
│ style.css    │              │                ├──► Repository (sqlite3) ──► data/labels.sqlite3        │
│ (vanilla)    │              │                ├──► Translator (plugável) ─────────────────────────────│──► serviço de tradução
│              │              │                ├──► Decider slot 1 (gemini-decision-1) ───────────────│──► API Gemini
│              │              │                ├──► Decider slot 2 (typesafe/jev-1.14) ───────────────│──► OpenRouter
│              │              │                └──► Advisor / Dúvida (gemini-2.5-flash-lite) ─────────│──► API Gemini
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
2. Para servir um registro: usa **uma fonte por vez, alternando** (`abp → epl_1 → epl_0`),
   com uma só rotação no servidor para todos os usuários (decisão do dono, 2026-11-19);
   na fonte da vez sorteia um `OBJECTID` e busca **só esse** registro
   (`objectIds=<id>&outFields=...&returnGeometry=false`).
3. Valida (número e descrição não vazios) e checa no banco pela chave natural
   (`source`, `planning_authority`, `application_number`). Se já existir ou for inválido,
   marca o ID como "visto nesta execução" e repete (até 10 tentativas na fonte; depois passa à próxima).

Vantagens: uma requisição pequena por registro, aleatoriedade real, nada gravado antes
do rótulo. Alternativa rejeitada: paginar por offset (custa mais e enviesa para os
registros antigos).

### 2.5 O que acontece com o registro em exibição?
Fica **no servidor, em memória**, numa "sessão de rotulagem" identificada por um
`token` (UUID) devolvido ao frontend. O `POST /api/labels` envia o `token` + rótulo; o
servidor grava os dados **que ele mesmo buscou** — o cliente não consegue alterar número,
fonte ou descrição. Pendências não vão para o banco (RF-10).

### 2.6 Tradução — interface `Translator` plugável
| Opção | Custo | Qualidade | Observação |
|---|---|---|---|
| `deep-translator` (Google Translate não oficial) | grátis | boa | sem chave; pode sofrer limite de uso |
| DeepL API Free | grátis até 500 mil caracteres/mês | muito boa | precisa de chave |
| Claude API (`claude-haiku-5-5`) | baixo | muito boa, entende jargão de planning | precisa de chave |

Decisão do dono (2026-11-19): `deep-translator` (Google Translate não oficial, sem chave),
configurável por `PLANLABEL_TRANSLATOR`. Não usar `gemini-2.5-flash-lite` para traduzir: ele
dividiria a cota diária com o botão Dúvida. Traduções
são cacheadas em memória (LRU) e **não** são gravadas no dataset.

### 2.6.1 Dois modelos decisores (slots 1 e 2) e o conselheiro (Dúvida)
- **Papel:** só sugerir. Os modelos nunca gravam rótulo; a única porta de escrita em
  `labeled_application` continua sendo `POST /api/labels`, disparado pelo clique do usuário.
- **Slots:** slot 1 = `gemini-decision-1` (API Gemini), slot 2 = `typesafe/jev-1.14`
  (OpenRouter, versão fixa). Cada slot é um `Decider` escolhido por configuração
  (`PLANLABEL_MODEL{1,2}_PROVIDER`/`_ID`); trocar um modelo não muda o código, e o banco
  grava o nome do modelo de cada slot em `m1_model`/`m2_model`, sempre preenchidos.
- **Uma chamada, dois julgamentos:** cada modelo devolve, numa chamada, o percentual das 11
  subcategorias e depois o das 2 categorias (saída JSON estruturada, nessa ordem). A maior de
  cada uma é escolhida de forma independente. Se elas se contradizem, a tela avisa e o banco
  grava como veio: a contradição marca casos de fronteira e é informação útil para o
  dataset. Duas chamadas separadas dariam julgamentos mais independentes, mas gastariam o
  dobro da cota e da espera; foi descartado.
- **Fluxo assíncrono:** `GET /api/next` devolve a aplicação imediatamente; o frontend chama
  `POST /api/decide` para os dois slots em paralelo. A latência de um modelo não atrasa o
  outro nem a exibição. Escolha manual feita antes não é sobrescrita.
- **Lado do servidor:** as decisões ficam no pendente (junto do token) e são gravadas com o
  rótulo — o cliente não consegue forjá-las.
- **Chamadas:** REST via `httpx` (Gemini `generateContent`; OpenRouter `chat/completions` com
  `response_format: json_schema`), `temperature: 0`, timeout 10 s, sem retry, cache por hash
  da descrição. `httpx` em vez dos SDKs mantém o mock simples com `respx`.
- **Falha:** qualquer erro deixa o painel daquele modelo sem sugestão; nada bloqueia.
- **Conselheiro (Dúvida):** `gemini-2.5-flash-lite` com a mesma `GEMINI_API_KEY`, chamado só
  quando o usuário clica. Um limitador próprio (janela de 60 s em memória + contador diário
  no SQLite) aplica 15 req/min, 25 000 tokens/min e 1 000 req/dia; o botão fica desabilitado
  enquanto algum limite estiver atingido e volta sozinho. A opinião não é gravada.
- **Cotas:** tabela `model_usage` (dia, modelo, requisições, tokens) alimenta os contadores
  da tela; o dia segue o fuso do provedor (Pacífico para o Gemini, UTC para o OpenRouter).
- **Taxonomia:** definida pelo dono em 2026-11-19 (SPEC §1.1); é o guia humano e o prompt.

### 2.7 Esquema de dados — campos além dos pedidos
O pedido lista: número, fonte, descrição, categoria e subcategoria. Acrescentados:
- `planning_authority` — **necessário**: `ApplicationNumber` se repete entre conselhos.
- `source_object_id` — rastreabilidade até o registro original.
- `labeled_at` (UTC) — auditoria e divisão treino/validação por tempo.
- `application_url` — link da página pública da aplicação (pedido do dono em 2026-11-19).
- `m1_model`/`m1_decision` e `m2_model`/`m2_decision` — o nome do modelo de cada slot (sempre
  preenchido) e, num
  único campo de texto (JSON), a categoria e a subcategoria de maior percentual com os seus
  percentuais (decidido pelo dono em 2026-11-19). Permite medir a concordância de cada modelo com o
  humano, comparar os modelos e trocar modelos em versões futuras sem perder a referência.

### 2.8 Interpretação do "Cancelar"
Leitura adotada: Cancelar → diálogo **Encerrar | Próxima**. "Próxima" pula o registro
(sem gravar); "Encerrar" termina a sessão e mostra a tela final. Registros pulados podem
reaparecer numa execução futura (não são gravados, por RF-10) — confirmado pelo dono em 2026-11-19.

## 3. Estrutura de pastas

```
planlabel/
  __init__.py  __main__.py   # python -m planlabel
  config.py                  # Settings via env (PLANLABEL_*)
  models.py                  # Application, Label, Category, Subcategory, Decision — Pydantic
  sources/
    base.py                  # Protocol Source
    arcgis.py                # ArcGISSource (httpx) + mapeamento de campos
    registry.py              # rodízio entre fontes, fallback
  repository.py              # sqlite3: schema, exists(), save(), counts()
  translator.py              # Protocol Translator + implementações
  deciders/
    base.py                  # Protocol Decider, validação das distribuições
    prompt.py                # prompt gerado da taxonomia
    gemini.py                # GeminiDecider (slot 1)
    openrouter.py            # OpenRouterDecider (slot 2)
  advisor.py                 # Protocol Advisor, GeminiAdvisor, NoneAdvisor, limitador RPM/TPM/RPD
  usage.py                   # cotas: dia por fuso, janelas de 60 s
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

## 5. Deploy de teste — VPS 3 (`https://planlabel-test.bundoran.tech`)

Segue as convenções do projeto `vps_infra` (memória no Drive, `Claude_Memoria/vps_infra/`):

- **Servidor:** VPS 3 de testes (31.97.113.166, Hostinger), usuário `deploy`, Docker.
- **DNS:** registro A `planlabel-test.bundoran.tech` → 31.97.113.166 (criado pelo dono em 2026-11-18).
- **Branch:** `develop` → VPS 3 (teste); `main` → produção futura (`planlabel.bundoran.tech`, sem data).
- **Sem Caddy próprio:** o app entra na rede Docker externa `edge` com o apelido fixo
  `planlabel`; o Caddy compartilhado (`/opt/edge`, versionado em `vps-infra/vps-3/edge`)
  ganha um bloco.
- **Login com conta Google (oauth2-proxy):** o app não tem login próprio e grava o
  dataset, então não pode ficar aberto. O acesso passa por um container
  [`oauth2-proxy`](https://oauth2-proxy.github.io/oauth2-proxy/) (apelido `planlabel-oauth2`
  na rede `edge`) com o provedor Google. O Caddy consulta o oauth2-proxy em cada requisição
  (`forward_auth`); sem sessão válida, redireciona para o login do Google; só passam e-mails
  da lista de permitidos. **Nenhum código de autenticação no app Python.**

  ```caddyfile
  planlabel-test.bundoran.tech {
      handle /oauth2/* {
          reverse_proxy planlabel-oauth2:4180 {
              header_up X-Real-IP {remote_host}
              header_up X-Forwarded-Uri {uri}
          }
      }
      handle {
          forward_auth planlabel-oauth2:4180 {
              uri /oauth2/auth
              copy_headers X-Auth-Request-User X-Auth-Request-Email
              @bad status 4xx
              handle_response @bad {
                  redir * /oauth2/start?rd={scheme}://{host}{uri}
              }
          }
          reverse_proxy planlabel:8000
      }
  }
  ```

  Configuração do oauth2-proxy (variáveis no `.env` da VPS; imagem
  `quay.io/oauth2-proxy/oauth2-proxy` com versão fixada na T12):

  | Variável | Valor |
  |---|---|
  | `OAUTH2_PROXY_PROVIDER` | `google` |
  | `OAUTH2_PROXY_CLIENT_ID` / `OAUTH2_PROXY_CLIENT_SECRET` | do Google Cloud Console (segredo) |
  | `OAUTH2_PROXY_COOKIE_SECRET` | 32 bytes aleatórios (`openssl rand -base64 32 \| tr -- '+/' '-_'`) (segredo) |
  | `OAUTH2_PROXY_REDIRECT_URL` | `https://planlabel-test.bundoran.tech/oauth2/callback` |
  | `OAUTH2_PROXY_AUTHENTICATED_EMAILS_FILE` | `/etc/oauth2-proxy/emails.txt` (um e-mail por linha; fora do git) |
  | `OAUTH2_PROXY_HTTP_ADDRESS` | `0.0.0.0:4180` |
  | `OAUTH2_PROXY_REVERSE_PROXY` / `OAUTH2_PROXY_SET_XAUTHREQUEST` | `true` / `true` |
  | `OAUTH2_PROXY_COOKIE_SECURE` | `true` |
  | `OAUTH2_PROXY_UPSTREAMS` | `static://202` (só autentica; quem serve o app é o Caddy) |

  **Google Cloud Console (feito pelo dono):** projeto `planlabel`; tela de consentimento
  OAuth "Externo" em modo "Teste", com a conta do dono como usuário de teste; credencial
  "ID do cliente OAuth" tipo "Aplicativo da Web" com URI de redirecionamento
  `https://planlabel-test.bundoran.tech/oauth2/callback`.

  **Regras de segurança:** os containers `planlabel` e `planlabel-oauth2` **não publicam
  portas** no host (só a rede `edge`), para que ninguém contorne o login acessando
  `IP:8000`. O app ignora os headers `X-Auth-Request-*` no MVP. **[DECIDIR]** Gravar
  `labeled_by` a partir de `X-Auth-Request-Email` se houver mais de um rotulador.

  O mesmo padrão pode proteger depois os outros apps de teste da VPS 3 (`lo-eng-test`,
  `roxjournal-test`); isso é decisão do projeto `vps_infra`.
- **Arquivos no repositório do app:** `Dockerfile` (python:3.12-slim, usuário não root,
  `uvicorn planlabel.api:app --host 0.0.0.0 --port 8000`), `docker-compose.edge.yml`
  (serviços `planlabel` e `planlabel-oauth2`, rede `edge` externa, sem `ports:`,
  volume `planlabel_data:/app/data`, `env_file: .env`, `restart: unless-stopped`,
  healthcheck em `/healthz`), `.env.example` (só nomes das variáveis, sem valores).
- **Segredos:** `GEMINI_API_KEY`, `OPENROUTER_API_KEY`, `OAUTH2_PROXY_CLIENT_SECRET`, `OAUTH2_PROXY_COOKIE_SECRET`
  (e chaves de tradução, se houver) só em `~/planlabel/.env` na VPS, modo 600, fora do git;
  `emails.txt` também fora do git.
- **Dados:** SQLite no volume `planlabel_data`. Backup diário fora do servidor
  (`sqlite3 labels.sqlite3 ".backup ..."` → cópia para o Drive/PC) — **[DECIDIR]** destino e rotina.
- **Divisão de trabalho:** o deploy do app é deste projeto; a alteração no `Caddyfile` e nas
  fichas da VPS 3 é registrada também no projeto `vps_infra` (e copiada para o Hermes).
- **Vantagem:** a VPS não tem o bloqueio de rede do container de desenvolvimento; a T00
  (esquemas ePlanning e IDs dos modelos) pode ser conferida a partir dela.
