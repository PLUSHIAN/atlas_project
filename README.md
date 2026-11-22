# ATLAS — Passagens Europa 2027

Monitor pessoal de passagens para dois adultos com prioridade para Barcelona e Madri, incluindo Roma, Milão e multidestinos.

## Ativação do GitHub Pages (quando o repositório for público)

O workflow já publica o React via `actions/deploy-pages@v4` se o repositório estiver público.

**Antes de mudar a visibilidade:** crie em **Settings > Secrets and variables > Actions** o secret `ATLAS_STATE_KEY` com pelo menos 32 caracteres aleatórios e execute uma vez o workflow ainda com o repositório privado. Confirme que o artefato `atlas-state-encrypted` foi criado. Atenção: os novos workflows **não recuperam automaticamente bancos antigos** armazenados em artefatos `atlas-state`. Exclua os antigos artefatos `atlas-state` sem criptografia antes de tornar o repositório público; eles podem conter histórico e dados pessoais.

Depois acesse **Settings > General > Danger Zone > Change repository visibility > Make public**. Em **Settings > Pages**, escolha **Build and deployment > Source > GitHub Actions**. Rode **Actions > ATLAS - Passagens Europa > Run workflow** e verifique o link [ATLAS no GitHub Pages](https://plushian.github.io/atlas_project/).

**O frontend será público e somente leitura.** O backend FastAPI continuará executando apenas durante o Actions, não como serviço 24h.

## GitHub Actions (agendamento e armazenamento)

- `.github/workflows/atlas.yml` é acionado a cada 2 horas (UTC, minuto 17), mas só pesquisa quando a janela de economia permite (8h por padrão).
- O GitHub executa o backend pontualmente, **não hospeda FastAPI permanentemente**.
- O histórico SQLite é restaurado e salvo como artefato criptografado `atlas-state-encrypted` por até 30 dias. `ATLAS_STATE_KEY` é obrigatório; mantenha uma cópia segura da chave e faça backups periódicos.
- O React é compilado em modo estático e entregue como artefato `atlas-dashboard`. Quando o repositório for público e Pages estiver ativado, também será publicado como website.
- A mudança da visibilidade para público deve ser feita pelo proprietário na interface do GitHub; a integração de código não oferece essa configuração.

## Configurar a primeira execução

Em `Settings > Secrets and variables > Actions`, crie `SERPAPI_KEY` (obrigatório para consultas). Para alertas, crie `MAIL_ENABLED=true`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_SSL`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, `ALERT_TO`. Não adicione segredos ao código.

Em `Actions > ATLAS - Passagens Europa > Run workflow`, selecione `auto`. O resultado e o banco privado ficam nos artefatos da execução. Para visualizar o painel localmente, use as instruções abaixo.

**Custo:** execuções em repositórios privados consomem a franquia GitHub Actions do seu plano. O bot limita pesquisas SerpApi para reduzir o consumo, mas o agendamento pode atrasar e o GitHub não garante custo zero após exceder a franquia.

## VS Code no Windows

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

Novo terminal:

```powershell
cd frontend
npm install
npm run dev
```

Painel local: `http://127.0.0.1:5173`. A versão para GitHub gera arquivos em `frontend/dist`, baixáveis na execução Actions. Para visualizar com dados atualizados, use o artifact `atlas-dashboard`.

Execute testes locais: `python -m pip install -r backend/requirements-dev.txt; python -m pytest backend/tests -q`.

Nunca envie `.env`, bancos locais, `.venv` ou senhas ao GitHub. A chave publicada previamente em chat deve ter sido substituída.
