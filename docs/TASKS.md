# Tarefas

Cada tarefa segue o ciclo red → green → refactor do [TDD.md](TDD.md). "Pronto" de uma
tarefa = testes listados verdes + `ruff` limpo + commit feito.

| ID | Tarefa | Testes que precisam passar | Depende de |
|---|---|---|---|
| T00 | **Verificar esquemas** das 3 camadas (`?f=json`), registrar campos reais em `docs/SPEC.md §2` e gravar fixtures em `tests/fixtures/arcgis/`. Se `epl_0`/`epl_1` não forem acessíveis do ambiente, registrar o bloqueio e usar o esquema da SPEC. | — (documental) | — |
| T01 | Esqueleto: `pyproject.toml` (deps, ruff, pytest, cobertura), pacote `planlabel/`, `tests/conftest.py`, `.gitignore` (`data/`, `.venv/`) | `pytest` roda (0 testes) | — |
| T02 | `models.py`: `Category`, `Application`, `Label` | M-01..M-06 | T01 |
| T03 | `repository.py`: schema, `exists`, `save`, `counts` | R-01..R-08 | T02 |
| T04 | `sources/arcgis.py`: `list_ids` (cache/TTL), `fetch`, mapeamento, retry, erros | A-01..A-09 | T00, T02 |
| T05 | `sources/registry.py` + `service.py`: sorteio, dedup, pendentes, confirm, skip | S-01..S-13 | T03, T04 |
| T06 | `translator.py`: protocolo, `NoneTranslator`, `GoogleTranslator`, fábrica, cache | T-01..T-04 | T01 |
| T07 | `api.py`: rotas, códigos de erro, `create_app` injetável; `__main__.py` | I-01..I-14 | T05, T06 |
| T08 | Frontend `static/`: layout, estados, diálogo, teclado | E-01..E-10 | T07 |
| T09 | Testes live opcionais | L-01, L-02 (quando a rede permitir) | T04 |
| T10 | `README.md` (instalar, rodar, testar, exportar), conferência do critério de conclusão | checklist do `GO_PROMPT.md` | T01..T08 |
| T11 | Atualizar memória da conversa no Google Drive (skill `project-conversation-memory`) | — | T10 |
