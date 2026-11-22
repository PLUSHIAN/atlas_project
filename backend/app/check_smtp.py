"""Envia apenas email de TESTE SMTP, sem consultar preços nem criar cotação."""
import smtplib
import ssl
from email.message import EmailMessage
from .config import Settings


def main():
    config = Settings()
    if not config.smtp_ready:
        raise SystemExit('Configure MAIL_ENABLED=true e todos os campos SMTP em .env')
    msg = EmailMessage()
    msg['From'] = config.smtp_from
    msg['To'] = config.alert_to
    msg['Subject'] = '[Passagens Europa] Teste de configuração SMTP'
    msg.set_content('Este é apenas um teste da configuração SMTP do bot. Não é uma cotação nem uma oferta de passagens.')
    ctx = ssl.create_default_context()
    if config.smtp_ssl:
        with smtplib.SMTP_SSL(config.smtp_host, config.smtp_port, timeout=20, context=ctx) as server:
            if config.smtp_user:
                server.login(config.smtp_user, config.smtp_password)
            server.send_message(msg)
    else:
        with smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=20) as server:
            server.ehlo()
            server.starttls(context=ctx)
            server.ehlo()
            if config.smtp_user:
                server.login(config.smtp_user, config.smtp_password)
            server.send_message(msg)
    print('SMTP aceitou o e-mail de teste. Confirme na caixa de entrada/destinatário.')


if __name__ == '__main__':
    main()
