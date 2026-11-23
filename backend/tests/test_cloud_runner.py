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


def test_scheduled_trigger_uses_same_real_interval_guard(monkeypatch):
    """Execuções schedule respeitam a janela real de duas horas."""
    monkeypatch.setenv('GITHUB_EVENT_NAME', 'schedule')
    monkeypatch.setattr(cloud_runner.settings, 'serpapi_key', 'chave-falsa-do-teste')
    def blocked_if_called(*args, **kwargs):
        raise AssertionError('should_scan não deve bloquear schedule')
    monkeypatch.setattr(cloud_runner, 'should_scan', blocked_if_called)
    monkeypatch.setattr(cloud_runner, 'should_scan_scheduled', lambda: (True, 'Slot disponível'))
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


def test_fallback_skips_when_real_search_is_recent(monkeypatch):
    now = datetime(2026, 11, 22, 22, 17, tzinfo=timezone.utc)  # 19h17 Brasília
    monkeypatch.setattr(cloud_runner.db, 'recent_checks', lambda n: [
        {'status':'somente_indicativo','checked_at':datetime(2026,11,22,22,1,tzinfo=timezone.utc).isoformat()}])
    assert cloud_runner.should_scan_scheduled(now)[0] is False


def test_fallback_runs_when_last_search_is_more_than_two_hours_old(monkeypatch):
    now = datetime(2026, 11, 22, 22, 17, tzinfo=timezone.utc)  # 19h17 Brasília
    monkeypatch.setattr(cloud_runner.db, 'recent_checks', lambda n: [
        {'status':'cotado','checked_at':datetime(2026,11,22,20,5,tzinfo=timezone.utc).isoformat()}])
    monkeypatch.setattr(cloud_runner.db, 'requests_in_30d', lambda: 8)
    assert cloud_runner.should_scan_scheduled(now)[0] is True


def test_scheduled_late_primary_is_not_duplicate(monkeypatch):
    now = datetime(2026, 11, 22, 23, 5, tzinfo=timezone.utc)  # atraso de 53 minutos
    monkeypatch.setattr(cloud_runner.db, 'recent_checks', lambda n: [
        {'status':'cotado','checked_at':datetime(2026,11,22,22,42,tzinfo=timezone.utc).isoformat()}])
    assert cloud_runner.should_scan_scheduled(now)[0] is False


def test_fallback_at_midnight_utc_deduplicates_correct_slot(monkeypatch):
    # 00h UTC equivale às 21h Brasília do dia anterior.
    now = datetime(2026, 11, 23, 0, 11, tzinfo=timezone.utc)
    monkeypatch.setattr(cloud_runner.db, 'recent_checks', lambda n: [
        {'status':'cotado','checked_at':datetime(2026,11,23,0,3,tzinfo=timezone.utc).isoformat()}])
    assert cloud_runner.should_scan_scheduled(now)[0] is False


def test_push_initial_run_shares_scheduled_slot(monkeypatch):
    """Primeiro disparo por push é automático e usa mesma trava das contingências."""
    monkeypatch.setenv('GITHUB_EVENT_NAME', 'push')
    monkeypatch.setattr(cloud_runner.settings, 'serpapi_key', 'CHAVE_TESTE_NAO_REAL')
    monkeypatch.setattr(cloud_runner, 'should_scan', lambda: (_ for _ in ()).throw(
        AssertionError('push não deve usar a janela manual')))
    called = []
    monkeypatch.setattr(cloud_runner, 'should_scan_scheduled', lambda: (True, 'slot disponível'))
    monkeypatch.setattr(cloud_runner.monitor, 'scan_once', lambda destination=None: (
        called.append(destination) or {'status': 'sem_resultado'}))
    assert cloud_runner.main([]) == 0
    assert called == [None]


def test_push_initial_run_skips_if_same_slot_was_queried(monkeypatch):
    monkeypatch.setenv('GITHUB_EVENT_NAME', 'push')
    monkeypatch.setattr(cloud_runner.settings, 'serpapi_key', 'CHAVE_TESTE_NAO_REAL')
    monkeypatch.setattr(cloud_runner, 'should_scan_scheduled', lambda: (False, 'já pesquisado'))
    monkeypatch.setattr(cloud_runner.monitor, 'scan_once', lambda destination=None: (
        _ for _ in ()).throw(AssertionError('não pode duplicar pesquisa')))
    assert cloud_runner.main([]) == 0


