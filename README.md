# ATLAS — Passagens Europa 2027

Monitor de passagens para dois adultos (Brasil → Europa), priorizando Barcelona e Madri sem ignorar Roma, Milão ou rotas multidestinos.

## Status da publicação

O arquivo [GitHub Actions](.github/workflows/atlas.yml) já está configurado com agendamento `17 */2 * * *` (UTC), equivalente a uma tentativa de execução a cada duas horas. **O código do backend e do frontend ainda precisa ser adicionado neste repositório antes da primeira execução bem-sucedida.** O workflow isolado não executa o bot.

## Instalação do código do ATLAS

Baixe o pacote completo v5.1 disponibilizado na conversa ChatGPT e extraia-o no Windows. Dentro da pasta `europa-passagens-gratis`, execute:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\PUBLICAR_NO_GITHUB.ps1
```

O script clona este repositório, copia os arquivos do projeto com exclusão de segredos, apresenta a lista de alterações e **pede a confirmação `PUBLICAR`** antes de fazer commit e push.

## Ativar pesquisas reais

Em **Settings > Secrets and variables > Actions**, crie `SERPAPI_KEY` com uma chave ativa de sua conta. **Nunca publique o arquivo `.env`.** Para os alertas, crie `MAIL_ENABLED=true`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_SSL`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM` e `ALERT_TO` (senha de aplicativo SMTP, se aplicável). Depois vá a **Actions > ATLAS - Passagens Europa > Run workflow**.

Cada evento automático ocorre a cada 2h, mas buscas reais são limitadas pelo intervalo de economia (padrão 8h) e pela cota gratuita da SerpApi. O SQLite e o build React são guardados como artefatos privados por 30 dias; baixe backups periodicamente.

## Dashboard

Este repositório está **privado**. GitHub Pages gratuito exige repositório público; não mudamos a visibilidade sem consentimento. A compilação React será guardada no artefato privado `atlas-dashboard`, não hospedada como website. O FastAPI não fica ligado 24h no GitHub Actions.

O GitHub Actions usa minutos de execução e armazenamento; verifique a franquia gratuita de sua conta.