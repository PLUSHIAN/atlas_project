from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
import logging
from logging.handlers import RotatingFileHandler
import os

from threading import Event, Thread
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from .config import ROOT, Settings
from .db import Database
from .monitor import Monitor
from .trip import all_routes, SEARCH_CITIES, classification
from .value import enrich_offer, value_ranking, transfer_key

settings = Settings()
db = Database(settings.db_path)
monitor = Monitor(db,settings)
logs = ROOT / 'logs'
logs.mkdir(parents=True,exist_ok=True)
logging.basicConfig(level=logging.INFO, handlers=[logging.StreamHandler(),
                    RotatingFileHandler(logs/'monitor.log',maxBytes=1_000_000,backupCount=2,encoding='utf-8')],
                    format='%(asctime)s %(levelname)s %(name)s %(message)s')
# httpx pode incluir a api_key na URL de requisições em nível INFO. Não gravar credenciais.
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('httpcore').setLevel(logging.WARNING)
stop_monitor = Event()
monitor_thread = None

def scheduled_loop():
    # Não inicia consumo de créditos ao abrir o app: primeira execução é manual
    # ou ao atingir o próximo intervalo. O loop roda sem navegador aberto.
    while not stop_monitor.wait(settings.scan_interval_hours * 3600):
        monitor.scan_once()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global monitor_thread
    if settings.scan_enabled and settings.serpapi_key:
        stop_monitor.clear()
        monitor_thread = Thread(target=scheduled_loop, name='passagens-agenda', daemon=True)
        monitor_thread.start()
    yield
    stop_monitor.set()
    if monitor_thread and monitor_thread.is_alive():
        monitor_thread.join(timeout=1)



app = FastAPI(title='Passagens Europa 2027',version='4.0.0',lifespan=lifespan)
# O Vite utiliza proxy de desenvolvimento; em produção bind apenas em localhost/túnel SSH.
app.add_middleware(CORSMiddleware,allow_origins=['http://localhost:5173','http://127.0.0.1:5173'],
                   allow_credentials=False,allow_methods=['GET','POST','PUT'],allow_headers=['*'])


def authenticate(x_api_token: str | None = Header(default=None)):
    if settings.app_api_token and x_api_token != settings.app_api_token:
        raise HTTPException(status_code=401,detail='Token de administração inválido')


class ExtraInput(BaseModel):
    destination: Literal['BCN','MAD','ROM_MIL','MIL_ROM']
    mode: Literal['avião','trem','ônibus','outro']
    target_city: Literal['Roma','Milão']
    couple_transfer_brl: float | None = Field(default=None,ge=0)
    couple_baggage_brl: float | None = Field(default=None,ge=0)
    couple_airport_brl: float | None = Field(default=None,ge=0)
    hours_each_way: float | None = Field(default=None,ge=0)
    notes: str = Field(default='',max_length=400)


@app.get('/api/health')
def health():
    return {'ok':True,'utc':datetime.now(timezone.utc).isoformat(),'source':'SerpApi Google Flights'}


def _extras_for_compare(offer, manual_extras):
    """Calcula somente custos informados pelo usuário, sem cotar bilhetes adicionais."""
    key = transfer_key(offer)
    if key is None:
        return []
    result = []
    for x in manual_extras:
        if x['destination'] != key:
            continue
        values = [x['couple_transfer_brl'], x['couple_baggage_brl'], x['couple_airport_brl']]
        additional = sum(values) if all(v is not None for v in values) else None
        result.append({'additional_total': additional, 'estimated_total':
                       offer['price_couple'] + additional if additional is not None else None})
    return result


@app.get('/api/overview')
def overview():
    state = monitor.status()
    offers = db.best_offers(limit=200)
    all_checks = db.recent_checks(1)
    return {'monitor':state,'best_price':min((o['price_couple'] for o in offers),default=None),
            'best_total_known':min((x['comparable_total'] for x in (
                enrich_offer(o, _extras_for_compare(o, db.extras())) for o in offers)
                if x['comparable_total'] is not None), default=None),
            'offers_count':len(offers), 'opportunities_count':sum(o['price_couple']<=8000 for o in offers),
            'indicative_min_price':db.snapshot_minimum(), 'indicative_count':db.snapshot_count(),
            'market_by_destination':db.last_snapshot_by_destination(),
            'market_reference':db.market_reference(),
            'coverage':db.route_coverage([route.key for route in monitor.plan()]),
            'last_scan_at':all_checks[0]['checked_at'] if all_checks else None,
            'trip':{'vacation_start':'2027-09-08','vacation_end':'2027-09-27',
                    'duration_inclusive_days':17,'adults':2,'currency':'BRL'},
            'note':'Tarifas são snapshots consultados; disponibilidade atual exige nova confirmação.'}


