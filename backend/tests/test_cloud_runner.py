"""Testes do controle de cadência da versão GitHub Actions."""
from datetime import datetime, timedelta, timezone
from backend.app import cloud_runner

def test_skip_if_recent_consultation(monkeypatch):
    now = datetime(2026, 11, 22, 18, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(cloud_runner.db,'recent_checks',lambda n: [
        {'status':'cotado','checked_at':(now-timedelta(hours=1)).isoformat()}])
    monkeypatch.setattr(cloud_runner.db,'requests_in_30d',lambda : 12)
    allowed, _=cloud_runner.should_scan(now,2)
    assert not allowed

def test_run_when_due(monkeypatch):
    now = datetime(2026, 11, 22, 18, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(cloud_runner.db,'recent_checks',lambda n: [
        {'status':'cotado','checked_at':(now-timedelta(hours=10)).isoformat()}])
    monkeypatch.setattr(cloud_runner.db,'requests_in_30d',lambda : 40)
    allowed, _=cloud_runner.should_scan(now,2)
    assert allowed

def test_skip_when_low_credits(monkeypatch):
    now = datetime(2026, 11, 22, 18, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(cloud_runner.settings, 'max_30d_requests', 250)
    monkeypatch.setattr(cloud_runner.db,'recent_checks',lambda n: [])
    monkeypatch.setattr(cloud_runner.db,'requests_in_30d',lambda : 249)
    allowed, _=cloud_runner.should_scan(now,2)
    assert not allowed


def test_runs_again_2h_after_last_search(monkeypatch):
    now = datetime(2026, 11, 27, 18, 0, tzinfo=timezone.utc)
    monkeypatch.setenv('CLOUD_MIN_SCAN_HOURS', '2')
    monkeypatch.setattr(cloud_runner.db, 'recent_checks', lambda n: [
        {'status': 'somente_indicativo', 'checked_at': (now-timedelta(hours=2)).isoformat()}])
    monkeypatch.setattr(cloud_runner.db, 'requests_in_30d', lambda: 42)
    allowed, _ = cloud_runner.should_scan(now)
    assert allowed


def test_does_not_run_again_before_2h(monkeypatch):
    now = datetime(2026, 11, 27, 18, 0, tzinfo=timezone.utc)
    monkeypatch.setenv('CLOUD_MIN_SCAN_HOURS', '2')
    monkeypatch.setattr(cloud_runner.db, 'recent_checks', lambda n: [
        {'status': 'cotado', 'checked_at': (now-timedelta(hours=1, minutes=59)).isoformat()}])
    monkeypatch.setattr(cloud_runner.db, 'requests_in_30d', lambda: 42)
    allowed, _ = cloud_runner.should_scan(now)
    assert not allowed


def test_can_use_up_to_250_credits_but_wont_exceed(monkeypatch):
    now = datetime(2026, 11, 27, 18, 0, tzinfo=timezone.utc)
    monkeypatch.setenv('CLOUD_MIN_SCAN_HOURS', '2')
    monkeypatch.setattr(cloud_runner.db, 'recent_checks', lambda n: [])
    monkeypatch.setattr(cloud_runner.settings, 'max_30d_requests', 250)
    monkeypatch.setattr(cloud_runner.db, 'requests_in_30d', lambda: 248)
    assert cloud_runner.should_scan(now)[0]
    monkeypatch.setattr(cloud_runner.db, 'requests_in_30d', lambda: 249)
    assert not cloud_runner.should_scan(now)[0]


def test_scheduled_trigger_queries_even_after_manual(monkeypatch):
    """A execução schedule não deve pular a busca só por consulta manual recente."""
    monkeypatch.setenv('GITHUB_EVENT_NAME', 'schedule')
    monkeypatch.setattr(cloud_runner.settings, 'serpapi_key', 'chave-falsa-do-teste')
    def blocked_if_called(*args, **kwargs):
        raise AssertionError('should_scan não deve bloquear schedule')
    monkeypatch.setattr(cloud_runner, 'should_scan', blocked_if_called)
    calls = []
    def fake_scan(destination=None):
        calls.append(destination)
        return {'status': 'sem_resultado', 'offers': 0}
    monkeypatch.setattr(cloud_runner.monitor, 'scan_once', fake_scan)
    assert cloud_runner.main([]) == 0
    assert calls == [None]


def test_manual_auto_still_obeys_cooldown(monkeypatch):
    monkeypatch.setenv('GITHUB_EVENT_NAME', 'workflow_dispatch')
    monkeypatch.setattr(cloud_runner.settings, 'serpapi_key', 'chave-falsa-do-teste')
    monkeypatch.setattr(cloud_runner, 'should_scan', lambda: (False, 'Consulta manual recente'))
    def unexpected_scan(destination=None):
        raise AssertionError('Não deveria consultar dentro da janela manual')
    monkeypatch.setattr(cloud_runner.monitor, 'scan_once', unexpected_scan)
    assert cloud_runner.main([]) == 0
