import logging
import smtplib
import ssl
from email.message import EmailMessage
from .trip import classification

log = logging.getLogger(__name__)


def format_brl(amount):
    return 'R$ ' + f'{amount:,.2f}'.replace(',','X').replace('.',',').replace('X','.')


def create_message(settings, offer, extras):
    price = offer['price_couple']
    msg = EmailMessage()
    msg['From'] = settings.smtp_from
    msg['To'] = settings.alert_to
    msg['Subject'] = f"[Passagens Europa] {classification(price)} | {format_brl(price)} o casal"
    detail = 'Não disponível: nenhuma tarifa adicional confirmada.'
    if extras:
        t = extras.get('estimated_total')
        detail = ('Estimativas informadas manualmente: ' + (format_brl(t) if t is not None else 'incompletas') +
                  '. Não são ofertas nem comprovam conexão. ' + extras.get('mode',''))
    text = f'''Cotação consultada via {offer['source']} em {offer['seen_at']}.

{classification(price)}
Passagens INTERNACIONAIS para 2 adultos (ida e volta): {format_brl(price)}
Valor médio matemático por adulto: {format_brl(price / 2)}
Origem: {offer['origin']} | Entrada na Europa: {offer['destination']}
Saída da Europa: {offer.get('return_origin') or offer['destination']} | Modalidade: {offer.get('journey_type','round_trip')}
Ida: {offer['departure']} | Retorno parte da Europa: {offer['return_departure']}
Chegada ao Brasil: {offer['arrival_home']} (17 dias corridos desde a saída)
Companhia(s): {offer['airline'] or 'Não informada'}
Escalas: ida {offer['stops_out']}; volta {offer['stops_back']}
Duração: ida {offer['duration_out'] or '?'} min; volta {offer['duration_back'] or '?'} min
Bagagem: {offer['baggage']}
Taxas/observações: {offer['remarks']}

Deslocamento adicional necessário (Espanha–Itália ou Roma–Milão): {detail}
Link de PESQUISA/CONFERÊNCIA (não garante a mesma tarifa): {offer['search_url']}
Tipo do link: {offer['url_type']}

IMPORTANTE: preço obtido por API, mas não reservado. Confirme valores, bagagens, taxas,
conexões, disponibilidade e eventuais bilhetes separados antes de comprar.
Não inclua o custo de deslocamento da Espanha no limite de R$ 8.000.
'''
    msg.set_content(text)
    return msg


def send_mail(settings, offer, extras=None):
    if not settings.smtp_ready:
        raise RuntimeError('SMTP incompleto ou alertas desabilitados')
    message = create_message(settings,offer,extras)
    context = ssl.create_default_context()
    if settings.smtp_ssl:
        with smtplib.SMTP_SSL(settings.smtp_host,settings.smtp_port,timeout=20,context=context) as srv:
            if settings.smtp_user: srv.login(settings.smtp_user,settings.smtp_password)
            srv.send_message(message)
    else:
        with smtplib.SMTP(settings.smtp_host,settings.smtp_port,timeout=20) as srv:
            srv.ehlo()
            srv.starttls(context=context)
            srv.ehlo()
            if settings.smtp_user: srv.login(settings.smtp_user,settings.smtp_password)
            srv.send_message(message)
    log.info('Alerta SMTP aceito: %s',offer['itinerary_key'])
