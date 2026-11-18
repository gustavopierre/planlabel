# GO — Plan Labeler

> Cole este prompt numa sessão do Claude Code aberta neste repositório. Ele é
> autossuficiente e tem um **critério de conclusão** verificável. Não pare antes de
> todos os itens do critério estarem marcados.

---

**Objetivo.** Implementar o Plan Labeler: web app local (backend Python/FastAPI, SQLite,
frontend HTML/CSS/JS puro e minimalista) que apresenta uma planning application irlandesa
por vez, vinda de três camadas ArcGIS, e grava no banco apenas registros com rótulo
completo (energia True/False e, se energia, categoria `hybrid|wind|solar|bess|leu`).

**Leia antes de codar, nesta ordem:** `docs/PRD.md`, `docs/ARCHITECTURE.md`,
`docs/SPEC.md`, `docs/TDD.md`, `docs/TASKS.md`. A SPEC é normativa; em conflito,
SPEC > TDD > ARCHITECTURE > PRD. Decisões marcadas **[DECIDIR]** em ARCHITECTURE usam a
opção proposta como padrão, a menos que o arquivo registre outra decisão.

**Como trabalhar.**
1. Execute as tarefas de `docs/TASKS.md` em ordem (T00 → T11).
2. Para cada tarefa: escreva os testes listados **primeiro**, rode e confirme que falham;
   implemente o mínimo; rode a suíte inteira; refatore; `ruff check . && ruff format .`;
   commit (`feat(T0x): …`).
3. Nunca use rede real nos testes padrão (use `respx` e fakes). Testes reais só em `tests/live/` com `-m live`.
4. Não altere testes para fazê-los passar, exceto se o teste contrariar a SPEC — nesse caso corrija a SPEC primeiro e explique no commit.
5. Não grave segredos. Chaves de tradução só por variáveis de ambiente.
6. Ao fim de cada tarefa grande (T03, T05, T07, T08, T10), atualize a memória da conversa
   no Google Drive com a skill `project-conversation-memory` (projeto
   `generator_plan_app_data_for_training`).
7. Faça push para o branch de trabalho ao fim de cada tarefa.

## Critério de conclusão (todos obrigatórios)

- [ ] **C1** — Todos os testes de `docs/TDD.md` §3.1–3.7 existem com os IDs no nome
      (ex.: `test_R04_...`) e `pytest` passa com **0 falhas, 0 erros, 0 skips** (exceto `live`).
- [ ] **C2** — `pytest --cov=planlabel --cov-fail-under=90` passa.
- [ ] **C3** — `ruff check .` e `ruff format --check .` sem apontamentos.
- [ ] **C4** — Regra RF-10 garantida em duas camadas: validação Pydantic (I-06, I-07) **e**
      `CHECK` no SQLite (R-04, R-05); S-11 prova que `next`/`skip` não escrevem no banco.
- [ ] **C5** — Deduplicação: R-03, S-02 e I-14 verdes; chave `UNIQUE(source, planning_authority, application_number)` presente no schema.
- [ ] **C6** — E2E E-01..E-10 verdes em Chromium headless.
- [ ] **C7** — `python -m planlabel` sobe em `127.0.0.1:8000`; com rede liberada, `GET /api/next`
      devolve uma aplicação real de pelo menos uma fonte (registrar resultado no README;
      se a rede do ambiente bloquear um host, registrar qual e seguir).
- [ ] **C8** — T00 concluída: esquemas reais (ou o bloqueio) documentados na SPEC §2 e fixtures gravadas.
- [ ] **C9** — `README.md` com: instalação, execução, testes, variáveis de ambiente,
      e consulta SQL de exportação do dataset.
- [ ] **C10** — Interface minimalista conforme SPEC §6: uma tela, sem frameworks de UI, sem build step.
- [ ] **C11** — Tudo commitado e enviado (`git status` limpo, push feito).
- [ ] **C12** — Memória da conversa atualizada no Google Drive (sessão + índices).

Ao terminar, responda com a lista C1–C12 marcada e a evidência de cada item
(saída resumida dos comandos, hash do commit).
