"""Execução pontual em runners temporários do GitHub Actions. Sem servidor."""
import argparse
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from .main import db, monitor, settings

COMPLETED = {'cotado','somente_indicativo','resultados_descartados','sem_resultado','parcial'}

def should_scan(now=None, min_hours=None):
    """Permite pesquisa a cada 2h, respeitando apenas o teto de créditos da SerpApi."""
    now = now or datetime.now(timezone.utc)
    min_hours = int(min_hours if min_hours is not None else os.environ.get('CLOUD_MIN_SCAN_HOURS','2'))
    if min_hours < 2:
        raise ValueError('CLOUD_MIN_SCAN_HOURS deve ser >= 2')
    recent = db.recent_checks(100)
    for item in recent:
        if item['status'] in COMPLETED:
            last = datetime.fromisoformat(item['checked_at'])
            if now - last < timedelta(hours=min_hours):
                return False, f'Janela de economia: última busca efetiva {item["checked_at"]} (mínimo {min_hours}h)'
            break
    if db.requests_in_30d() >= settings.max_30d_requests - 1:
        return False, 'Limite local de segurança para o mês; sem novas pesquisas'
    return True, 'Nova rodada elegível'

def should_scan_scheduled(now=None):
    """Evita duas consultas efetivas no mesmo slot (cron principal + retentativa).

    Os horários UTC ímpares equivalem às horas pares de Brasília.
    Consultas manuais ANTERIORES ao slot não bloqueiam a busca agendada.
    """
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    slot_start = now.replace(minute=0, second=0, microsecond=0)
    if slot_start.hour % 2 == 0:
        slot_start -= timedelta(hours=1)
    for item in db.recent_checks(100):
        if item['status'] not in COMPLETED:
            continue
        checked = datetime.fromisoformat(item['checked_at'])
        if checked.tzinfo is None:
            checked = checked.replace(tzinfo=timezone.utc)
        if slot_start <= checked.astimezone(timezone.utc) <= now:
            return False, 'Esta janela agendada já tem uma pesquisa efetiva; retentativa sem consumo'
    if db.requests_in_30d() >= settings.max_30d_requests - 1:
        return False, 'Limite local de segurança de consultas; sem novas pesquisas'
    return True, 'Janela agendada disponível para busca'


def main(argv=None):
    parser = argparse.ArgumentParser(description='ATLAS GitHub Actions')
    parser.add_argument('--destination',default='auto',choices=[
        'auto','Barcelona','Madri','Roma','Milão','Roma → Milão','Milão → Roma'])
    args = parser.parse_args(argv)
    if not settings.serpapi_key:
        print('SERPAPI_KEY ausente. Defina GitHub Actions Secret SERPAPI_KEY.', file=sys.stderr)
        return 2
    # Cron principal e contingência compartilham o mesmo slot de 2h.
    # Execuções manuais mantêm o controle de cadência próprio.
    if args.destination == 'auto':
        allowed, reason = (should_scan_scheduled()
                           if os.environ.get('GITHUB_EVENT_NAME') == 'schedule'
                           else should_scan())
        if not allowed:
            print(json.dumps({'status':'aguardando_cota','message':reason},ensure_ascii=False))
            return 0
    result = monitor.scan_once(destination=None if args.destination=='auto' else args.destination)
    print(json.dumps(result,ensure_ascii=False,default=str))
    return 1 if result.get('status') in ('erro','ocupado') else 0

if __name__ == '__main__':
    raise SystemExit(main())
