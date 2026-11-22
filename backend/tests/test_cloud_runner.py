"""Testes do controle de cadência da versão GitHub Actions."""
from datetime import datetime, timedelta, timezone
from backend.app import cloud_runner

def test_skip_if_recent_consultation(monkeypatch):
    now = datetime(2026, 11, 22, 18, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(cloud_runner.db,'recent_checks',lambda n: [
        {'status':'cotado','checked_at':(now-timedelta(hours=3)).isoformat()}])
    monkeypatch.setattr(cloud_runner.db,'requests_in_30d',lambda : 12)
    allowed, _=cloud_runner.should_scan(now,8)
    assert not allowed

def test_run_when_due(monkeypatch):
    now = datetime(2026, 11, 22, 18, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(cloud_runner.db,'recent_checks',lambda n: [
        {'status':'cotado','checked_at':(now-timedelta(hours=10)).isoformat()}])
    monkeypatch.setattr(cloud_runner.db,'requests_in_30d',lambda : 40)
    allowed, _=cloud_runner.should_scan(now,8)
    assert allowed

def test_skip_when_low_credits(monkeypatch):
    now = datetime(2026, 11, 22, 18, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(cloud_runner.db,'recent_checks',lambda n: [])
    monkeypatch.setattr(cloud_runner.db,'requests_in_30d',lambda : 209)
    allowed, _=cloud_runner.should_scan(now,8)
    assert not allowed