def test_late_cron_runs_when_last_search_over_2h_ago(monkeypatch):
    """O cálculo usa o intervalo real entre cotações, não a paridade UTC."""
    now = datetime(2026, 11, 22, 22, 17, tzinfo=timezone.utc)
    monkeypatch.setattr(cloud_runner.db, 'recent_checks', lambda n: [
        {'status': 'somente_indicativo',
         'checked_at': datetime(2026, 11, 22, 20, 1, tzinfo=timezone.utc).isoformat()}])
    monkeypatch.setattr(cloud_runner.db, 'requests_in_30d', lambda: 8)
    assert cloud_runner.should_scan_scheduled(now)[0] is True


def test_cron_retry_skips_if_real_query_after_1912(monkeypatch):
    now = datetime(2026, 11, 22, 22, 27, tzinfo=timezone.utc)
    monkeypatch.setattr(cloud_runner.db, 'recent_checks', lambda n: [
        {'status': 'sem_resultado',
         'checked_at': datetime(2026, 11, 22, 22, 12, tzinfo=timezone.utc).isoformat()}])
    assert cloud_runner.should_scan_scheduled(now)[0] is False


def test_report_distinguishes_run_and_search(monkeypatch, tmp_path):
    import json
    output = tmp_path / 'report.json'
    monkeypatch.setenv('ATLAS_RUN_REPORT', str(output))
    monkeypatch.setenv('GITHUB_EVENT_NAME', 'schedule')
    monkeypatch.setenv('GITHUB_RUN_ID', '123456')
    cloud_runner.write_run_report({'status':'aguardando_cota', 'message':'Janela já pesquisada'}, searched=False)
    data = json.loads(output.read_text(encoding='utf-8'))
    assert data['event'] == 'schedule'
    assert data['run_id'] == '123456'
    assert data['searched'] is False
    cloud_runner.write_run_report({'status':'somente_indicativo','destination':'Madri'}, searched=True)
    data = json.loads(output.read_text(encoding='utf-8'))
    assert data['searched'] is True
    assert data['destination'] == 'Madri'


def test_retry_guard_respects_real_2h_from_last_completed_scan(monkeypatch):
    """O relógio vale por 2h desde a última cotação, inclusive entre horas pares."""
    monkeypatch.setattr(cloud_runner.db, 'requests_in_30d', lambda: 20)
    first = datetime(2026, 11, 22, 22, 9, tzinfo=timezone.utc)  # início via push
    for minute in (12, 17, 22, 27):
        now = datetime(2026, 11, 22, 22, minute, tzinfo=timezone.utc)
        monkeypatch.setattr(cloud_runner.db, 'recent_checks', lambda n: [
            {'status':'cotado', 'checked_at':first.isoformat()}])
        assert cloud_runner.should_scan_scheduled(now)[0] is False
    next_cycle = datetime(2026, 11, 23, 0, 12, tzinfo=timezone.utc)  # 21h12 BRT
    assert cloud_runner.should_scan_scheduled(next_cycle)[0] is True


def test_delayed_2344_search_blocks_0112_but_allows_0211(monkeypatch):
    """Regressão real: GitHub atrasou a pesquisa 23h44 e os próximos slots."""
    last = datetime(2026, 11, 23, 2, 44, tzinfo=timezone.utc)  # 23h44 Brasília
    monkeypatch.setattr(cloud_runner.db, 'recent_checks', lambda n: [
        {'status':'cotado', 'checked_at':last.isoformat()}])
    monkeypatch.setattr(cloud_runner.db, 'requests_in_30d', lambda: 24)
    assert cloud_runner.should_scan_scheduled(datetime(
        2026, 11, 23, 4, 12, tzinfo=timezone.utc))[0] is False  # 01h12
    assert cloud_runner.should_scan_scheduled(datetime(
        2026, 11, 23, 5, 11, tzinfo=timezone.utc))[0] is True  # 02h11


def test_scheduled_retry_does_not_reset_cooldown(monkeypatch):
    now = datetime(2026, 11, 23, 5, 11, tzinfo=timezone.utc)
    check = {'status':'aguardando_cota', 'checked_at':now.isoformat()}
    older = {'status':'cotado', 'checked_at':datetime(
        2026, 11, 23, 2, 44, tzinfo=timezone.utc).isoformat()}
    monkeypatch.setattr(cloud_runner.db, 'recent_checks', lambda n: [check, older])
    monkeypatch.setattr(cloud_runner.db, 'requests_in_30d', lambda: 22)
    assert cloud_runner.should_scan_scheduled(now)[0] is True


def test_recent_manual_result_counts_toward_2h_cooldown(monkeypatch):
    now = datetime(2026, 11, 23, 5, 11, tzinfo=timezone.utc)
    monkeypatch.setattr(cloud_runner.db, 'recent_checks', lambda n: [
        {'status':'somente_indicativo','checked_at':(now-timedelta(minutes=45)).isoformat()}])
    assert cloud_runner.should_scan_scheduled(now)[0] is False
