# Runbook — preparar a VPS 2 para desenvolver o Plan Labeler

**Objetivo:** deixar a VPS 2 (desenvolvimento) pronta para rodar o Claude Code, os testes
(incluindo E2E com Chromium) e o app localmente, com acesso às fontes ArcGIS e à API Gemini.

**Tempo estimado:** 20–30 minutos. **Quem executa:** o dono (SSH na VPS 2).

> Segredos (`GEMINI_API_KEY`, tokens do GitHub) nunca vão para o git, o chat ou prints.
> Só para o `.env` (`chmod 600`) ou para o gerenciador de credenciais do `gh`.

## Valores que você vai usar

| Item | Valor |
|---|---|
| VPS | VPS 2 — desenvolvimento (Hostinger) |
| Acesso SSH | usuário `gustavopierre`, atalho `dev-vps` no `~/.ssh/config` do AustraLaptop |
| Repositório | `https://github.com/gustavopierre/planlabel` |
| Pasta do projeto | `~/dev/planlabel` |
| Python | 3.12 ou mais novo |
| Hosts que precisam responder | `services-eu1.arcgis.com`, `services.arcgis.com`, `generativelanguage.googleapis.com`, `openrouter.ai`, `github.com`, `pypi.org` |

## Parte 1 — Entrar e conferir o sistema

1. Do seu PC:

   ```bash
   ssh dev-vps
   ```

2. Veja a versão do sistema e do Python (a ficha da VPS 2 no `vps_infra` ainda tem itens "to be confirmed"):

   ```bash
   lsb_release -ds; python3 --version; git --version
   ```

3. Atualize os pacotes e instale o básico:

   ```bash
   sudo apt update && sudo apt -y upgrade
   ```

   ```bash
   sudo apt install -y git curl sqlite3 build-essential ca-certificates
   ```

## Parte 2 — Python 3.12+ com `uv`

O `uv` instala a versão certa do Python sem depender da versão do Ubuntu.

4. Instale o `uv`:

   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

   ```bash
   source ~/.local/bin/env
   ```

5. Instale o Python 3.12:

   ```bash
   uv python install 3.12
   ```

## Parte 3 — GitHub

6. Instale o GitHub CLI (se ainda não houver):

   ```bash
   sudo apt install -y gh
   ```

7. Autentique (escolha **GitHub.com**, **HTTPS** e **Login with a web browser**; abra o link
   e digite o código mostrado no seu PC):

   ```bash
   gh auth login
   ```

   ```bash
   gh auth setup-git
   ```

8. Configure seu nome e e-mail de commit (se ainda não estiverem configurados):

   ```bash
   git config --global user.name "Gustavo Pierre"
   ```

   ```bash
   git config --global user.email "<seu e-mail do GitHub>"
   ```

## Parte 4 — Clonar o projeto

9. Clone o repositório:

   ```bash
   mkdir -p ~/dev && cd ~/dev && git clone https://github.com/gustavopierre/planlabel.git
   ```

10. Crie o branch de desenvolvimento (se ainda não existir no GitHub):

    ```bash
    cd ~/dev/planlabel && git switch -c develop && git push -u origin develop
    ```

    Se o `develop` já existir: `git switch develop`.

## Parte 5 — Conferir a rede (faz a T00 andar)

11. Fontes ArcGIS (as três devem mostrar um `"count"`):

    ```bash
    curl -s "https://services-eu1.arcgis.com/o56BSnENmD5mYs3j/ArcGIS/rest/services/Cases_2016_Onwards/FeatureServer/3/query?where=1%3D1&returnCountOnly=true&f=json"; echo
    ```

    ```bash
    curl -s "https://services.arcgis.com/NzlPQPKn5QF9v2US/ArcGIS/rest/services/IrishPlanningApplications/FeatureServer/1/query?where=1%3D1&returnCountOnly=true&f=json"; echo
    ```

    ```bash
    curl -s "https://services.arcgis.com/NzlPQPKn5QF9v2US/ArcGIS/rest/services/IrishPlanningApplications/FeatureServer/0/query?where=1%3D1&returnCountOnly=true&f=json"; echo
    ```

12. API Gemini responde (sem chave, deve voltar um erro `401`/`403` em JSON, e não um erro de conexão):

    ```bash
    curl -s -o /dev/null -w "%{http_code}\n" https://generativelanguage.googleapis.com/v1beta/models
    ```

## Parte 6 — Segredos do app (`.env`)

