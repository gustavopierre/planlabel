# GO — Plan Labeler

> Cole este prompt numa sessão do Claude Code aberta neste repositório. Ele é
> autossuficiente e tem um **critério de conclusão** verificável. Não pare antes de
> todos os itens do critério estarem marcados.

---

**Objetivo.** Implementar o Plan Labeler: web app local (backend Python/FastAPI, SQLite,
frontend HTML/CSS/JS puro e minimalista) que apresenta uma planning application irlandesa
por vez, vinda de três camadas ArcGIS, mostra a decisão de dois modelos (slot 1
`gemini-decision-1` via API Gemini, slot 2 `typesafe/jev-1.14` via OpenRouter) com o
percentual de cada subcategoria e categoria, oferece o botão **Dúvida** (opinião do
`gemini-3.5-flash-lite`, com limites de uso) e grava no banco apenas rótulos **confirmados
pelo usuário**: a categoria `energy|not_energy` e uma subcategoria dela (SPEC §1.1), mais o link da aplicação.
As sugestões dos modelos, sozinhas, nunca gravam nada.

**Leia antes de codar, nesta ordem:** `docs/PRD.md`, `docs/ARCHITECTURE.md`,
`docs/SPEC.md`, `docs/TDD.md`, `docs/TASKS.md`. A SPEC é normativa; em conflito,
SPEC > TDD > ARCHITECTURE > PRD. Decisões marcadas **[DECIDIR]** em ARCHITECTURE usam a
opção proposta como padrão, a menos que o arquivo registre outra decisão.

**Como trabalhar.**
1. Execute as tarefas de `docs/TASKS.md` em ordem (T00 → T10, T12, T11; T06b e T06c após T06).
2. Para cada tarefa: escreva os testes listados **primeiro**, rode e confirme que falham;
   implemente o mínimo; rode a suíte inteira; refatore; `ruff check . && ruff format .`;
   commit (`feat(T0x): …`).
3. Nunca use rede real nos testes padrão (use `respx` e fakes). Testes reais só em `tests/live/` com `-m live`.
4. Não altere testes para fazê-los passar, exceto se o teste contrariar a SPEC — nesse caso corrija a SPEC primeiro e explique no commit.
5. Procedimentos operacionais (deploy, credenciais, backup, rotação de segredos) viram **runbooks** em `docs/runbooks/` (um arquivo por procedimento, nome em `kebab-case`, listado no índice `docs/runbooks/README.md`). Se não houver acesso SSH à VPS, o deploy da T12 vira o runbook `deploy-vps3.md`.
6. Não grave segredos. `GEMINI_API_KEY`, `OPENROUTER_API_KEY`, segredos OAuth do Google e chaves de tradução só por variáveis de ambiente; nunca peça para colá-los no chat.
7. Ao fim de cada tarefa grande (T03, T05, T07, T08, T10), atualize a memória da conversa
   no Google Drive com a skill `project-conversation-memory` (projeto
   `generator_plan_app_data_for_training`).
8. Faça push para o branch de trabalho ao fim de cada tarefa.

## Critério de conclusão (todos obrigatórios)

- [ ] **C1** — Todos os testes de `docs/TDD.md` §3.1–3.7 existem com os IDs no nome
      (ex.: `test_R04_...`) e `pytest` passa com **0 falhas, 0 erros, 0 skips** (exceto `live`).
- [ ] **C2** — `pytest --cov=planlabel --cov-fail-under=90` passa.
- [ ] **C3** — `ruff check .` e `ruff format --check .` sem apontamentos.
- [ ] **C4** — Regra RF-10 garantida em duas camadas: validação Pydantic (I-06, I-07) **e**
      `CHECK` no SQLite (R-04, R-05); S-11 prova que `next`/`skip` não escrevem no banco.
- [ ] **C5** — Deduplicação: R-03, S-02 e I-14 verdes; chave `UNIQUE(source, planning_authority, application_number)` presente no schema.
- [ ] **C6** — E2E E-01..E-19 verdes em Chromium headless.
- [ ] **C7** — `python -m planlabel` sobe em `127.0.0.1:8000`; com rede liberada, `GET /api/next`
      devolve uma aplicação real de pelo menos uma fonte (registrar resultado no README;
      se a rede do ambiente bloquear um host, registrar qual e seguir).
- [ ] **C8** — T00 concluída: esquemas reais e nomes dos três modelos (`gemini-decision-1`, `typesafe/jev-1.14`, `gemini-3.5-flash-lite`), ou o bloqueio, documentados na SPEC e fixtures gravadas.
- [ ] **C9** — `README.md` com: instalação, execução, testes, variáveis de ambiente,
      e consulta SQL de exportação do dataset.
- [ ] **C10** — Interface minimalista conforme SPEC §6: uma tela, sem frameworks de UI, sem build step.
- [ ] **C11** — Tudo commitado e enviado (`git status` limpo, push feito).
- [ ] **C12** — Memória da conversa atualizada no Google Drive (sessão + índices).
- [ ] **C13** — Sugestão não salva sozinha: S-14, S-19, I-15, I-17, E-11 e E-12 verdes; a única rota que escreve em `labeled_application` é `POST /api/labels` (o contador `model_usage` é a exceção prevista no RF-20/RF-21) (verificado por teste ou por grep no código).
- [ ] **C14** — Falha de qualquer modelo não bloqueia: G-04, G-05, O-03, O-04, I-16, E-15 verdes; app funciona sem `GEMINI_API_KEY` e sem `OPENROUTER_API_KEY` (decisões em branco, `m1_model`/`m2_model` preenchidos).
- [ ] **C15** — App de teste no ar em `https://planlabel-test.bundoran.tech` (VPS 3, Caddy compartilhado, **login Google via oauth2-proxy**): D-01..D-06 verificados (D-03/D-04 manuais, pelo dono); `GEMINI_API_KEY`, `OPENROUTER_API_KEY` e segredos OAuth só no `.env` do servidor; nenhuma porta do app publicada no host; mudança no Caddyfile registrada no projeto `vps_infra`. Se faltar acesso SSH à VPS a partir da sessão, deixar `Dockerfile`/compose prontos e o runbook `docs/runbooks/deploy-vps3.md`, e marcar o item como bloqueado com o motivo.

- [ ] **C16** — Histórias US-01..US-15 do `docs/PRD.md` §5.1 prontas conforme `docs/TDD.md` §6 (nível história).

Ao terminar, responda com a lista C1–C16 marcada e a evidência de cada item
(saída resumida dos comandos, hash do commit).
