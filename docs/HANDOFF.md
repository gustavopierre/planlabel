# Handoff — Plan Labeler

**Data:** 2026-11-19 · **De:** sessão Claude Code na nuvem (branch `claude/dreamy-allen-tnqmnq`) · **Para:** desenvolvimento na **VPS 2** (VPS de desenvolvimento)

Leia este arquivo primeiro. Ele diz onde o projeto parou, o que falta e como continuar.
Os detalhes ficam nos documentos linkados.

## 1. O que é

Web app minimalista (backend Python/FastAPI, SQLite, frontend HTML/CSS/JS puro) que mostra
**uma** planning application irlandesa por vez (An Bord Pleanála + ePlanning, via ArcGIS),
pré-preenche o rótulo com a sugestão do modelo Google **`gemini-decision-1`** e grava no
banco **só depois que o usuário confirma**: energia True/False e, se energia, a categoria
`hybrid | wind | solar | bess | leu`. O banco vira dataset para treino e fine-tuning de IA.

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
  T00–T12, GO prompt com critério C1–C15, runbook do OAuth).
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
4. **Nada é gravado sem a confirmação do usuário.** A sugestão do `gemini-decision-1` só
   pré-preenche; a única rota que escreve no banco é `POST /api/labels`. Essa regra vale
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
| Responder os **[DECIDIR]**: definições das categorias no prompt (solar + bateria conta como `hybrid`? data centre entra em `leu`?), gravar a sugestão no banco (RF-19), pesos do sorteio, tradutor, pulados | Texto final do prompt (SPEC §4.2) e schema | Responder na sessão; atualizar SPEC/ARCHITECTURE |
| `GEMINI_API_KEY` | T00 (modelo), L-03, uso real da sugestão | Criar no Google AI Studio; guardar só no `.env` da VPS |
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