def enriched_offers(origin='', destination='', departure='', max_price=0):
    entries = []
    extra_list = db.extras()
    for row in db.best_offers(origin, destination, max_price, departure, limit=500):
        row.pop('data_json', None)
        extras = []
        key = transfer_key(row)
        if key:
            for item in extra_list:
                if item['destination'] != key:
                    continue
                x = dict(item)
                prices = [x['couple_transfer_brl'], x['couple_baggage_brl'], x['couple_airport_brl']]
                x['additional_total'] = sum(prices) if all(z is not None for z in prices) else None
                x['estimated_total'] = row['price_couple'] + x['additional_total'] if x['additional_total'] is not None else None
                x['basis'] = 'estimativa_manual'
                extras.append(x)
            if not extras:
                extras = [{'basis': 'indisponivel', 'additional_total': None, 'estimated_total': None}]
        entry = enrich_offer(row, extras)
        entry['category'] = classification(row['price_couple'])
        entries.append(entry)
    return value_ranking(entries)


@app.get('/api/offers')
def offers(origin: str='', destination: str='', departure: str='', max_price: float=Query(0,ge=0)):
    entries = enriched_offers(origin, destination, departure, max_price)
    # Custo internacional é um ranking universal, mesmo com adicionais desconhecidos.
    return sorted(entries, key=lambda x: x['price_couple'])


@app.get('/api/rankings')
def rankings():
    entries = enriched_offers()
    international = sorted(entries, key=lambda x: x['price_couple'])
    comparable = sorted((x for x in entries if x['comparable_total'] is not None),
                        key=lambda x: (-x['value_score'], x['comparable_total']))
    excluded = [x for x in entries if x['comparable_total'] is None]
    by_total = sorted((x for x in entries if x['comparable_total'] is not None),
                      key=lambda x: x['comparable_total'])
    return {'international_cheapest': international[:25], 'best_value': comparable[:25],
            'lowest_known_total': by_total[:25], 'without_additional_costs': excluded[:25],
            'sample_size': len(entries), 'note': 'Rankings apenas de cotações históricas completas; não garantem compra. Nota heurística e gastos extras manuais.'}


@app.get('/api/coverage-insights')
def coverage_insights():
    """Transparência sobre as datas e rotas efetivamente consultadas."""
    return db.coverage_insights(monitor.plan())


@app.get('/api/market-reference')
def market_reference():
    return db.market_reference()


@app.get('/api/diagnostics')
def diagnostics(limit: int=Query(35,ge=1,le=100)):
    return db.scan_diagnostics(limit)


@app.get('/api/snapshots')
def snapshots(limit: int = Query(150,ge=1,le=500)):
    return db.recent_snapshots(limit)


@app.get('/api/history')
def history():
    return db.history()


@app.get('/api/checks')
def checks():
    return db.recent_checks()


@app.get('/api/route-plan')
def route_plan():
    return [{'key':r.key,'origin_airports':list(r.origins),'destination_airports':list(r.destinations),
             'departure':str(r.departure),'return_departure':str(r.return_departure)} for r in monitor.plan()]


class ScanInput(BaseModel):
    destination: Literal['Roma','Milão','Barcelona','Madri','Roma → Milão','Milão → Roma'] | None = None


@app.post('/api/scan',dependencies=[Depends(authenticate)],status_code=202)
def scan(body: ScanInput | None = None):
    if not settings.serpapi_key:
        raise HTTPException(status_code=400,detail='Configure SERPAPI_KEY no .env primeiro')
    if monitor.lock.locked():
        raise HTTPException(status_code=409,detail='Pesquisa já está em execução')
    city = body.destination if body else None
    selected = city or monitor.pick_route().city
    if not monitor.start_async(destination=city):
        raise HTTPException(status_code=409,detail='Pesquisa já está em execução')
    return {'message':f'Pesquisa de {selected} iniciada. Aguarde o registro no Histórico.',
            'destination':selected}


@app.get('/api/extras')
def extra_list():
    return db.extras()


@app.put('/api/extras',dependencies=[Depends(authenticate)])
def save_extra(extra: ExtraInput):
    db.save_extra(extra.model_dump())
    return {'saved':True,'message':'Estimativa manual salva; NÃO é cotação real'}

# Frontend build opcional: após npm run build, o backend também serve o painel.
FRONT = ROOT / 'frontend' / 'dist'
if (FRONT / 'assets').exists():
    app.mount('/assets',StaticFiles(directory=FRONT/'assets'),name='assets')

@app.get('/')
def index():
    if (FRONT/'index.html').exists():
        return FileResponse(FRONT/'index.html')
    return {'message':'Backend ativo. Em desenvolvimento, abra http://localhost:5173'}
