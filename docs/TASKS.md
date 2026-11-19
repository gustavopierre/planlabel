# Tarefas

Cada tarefa segue o ciclo red → green → refactor do [TDD.md](TDD.md). "Pronto" de uma
tarefa segue a [definição de pronto](TDD.md#6-definição-de-pronto) (nível tarefa).

| ID | Tarefa | Testes que precisam passar | Depende de |
|---|---|---|---|
| T00 | **Verificar esquemas** das 3 camadas (`?f=json`), registrar campos reais em `docs/SPEC.md §2` e gravar fixtures em `tests/fixtures/arcgis/`. **Verificar os modelos**: `gemini-decision-1` e `gemini-3.5-flash-lite` (`GET https://generativelanguage.googleapis.com/v1beta/models` com `GEMINI_API_KEY`) e `typesafe/jev-1.14` (`GET https://openrouter.ai/api/v1/models`); confirmar os IDs exatos, que o jev aceita `response_format` `json_schema`, e gravar respostas reais em `tests/fixtures/gemini/` e `tests/fixtures/openrouter/`. **Descobrir o link de cada fonte** (campo da camada ou modelo de URL) e registrar no `FIELD_MAP` da SPEC §2. Registrar bloqueios (host ou chave) e seguir com a SPEC. | — (documental) | — |
| T01 | Esqueleto: `pyproject.toml` (deps, ruff, pytest, cobertura), pacote `planlabel/`, `tests/conftest.py`, `.gitignore` (`data/`, `.venv/`) | `pytest` roda (0 testes) | — |
| T02 | `models.py`: `Category`, `Subcategory`, `CATEGORY_OF`, `Application`, `Label`, `Decision` (validação e normalização das duas distribuições, coerência do rótulo humano) | M-01..M-08 | T01 |
| T03 | `repository.py`: schema, `exists`, `save`, `counts`, `add_usage`/`usage` | R-01..R-08, R-11 | T02 |
| T04 | `sources/arcgis.py`: `list_ids` (cache/TTL), `fetch`, mapeamento (incl. link da aplicação), retry, erros | A-01..A-10 | T00, T02 |
| T05 | `sources/registry.py` + `service.py`: rodízio de fontes, dedup, pendentes, confirm, skip | S-01..S-13 | T03, T04 |
| T06 | `translator.py`: protocolo, `NoneTranslator`, `GoogleTranslator`, fábrica, cache | T-01..T-04 | T01 |
| T06b | `deciders/`: protocolo, prompt da taxonomia, `GeminiDecider` (slot 1), `OpenRouterDecider` (slot 2), comportamento sem chave, cache, cotas (`usage.py`), fábrica por slot; integração no serviço e no repository | G-01..G-11, O-01..O-07, S-14..S-18, R-09, R-10 | T03, T05 |
| T06c | `advisor.py`: `GeminiAdvisor` (`gemini-3.5-flash-lite`), limitador 15 req/min · 25 000 tokens/min · 1 000 req/dia, `NoneAdvisor`, cache; `doubt` no serviço | H-01..H-08, S-19 | T03, T05, T06b |
| T07 | `api.py`: rotas (incl. `/api/decide`, `/api/doubt`, `/api/advisor`), códigos de erro, `create_app` injetável; `__main__.py` | I-01..I-19, I-21, I-22 | T05, T06, T06b, T06c |
| T08 | Frontend `static/`: layout, painéis dos dois modelos com percentuais, pré-marcação, botão Dúvida, cotas, diálogo, teclado | E-01..E-19 | T07 |
| T09 | Testes live opcionais | L-01..L-05 (quando a rede/chave permitir) | T04, T06b, T06c |
| T10 | `README.md` (instalar, rodar, testar, exportar), conferência do critério de conclusão | checklist do `GO_PROMPT.md` | T01..T08 |
| T12 | Deploy de teste na VPS 3: `Dockerfile`, `docker-compose.edge.yml`, `.env.example`, `/healthz`; branch `develop`; container `planlabel-oauth2` (oauth2-proxy, Google) e bloco `forward_auth` no Caddyfile compartilhado; `emails.txt` com os e-mails autorizados (pré-requisito do dono: [runbook google-oauth-setup](runbooks/google-oauth-setup.md)); registrar no `vps_infra` | I-20, D-01..D-06 | T07, T08 |
| T11 | Atualizar memória da conversa no Google Drive (skill `project-conversation-memory`) | — | T10 |
