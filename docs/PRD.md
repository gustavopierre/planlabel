# PRD — Rotulador de Planning Applications da Irlanda

**Versão:** 0.1 (rascunho para discussão) · **Data:** 2026-11-18 · **Dono:** Gustavo Pierre

## 1. Problema

Precisamos de um conjunto de dados **rotulado por humano** de planning applications da
República da Irlanda para treinar e fazer fine-tuning de um modelo de IA que classifique
descrições de empreendimentos como **energia / não energia** e, quando energia, por
**categoria** (hybrid, wind, solar, bess, leu).

As descrições existem em serviços ArcGIS públicos, mas não têm esse rótulo. Rotular em
planilha é lento e sujeito a erro (duplicidade, rótulo incompleto). Queremos uma
ferramenta mínima que apresente **uma aplicação por vez**, colete o rótulo e grave
somente registros completos.

## 2. Objetivo e métricas de sucesso

| Objetivo | Métrica |
|---|---|
| Rotular rápido | ≤ 2 cliques + 1 confirmação por registro; nova aplicação exibida em < 3 s (p95) |
| Dados limpos | 0 registros duplicados; 0 registros com rótulo incompleto (garantido por constraint) |
| Dataset utilizável | Exportação direta do SQLite (sem pós-processamento para deduplicar ou validar) |

## 3. Usuário

Um único rotulador (o próprio Gustavo), rodando localmente. Não há login nem
multiusuário no MVP.

## 4. Fontes de dados

| Código (`source`) | Serviço | Camada | Campo nº | Campo descrição |
|---|---|---|---|---|
| `abp` | An Bord Pleanála / An Coimisiún Pleanála — Cases 2016 Onwards | `services-eu1.arcgis.com/o56BSnENmD5mYs3j/.../Cases_2016_Onwards/FeatureServer/3` | `ABPCASEID` | `DEVDESC` |
| `epl_1` | ePlanning / LGMA — IrishPlanningApplications | `services.arcgis.com/NzlPQPKn5QF9v2US/.../IrishPlanningApplications/FeatureServer/1` | `ApplicationNumber` | `DevelopmentDescription` |
| `epl_0` | ePlanning / LGMA — IrishPlanningApplications | `services.arcgis.com/NzlPQPKn5QF9v2US/.../IrishPlanningApplications/FeatureServer/0` | `ApplicationNumber` (a confirmar) | `DevelopmentDescription` (a confirmar) |

URLs completas em [SPEC.md §2](SPEC.md#2-fontes).

## 5. Fluxo do usuário (história principal)

1. O usuário abre o app → o sistema busca **uma** planning application aleatória e válida,
   que **ainda não existe** no banco, e a exibe.
2. A tela mostra: **número da aplicação**, **fonte**, **descrição** (em inglês) e o
   **contador** de registros já rotulados.
3. O usuário pode clicar em **Traduzir** para ver a descrição em português (a tradução é
   só para leitura e não é gravada).
4. O usuário escolhe **Energia** ou **Não energia**.
   - Se **Energia**, precisa escolher **uma** categoria: `hybrid`, `wind`, `solar`, `bess`, `leu`.
5. **Confirmar** só fica habilitado quando as escolhas obrigatórias estão feitas.
   Ao confirmar, o registro é salvo, o contador é atualizado e a próxima aplicação é carregada.
6. **Cancelar** abre a pergunta: **Encerrar** ou **Próxima**?
   - **Próxima** → descarta a aplicação atual (nada é gravado) e carrega outra.
   - **Encerrar** → encerra a sessão de rotulagem (tela final com o contador; nada pendente é gravado).

## 6. Requisitos funcionais

| ID | Requisito |
|---|---|
| RF-01 | Buscar **um** registro por vez, aleatoriamente, entre as três fontes. |
| RF-02 | Antes de exibir, verificar se o registro já existe no banco; se existir, descartar e buscar outro. |
| RF-03 | Nunca exibir uma aplicação que já está no banco. |
| RF-04 | Considerar inválido (e pular) registro sem número ou sem descrição (vazio/só espaços). |
| RF-05 | Exibir número, fonte e descrição da aplicação. |
| RF-06 | Botão **Traduzir** mostra a descrição em português; o original continua acessível. |
| RF-07 | Escolha obrigatória Energia / Não energia. |
| RF-08 | Se Energia, escolha obrigatória de exatamente uma categoria entre `hybrid`, `wind`, `solar`, `bess`, `leu`. |
| RF-09 | Confirmar salva: número, fonte, descrição, `energy` (True/False) e `category` (null se não energia). |
| RF-10 | **Nunca** gravar no banco antes de o rótulo estar completo (regra garantida na API **e** no banco). |
| RF-11 | Cancelar → pergunta Encerrar / Próxima, com o comportamento do §5.6. |
| RF-12 | Ao abrir (ou recarregar) o app, uma nova aplicação válida é buscada. |
| RF-13 | Mostrar sempre o total de registros rotulados no banco, atualizado após cada confirmação (com divisão energia / não energia e por categoria). |
| RF-14 | Se uma fonte estiver indisponível, usar as outras; se todas falharem, mostrar erro claro com botão **Tentar de novo**. |

## 7. Requisitos não funcionais

| ID | Requisito |
|---|---|
| RNF-01 | Backend em **Python 3.12+**; banco **SQLite** (arquivo local). |
| RNF-02 | Interface **minimalista**: uma tela, sem framework visual pesado, sem navegação. |
| RNF-03 | Atalhos de teclado para rotular sem mouse (ver SPEC §6.3). |
| RNF-04 | Desenvolvimento em **TDD**; cobertura ≥ 90 % no backend. |
| RNF-05 | Sem segredos no repositório; configuração por variáveis de ambiente. |
| RNF-06 | Respeitar as fontes públicas: timeout, retry com backoff, no máximo poucas requisições por registro exibido. |

## 8. Fora de escopo (MVP)

Autenticação, multiusuário, edição/remoção de rótulos já gravados pela interface,
geometrias/mapa, Irlanda do Norte, rotulagem automática por IA, exportação para
formatos de treino (JSONL etc.) — este último é o candidato natural para a v0.2.

## 9. Riscos

| Risco | Mitigação |
|---|---|
| Esquema das camadas `epl_0`/`epl_1` diferente do esperado | Tarefa T00 verifica os esquemas reais antes de codar o adaptador; mapeamento de campos fica em configuração. |
| `ApplicationNumber` não é único no país (o mesmo número existe em Laois e Offaly) | Chave de unicidade inclui a autoridade de planejamento (SPEC §3). |
| Tradução depende de serviço externo | Interface `Translator` plugável; falha de tradução não bloqueia a rotulagem. |
| A mesma obra pode aparecer no ABP (recurso) e no ePlanning (pedido) | Aceito no MVP: são registros de fontes diferentes; documentado para o pipeline de treino. |

## 10. Definição de pronto do produto

Ver o **critério de conclusão** em [`GO_PROMPT.md`](../GO_PROMPT.md) — é a única fonte
da verdade para "terminado".
