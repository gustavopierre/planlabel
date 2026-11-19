# PRD — Rotulador de Planning Applications da Irlanda

**Versão:** 0.1 (rascunho para discussão) · **Data:** 2026-11-18 · **Dono:** Gustavo Pierre

## 1. Problema

Precisamos de um conjunto de dados **rotulado por humano** de planning applications da
República da Irlanda para treinar e fazer fine-tuning de um modelo de IA que classifique
descrições de empreendimentos por **subcategoria** e, a partir dela, por **categoria**
(**energia** / **não energia**). Subcategorias de energia: hybrid, wind, solar, bess, hydro,
substation, energy support, leu, data centre. Subcategorias de não energia: não energia e
baixa energia. Definições: [SPEC §1.1](SPEC.md#11-taxonomia-guia-de-rotulagem).

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
| `eplanning` | ePlanning / LGMA — IrishPlanningApplications (camada 0, pontos; a camada 1 tem as mesmas aplicações e não é usada) | `services.arcgis.com/NzlPQPKn5QF9v2US/.../IrishPlanningApplications/FeatureServer/0` | `ApplicationNumber` | `DevelopmentDescription` |

URLs completas em [SPEC.md §2](SPEC.md#2-fontes).

## 5. Fluxo do usuário (história principal)

1. O usuário abre o app → o sistema busca **uma** planning application aleatória e válida,
   que **ainda não existe** no banco, e a exibe.
2. A tela mostra: **número da aplicação**, **fonte**, **link** para a página da aplicação, **descrição** (em inglês), o
   **contador** de registros já rotulados e o uso do dia de cada modelo.
3. Logo após a exibição, **dois modelos decisores** analisam a descrição, cada um numa só
   chamada que julga primeiro a subcategoria e depois a categoria, de forma independente
   (as duas escolhas podem se contradizer; a tela avisa):
   modelo 1 = `gemini-decision-1` (API Gemini) e modelo 2 = `typesafe/jev-1.14` (OpenRouter).
   Cada um mostra o **percentual de todas as subcategorias e das duas categorias**, com a
   maior de cada uma em destaque. As sugestões, sozinhas, **não gravam nada**. Se um modelo
   (ou os dois) não entregar a sugestão por qualquer motivo, o painel dele fica apenas sem
   sugestão e o usuário segue.
4. O usuário pode clicar em **Traduzir** para ver a descrição em português (só leitura, não gravada).
5. Se tiver dúvida, o usuário pode clicar em **Dúvida** e ler a opinião do
   `gemini-3.5-flash-lite` (mesma chave do Gemini). O botão fica desabilitado enquanto um
   limite do modelo estiver atingido (15 req/min, 25 000 tokens/min ou 1 000 req/dia) e
   volta sozinho quando o limite libera.
6. O usuário tem a **decisão final**: escolhe primeiro a **categoria** (energia / não
   energia) e depois a **subcategoria**, numa lista filtrada só com as subcategorias daquela
   categoria. O rótulo humano nunca é contraditório.
7. **Confirmar** só fica habilitado com categoria e subcategoria escolhidas. Ao confirmar, o registro
   é salvo (com o rótulo do usuário e, separadas, as decisões dos dois modelos), o contador
   é atualizado e a próxima aplicação é carregada.
8. **Cancelar** abre a pergunta: **Encerrar** ou **Próxima**? Serve também para quando o
   usuário fica em dúvida, com ou sem ajuda dos modelos.
   - **Próxima** → descarta a aplicação atual (nada é gravado) e carrega outra.
   - **Encerrar** → encerra a rodada de rotulagem (tela final com o contador; nada pendente é gravado).

## 5.1 Histórias de usuário

Formato: *Como rotulador, quero … para …*. Cada história tem critérios de aceite
(Dado / Quando / Então) e os testes que os provam ([TDD.md §3](TDD.md#3-catálogo-de-testes)).
Uma história está pronta quando cumpre a [definição de pronto](TDD.md#6-definição-de-pronto).

**US-01 — Ver uma aplicação nova** · RF-01..RF-05, RF-12, RF-23
Como rotulador, quero ver uma planning application por vez, que eu ainda não rotulei,
para rotular sem repetir trabalho.
- Dado que abro ou recarrego o app, então vejo número, fonte, autoridade e descrição de uma aplicação válida.
- Dado que a aplicação sorteada já está no banco ou não tem número/descrição, então ela é descartada e outra aparece.
- Dado que a fonte tem link para a aplicação, então vejo "abrir aplicação ↗", e o link é gravado com o rótulo.
- Testes: S-01..S-04, S-12, A-03..A-06, A-10, M-06, I-03, I-14, E-01, E-09, E-19.

**US-02 — Rotular categoria e subcategoria** · RF-07..RF-09
Como rotulador, quero escolher primeiro a categoria (energia / não energia) e depois a
subcategoria daquela categoria, para gerar um rótulo coerente seguindo o guia da SPEC §1.1.
- Dado que não escolhi a categoria, então nenhuma subcategoria aparece.
- Quando escolho a categoria, então só aparecem as subcategorias dela; trocar a categoria limpa a subcategoria.
- Dado que falta categoria ou subcategoria, então Confirmar fica desabilitado; um par incoerente enviado à API é recusado.
- Quando confirmo, então o registro gravado tem exatamente os dados exibidos e a minha categoria e subcategoria.
- Testes: M-01..M-03, S-07, I-04..I-07, I-13, E-02..E-04.

**US-03 — Nunca gravar rótulo incompleto ou duplicado** · RF-02, RF-03, RF-10
Como dono do dataset, quero que o banco recuse rótulo incompleto e duplicata, para não
precisar limpar os dados depois.
- Dado um rótulo incompleto enviado à API ou inserido direto no SQLite, então ele é recusado.
- Dado que a mesma aplicação é confirmada duas vezes, então só um registro existe.
- Testes: R-02..R-05, S-08, S-09, S-11, I-06..I-10, E-07.

**US-04 — Traduzir a descrição** · RF-06
Como rotulador, quero ver a descrição em português quando precisar, sem perder o original.
- Quando clico em Traduzir (ou `T`), então vejo a tradução e posso voltar ao original.
- Dado que o tradutor falha, então aparece um aviso em linha e a rotulagem continua.
- Testes: T-01..T-04, I-12, E-05.

**US-05 — Pular ou encerrar** · RF-11
Como rotulador, quero pular uma aplicação ou encerrar a sessão sem gravar nada.
- Quando clico em Cancelar → Próxima, então outra aplicação aparece e nada é gravado.
- Quando clico em Cancelar → Encerrar, então vejo a tela final com o total e nada pendente é gravado.
- Dado que estou em dúvida, com ou sem ajuda dos modelos, então posso ir para a próxima ou encerrar a rodada.
- Testes: S-10, S-13, I-10, E-06, E-07, E-12.

**US-06 — Acompanhar o progresso** · RF-13
Como rotulador, quero ver o total rotulado (energia, não energia e por subcategoria).
- Quando confirmo um rótulo, então o contador sobe na hora, sem recarregar.
- Testes: R-06, R-07, I-02, I-04, I-05, E-03.

**US-07 — Continuar quando uma fonte cai** · RF-14
Como rotulador, quero continuar rotulando se uma fonte ArcGIS estiver fora do ar.
- Dado que uma fonte falha, então o app usa as outras.
- Dado que todas falham, então vejo uma mensagem clara e o botão Tentar de novo.
- Testes: A-07..A-09, S-05, S-06, I-11, E-10.

**US-08 — Ver a decisão dos dois modelos** · RF-15..RF-17
Como rotulador, quero ver o que o `gemini-decision-1` e o `typesafe/jev-1.14` decidiram, com
o percentual de cada subcategoria e categoria, para rotular mais rápido e com mais segurança.
- Quando as decisões chegam, então vejo dois painéis com os 11 percentuais de subcategoria e os 2 de categoria; a maior subcategoria e a maior categoria de cada modelo ficam em destaque, escolhidas de forma independente; se elas se contradizem, o painel mostra "⚠ contradição".
- Nada é gravado até eu confirmar; a decisão final é sempre minha.
- Dado que os dois modelos concordam na categoria e na subcategoria, então as duas vêm pré-marcadas; se concordam só na categoria, só a categoria vem pré-marcada; se divergem na categoria, nada é pré-marcado.
- Dado que já escolhi algo antes de as decisões chegarem, então minha escolha não é sobrescrita.
- Testes: M-04, M-05, M-07, M-08, G-01..G-03, G-06, G-07, O-01, O-02, S-14, S-15, S-18, I-15, I-17, I-18, E-11..E-14, E-18.

**US-09 — Rotular mesmo se um modelo falhar** · RF-18
Como rotulador, quero continuar rotulando quando um ou os dois modelos não entregam a sugestão.
- Dado erro, timeout, limite ou resposta inválida de um modelo, então o painel dele mostra só "sem sugestão", sem mensagem de erro, e o outro aparece normalmente.
- Testes: G-04, G-05, O-03, O-04, I-16, E-15.

**US-10 — Medir a concordância modelo × humano** · RF-19
Como dono do dataset, quero guardar as decisões dos dois modelos junto com o meu rótulo, e
saber qual modelo era o 1 e qual era o 2, para comparar os modelos mesmo depois de trocá-los.
- Quando confirmo, então o registro guarda o meu rótulo e, para o modelo 1 e o modelo 2, o nome do modelo (sempre preenchido) e um único campo de texto com a categoria e a subcategoria de maior percentual e os seus percentuais (mesmo se contraditórias); o campo de decisão fica em branco para o modelo que não respondeu.
- O cliente não consegue forjar o rótulo nem as decisões gravadas.
- Testes: R-09, R-10, S-16, S-17, I-19.

**US-11 — Acompanhar o uso dos modelos** · RF-20
Como rotulador, quero ver quantas requisições já fiz hoje a cada modelo e os limites, para
não ser surpreendido pelo fim da cota.
- Dado que o app está aberto, então vejo "gemini-decision-1 hoje N/10.000", "jev-1.14 hoje N" e "Dúvida N/1.000", atualizados a cada chamada.
- Dado que o `gemini-decision-1` chegou a 200/min ou 10 000/dia, então ele não é chamado e o painel mostra "limite diário atingido"; a rotulagem continua.
- Os contadores zeram no dia do provedor (meia-noite do Pacífico para o Gemini) e sobrevivem a reinícios.
- Testes: R-11, G-09..G-11, O-06, I-21, E-16.

**US-12 — Rotular só pelo teclado** · RNF-03
Como rotulador, quero rotular sem tirar a mão do teclado.
- `E`/`N` (categoria), `1–9` (subcategoria da categoria escolhida), `D`, `T`, `Enter` e `Esc` fazem o mesmo que os botões (SPEC §6.3).
- Testes: E-08.

**US-13 — Usar o ambiente de teste com login Google** · RNF-07
Como dono, quero abrir o app em `planlabel-test.bundoran.tech` com a minha conta Google, e
que ninguém fora da lista entre.
- Sem login, então nenhuma rota do app responde com dados.
- Com e-mail autorizado, então o app abre e grava; com outro e-mail, então 403.
- Reiniciar o container não perde registros.
- Testes: I-20, D-01..D-06.

**US-14 — Pedir uma opinião quando estou em dúvida** · RF-21
Como rotulador, quero pedir a opinião do `gemini-3.5-flash-lite` quando estou em dúvida, sem
estourar os limites do plano gratuito.
- Quando clico em Dúvida (ou `D`), então vejo a opinião em português, com a categoria e a subcategoria que o modelo escolheria e o porquê; nenhuma opção é marcada e nada é gravado.
- Dado que o limite de 15 req/min, 25 000 tokens/min ou 1 000 req/dia foi atingido, então o botão fica desabilitado, com o motivo e o horário de volta na dica.
- Quando o limite libera, então o botão volta a ficar habilitado sem recarregar a página.
- Testes: H-01..H-08, S-19, I-22, E-17.

**US-15 — Trocar os modelos sem mexer no código** · RF-22
Como dono, quero trocar o modelo do slot 1 ou do slot 2 por configuração, para testar outros
modelos em versões futuras.
- Dado que mudo `PLANLABEL_MODEL{1,2}_PROVIDER`/`_ID` no `.env`, então o app usa o novo modelo e os registros novos gravam o nome novo em `m1_model`/`m2_model`.
- Os dois slots sempre têm modelo; se faltar a chave de um, o painel dele fica sem sugestão e o app funciona normalmente.
- Os modelos ficam explícitos no `.env`; sem eles o app não sobe.
- Testes: G-08, O-05, O-07, I-21.

## 6. Requisitos funcionais

| ID | Requisito |
|---|---|
| RF-01 | Buscar **um** registro por vez, usando uma fonte por vez em rodízio (ABP → ePlanning), com um só rodízio para todos os usuários; dentro da fonte, registro aleatório. |
| RF-02 | Antes de exibir, verificar se o registro já existe no banco; se existir, descartar e buscar outro. |
| RF-03 | Nunca exibir uma aplicação que já está no banco. |
| RF-04 | Considerar inválido (e pular) registro sem número ou sem descrição (vazio/só espaços). |
| RF-05 | Exibir número, fonte e descrição da aplicação. |
| RF-06 | Botão **Traduzir** mostra a descrição em português; o original continua acessível. |
| RF-07 | Escolha obrigatória da **categoria** (`energy` / `not_energy`) e, depois, de exatamente **uma subcategoria daquela categoria** (lista filtrada). Rótulo humano incoerente é recusado na interface, na API e no banco. |
| RF-08 | A taxonomia da SPEC §1.1 é o guia de rotulagem e o conteúdo do prompt dos modelos decisores. |
| RF-09 | Confirmar salva: número, fonte, link, descrição, `category` e `subcategory` (e as decisões dos modelos, RF-19). |
| RF-10 | **Nunca** gravar no banco antes de o rótulo estar completo (regra garantida na API **e** no banco). |
| RF-11 | Cancelar → pergunta Encerrar / Próxima, com o comportamento do §5.6. |
| RF-12 | Ao abrir (ou recarregar) o app, uma nova aplicação válida é buscada. |
| RF-13 | Mostrar sempre o total de registros rotulados no banco, atualizado após cada confirmação (com divisão energia / não energia e por subcategoria). |
| RF-14 | Se uma fonte estiver indisponível, usar as outras; se todas falharem, mostrar erro claro com botão **Tentar de novo**. |
| RF-15 | Para cada aplicação exibida, pedir a **dois modelos decisores** (slot 1 `gemini-decision-1`, slot 2 `typesafe/jev-1.14`), numa só chamada cada, o percentual de cada subcategoria e, em seguida, de cada categoria, julgados de forma independente; mostrar os dois com todos os percentuais, destacando a maior subcategoria e a maior categoria e avisando quando elas se contradizem. |
| RF-16 | As decisões dos modelos **nunca** gravam rótulo; só o clique do usuário em Confirmar grava. |
| RF-17 | O usuário tem a decisão final. Pré-marcar categoria e subcategoria quando os dois modelos concordam nas duas; só a categoria quando concordam só nela; nada nos outros casos. |
| RF-18 | Se um modelo não entregar a sugestão (falha, timeout, limite, resposta inválida), o painel dele fica sem sugestão e a rotulagem segue normalmente. |
| RF-19 | Gravar junto com o rótulo humano, para o modelo 1 e o modelo 2, o nome do modelo em `m1_model`/`m2_model` (sempre preenchidos) e um único campo de texto com a categoria e a subcategoria de maior percentual e os seus percentuais, como vieram, mesmo se contraditórias (decidido pelo dono em 2026-11-19). |
| RF-20 | A interface mostra quantas requisições foram feitas no dia a cada modelo e os limites (slot 1: 200/min e 10 000/dia, dados oficiais do free tier). Modelo no limite não é chamado. |
| RF-21 | Botão **Dúvida**: mostra a opinião do `gemini-3.5-flash-lite` (mesma `GEMINI_API_KEY`). Desabilitado quando atingir 15 req/min, 25 000 tokens/min ou 1 000 req/dia; reabilitado sozinho quando o uso voltar ao normal. A opinião não é gravada. |
| RF-22 | O modelo de cada slot é trocável por configuração, sem mudar o código. |
| RF-23 | Mostrar e gravar o link da página pública da aplicação (`application_url`), quando a fonte permitir. |

## 7. Requisitos não funcionais

| ID | Requisito |
|---|---|
| RNF-01 | Backend em **Python 3.12+**; banco **SQLite** (arquivo local). |
| RNF-02 | Interface **minimalista**: uma tela, sem framework visual pesado, sem navegação. |
| RNF-03 | Atalhos de teclado para rotular sem mouse (ver SPEC §6.3). |
| RNF-04 | Desenvolvimento em **TDD**; cobertura ≥ 90 % no backend. |
| RNF-05 | Sem segredos no repositório; configuração por variáveis de ambiente. |
| RNF-07 | No ambiente de teste na internet (`https://planlabel-test.bundoran.tech`), acesso só com **login Google** de e-mails autorizados (oauth2-proxy na frente do app). |
| RNF-06 | Respeitar as fontes públicas: timeout, retry com backoff, no máximo poucas requisições por registro exibido. |

## 8. Fora de escopo (MVP)

Autenticação dentro do app (o login Google fica no oauth2-proxy, fora do código), multiusuário, edição/remoção de rótulos já gravados pela interface,
geometrias/mapa, Irlanda do Norte, gravação automática de rótulos por IA (a IA só sugere), gravação da opinião do botão Dúvida, exportação para
formatos de treino (JSONL etc.) — este último é o candidato natural para a v0.2.

## 9. Riscos

| Risco | Mitigação |
|---|---|
| Esquema das camadas muda | Verificado na T00 (SPEC §2); mapeamento de campos num só lugar (`FIELD_MAP`); testes live L-01. |
| `ApplicationNumber` não é único no país (o mesmo número existe em Laois e Offaly) | Chave de unicidade inclui a autoridade de planejamento (SPEC §3). |
| Nome exato ou acesso aos modelos (`gemini-decision-1`, `typesafe/jev-1.14`, `gemini-3.5-flash-lite`) diferente do esperado | Tarefa T00 lista os modelos disponíveis para cada chave; nomes configuráveis (SPEC §7). |
| Percentual "autodeclarado" pelo modelo não é probabilidade calibrada | Mostrado como indicação; gravar distribuição e rótulo humano permite medir a calibração depois. |
| Viés de ancoragem: o usuário tende a aceitar a sugestão | Pré-marcação só com os dois modelos de acordo; sugestões visivelmente marcadas; gravar decisões e rótulo separadamente (RF-19) permite medir e auditar a concordância. |
| Tradução depende de serviço externo | Interface `Translator` plugável; falha de tradução não bloqueia a rotulagem. |
| A mesma obra pode aparecer no ABP (recurso) e no ePlanning (pedido) | Aceito no MVP: são registros de fontes diferentes; documentado para o pipeline de treino. |

## 10. Definição de pronto do produto

Os níveis de pronto (tarefa, história e produto) estão em [TDD.md §6](TDD.md#6-definição-de-pronto).
O pronto do produto é o **critério de conclusão** C1–C16 do [`GO_PROMPT.md`](../GO_PROMPT.md),
a única fonte da verdade para "terminado".
