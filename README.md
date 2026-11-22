# ATLAS — Passagens Europa 2027

Monitor pessoal de passagens para dois adultos com prioridade para Barcelona e Madri, incluindo Roma, Milão e multidestinos.

## Ativação do GitHub Pages (quando o repositório for público)

O workflow já publica o React via `actions/deploy-pages@v4` se o repositório estiver público.

**Antes de mudar a visibilidade:** crie em **Settings > Secrets and variables > Actions** o secret `ATLAS_STATE_KEY` com pelo menos 32 caracteres aleatórios e execute uma vez o workflow ainda com o repositório privado. Confirme que o artefato `atlas-state-encrypted` foi criado. Atenção: os novos workflows **não recuperam automaticamente bancos antigos** armazenados em artefatos `atlas-state`. Exclua os antigos artefatos `atlas-state` sem criptografia antes de tornar o repositório público; eles podem conter histórico e dados pessoais.

Depois acesse **Settings > General > Danger Zone > Change repository visibility > Make public**. Em **Settings > Pages**, escolha **Build and deployment > Source > GitHub Actions**. Rode **Actions > ATLAS - Passagens Europa > Run workflow** e verifique o link [ATLAS no GitHub Pages](https://plushian.github.io/atlas_project/).

**O frontend será público e somente leitura.** O backend FastAPI continuará executando apenas durante o Actions, não como serviço 24h.

## GitHub Actions (agendamento e armazenamento)

- `.github/workflows/atlas.yml` é acionado a cada 2 horas (horas ímpares em Brasília: 19h12, 21h12, 23h12 etc., retentativas aos minutos 17, 22 e 27), com tentativa de pesquisa a cada execução (intervalo mínimo de 2h).
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


## Black Friday 2026: cadência reforçada

O workflow roda com `CLOUD_MIN_SCAN_HOURS=2`, `MAX_REQUESTS_30D=250` e `CACHE_HOURS=1`, priorizando Espanha. Não há mais janela obrigatória de 8 horas. O agendamento GitHub `17 */2 * * *` é em UTC e pode atrasar ou eventualmente falhar; o monitor não garante execução no minuto exato. O robô para de consultar quando a conta não tiver créditos gratuitos ou o teto local for atingido, sem gerar cobranças. Como cada rodada pode consumir duas ou três consultas, 12 rodadas diárias podem consumir até aproximadamente 24 a 36 créditos/dia.


## Google Flights: alertas gratuitos oficiais

O ATLAS agora mostra **cobertura por destino e data**, separa tarifas indicativas de viagens completas e distribui a fila para explorar as quatro datas antes de repetir a mesma saída. A aba **Alertas Google** oferece buscas já preenchidas: selecione o aeroporto de saída (GRU/CGH/VCP ou GIG/SDU), o destino (incluindo MXP/BGY/LIN para Milão) e clique em uma das duas datas de volta. Os links montam uma busca textual do Google Flights com ida, volta, 2 adultos, econômica e BRL. O Google pode reinterpretar o filtro de passageiros: confira a pesquisa ao abrir.

**Importante:** o ATLAS **não ativa automaticamente** os acompanhamentos de preços do Google. Para receber os avisos oficiais, abra https://www.google.com/travel/flights?hl=pt-BR com sua conta Google, escolha origem, destino, datas, 2 adultos, econômica e ative **Acompanhar preços**. Repita para as rotas que desejar. O Google envia os avisos diretamente para o Gmail vinculado à conta; o ATLAS não recebe nem importa esses avisos automaticamente. O Google controla quando avisa, sem prazo fixo. Não usamos scraping ou APIs não oficiais do Google Flights.

Para começar com melhor cobertura, habilite Barcelona e Madri com GRU e GIG para idas em 08, 09, 10 e 11/09/2027 e retornos que permitam **chegar ao Brasil no 17º dia**. Depois acrescente Roma, Milão e VCP/CGH/SDU. As datas de saída da Europa podem ser D+15 ou D+16, dependendo do voo e da conexão.

Os e-mails **do ATLAS** continuam independentes e são disparados por cotações completas verificadas via SerpApi até R$ 8.000 para o casal.


## Execuções automáticas e contingências (novembro 2026)

- A primeira implantação deste agendamento executa automaticamente pelo evento `push` quando `.github/workflows/atlas.yml` é atualizado na `main`. O evento é **push**, não **schedule**; para validar a agenda espere aparecer uma execução `Scheduled`.
- O cron principal roda às 19h12, 21h12, 23h12, 01h12 etc. (horário de Brasília) e existem **três tentativas extras** aos minutos 17, 22 e 27 de cada janela, todas gratuitas no GitHub Actions para repositórios públicos conforme as condições do serviço.
- O histórico SQLite impede repetir uma pesquisa **concluída** no mesmo ciclo. Os retries só consultam a fonte se não houver consulta efetiva gravada no ciclo; o custo em créditos SerpApi pode aumentar se as buscas falharem repetidamente.
- GitHub Actions pode atrasar ou descartar **todas** as tentativas; não existe SLA ou garantia de início pontual. Para identificar a origem no log, procure `Evento: push` (automático por commit), `Evento: schedule` (automático por cron) ou `Evento: workflow_dispatch` (manual).
- Para verificar: https://github.com/PLUSHIAN/atlas_project/actions/workflows/atlas.yml . Pesquisas e e-mails dependem dos Secrets e da cota disponível.


## Google Flights: links preenchidos e contabilidade da API (novembro/2026)

- A aba **Alertas Google** monta links de pesquisa com o parâmetro `tfs` (dados codificados de origem, destino, ida, volta, dois adultos e econômica) e moeda `BRL`. Diferentemente do parâmetro `q`, ignorado pelo Google Flights nos testes de tela, `tfs` contém a estrutura da pesquisa.
- `tfs` é um formato interno **não documentado oficialmente pelo Google** e pode mudar. O ATLAS **não faz scraping nem acessa o Google automaticamente**. Ao abrir o link, confira os filtros e ative **Acompanhar preços** manualmente.
- Os cartões mostram agora **USO MENSAL DA SERPAPI** a partir do endpoint oficial de conta (`this_month_usage`, `searches_per_month` e `plan_searches_left`), não a contagem do SQLite. Se o saldo da fonte estiver indisponível, exibem **—**, sem substituir por um número local enganoso.
- A contagem `used_requests_30d` continua sendo uma trava **independente** dos últimos 30 dias do ATLAS; não deve coincidir com o ciclo mensal da SerpApi nem incluir consumos realizados fora do ATLAS.
- Para alterar agendamento, preservar a cota de 250 pesquisas mensais do plano gratuito; consultas de ida e volta podem consumir duas ou mais chamadas.
