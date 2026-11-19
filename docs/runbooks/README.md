# Runbooks

Procedimentos operacionais passo a passo, para serem seguidos por uma pessoa (ou por uma
sessão de IA) sem precisar ler o resto da documentação.

**Convenções**
- Um arquivo por procedimento, nome em `kebab-case` (`acao-alvo.md`).
- Estrutura: objetivo · pré-requisitos · valores a usar · passos numerados · checklist final · problemas comuns.
- Segredos nunca aparecem no runbook — só os nomes das variáveis e onde guardá-las.
- Quando o procedimento mudar, atualize o runbook no mesmo commit da mudança.

| Runbook | Quando usar | Quem executa |
|---|---|---|
| [google-oauth-setup.md](google-oauth-setup.md) | Criar a credencial de login Google do oauth2-proxy e gravar os segredos na VPS 3 | Dono (Google Cloud Console + SSH na VPS 3) |
| [setup-dev-vps2.md](setup-dev-vps2.md) | Preparar a VPS 2 (desenvolvimento): Python, GitHub, rede, `.env`, Claude Code, testes | Dono (SSH na VPS 2) |
| `deploy-vps3.md` *(a criar na T12)* | Subir/atualizar o app de teste em `planlabel-test.bundoran.tech` | Dono ou sessão com SSH |
| `backup-sqlite.md` *(a criar)* | Backup e restauração do dataset SQLite da VPS 3 | Dono |
