# Handoff — Plan Labeler

**Atualizado:** 2026-11-20 · **Por:** sessão Claude Code na **VPS 2** (branch `develop`) · **Para:** o dono e a próxima sessão

Leia este arquivo primeiro. Ele diz onde o projeto parou, o que falta e como continuar.
Os detalhes ficam nos documentos linkados.

## 1. O que é

Web app minimalista (backend Python/FastAPI, SQLite, frontend HTML/CSS/JS puro) que mostra
**uma** planning application irlandesa por vez (An Bord Pleanála + ePlanning, via ArcGIS),
mostra a decisão de dois modelos — **`gemini-decision-1`** (API Gemini) e
**`typesafe/jev-1.14`** (OpenRouter) — com o percentual de cada subcategoria e categoria,
oferece o botão **Dúvida** (`gemini-3.5-flash-lite`) e grava no banco **só depois que o
usuário confirma**: a categoria e depois uma subcategoria dela (`energy`: `hybrid | wind |
solar | bess | hydro | substation | energy_support | leu | data_centre`; `not_energy`:
`not_energy | low_energy`), mais o link da aplicação.
O banco vira dataset para treino e fine-tuning de IA.

## 2. Onde está tudo

| O quê | Onde |
|---|---|
| Repositório | <https://github.com/gustavopierre/planlabel> (antes `generator_plan_app_data_for_training`; a URL antiga redireciona) |
| Branches | `main` (só docs até `2ad7399`) · **`develop`** (todo o código; é o que a VPS 3 publica) |
| Memória das conversas | Google Drive › `Claude_Memoria/generator_plan_app_data_for_training/` (índice do projeto + uma `.md` por sessão) |
| Ambiente de teste (preparado, não publicado) | `https://planlabel-test.bundoran.tech` na **VPS 3**, com login Google (oauth2-proxy) — [runbook deploy-vps3](runbooks/deploy-vps3.md) |
| Infra das VPS | projeto `vps_infra` (repositório `gustavopierre/vps-infra`, memória `Claude_Memoria/vps_infra/`) |

Documentos, na ordem de leitura:
[PRD](PRD.md) → [ARCHITECTURE](ARCHITECTURE.md) → [SPEC](SPEC.md) (normativa) →
[TDD](TDD.md) → [TASKS](TASKS.md) → [GO_PROMPT](../GO_PROMPT.md) → [runbooks](runbooks/README.md).

## 3. Estado atual

- **Implementado e testado (T00–T10, T12 preparada):** app completo no `develop`.
  196 testes verdes sem rede (unidade, integração e 19 E2E no Chromium), cobertura 97 %,
  `ruff` limpo; 11 testes live contra as fontes e os modelos reais verdes em 2026-11-19.
- **Rodar na VPS 2:** `source .venv/bin/activate && python -m planlabel` e túnel SSH
  (`ssh -L 8000:127.0.0.1:8000 dev-vps`) → <http://localhost:8000>. O `.env` já tem as chaves
  e os modelos.
- **Achados da T00 que mudaram a SPEC:**
  - `gemini-decision-1` e `typesafe/jev-1.14` são **modelos de decisão** (não geram texto):
    `POST /v1beta/decisions` (Google) e `POST /api/alpha/decisions` (OpenRouter), com
    perguntas `choice` e **probabilidade calibrada por opção**. O app faz duas perguntas
    independentes por modelo (subcategoria e categoria).
  - `gemini-2.5-flash-lite` não está disponível para usuários novos → Dúvida usa `gemini-3.5-flash-lite`.
  - ePlanning: camadas 0 e 1 são quase as mesmas aplicações → entram juntas como **uma**
    fonte (`LayeredSource`, 2026-11-20); a chave de duplicata usa a fonte (`eplanning`), não a
    camada, então a mesma aplicação nunca é rotulada duas vezes. A lista de IDs é pedida por faixas
    de `OBJECTID` (o ArcGIS corta em 400 000 e devolve um subconjunto arbitrário).
  - Google Translate não oficial bloqueia o IP da VPS → reserva automática MyMemory.
- **Backup do SQLite (T13, 2026-11-20):** container `planlabel-backup` no mesmo compose, todo dia
  às 02:00 (Dublin) → `gdrive:planlabel-test-backups`, 60 dias, mesma conta Google dos backups do
  LO Engagement (cópia do `rclone.conf` dele na VPS 3). Testado com rclone real (remote local);
  falta ligar na VPS 3 — [runbook backup-sqlite](runbooks/backup-sqlite.md).
