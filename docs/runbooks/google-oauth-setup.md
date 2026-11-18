# Runbook — autorização de login Google (Google Cloud Console)

Objetivo: criar a credencial OAuth que o **oauth2-proxy** usa para exigir login com conta
Google em `https://planlabel-test.bundoran.tech` (ver [ARCHITECTURE.md §5](../ARCHITECTURE.md#5-deploy-de-teste--vps-3-httpsplanlabel-testbundorantech)).

Tempo estimado: 15 minutos. Custo: zero (login Google não é cobrado).

> **Regra de ouro:** o *Client Secret* e o *Cookie Secret* nunca vão para o git, para o
> chat com a IA, para e-mail ou para print. Eles vão **só** para o arquivo `.env` na VPS 3
> (e, se quiser, para o seu gerenciador de senhas).

> **Sobre os nomes na tela:** o Google reorganizou o console em 2025. A área de OAuth hoje
> se chama **Google Auth Platform** (menus *Branding*, *Público-alvo*/*Audience*,
> *Clientes*/*Clients*, *Acesso a dados*/*Data access*). Em contas com a interface antiga,
> o mesmo fica em **APIs e serviços › Tela de consentimento OAuth** e
> **APIs e serviços › Credenciais**. Os passos são os mesmos; só os nomes dos menus mudam.

---

## Valores que você vai usar (copie daqui)

| Campo | Valor |
|---|---|
| Nome do projeto | `planlabel` |
| Nome do app (tela de consentimento) | `Plan Labeler` |
| Tipo de público | **Externo** (*External*) |
| Domínio autorizado | `bundoran.tech` |
| Página inicial do app | `https://planlabel-test.bundoran.tech` |
| Tipo de cliente OAuth | **Aplicativo da Web** (*Web application*) |
| Nome do cliente | `planlabel-test oauth2-proxy` |
| URI de redirecionamento autorizado | `https://planlabel-test.bundoran.tech/oauth2/callback` |
| Origens JavaScript autorizadas | *(deixar vazio)* |
| Escopos | `openid`, `.../auth/userinfo.email`, `.../auth/userinfo.profile` (todos não sensíveis) |

---

## Parte 1 — Criar o projeto

1. Abra <https://console.cloud.google.com/> logado com a **sua conta Google principal**
   (a mesma que vai usar para entrar no app).
2. Se for o primeiro acesso, aceite os Termos de Serviço. **Não** é preciso ativar
   faturamento nem cadastrar cartão.
3. No topo da página, clique no **seletor de projeto** (ao lado do logotipo
   "Google Cloud") › **Novo projeto** (*New project*).
4. Preencha:
   - **Nome do projeto:** `planlabel`
   - **Organização/Local:** *Sem organização* (*No organization*), se aparecer.
5. Clique em **Criar** e espere a notificação (sino, canto superior direito).
6. No seletor de projeto, **selecione `planlabel`**. Confira que o nome aparece no topo
   antes de seguir — é comum criar a credencial no projeto errado.

## Parte 2 — Tela de consentimento (Google Auth Platform)

7. Menu ☰ › **APIs e serviços** › **Tela de consentimento OAuth**
   (ou pesquise "Google Auth Platform" na barra de busca do console).
8. Clique em **Começar** (*Get started*). O assistente tem 4 etapas:
   1. **Informações do app:**
      - *Nome do app:* `Plan Labeler`
      - *E-mail de suporte do usuário:* a sua conta Google.
      - **Próxima**.
   2. **Público-alvo:** marque **Externo** (*External*). **Próxima**.
      (*Interno* só existe para contas Google Workspace com organização; não se aplica.)
   3. **Dados de contato:** o seu e-mail. **Próxima**.
   4. **Concluir:** marque que concorda com a *Política de dados do usuário dos serviços
      de API do Google* › **Continuar** › **Criar**.
9. Menu lateral **Branding** (identidade visual) — opcional, mas recomendado:
   - *Página inicial do aplicativo:* `https://planlabel-test.bundoran.tech`
   - *Domínios autorizados* › **Adicionar domínio** › `bundoran.tech`
   - Deixe o logotipo em branco (enviar logotipo exige verificação do Google).
   - **Salvar**.

## Parte 3 — Público-alvo e usuários de teste

10. Menu lateral **Público-alvo** (*Audience*). O *Status de publicação* estará em
    **Teste** (*Testing*).
11. Em **Usuários de teste** › **Adicionar usuários** › digite o seu e-mail Google
    (e de qualquer outra pessoa que vá rotular) › **Salvar**.
    Em modo Teste, **só** as contas desta lista conseguem completar o login.
12. Decisão sobre o modo:
    - **Ficar em Teste (recomendado para começar):** funciona na hora. Ao entrar, o Google
      mostra o aviso *"O Google não verificou este app"* — clique em **Continuar**. Em modo
      Teste o consentimento expira em cerca de 7 dias, então de vez em quando o login será
      pedido de novo.
    - **Publicar (opcional, depois):** botão **Publicar app** › confirmar. Como o app usa só
      escopos não sensíveis (e-mail e perfil), não exige o processo de verificação. Qualquer
      conta Google consegue *autenticar*, mas o **oauth2-proxy continua barrando** quem não
      estiver no `emails.txt` — o controle de acesso real é dele.

## Parte 4 — Escopos (opcional)

13. Menu lateral **Acesso a dados** (*Data access*) › **Adicionar ou remover escopos**.
14. Marque `openid`, `.../auth/userinfo.email` e `.../auth/userinfo.profile` ›
    **Atualizar** › **Salvar**. (O oauth2-proxy pede esses três; declarar é só boa
    prática — o login funciona mesmo sem este passo.)
    **Não** adicione nenhum outro escopo (Drive, Gmail etc.).

## Parte 5 — Criar o cliente OAuth (a credencial)

15. Menu lateral **Clientes** (*Clients*) › **Criar cliente** (*Create client*).
    (Interface antiga: **APIs e serviços › Credenciais › Criar credenciais › ID do cliente OAuth**.)
16. **Tipo de aplicativo:** **Aplicativo da Web** (*Web application*).
17. **Nome:** `planlabel-test oauth2-proxy` (só para você identificar).
18. **Origens JavaScript autorizadas:** deixe **vazio**.
19. **URIs de redirecionamento autorizados** › **Adicionar URI** › cole exatamente:

    ```
    https://planlabel-test.bundoran.tech/oauth2/callback
    ```

    Atenção: `https`, sem barra no final, sem `www`, tudo minúsculo. Qualquer diferença
    gera o erro `redirect_uri_mismatch`.
20. Clique em **Criar**.
21. Abre uma janela com o **ID do cliente** (*Client ID*, termina em
    `.apps.googleusercontent.com`) e a **Chave secreta do cliente** (*Client secret*,
    começa com `GOCSPX-`).
    - Clique em **Fazer download do JSON** e guarde o arquivo num lugar seguro do seu PC
      (fora de qualquer pasta de repositório git).
    - **Copie o Client Secret agora:** o console atual **não mostra o segredo de novo**
      depois que você fecha a janela. Se perder, é preciso criar um novo segredo
      (Parte 8).
22. Alterações no cliente podem levar de 5 minutos a algumas horas para valerem no Google.

## Parte 6 — Gerar o Cookie Secret (na VPS 3)

23. No seu PC, entre na VPS 3:

    ```bash
    ssh deploy@31.97.113.166
    ```

24. Gere 32 bytes aleatórios no formato que o oauth2-proxy aceita:

    ```bash
    openssl rand -base64 32 | tr -- '+/' '-_'
    ```

    Copie a saída (uma linha de ~44 caracteres). Esse é o `OAUTH2_PROXY_COOKIE_SECRET`.

## Parte 7 — Gravar os segredos na VPS 3

25. Ainda na VPS 3, crie a pasta do app e o `.env`:

    ```bash
    mkdir -p ~/planlabel/oauth2 && cd ~/planlabel
    ```

    ```bash
    nano .env
    ```

    Conteúdo (substitua os `<...>`; não use aspas):

    ```dotenv
    # --- oauth2-proxy (login Google) ---
    OAUTH2_PROXY_PROVIDER=google
    OAUTH2_PROXY_CLIENT_ID=<ID do cliente>.apps.googleusercontent.com
    OAUTH2_PROXY_CLIENT_SECRET=<GOCSPX-...>
    OAUTH2_PROXY_COOKIE_SECRET=<saída do openssl>
    OAUTH2_PROXY_REDIRECT_URL=https://planlabel-test.bundoran.tech/oauth2/callback
    OAUTH2_PROXY_AUTHENTICATED_EMAILS_FILE=/etc/oauth2-proxy/emails.txt
    OAUTH2_PROXY_HTTP_ADDRESS=0.0.0.0:4180
    OAUTH2_PROXY_REVERSE_PROXY=true
    OAUTH2_PROXY_SET_XAUTHREQUEST=true
    OAUTH2_PROXY_COOKIE_SECURE=true
    OAUTH2_PROXY_UPSTREAMS=static://202

    # --- app ---
    GEMINI_API_KEY=<sua chave da API Gemini>
    ```

    Salve com `Ctrl+O`, `Enter`, e saia com `Ctrl+X`.

26. Crie a lista de e-mails autorizados (um por linha):

    ```bash
    nano ~/planlabel/oauth2/emails.txt
    ```

27. Proteja os arquivos:

    ```bash
    chmod 600 ~/planlabel/.env ~/planlabel/oauth2/emails.txt
    ```

28. Pronto da sua parte. A tarefa **T12** do `GO_PROMPT.md` sobe os containers
    `planlabel` e `planlabel-oauth2` (o compose monta `~/planlabel/oauth2/emails.txt` em
    `/etc/oauth2-proxy/emails.txt`) e adiciona o bloco no Caddyfile compartilhado.

## Parte 8 — Manutenção

- **Adicionar/remover quem pode entrar:** edite `~/planlabel/oauth2/emails.txt` e rode
  `docker compose -f docker-compose.edge.yml restart planlabel-oauth2`. Em modo Teste,
  adicione a pessoa também em *Usuários de teste* (Parte 3).
- **Trocar o Client Secret** (vazou ou perdeu): Google Auth Platform › **Clientes** ›
  `planlabel-test oauth2-proxy` › **Adicionar segredo** › atualize o `.env` › reinicie o
  `planlabel-oauth2` › volte e **desative/exclua o segredo antigo**.
- **Produção futura** (`planlabel.bundoran.tech`): adicione um segundo URI de
  redirecionamento `https://planlabel.bundoran.tech/oauth2/callback` no mesmo cliente,
  ou crie um cliente separado (recomendado).

## Checklist final

- [ ] Projeto `planlabel` criado e selecionado.
- [ ] Tela de consentimento: Externo, nome `Plan Labeler`, domínio `bundoran.tech`.
- [ ] Seu e-mail em *Usuários de teste*.
- [ ] Cliente "Aplicativo da Web" com o URI `https://planlabel-test.bundoran.tech/oauth2/callback`.
- [ ] Client ID e Client Secret guardados (JSON baixado, fora do git).
- [ ] `~/planlabel/.env` na VPS 3 preenchido, `chmod 600`.
- [ ] `~/planlabel/oauth2/emails.txt` com os e-mails autorizados, `chmod 600`.
- [ ] Nenhum segredo colado no chat, em commit ou em print.

## Problemas comuns

| Sintoma | Causa | Correção |
|---|---|---|
| `Erro 400: redirect_uri_mismatch` | URI no cliente diferente do usado | Conferir o passo 19 letra por letra; esperar alguns minutos após salvar |
| `Erro 403: access_denied` / "app em teste" | Conta não está em *Usuários de teste* | Passo 11 (ou publicar o app, passo 12) |
| Aviso "O Google não verificou este app" | Normal em modo Teste | Clicar em **Continuar** |
| Login Google funciona, mas aparece 403 do oauth2-proxy | E-mail não está no `emails.txt` | Passo 26 e reiniciar `planlabel-oauth2` |
| Login em loop (volta sempre para o Google) | Cookie secret inválido ou `COOKIE_SECURE` sem HTTPS | Regerar o cookie secret (passo 24); acessar sempre por `https://` |
| `invalid_client` | Client ID/Secret trocados ou com espaço | Conferir o `.env` (sem aspas, sem espaços) |

Referências: documentação do oauth2-proxy (provedor Google) —
<https://oauth2-proxy.github.io/oauth2-proxy/configuration/providers/google> ·
OAuth 2.0 para apps web (Google) — <https://developers.google.com/identity/protocols/oauth2/web-server>.
