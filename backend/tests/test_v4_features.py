"""ATLAS v4: tudo offline, sem usar chave de API real ou enviar e-mails."""
import json
from dataclasses import replace
from datetime import date
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from app.config import Settings
from app.db import Database
from app.monitor import Monitor, SPAIN_CYCLE
from app.serpapi import SerpApi, reject_reason, make_offer
from app.trip import OpenJawRoute, open_jaw_routes
from app.value import enrich_offer, value_ranking


def leg(a, b, depart, arrive):
    return {'departure_airport': {'id': a, 'time': depart},
            'arrival_airport': {'id': b, 'time': arrive},
            'airline': 'Companhia TESTE', 'flight_number': 'ZZ901'}


def test_open_jaw_has_valid_dates_and_groups():
    trips = open_jaw_routes()
    assert len(trips) == 32
    assert {x.city for x in trips} == {'Roma → Milão', 'Milão → Roma'}
    assert {r.return_origins for r in trips} == {('FCO',), ('MXP', 'BGY', 'LIN')}
    assert all(r.departure >= date(2027, 9, 8) and r.return_departure <= date(2027, 9, 27) for r in trips)


def test_serpapi_multi_city_params_and_second_call():
    seen = []

    def transport(req):
        seen.append(req)
        return httpx.Response(200, json={'best_flights': []})

    client = httpx.Client(transport=httpx.MockTransport(transport))
    api = SerpApi('CHAVE_EXCLUSIVA_DO_TESTE', client)
    route = open_jaw_routes()[0]
    invoices = []

    def reserve(kind, request_id=None, state=None):
        invoices.append((kind, state))
        return len(invoices)

    api.search(route, reserve)
    api.search(route, reserve, departure_token='TOKEN_EXCLUSIVO_DO_TESTE')
    assert len(seen) == 2
    params = seen[0].url.params
    assert params['type'] == '3'
    assert 'outbound_date' not in params and 'return_date' not in params
    itinerary = json.loads(params['multi_city_json'])
    assert itinerary[0]['arrival_id'] == 'FCO'
    assert set(itinerary[1]['departure_id'].split(',')) == {'MXP','BGY','LIN'}
    assert itinerary[1]['arrival_id'] == 'GRU,CGH,VCP'
    assert seen[1].url.params['departure_token'] == 'TOKEN_EXCLUSIVO_DO_TESTE'
    assert invoices == [('outbound', None), ('settle', 'completed'),
                        ('return', None), ('settle', 'completed')]


def test_only_complete_17_day_openjaw_offer_is_accepted():
    route = next(x for x in open_jaw_routes() if x.city == 'Roma → Milão' and x.departure == date(2027,9,8) and x.return_departure == date(2027,9,23))
    outbound = {'price': 9500, 'flights': [leg('GRU', 'FCO', '2027-09-08 19:00', '2027-09-09 11:00')]}
    returning = {'price': 10400, 'flights': [leg('MXP', 'GRU', '2027-09-23 20:00', '2027-09-24 06:00')]}
    offer = make_offer(outbound, returning, route, {})
    assert offer['price_couple'] == 10400
    assert offer['journey_type'] == 'open_jaw'
    assert offer['return_origin'] == 'MXP'
    assert 'NÃO incluído' in offer['remarks']
    assert reject_reason(outbound, returning, route) is None
    invalid = {'price': 10400, 'flights': [leg('MXP', 'GRU', '2027-09-23 20:00', '2027-09-25 06:00')]}
    assert make_offer(outbound, invalid, route, {}) is None
    assert reject_reason(outbound, invalid, route) == 'nao_completa_17_dias'


class NoOffersProvider:
    def __init__(self):
        self.request_count = 0

    def account(self):
        return {'plan_searches_left':250, 'this_hour_searches':0, 'account_rate_limit_per_hour':50}

    def search(self, route, reserve, departure_token=None):
        rid = reserve('outbound')
        self.request_count += 1
        reserve('settle', rid, 'completed')
        return {'best_flights':[]}


def test_spain_priority_and_milan_rome_are_not_excluded(tmp_path):
    provider = NoOffersProvider()
    cfg = replace(Settings(), serpapi_key='CHAVE_TESTE', spain_priority=True,
                  open_jaw_enabled=True, max_30d_requests=30)
    mon = Monitor(Database(str(tmp_path/'db.sqlite3')),cfg,provider)
    cities = []
    for _ in range(12):
        city = mon.pick_route().city
        cities.append(city)
        assert mon.scan_once()['status'] == 'sem_resultado'
    assert cities == list(SPAIN_CYCLE)
    assert sum(c in ('Barcelona','Madri') for c in cities) == 8
    assert {'Roma','Milão','Roma → Milão','Milão → Roma'}.issubset(set(cities))
    assert mon.status()['route_count'] == 96
    assert provider.request_count == 12


def test_rankings_separate_prices_from_value_and_unknown_costs():
    base = {'origin':'GRU','destination':'FCO','price_couple':8000,'baggage':'Não informada',
            'stops_out':2,'stops_back':1,'duration_out':1350,'duration_back':700,
            'overnight':1,'airport_change':0}
    clean = {**base,'price_couple':8300,'stops_out':0,'stops_back':0,
             'duration_out':650,'overnight':0,'baggage':'1 mala despachada incluída'}
    esp = {**clean,'destination':'BCN','price_couple':6100}
    o1 = enrich_offer(base,[])
    o2 = enrich_offer(clean,[])
    o3 = enrich_offer(esp,[])
    ranked = value_ranking([o1,o2,o3])
    assert ranked[0]['value_score'] < ranked[1]['value_score']
    assert ranked[2]['value_score'] is None
    assert ranked[2]['comparable_total'] is None
    assert ranked[2]['price_couple'] == 6100  # sem adicionar valores imaginários
    manual = value_ranking([o1,enrich_offer(esp,[{'estimated_total':7600}])])
    assert manual[1]['comparable_total'] == 7600
    assert manual[1]['value_score'] is not None


