# Runbook — subir e atualizar o teste na VPS 3 (`planlabel-test.bundoran.tech`)

**Objetivo:** pôr o Plan Labeler no ar na VPS 3 (teste), atrás do Caddy compartilhado e do
login Google (oauth2-proxy), e atualizá-lo quando o branch `develop` mudar.

**Quem executa:** o dono, por SSH na VPS 3. Pela regra do `vps_infra`, sessões de IA **não**
rodam nada na VPS 3: elas escrevem os comandos e o dono cola a saída.

**Tempo estimado:** 15–20 minutos na primeira vez; 2 minutos nas atualizações.

> Segredos nunca vão para o git, o chat ou prints. Só para `/opt/planlabel/*.env` (`chmod 600`).

## Pré-requisitos

- [ ] Registro DNS `planlabel-test.bundoran.tech` → `31.97.113.166` (feito em 2026-11-18).
- [ ] Credencial OAuth criada e `/opt/planlabel/oauth2.env` + `/opt/planlabel/emails.txt`
      gravados: [runbook google-oauth-setup](google-oauth-setup.md), Partes 1–7.
- [ ] `GEMINI_API_KEY` e `OPENROUTER_API_KEY` à mão (as mesmas da VPS 2 servem).

## Valores que você vai usar

| Item | Valor |
|---|---|
| SSH | `ssh deploy@31.97.113.166` |
| Código | `/home/deploy/planlabel` (clone do branch `develop`; o repositório é público) |
| Segredos | `/opt/planlabel/app.env` (app), `/opt/planlabel/oauth2.env` (login), `/opt/planlabel/emails.txt` |
| Compose | `docker-compose.edge.yml` (projeto `planlabel-test`; containers `planlabel` e `planlabel-oauth2`) |
| Rede | `edge` (externa, já existe); apelidos `planlabel` e `planlabel-oauth2`; **nenhuma porta publicada** |
| Dados | volume Docker `planlabel-test_planlabel_data` (SQLite em `/app/data/labels.sqlite3`) |

## Parte 1 — Código

1. Entre na VPS 3:

   ```bash
   ssh deploy@31.97.113.166
   ```

2. Clone o repositório no branch `develop`:

   ```bash
   cd ~ && git clone --branch develop https://github.com/gustavopierre/planlabel.git
   ```

## Parte 2 — Segredos do app

3. Crie o `app.env` a partir do modelo do repositório:

   ```bash
   cp ~/planlabel/.env.example /opt/planlabel/app.env && chmod 600 /opt/planlabel/app.env && nano /opt/planlabel/app.env
   ```

   Preencha `GEMINI_API_KEY=` e `OPENROUTER_API_KEY=` (sem aspas, sem espaços em volta do
   `=`). Deixe as linhas `PLANLABEL_MODEL*` e `PLANLABEL_ADVISOR_ID` como estão.

4. Confira que os três arquivos existem (o comando mostra só nomes e permissões):

   ```bash
   ls -l /opt/planlabel/
   ```

   Esperado: `app.env` e `oauth2.env` com `-rw-------`, `emails.txt` com `-rw-r--r--`.

## Parte 3 — Subir os containers

5. Construa e suba:

   ```bash
   cd ~/planlabel && docker compose -f docker-compose.edge.yml up -d --build
   ```

6. Espere uns 30 s e confira (os dois devem estar `running`; o `planlabel`, `healthy`):

   ```bash
   docker compose -f docker-compose.edge.yml ps
   ```

## Parte 4 — Caddy compartilhado

7. Acrescente o bloco abaixo ao fim de `/opt/edge/Caddyfile`:

   ```bash
   nano /opt/edge/Caddyfile
   ```

   ```caddyfile
   # Plan Labeler (project planlabel), test instance, behind Google login (oauth2-proxy).
   planlabel-test.bundoran.tech {
   	encode zstd gzip
   	header {
   		Strict-Transport-Security "max-age=31536000"
   		X-Content-Type-Options "nosniff"
   		X-Frame-Options "DENY"
   		Referrer-Policy "strict-origin-when-cross-origin"
   		X-Robots-Tag "noindex, nofollow"
   		-Server
   	}
   	handle /oauth2/* {
   		reverse_proxy planlabel-oauth2:4180 {
   			header_up X-Real-IP {remote_host}
   			header_up X-Forwarded-Uri {uri}
   		}
   	}
   	handle {
   		forward_auth planlabel-oauth2:4180 {
   			uri /oauth2/auth
   			copy_headers X-Auth-Request-User X-Auth-Request-Email
   			@bad status 4xx
   			handle_response @bad {
   				redir * /oauth2/start?rd={scheme}://{host}{uri}
   			}
   		}
   		reverse_proxy planlabel:8000
   	}
   }
   ```

