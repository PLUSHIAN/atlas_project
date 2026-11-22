"""Execução pontual em runners temporários do GitHub Actions. Sem servidor."""
import argparse
import json
import os
import sys
from pathlib import Path
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

    Os horários UTC pares equivalem às horas ímpares de Brasília (19h, 21h...).
    Consultas manuais ANTERIORES ao slot não bloqueiam a busca agendada.
    """
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    slot_start = now.replace(minute=0, second=0, microsecond=0)
    if slot_start.hour % 2 == 1:
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



def write_run_report(result, searched):
    """Relatório público apenas de status; nunca inclui credenciais ou dados brutos."""
    path = os.environ.get('ATLAS_RUN_REPORT', '').strip()
    if not path:
        return
    data = {
        'event': os.environ.get('GITHUB_EVENT_NAME', 'local'),
        'run_id': os.environ.get('GITHUB_RUN_ID', ''),
        'at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'status': str(result.get('status', 'erro'))[:48],
        'searched': bool(searched),
        'destination': str(result.get('destination') or '')[:64],
        'message': str(result.get('message') or '')[:240]
    }
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')



def main(argv=None):
    parser = argparse.ArgumentParser(description='ATLAS GitHub Actions')
    parser.add_argument('--destination',default='auto',choices=[
        'auto','Barcelona','Madri','Roma','Milão','Roma → Milão','Milão → Roma'])
    args = parser.parse_args(argv)
    if not settings.serpapi_key:
        message = 'SERPAPI_KEY ausente. Defina GitHub Actions Secret SERPAPI_KEY.'
        print(message, file=sys.stderr)
        write_run_report({'status': 'erro', 'message': message}, searched=False)
        return 2
    # Cron principal, 3 contingências e o disparo inicial por push compartilham
    # o mesmo slot de 2h. Execuções manuais mantêm a própria cadência.
    if args.destination == 'auto':
        allowed, reason = (should_scan_scheduled()
                           if os.environ.get('GITHUB_EVENT_NAME') in ('schedule', 'push')
                           else should_scan())
        if not allowed:
            report = {'status':'aguardando_cota','message':reason}
            write_run_report(report, searched=False)
            print(json.dumps(report, ensure_ascii=False))
            return 0
    before_requests = db.requests_in_30d()
    result = monitor.scan_once(destination=None if args.destination=='auto' else args.destination)
    new_requests = db.requests_in_30d() - before_requests
    write_run_report(result, searched=new_requests > 0)
    print(json.dumps(result,ensure_ascii=False,default=str))
    return 1 if result.get('status') in ('erro','ocupado') else 0

if __name__ == '__main__':
    raise SystemExit(main())