def test_diagnostics_and_history_persist_across_restarts(tmp_path):
    path = str(tmp_path/'history.sqlite3')
    db = Database(path)
    db.record_check('OJ|exemplo','somente_indicativo','teste local',2,'Roma → Milão',
                    {'received_first_stage': 8,'return_candidates':2,
                     'complete_itineraries':0,'rejections':{'nao_completa_17_dias':2}})
    reopened = Database(path)
    results = reopened.scan_diagnostics()
    assert results[0]['city'] == 'Roma → Milão'
    assert results[0]['metrics']['rejections']['nao_completa_17_dias'] == 2
    assert reopened.recent_checks(1)[0]['api_requests'] == 2


def test_compare_endpoints_do_not_call_serpapi(monkeypatch, tmp_path):
    from backend.app import main
    temp_db = Database(str(tmp_path/'web.sqlite3'))
    monkeypatch.setattr(main, 'db', temp_db)
    monkeypatch.setattr(main.monitor, 'db', temp_db)
    monkeypatch.setattr(main.settings, 'serpapi_key', '')
    with TestClient(main.app) as client:
        for url in ('/api/rankings','/api/market-reference','/api/diagnostics','/api/overview'):
            response=client.get(url)
            assert response.status_code == 200, (url,response.text)
        ranks=client.get('/api/rankings').json()
        assert ranks['sample_size'] == 0
        assert ranks['best_value'] == []
        assert len(client.get('/api/market-reference').json()) == 4


def test_open_jaw_scan_persists_complete_itinerary_without_alert_above_limit(tmp_path, monkeypatch):
    from app.monitor import send_mail
    class OpenJawProvider(NoOffersProvider):
        def search(self, route, reserve, departure_token=None):
            rid = reserve('return' if departure_token else 'outbound')
            self.request_count += 1
            reserve('settle',rid,'completed')
            if departure_token:
                return {'best_flights':[{'price':10800,
                          'flights':[leg('MXP','GRU','2027-09-23 21:00','2027-09-24 06:00')]}]}
            return {'best_flights':[{'price':10000,'departure_token':'TEST_TOKEN',
                                    'flights':[leg('GRU','FCO','2027-09-08 20:00','2027-09-09 12:00')]}]}

    def unexpected_mail(*args,**kwargs):
        raise AssertionError('Não se pode alertar acima de R$ 8.000')
    monkeypatch.setattr('app.monitor.send_mail',unexpected_mail)
    db=Database(str(tmp_path/'openjaw.sqlite3'))
    cfg=replace(Settings(),serpapi_key='CHAVE_TESTE',max_30d_requests=5,
                smtp_host='example.test',smtp_from='test@example.test',alert_to='test@example.test',mail_enabled=True)
    m=Monitor(db,cfg,OpenJawProvider())
    result=m.scan_once('Roma → Milão')
    assert result['status']=='cotado',result
    assert result['offers']==1
    assert db.requests_in_30d()==2
    offer=db.best_offers()[0]
    assert offer['return_origin']=='MXP'
    assert offer['journey_type']=='open_jaw'
    assert db.scan_diagnostics()[0]['metrics']['complete_itineraries']==1
    assert db.recent_snapshots()[0]['status']=='indicativo_sem_volta_validada'


def test_coverage_insights_by_city_and_departure(tmp_path):
    from app.trip import routes
    db = Database(str(tmp_path/'city-coverage.sqlite3'))
    plan = routes()
    selected = next(r for r in plan if r.city == 'Barcelona' and str(r.departure) == '2027-09-08')
    db.record_check(selected.key, 'somente_indicativo', 'amostra de teste', 1)
    db.add_snapshots([{
        'seen_at': '2026-11-22T21:30:00+00:00',
        'route_key': selected.key, 'origin': 'GRU', 'destination': 'BCN',
        'departure': '2027-09-08', 'return_departure': '2027-09-23',
        'price_couple': 12345.0, 'outbound_key': 'apenas-teste',
        'source': 'TESTE_OFFLINE', 'status': 'indicativo_sem_volta_validada'
    }])
    cities = {x['city']: x for x in db.coverage_insights(plan)}
    barcelona = cities['Barcelona']
    assert barcelona['total'] == 16
    assert barcelona['consulted'] == 1
    assert barcelona['dates_covered'] == 1
    assert barcelona['dates_total'] == 4
    assert barcelona['min_indicative'] == 12345
    assert barcelona['min_complete'] is None
    assert barcelona['sample_size'] == 1
    assert any(d['departure'] == '2027-09-08' and d['consulted'] == 1 for d in barcelona['dates'])
    assert all(x['min_indicative'] is None for x in cities['Madri']['dates'])
    assert cities['Roma']['consulted'] == 0


def test_destination_search_explores_all_departure_dates_before_repeating(tmp_path):
    from app.trip import routes
    db = Database(str(tmp_path/'rotation.sqlite3'))
    cfg = replace(Settings(),serpapi_key='TEST_ONLY',spain_priority=True,open_jaw_enabled=False)
    mon = Monitor(db,cfg,NoOffersProvider())
    searched = []
    for _ in range(4):
        route = mon.pick_route('Barcelona')
        searched.append(str(route.departure))
        db.record_check(route.key,'sem_resultado','teste local',1,city='Barcelona')
    assert searched == ['2027-09-08','2027-09-09','2027-09-10','2027-09-11']
    assert len(set(searched)) == 4