8. Valide e recarregue o Caddy (sem derrubar os outros sites):

   ```bash
   docker exec edge-caddy caddy validate --config /etc/caddy/Caddyfile && docker exec edge-caddy caddy reload --config /etc/caddy/Caddyfile
   ```

9. Registre a mudança no projeto `vps_infra`: copie o mesmo bloco para
   `vps-3/edge/Caddyfile` do repositório `vps-infra` e atualize a ficha
   `current/vps-3-test.md` (nova aplicação, compose `planlabel-test`, segredos em
   `/opt/planlabel/`). Isso é feito numa sessão do `vps_infra`, não daqui.

## Parte 5 — Verificar (testes D-01..D-06 do TDD)

Do seu PC:

10. **D-01** — sem login, a raiz redireciona para o login Google:

    ```bash
    curl -sI https://planlabel-test.bundoran.tech/ | grep -iE "^(HTTP|location)"
    ```

    Esperado: `HTTP/2 302` e `location: .../oauth2/start?...`.

11. **D-02** — sem login, a API não entrega dados:

    ```bash
    curl -s -o /dev/null -w "%{http_code}\n" https://planlabel-test.bundoran.tech/api/next
    ```

    Esperado: `302` ou `401` (nunca `200`).

12. **D-03** (manual) — abra <https://planlabel-test.bundoran.tech> no navegador, entre com
    um e-mail da lista, rotule uma aplicação e confira que o contador sobe.

13. **D-04** (manual) — numa janela anônima, entre com uma conta Google **fora** da lista.
    Esperado: página 403 do oauth2-proxy.

14. **D-05** — as portas do app não estão expostas:

    ```bash
    curl -s --max-time 5 http://31.97.113.166:8000/ ; echo "exit $?"
    ```

    ```bash
    curl -s --max-time 5 http://31.97.113.166:4180/ ; echo "exit $?"
    ```

    Esperado: os dois falham (exit diferente de 0).

15. **D-06** — na VPS 3, reiniciar não perde registros:

    ```bash
    cd ~/planlabel && docker compose -f docker-compose.edge.yml restart planlabel && sleep 10 && docker compose -f docker-compose.edge.yml exec planlabel python -c "from planlabel.repository import Repository; print(Repository('/app/data/labels.sqlite3').counts().total)"
    ```

    Esperado: o mesmo total que aparecia na tela antes do reinício.

## Atualizar (novo commit no `develop`)

```bash
cd ~/planlabel && git pull --ff-only && docker compose -f docker-compose.edge.yml up -d --build
```

O volume `planlabel_data` é mantido; o schema é criado/conferido na subida.

## Ver logs

```bash
cd ~/planlabel && docker compose -f docker-compose.edge.yml logs -f --tail 100 planlabel
```

## Checklist final

- [ ] `docker compose ... ps`: `planlabel` healthy e `planlabel-oauth2` running.
- [ ] Bloco no `/opt/edge/Caddyfile` validado e recarregado; cópia registrada no `vps_infra`.
- [ ] D-01..D-06 conferidos.
- [ ] `docker port planlabel-test-planlabel-1` e `docker port planlabel-test-planlabel-oauth2-1` não mostram nada.

## Problemas comuns

| Sintoma | Causa | Correção |
|---|---|---|
| `planlabel` reinicia em loop; log diz `model1_provider Field required` | `app.env` sem as linhas `PLANLABEL_MODEL*` | Copie de novo do `.env.example` e preencha só as chaves |
| `network edge declared as external, but could not be found` | Rede do Caddy compartilhado não existe | `docker network create edge` (normalmente já existe) |
| Login volta para o Google em loop | `OAUTH2_PROXY_COOKIE_SECRET` com tamanho errado ou cookie bloqueado | Gere de novo (runbook OAuth, Parte 6) e reinicie `planlabel-oauth2` |
| `403` para o seu próprio e-mail | E-mail fora de `/opt/planlabel/emails.txt` ou do modo Teste do Google | Corrija a lista e `restart planlabel-oauth2`; confira *Usuários de teste* |
| `redirect_uri_mismatch` no Google | URI do cliente OAuth diferente | Tem de ser exatamente `https://planlabel-test.bundoran.tech/oauth2/callback` |
| Tradução sempre indisponível | Google Translate bloqueia IP de datacenter e a cota anônima do MyMemory acabou | Rotular sem tradução; a cota do MyMemory volta no dia seguinte |
| Painel "sem sugestão" em todas as aplicações | Chave ausente ou errada em `app.env` | Corrija e `up -d` de novo; confira `logs planlabel` |
