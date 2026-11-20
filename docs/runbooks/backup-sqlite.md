# Runbook — backup e restauração do SQLite (VPS 3 → Google Drive)

**Objetivo:** ligar o backup diário do dataset (`labels.sqlite3`) para o Google Drive,
conferir que ele funciona e, quando preciso, restaurar uma cópia.

**Quem executa:** o dono, por SSH na VPS 3. Sessões de IA escrevem os comandos e o dono cola
a saída (regra do `vps_infra`).

**Tempo estimado:** 10 minutos para ligar; 5 minutos para restaurar.

> O `rclone.conf` guarda o token do Google Drive: é um segredo. Nunca no git, no chat ou em print.

## Como funciona

- Container `planlabel-backup` (`Dockerfile.backup`, código em `planlabel/backup.py`), no
  mesmo compose do app (`docker-compose.edge.yml`), montando o mesmo volume de dados.
- Todo dia às **02:00 (Europe/Dublin)**: cópia consistente com a API de backup do SQLite
  (o app pode estar rodando), `PRAGMA integrity_check` na cópia, gzip, envio com `rclone`
  para **`gdrive:planlabel-test-backups`** e remoção das cópias com mais de **60 dias**.
- Se falhar, tenta de novo a cada 5 minutos dentro da mesma hora. O último sucesso fica em
  `/app/data/backup-last-ok`.
- **Conta Google:** a mesma do backup do LO Engagement (`gustavo.pierre@planenergy.com`,
  escopo `drive.file`). O `rclone.conf` é uma **cópia** do que o LO Engagement de teste já usa
  na VPS 3; não precisa autorizar de novo. Cada sistema escreve e poda só a sua pasta.

## Valores que você vai usar

| Item | Valor |
|---|---|
| SSH | `ssh deploy@31.97.113.166` |
| Código / compose | `~/planlabel`, `docker-compose.edge.yml`, serviço `planlabel-backup` |
| Credencial do Drive | `/opt/planlabel/rclone/rclone.conf` (dono UID 10001, modo 600) — cópia de `/opt/lo-engagement/rclone/rclone.conf` |
| Destino | `gdrive:planlabel-test-backups` (pasta `planlabel-test-backups` no Drive da conta acima) |
| Horário / retenção | `BACKUP_HOUR=2` em `TZ=Europe/Dublin` / `BACKUP_RETENTION=60d` |
| Nome dos arquivos | `planlabel_AAAA-MM-DD_HHMM.sqlite3.gz` |

Para atalhar os comandos abaixo, na VPS 3:

```bash
cd ~/planlabel && alias dc='docker compose -f docker-compose.edge.yml'
```

## Parte 1 — Credencial do Drive (uma vez)

1. Confira que o `rclone.conf` do LO Engagement tem o remote `gdrive` (mostra só os nomes):

   ```bash
   grep '^\[' /opt/lo-engagement/rclone/rclone.conf
   ```

   Esperado: `[gdrive]`. Se o arquivo não existir, o backup do LO de teste não está
   configurado; siga o runbook 05 do projeto `planenergy` (passo 4) apontando para
   `/opt/planlabel/rclone/rclone.conf` em vez de copiar.

2. Copie para a pasta do Plan Labeler com posse do usuário do container (UID 10001). A cópia
   é feita dentro de um container descartável, o que dispensa `sudo` e funciona mesmo se o
   Docker já tiver criado a pasta como root:

   ```bash
   docker run --rm -v /opt/lo-engagement/rclone/rclone.conf:/src:ro -v /opt/planlabel/rclone:/c alpine sh -c 'cp /src /c/rclone.conf && chown -R 10001:10001 /c && chmod 700 /c && chmod 600 /c/rclone.conf && ls -ln /c'
   ```

   Esperado: uma linha `-rw------- 1 10001 10001 ... rclone.conf`.

## Parte 2 — Subir o container

3. Atualize o código e suba (o app e o oauth2-proxy não são recriados se não mudaram):

   ```bash
   git pull --ff-only && dc up -d --build planlabel-backup
   ```

4. Confira a mensagem de início:

   ```bash
   dc logs --tail 5 planlabel-backup
   ```

   Esperado: `backup service up (db=/app/data/labels.sqlite3 remote=gdrive:planlabel-test-backups hour=2 retention=60d tz=Europe/Dublin)`.

## Parte 3 — Testar agora (B-12)

5. Rode um backup na hora:

   ```bash
   dc exec planlabel-backup python /backup.py --now
   ```

   Esperado: `backup ok: planlabel_AAAA-MM-DD_HHMM.sqlite3.gz (N rótulos, ... bytes) enviado`.
   Se o app ainda não criou o banco: `backup skip` — abra o site uma vez e repita.

6. Liste o que está no Drive:

   ```bash
   dc exec planlabel-backup rclone lsl gdrive:planlabel-test-backups
   ```

   A pasta também aparece no Google Drive da conta, pelo navegador.

## Restaurar uma cópia

O banco atual **não é apagado**: vai para `/app/data/pre-restore-AAAA-MM-DD_HHMM/`.

7. Escolha o arquivo (passo 6) e pare o app e o backup:

   ```bash
   dc stop planlabel planlabel-backup
   ```

8. Restaure (troque o nome do arquivo):

   ```bash
   dc run --rm planlabel-backup python /backup.py --restore planlabel_AAAA-MM-DD_HHMM.sqlite3.gz
   ```

   Esperado: `restore ok: ... restaurado (N rótulos); anterior em /app/data/pre-restore-...`.
   Se der `restore error`, nada foi alterado.

9. Suba de novo e confira o total na tela:

   ```bash
   dc up -d
   ```

10. Quando tiver certeza de que está tudo certo, apague a pasta `pre-restore-*`:

    ```bash
    dc exec planlabel-backup sh -c 'ls -d /app/data/pre-restore-*' && dc exec planlabel-backup sh -c 'rm -r /app/data/pre-restore-AAAA-MM-DD_HHMM'
    ```

## Checklist final

- [ ] `/opt/planlabel/rclone/rclone.conf` existe, com dono 10001 e modo 600.
- [ ] `dc ps` mostra `planlabel-backup` running.
- [ ] `--now` deu `backup ok` e o arquivo aparece em `rclone lsl`.
- [ ] No dia seguinte, `dc logs planlabel-backup` mostra a linha `backup ok` das 02:0x.
- [ ] Registrado no `vps_infra` (`current/vps-3-test.md`, seção do Plan Labeler: destino,
      retenção e conta), numa sessão daquele projeto.

## Problemas comuns

| Sintoma | Causa | Correção |
|---|---|---|
| `backup waiting: /config/rclone.conf não existe` | Parte 1 não feita ou feita em outra pasta | Refaça a Parte 1 e `dc restart planlabel-backup` |
| `Permission denied` no `rclone.conf` | Dono não é o UID 10001 | Repita o passo 2 |
| `envio ao Google Drive falhou` + `invalid_grant` no log | Token revogado ou autorização expirada | Reautorize (runbook 05 do `planenergy`, passo 4) no arquivo do LO e copie de novo (Parte 1) |
| `backup skip` todo dia | O app nunca criou o banco | Abra o site uma vez; o schema é criado na subida |
| Drive cheio | Cota da conta | Reduza `BACKUP_RETENTION` (variável no shell antes do `dc up -d`) ou libere espaço |
