# Handoff — Plan Labeler

**Data:** 2026-11-19 · **De:** sessão Claude Code na nuvem (branch `claude/dreamy-allen-tnqmnq`) · **Para:** desenvolvimento na **VPS 2** (VPS de desenvolvimento)

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
| Branch padrão | `main` |
| Último commit revisado | `5eb2ac1` (`main` = `claude/dreamy-allen-tnqmnq` nesse ponto) |
| Memória das conversas | Google Drive › `Claude_Memoria/generator_plan_app_data_for_training/` (índice do projeto + uma `.md` por sessão) |
| Ambiente de teste (futuro) | `https://planlabel-test.bundoran.tech` na **VPS 3**, com login Google (oauth2-proxy) |
| Infra das VPS | projeto `vps_infra` (repositório `gustavopierre/vps-infra`, memória `Claude_Memoria/vps_infra/`) |

Documentos, na ordem de leitura:
[PRD](PRD.md) → [ARCHITECTURE](ARCHITECTURE.md) → [SPEC](SPEC.md) (normativa) →
[TDD](TDD.md) → [TASKS](TASKS.md) → [GO_PROMPT](../GO_PROMPT.md) → [runbooks](runbooks/README.md).

## 3. Estado atual

- **Pronto:** documentação completa (PRD, arquitetura, SPEC, catálogo de testes, tarefas
  T00–T12, GO prompt com critério C1–C16, histórias US-01..US-15 e definição de pronto, runbook do OAuth).
- **Não iniciado:** **nenhuma linha de código**. Nenhuma tarefa do `GO_PROMPT.md` começou;
  não existe `pyproject.toml` nem a pasta `planlabel/`.
- **Verificado:** a camada An Bord Pleanála (`services-eu1.arcgis.com`, FeatureServer/3)
  responde: 27 310 registros, campos `ABPCASEID`, `DEVDESC`, `PLANINGATY`, `CATEGORY`;
  `returnIdsOnly=true` devolve todos os IDs numa resposta.
- **Não verificado:** as camadas ePlanning `IrishPlanningApplications/FeatureServer/0` e `/1`
  (`services.arcgis.com`) e o modelo `gemini-decision-1`. O container da nuvem bloqueava
  esses hosts. Os campos do ePlanning na SPEC vêm da skill `ireland-planning-gis`; a
  camada 0 foi presumida por analogia. **A T00 confirma tudo isso, e a VPS 2 deve conseguir.**

## 4. Decisões já tomadas (não reabrir)

1. Python + FastAPI + `sqlite3` da stdlib; frontend sem framework e sem build.
2. Busca aleatória por `OBJECTID` (lista de IDs em cache) → um registro por vez; descarta
   o que já está no banco.
3. Chave única `(source, planning_authority, application_number)`: `ApplicationNumber` se repete entre conselhos.
4. **Nada é gravado sem a confirmação do usuário.** As decisões dos modelos só sugerem;
   a única rota que grava rótulos (`labeled_application`) é `POST /api/labels`; o contador de uso dos modelos (`model_usage`) é a única outra escrita. Essa regra vale
   na API e também nas `CHECK` constraints do SQLite.
5. O registro em exibição fica na memória do servidor (com token); o cliente não forja dados.
6. Teste na VPS 3 em `planlabel-test.bundoran.tech`, atrás do Caddy compartilhado
   (rede `edge`) e com **login Google via oauth2-proxy** (sem basic auth, sem login no app).
7. Sem pull requests: o trabalho vai direto no branch, e o `main` só é atualizado quando o dono pedir.
8. Procedimentos operacionais viram **runbooks** em `docs/runbooks/`.
9. Documentação em português; nomes técnicos em inglês.

## 5. Pendências do dono (bloqueiam partes do trabalho)

| Pendência | Bloqueia | Como |
|---|---|---|
| `GEMINI_API_KEY` | T00 (modelos), L-03, L-05, slot 1 e Dúvida | Criar no Google AI Studio; guardar só no `.env` da VPS |
| `OPENROUTER_API_KEY` | T00 (jev), L-04, slot 2 | Criar em openrouter.ai (Keys); guardar só no `.env` da VPS |
| Credencial OAuth do Google | T12 (deploy de teste na VPS 3) | [runbook google-oauth-setup](runbooks/google-oauth-setup.md) |
| Destino do backup do SQLite | T12 | Decidir; virará `runbooks/backup-sqlite.md` |

Sem essas respostas é possível avançar em T01–T08 com os padrões propostos (o `GO_PROMPT`
manda usar a opção proposta quando não houver decisão registrada).

## 6. Como continuar na VPS 2

1. Prepare a VPS 2 seguindo o [runbook setup-dev-vps2](runbooks/setup-dev-vps2.md).
2. Na pasta do repositório, abra o Claude Code (`claude`).
3. Primeira mensagem sugerida:

   > Leia `docs/HANDOFF.md` e a memória do projeto no Google Drive
   > (`Claude_Memoria/generator_plan_app_data_for_training/`, skill
   > `project-conversation-memory`). Depois execute o `GO_PROMPT.md` a partir da T00.

4. Trabalhe num branch de desenvolvimento (sugestão: `develop`, que é também o branch que a
   VPS 3 vai publicar, pela convenção do `vps_infra`). Atualize o `main` só quando o dono pedir.

## 7. Atenção

- **Papel de cada VPS:** VPS 2 = desenvolvimento · VPS 3 = teste (`planlabel-test`) ·
  VPS 4 = produção pessoal · VPS 1 (Hermes) **não mexer** · VPS 5 = LO Engagement.
- **Segredos** (`GEMINI_API_KEY`, segredos OAuth) só em `.env` com `chmod 600`; nunca em
  commit, no chat ou em print.
- **App na VPS 2:** fica em `127.0.0.1:8000` e é acessado por túnel SSH
  (`ssh -L 8000:127.0.0.1:8000 dev-vps`). Não abra a porta 8000 no firewall: o app não tem login.
- **Memória:** se a sessão na VPS 2 não tiver o conector do Google Drive, a skill de memória
  grava os arquivos localmente e registra a cópia para o Drive como pendência. Nunca duplicar
  a memória dentro do repositório.