- **Falta:** publicar o teste na VPS 3 (dono, depois da credencial OAuth), ligar o backup lá
  e registrar os dois no `vps_infra`.

## 4. Decisões já tomadas (não reabrir)

1. Python + FastAPI + `sqlite3` da stdlib; frontend sem framework e sem build.
2. Rodízio de fontes (ABP → ePlanning, um rodízio só para todos); dentro da fonte, registro
   aleatório por `OBJECTID`; descarta o que já está no banco. Puladas podem voltar.
3. Chave única `(source, planning_authority, application_number)`: o número se repete entre conselhos (19 932 números em mais de um conselho).
4. **Nada é gravado sem a confirmação do usuário.** As decisões dos modelos só sugerem;
   a única rota que grava rótulos (`labeled_application`) é `POST /api/labels`; o contador de uso dos modelos (`model_usage`) é a única outra escrita. Essa regra vale
   na API e também nas `CHECK` constraints do SQLite.
5. O registro em exibição fica na memória do servidor (com token); o cliente não forja dados.
6. Teste na VPS 3 em `planlabel-test.bundoran.tech`, atrás do Caddy compartilhado
   (rede `edge`) e com **login Google via oauth2-proxy** (sem basic auth, sem login no app).
7. Sem pull requests: o trabalho vai direto no branch, e o `main` só é atualizado quando o dono pedir.
8. Procedimentos operacionais viram **runbooks** em `docs/runbooks/`.
9. Documentação em português; nomes técnicos em inglês.
10. Taxonomia da SPEC §1.1 (categoria primeiro, subcategoria filtrada); rótulo humano nunca
    contraditório; decisões dos modelos gravadas como vieram (`m1_model`/`m2_model` sempre
    preenchidos, `m1_decision`/`m2_decision` em JSON ou NULL).
11. Modelos obrigatórios no `.env`; pré-marcação só quando os dois modelos concordam.
12. Backup do SQLite no Google Drive da conta dos backups do LO Engagement (2026-11-20).

## 5. Pendências do dono

| Pendência | Bloqueia | Como |
|---|---|---|
| Credencial OAuth do Google | Publicar o teste na VPS 3 | [runbook google-oauth-setup](runbooks/google-oauth-setup.md) e depois [deploy-vps3](runbooks/deploy-vps3.md) |
| Limites do `gemini-3.5-flash-lite` no AI Studio | Ajuste fino do botão Dúvida (hoje 15/min, 25 000 tokens/min, 1 000/dia, valores do 2.5) | Conferir e ajustar `PLANLABEL_ADVISOR_*` no `.env` |
| Ligar o backup na VPS 3 | Cópia fora do servidor do dataset de teste | [runbook backup-sqlite](runbooks/backup-sqlite.md) Partes 1–3, junto com o deploy |
| Reinício da VPS 2 | Nada (kernel 7.0.0-44 instalado, rodando 7.0.0-38) | Reiniciar quando for conveniente |
| Atualizar `main` | Nada | Só quando o dono pedir (`develop` → `main`) |

## 6. Como continuar na VPS 2

1. `cd ~/dev/planlabel && git switch develop && git pull --ff-only && source .venv/bin/activate`
2. `pytest` (deve dar tudo verde) e `python -m planlabel` para usar.
3. Para uma sessão nova do Claude Code, primeira mensagem sugerida:

   > Leia `docs/HANDOFF.md` e a memória do projeto no Google Drive
   > (`Claude_Memoria/generator_plan_app_data_for_training/`, skill
   > `project-conversation-memory`).

## 7. Atenção

- **Papel de cada VPS:** VPS 2 = desenvolvimento · VPS 3 = teste (`planlabel-test`) ·
  VPS 4 = produção pessoal · VPS 1 (Hermes) **não mexer** · VPS 5 = LO Engagement.
- **Segredos** (`GEMINI_API_KEY`, `OPENROUTER_API_KEY`, segredos OAuth) só em `.env` com `chmod 600`; nunca em
  commit, no chat ou em print.
- **App na VPS 2:** fica em `127.0.0.1:8000` e é acessado por túnel SSH
  (`ssh -L 8000:127.0.0.1:8000 dev-vps`). Não abra a porta 8000 no firewall: o app não tem login.
- **Memória:** se a sessão na VPS 2 não tiver o conector do Google Drive, a skill de memória
  grava os arquivos localmente e registra a cópia para o Drive como pendência. Nunca duplicar
  a memória dentro do repositório.
