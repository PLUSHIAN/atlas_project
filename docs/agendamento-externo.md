# ATLAS — Agendador externo gratuito (redundância do GitHub Actions)

O agendador nativo do GitHub é **best effort** e pode atrasar/descartar execuções. Para ter um segundo serviço independente disparando o mesmo workflow, use [cron-job.org](https://cron-job.org/en/), que permite chamadas HTTPS POST com headers e corpo, no plano gratuito.

**Segurança:** use um token **fine-grained** do GitHub com acesso **somente** ao repositório `PLUSHIAN/atlas_project` e permissão **Actions: Read and write**. Nunca publique o token no código, no GitHub Pages ou no chat. Os headers serão armazenados no cron-job.org para executar os disparos: proteja a conta com senha forte e 2FA.

## 1. Criar o token restrito

Abra https://github.com/settings/personal-access-tokens/new e selecione:

- Resource owner: `PLUSHIAN`.
- Repository access: **Only select repositories** → `atlas_project`.
- Repository permissions → **Actions: Read and write**. Demais permissões: nenhuma além das obrigatórias.
- Expiration: escolha um prazo compatível e anote para renovar antes do vencimento.
- Crie e copie o token somente para a configuração privada do cron-job.org.

## 2. Cadastrar a chamada externa

Acesse https://console.cron-job.org/jobs e crie um cronjob:

**Nome**: `ATLAS Europa - backup 2h com 3 retries`

**URL**:
```text
https://api.github.com/repos/PLUSHIAN/atlas_project/actions/workflows/atlas.yml/dispatches
```

**Method**: `POST`

**Headers**:
```text
Accept: application/vnd.github+json
Authorization: Bearer SEU_TOKEN_RESTRITO
Content-Type: application/json
```

**Body (raw / JSON)**:
```json
{"ref":"main","inputs":{"source":"external","destination":"auto"}}
```

**Fuso para o cronjob**: `UTC`. **Horas selecionadas**: `0,2,4,6,8,10,12,14,16,18,20,22`. **Minutos selecionados**: `19,24,29,34`.

Com isso, a janela de backup das **09h de Brasília** corresponde a **12h19 / 12h24 / 12h29 / 12h34 UTC**, repetindo 2h depois. O GitHub continua tentando com seu agendamento nativo separado. Se o painel indicar que já houve uma consulta nos últimos 120 minutos, a nova execução será rápida e não gastará SerpApi.

> **Importante:** o cronjob faz uma requisição para iniciar um workflow, NÃO consulta passagens nem envia mensagens sozinho. Em caso de lentidão ou falha do GitHub na execução iniciada, o serviço externo não elimina a dependência dos runners do GitHub. Um HTTP 200/204 indica que o evento foi aceito, não que a pesquisa terminou. O status final aparece em Actions.

**Resultado esperado**: `2xx` (na API atual, pode retornar `200` com identificador da execução). Erros `401/403` indicam token ausente, inválido, expirado ou sem Actions write. Erros `404` podem indicar URL/workflow inválido ou permissão.

## 3. Testar e monitorar

1. No cron-job.org, use **Run now / Test** (se disponível).
2. No GitHub Actions, procure o evento **workflow_dispatch** com input `source=external` no job **Verificar janela sem consumir SerpApi**.
3. Se já houve consulta há menos de 2h, o passo `scan-build` é ignorado. Caso contrário, o job restaura o SQLite criptografado e consulta a SerpApi, respeitando a cota.
4. Habilite notificações de falha no cron-job.org. Renove o token antes da data de expiração.

**Não enviar o PAT em mensagens ou screenshots.** Se vazar, revogue imediatamente no GitHub.

## Agendamento de backup em horário de Brasília

| Rodada | Principal | Retry 1 | Retry 2 | Retry 3 |
| --- | --- | --- | --- | --- |
| 09h | 09h19 | 09h24 | 09h29 | 09h34 |
| 11h | 11h19 | 11h24 | 11h29 | 11h34 |
| 13h | 13h19 | 13h24 | 13h29 | 13h34 |
| 15h | 15h19 | 15h24 | 15h29 | 15h34 |

O cronjob repete o mesmo padrão todas as 12 janelas de 2 horas, inclusive de madrugada. As execuções **não** serão obrigatoriamente pesquisas: a proteção de duas horas e a cota de 250 da SerpApi continuam ativas.

Documentação:
- https://docs.github.com/en/rest/actions/workflows#create-a-workflow-dispatch-event
- https://cron-job.org/en/faq/
