"""Comando opcional para um scan único (útil em crontab/Task Scheduler)."""
import sys
from .main import monitor

if __name__=='__main__':
    result = monitor.scan_once()
    print(result)
    sys.exit(0 if result.get('status') not in ('erro','ocupado') else 1)