13. Crie a chave da API Gemini no Google AI Studio (<https://aistudio.google.com/apikey>),
    logado na sua conta Google. Copie a chave.
14. Grave no `.env` do projeto (o `.gitignore` deve listar `.env`; a T01 garante isso):

    ```bash
    cd ~/dev/planlabel && nano .env
    ```

    Conteúdo:

    ```dotenv
    GEMINI_API_KEY=<sua chave do AI Studio>
    OPENROUTER_API_KEY=<sua chave do OpenRouter>
    PLANLABEL_MODEL1_PROVIDER=gemini
    PLANLABEL_MODEL1_ID=gemini-decision-1
    PLANLABEL_MODEL2_PROVIDER=openrouter
    PLANLABEL_MODEL2_ID=typesafe/jev-1.14
    ```

    As chaves e os dois modelos são obrigatórios (o app não sobe sem os modelos). As outras
    variáveis (SPEC §7: limites, tradutor, banco, porta) já têm o padrão certo no código e só
    entram no `.env` se você quiser mudar algum valor.

    Sem aspas, sem espaços em volta do `=`. A chave do OpenRouter é criada em
    <https://openrouter.ai/settings/keys>.

    ```bash
    chmod 600 .env
    ```

15. Confirme que o modelo existe para a sua chave (deve listar `gemini-decision-1`):

    ```bash
    set -a; . ./.env; set +a; curl -s -H "x-goog-api-key: $GEMINI_API_KEY" https://generativelanguage.googleapis.com/v1beta/models | grep -o '"name": "models/[^"]*"' | grep -i decision
    ```

    Se não aparecer, anote o nome que aparece e informe na sessão (a SPEC usa
    `PLANLABEL_MODEL1_ID` justamente para isso).

## Parte 7 — Claude Code

16. Instale o Claude Code:

    ```bash
    curl -fsSL https://claude.ai/install.sh | bash
    ```

17. Abra na pasta do projeto e faça login com a sua conta Claude:

    ```bash
    cd ~/dev/planlabel && claude
    ```

18. Dentro do Claude Code, rode `/mcp` e confira se o **Google Drive** aparece entre os
    conectores (necessário para a skill de memória gravar no Drive). Se não aparecer, a
    memória é gravada localmente e copiada depois (ver `HANDOFF.md` §7).
19. Primeira mensagem: a do [HANDOFF §6](../HANDOFF.md#6-como-continuar-na-vps-2).

## Parte 8 — Depois da T01 (quando existir `pyproject.toml`)

20. Ambiente Python do projeto:

    ```bash
    cd ~/dev/planlabel && uv venv --python 3.12 && source .venv/bin/activate && uv pip install -e ".[dev]"
    ```

21. Navegador para os testes E2E (instala também as bibliotecas do sistema):

    ```bash
    playwright install --with-deps chromium
    ```

22. Rodar os testes e o app:

    ```bash
    pytest
    ```

    ```bash
    python -m planlabel
    ```

23. Ver o app no seu PC, por túnel SSH (o app fica só em `127.0.0.1` na VPS):

    ```bash
    ssh -L 8000:127.0.0.1:8000 dev-vps
    ```

    Depois abra <http://localhost:8000> no navegador do PC.

## Checklist final

- [ ] `ssh dev-vps` funciona.
- [ ] `uv python install 3.12` concluído.
- [ ] `gh auth status` mostra a conta logada; `git push` funciona.
- [ ] Repositório em `~/dev/planlabel`, no branch `develop`.
- [ ] As três chamadas ArcGIS devolvem `"count"`.
- [ ] `.env` com `GEMINI_API_KEY` e `OPENROUTER_API_KEY`, `chmod 600`; o modelo `gemini-decision-1` aparece na lista.
- [ ] Claude Code instalado e logado; Google Drive visível em `/mcp` (ou pendência anotada).
- [ ] Porta 8000 **não** aberta no firewall (`sudo ufw status` não lista 8000).

## Problemas comuns

| Sintoma | Causa | Correção |
|---|---|---|
| `curl` ArcGIS volta `{"error":...}` | Camada mudou de número ou de esquema | Anotar a resposta e informar na T00; ajustar `FIELD_MAP` e a SPEC |
| `curl` Gemini dá erro de conexão | Firewall de saída ou DNS da VPS | `curl -v https://generativelanguage.googleapis.com`; checar regras do provedor |
| Modelo não aparece na lista | Nome diferente ou chave sem acesso ao modelo | Usar o nome listado em `PLANLABEL_MODEL1_ID` (ou `PLANLABEL_MODEL2_ID` para o jev); conferir o projeto da chave no AI Studio |
| `playwright install --with-deps` falha | Ubuntu muito novo para o script de dependências | Rodar `playwright install chromium` e instalar as libs indicadas no erro com `apt` |
| `git push` pede senha | `gh auth setup-git` não rodou | Passo 7 |
| Claude Code sem Google Drive | Conectores do claude.ai não carregados nessa conta/sessão | Seguir sem Drive; a memória é gravada localmente e copiada depois |
