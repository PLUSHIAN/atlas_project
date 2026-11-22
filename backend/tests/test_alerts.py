from tempfile import TemporaryDirectory
from pathlib import Path
from app.db import Database
from app.monitor import Monitor
from app.config import Settings


def test_dedupe_and_price_drop():
    with TemporaryDirectory() as d:
        db=Database(str(Path(d)/'test.sqlite'))
        mon=Monitor(db,Settings())
        base={'itinerary_key':'abc','price_couple':6500}
        assert mon._should_alert(base)
        db.alert_sent('abc',6500)
        assert not mon._should_alert(base)
        assert not mon._should_alert(dict(base,price_couple=6400))
        assert mon._should_alert(dict(base,price_couple=6100))
        assert not mon._should_alert(dict(base,price_couple=8100))


def test_quota_local_counts_reservations():
    with TemporaryDirectory() as d:
        db=Database(str(Path(d)/'test.sqlite'))
        assert db.requests_in_30d()==0
        rid=db.reserve_request('outbound')
        assert db.requests_in_30d()==1
        db.settle_request(rid,'error')
        assert db.requests_in_30d()==1
