"""Garantias offline: nenhuma cidade fica atrás de todas as datas de Roma."""
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient

from app.config import Settings
from app.db import Database
from app.monitor import Monitor
from app.trip import DEST_GROUPS, routes


class StubProvider:
    def __init__(self):
        self.calls = []

    def account(self):
        return {'plan_name': 'Free', 'plan_monthly_price': 0, 'plan_searches_left': 250,
                'account_rate_limit_per_hour': 50, 'this_hour_searches': 0, 'last_hour_searches': 0}

    def search(self, route, reserve, departure_token=None):
        self.calls.append(route.city)
        req_id = reserve('outbound')
        reserve('settle', req_id, 'completed')
        return {'best_flights': []}


def _monitor(tmp_path):
    db = Database(str(tmp_path / 'radar.sqlite3'))
    settings = replace(Settings(), serpapi_key='CHAVE_TESTE', cache_hours=12, max_30d_requests=20)
    provider = StubProvider()
    return Monitor(db, settings, provider), provider


def test_cycle_covers_four_cities_before_repeating(tmp_path):
    monitor, provider = _monitor(tmp_path)
    cities = []
    for _ in range(8):
        cities.append(monitor.pick_route().city)
        result = monitor.scan_once()
        assert result['status'] == 'sem_resultado'
        assert result['destination'] == cities[-1]
    assert cities == ['Barcelona', 'Madri', 'Roma', 'Barcelona', 'Madri', 'Milão', 'Barcelona', 'Madri']
    assert provider.calls == cities
    assert monitor.db.requests_in_30d() == 8
    assert {x['city']:x['consulted'] for x in monitor.status()['city_coverage']} == {'Roma':1,'Milão':1,'Barcelona':3,'Madri':3,'Roma → Milão':0,'Milão → Roma':0}
    assert monitor.status()['next_destination'] == 'Roma → Milão'


def test_existing_rome_history_makes_milan_next(tmp_path):
    monitor, provider = _monitor(tmp_path)
    rome = next(x for x in routes() if x.city == 'Roma')
    monitor.db.record_check(rome.key, 'somente_indicativo', 'antiga consulta Roma', 2)
    assert monitor.pick_route().city == 'Madri'
    assert monitor.scan_once()['destination'] == 'Madri'
    assert provider.calls == ['Madri']


def test_manual_city_select_then_automatic_rotation(tmp_path):
    monitor, provider = _monitor(tmp_path)
    assert monitor.scan_once('Barcelona')['destination'] == 'Barcelona'
    assert monitor.scan_once('Madri')['destination'] == 'Madri'
    assert monitor.pick_route().city == 'Roma'
    assert monitor.scan_once()['destination'] == 'Roma'
    assert provider.calls == ['Barcelona', 'Madri', 'Roma']
    assert len(monitor.status()['city_coverage']) == 6


def test_api_select_city_without_consulting_provider(monkeypatch):
    from backend.app import main
    seen = []
    monkeypatch.setattr(main.settings, 'serpapi_key', 'CHAVE_TESTE')
    monkeypatch.setattr(main.monitor, 'start_async', lambda destination=None: seen.append(destination) or True)
    with TestClient(main.app) as client:
        response = client.post('/api/scan', json={'destination': 'Milão'})
        assert response.status_code == 202
        assert response.json()['destination'] == 'Milão'
        assert seen == ['Milão']
        invalid = client.post('/api/scan', json={'destination': 'Lisboa'})
        assert invalid.status_code == 422
        # Compatível com o botão antigo, que não enviava JSON.
        legacy = client.post('/api/scan')
        assert legacy.status_code == 202
        assert seen[-1] is None
