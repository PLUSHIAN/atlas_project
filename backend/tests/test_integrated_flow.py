"""Fluxo integrado offline usando somente respostas sintéticas de TESTE.
O monitor nunca mostra esse conjunto no dashboard real.
"""
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from app.config import Settings
from app.db import Database
from app.monitor import Monitor


def segment(o, d, depart, arrive):
    return {'departure_airport': {'id': o, 'time': depart},
            'arrival_airport': {'id': d, 'time': arrive},
            'airline': 'Operadora de teste', 'flight_number': 'TEST 1'}


class FakeProvider:
    def __init__(self):
        self.count = 0

    def account(self):
        return {'plan_name': 'Free Plan', 'plan_monthly_price': 0,
                'plan_searches_left': 250 - self.count,
                'account_rate_limit_per_hour': 50,
                'this_hour_searches': self.count,
                'last_hour_searches': self.count}

    def search(self, route, reserve, departure_token=None):
        request_id = reserve('return' if departure_token else 'outbound')
        self.count += 1
        reserve('settle', request_id, 'completed')
        if not departure_token:
            return {'best_flights': [{'price': 7200,
                      'departure_token': 'TOKEN_APENAS_TESTE',
                      'flights': [segment('GRU', 'FCO', '2027-09-08 18:00', '2027-09-09 10:00')]}],
                    'search_metadata': {'google_flights_url': 'https://www.google.com/travel/flights?hl=pt-BR'}}
        return {'best_flights': [{'price': 7400,
                  'flights': [segment('FCO', 'GRU', '2027-09-23 21:00', '2027-09-24 06:00')]}]}


def test_full_scan_creates_history_and_email_once(monkeypatch):
    mails = []
    monkeypatch.setattr('app.monitor.send_mail', lambda _settings, offer, extras: mails.append((offer, extras)))
    with TemporaryDirectory() as d:
        db = Database(str(Path(d) / 'it.sqlite3'))
        cfg = replace(Settings(), serpapi_key='CHAVE_APENAS_TESTE', max_30d_requests=5,
                      mail_enabled=True, smtp_host='example.test', smtp_from='destino@example.test',
                      alert_to='destino@example.test')
        p = FakeProvider()
        mon = Monitor(db, cfg, provider=p)
        result = mon.scan_once('Roma')
        assert result['status'] == 'cotado'
        assert result['offers'] == 1
        assert result['min_price'] == 7400
        assert len(mails) == 1
        assert mails[0][0]['arrival_home'] == '2027-09-24'
        assert db.requests_in_30d() == 2
        assert db.best_offers()[0]['price_couple'] == 7400
        assert mon._should_alert(db.best_offers()[0]) is False
        assert db.recent_checks(1)[0]['api_requests'] == 2


def test_missing_free_hourly_balance_blocks_requests(monkeypatch):
    with TemporaryDirectory() as d:
        db = Database(str(Path(d) / 'it.sqlite3'))
        cfg = replace(Settings(), serpapi_key='CHAVE_APENAS_TESTE')
        p = FakeProvider()
        p.account = lambda: {'plan_searches_left': 200, 'account_rate_limit_per_hour': 50,
                              'this_hour_searches': 50, 'last_hour_searches': 50}
        mon = Monitor(db, cfg, provider=p)
        assert mon.scan_once()['status'] == 'erro'
        assert db.requests_in_30d() == 0
        assert p.count == 0
