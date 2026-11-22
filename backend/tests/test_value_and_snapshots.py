"""Somente respostas artificiais neste teste; não consultam o provedor."""
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

from app.db import Database
from app.serpapi import outbound_market_snapshots
from app.trip import Route
from app.value import enrich_offer


def segment(o, d, dep, arr):
    return {'departure_airport': {'id': o, 'time': dep},
            'arrival_airport': {'id': d, 'time': arr}, 'airline': 'Teste'}


def test_snapshot_above_budget_without_return_flight():
    route = Route(('GRU', 'CGH', 'VCP'), ('FCO',), date(2027, 9, 8), date(2027, 9, 23))
    response = {'best_flights': [{'price': 12500, 'flights': [
        segment('GRU', 'FCO', '2027-09-08 17:00', '2027-09-09 09:00')]}]}
    snapshots = outbound_market_snapshots(response, route)
    assert len(snapshots) == 1
    assert snapshots[0]['price_couple'] == 12500
    assert snapshots[0]['status'] == 'indicativo_sem_volta_validada'
    with TemporaryDirectory() as d:
        db = Database(str(Path(d) / 'history.sqlite3'))
        db.add_snapshots(snapshots)
        assert db.snapshot_minimum() == 12500
        assert db.best_offers() == []
        assert db.route_coverage([route.key])['not_yet_consulted'] == 1
        db.record_check(route.key, 'somente_indicativo', 'prévia salva', 1)
        assert db.route_coverage([route.key])['consulted'] == 1


def test_flags_are_informational_not_fake_charges():
    base = {'price_couple': 6500, 'destination': 'FCO', 'stops_out': 2,
            'stops_back': 1, 'duration_out': 1260, 'duration_back': 710,
            'overnight': 1, 'airport_change': 0, 'baggage': 'Não informada pela fonte'}
    enriched = enrich_offer(base, [])
    assert enriched['comparable_total'] == 6500
    assert len(enriched['warnings']) == 4
    assert enriched['total_basis'] == 'somente_passagem_internacional'

    espanha = dict(base, destination='BCN')
    unknown = enrich_offer(espanha, [])
    assert unknown['comparable_total'] is None
    calculated = enrich_offer(espanha, [{'estimated_total': 8000}])
    assert calculated['comparable_total'] == 8000
    assert calculated['total_basis'] == 'passagem_internacional_mais_estimativa_manual'
