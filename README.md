# Plan Labeler — dados rotulados de Planning Applications da Irlanda

Web app minimalista para rotular, uma por vez, planning applications irlandesas
(An Bord Pleanála e ePlanning/LGMA) como **energia / não energia** e por **categoria**
(hybrid, wind, solar, bess, leu). O resultado (SQLite) alimenta treino e fine-tuning de modelos de IA.

**Status:** documentação pronta; implementação pendente (ver [`GO_PROMPT.md`](GO_PROMPT.md)).

| Documento | Conteúdo |
|---|---|
| [docs/PRD.md](docs/PRD.md) | problema, fluxo, requisitos (RF/RNF) |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | arquitetura proposta e pontos **[DECIDIR]** |
| [docs/SPEC.md](docs/SPEC.md) | fontes, schema SQLite, API, interface |
| [docs/TDD.md](docs/TDD.md) | catálogo de testes e rastreabilidade |
| [docs/TASKS.md](docs/TASKS.md) | tarefas T00–T11 |
| [GO_PROMPT.md](GO_PROMPT.md) | prompt de execução com critério de conclusão |
| [LEIA_ME_memoria_no_drive.md](LEIA_ME_memoria_no_drive.md) | onde está a memória das conversas |
