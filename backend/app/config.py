import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / '.env')


def bool_env(name: str, default=False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ('1','true','yes','sim')


def int_env(name: str, default: int) -> int:
    value = os.getenv(name, '').strip()
    return int(value) if value else default


@dataclass
class Settings:
    db_path: str = os.getenv('DB_PATH', str(ROOT / 'data' / 'passagens.sqlite3'))
    serpapi_key: str = os.getenv('SERPAPI_KEY', '').strip()
    open_jaw_enabled: bool = bool_env('OPEN_JAW_ENABLED', True)
    spain_priority: bool = bool_env('SPAIN_PRIORITY', True)
    scan_enabled: bool = bool_env('MONITOR_ENABLED', True)
    scan_interval_hours: int = max(1, int(os.getenv('SCAN_INTERVAL_HOURS', '6')))
    max_30d_requests: int = min(250, max(2, int(os.getenv('MAX_REQUESTS_30D', '210'))))
    cache_hours: int = max(1, int(os.getenv('CACHE_HOURS', '12')))
    max_return_checks_per_scan: int = min(2,max(1,int(os.getenv('MAX_RETURN_CHECKS_PER_SCAN','2'))))
    app_api_token: str = os.getenv('APP_API_TOKEN', '').strip()
    smtp_host: str = os.getenv('SMTP_HOST', '').strip()
    smtp_port: int = int_env('SMTP_PORT', 587)
    smtp_user: str = os.getenv('SMTP_USER', '').strip()
    smtp_password: str = os.getenv('SMTP_PASSWORD', '').strip()
    smtp_from: str = os.getenv('SMTP_FROM', '').strip()
    alert_to: str = os.getenv('ALERT_TO', '').strip()
    smtp_ssl: bool = bool_env('SMTP_SSL', False)
    mail_enabled: bool = bool_env('MAIL_ENABLED', False)
    alert_min_drop_pct: float = max(1, float(os.getenv('ALERT_MIN_DROP_PCT', '5')))
    alert_min_drop_brl: float = max(1, float(os.getenv('ALERT_MIN_DROP_BRL', '200')))

    @property
    def smtp_ready(self) -> bool:
        return bool(self.mail_enabled and self.smtp_host and self.smtp_from and self.alert_to and
                    (not self.smtp_user or self.smtp_password))
