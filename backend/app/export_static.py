"""Exporta APENAS dados do dashboard para o site estático. Nunca exportar chaves."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from . import main as api

# O GitHub Pages publica dados para qualquer pessoa com o link.
# Nunca serializar anotações livres, respostas cruas da API ou segredos.
PRIVATE_FIELDS = {'notes', 'data_json', 'api_key', 'departure_token',
                  'smtp_user', 'smtp_password', 'smtp_from', 'alert_to',
                  'serpapi_key', 'app_api_token'}

def public_only(value):
    if isinstance(value, dict):
        return {k: public_only(v) for k, v in value.items() if k.lower() not in PRIVATE_FIELDS}
    if isinstance(value, list):
        return [public_only(v) for v in value]
    return value

def create_snapshot():
    # Somente objetos explicitamente selecionados; não exportar dados JSON crus da API.
    overview = api.overview()
    monitor = overview['monitor']
    monitor['enabled'] = True  # Agenda externa via GitHub Actions; sem loop FastAPI.
    monitor['running'] = False
    monitor['interval_hours'] = 2
    monitor['cloud_min_scan_hours'] = int(os.getenv('CLOUD_MIN_SCAN_HOURS','8'))
    monitor['execution_platform'] = 'GitHub Actions'
    # Previne exposição futura de outros campos de conta ou configuração.
    quota = monitor.get('quota') or {}
    monitor['quota'] = {key: quota.get(key) for key in (
        'plan_name','searches_per_month','plan_searches_left','this_month_usage',
        'account_rate_limit_per_hour','this_hour_searches','plan_renewal_date')}
    # Mostra falhas que foram gravadas no último check, mesmo num processo novo.
    recent = api.db.recent_checks(1)
    if recent and recent[0]['status'] == 'erro':
        monitor['last_error'] = recent[0]['note']
    return public_only({
        'exported_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'overview': overview,
        'offers': api.offers(origin='',destination='',departure='',max_price=0),
        'history': api.history(),
        'checks': api.checks(),
        'extras': [dict(row,notes='') for row in api.extra_list()],
        'snapshots': api.snapshots(limit=150),
        'rankings': api.rankings(),
        'market_reference': api.market_reference(),
        'diagnostics': api.diagnostics(limit=35),
    })

def main():
    path = Path('frontend/public/atlas-data.json')
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(create_snapshot(), ensure_ascii=False, default=str), encoding='utf-8')
    tmp.replace(path)
    print('Dashboard atualizado (sem segredos):', path)

if __name__ == '__main__':
    main()
