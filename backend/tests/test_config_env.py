"""Variáveis de ambiente opcionais no GitHub Actions."""
from backend.app.config import int_env


def test_smtp_port_empty_uses_default(monkeypatch):
    monkeypatch.setenv("SMTP_PORT", "")
    assert int_env("SMTP_PORT", 587) == 587


def test_smtp_port_missing_uses_default(monkeypatch):
    monkeypatch.delenv("SMTP_PORT", raising=False)
    assert int_env("SMTP_PORT", 587) == 587


def test_smtp_port_explicit_is_preserved(monkeypatch):
    monkeypatch.setenv("SMTP_PORT", "465")
    assert int_env("SMTP_PORT", 587) == 465
