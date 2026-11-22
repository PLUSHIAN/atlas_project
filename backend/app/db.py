import json
import sqlite3
from statistics import median
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


SCHEMA = '''
CREATE TABLE IF NOT EXISTS checks (
 id INTEGER PRIMARY KEY AUTOINCREMENT, route_key TEXT NOT NULL, checked_at TEXT NOT NULL,
 status TEXT NOT NULL, note TEXT NOT NULL DEFAULT '', api_requests INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_checks_route ON checks(route_key, checked_at);
CREATE TABLE IF NOT EXISTS api_requests (
 id INTEGER PRIMARY KEY AUTOINCREMENT, requested_at TEXT NOT NULL, kind TEXT NOT NULL,
 state TEXT NOT NULL DEFAULT 'reserved'
);
CREATE TABLE IF NOT EXISTS observations (
 id INTEGER PRIMARY KEY AUTOINCREMENT, seen_at TEXT NOT NULL, itinerary_key TEXT NOT NULL,
 route_key TEXT NOT NULL, origin TEXT NOT NULL, destination TEXT NOT NULL,
 departure TEXT NOT NULL, return_departure TEXT NOT NULL, arrival_home TEXT NOT NULL,
 price_couple REAL NOT NULL, source TEXT NOT NULL,
 airline TEXT, stops_out INTEGER, stops_back INTEGER,
 duration_out INTEGER, duration_back INTEGER, baggage TEXT, remarks TEXT,
 search_url TEXT, url_type TEXT DEFAULT 'pesquisa_geral',
 overnight INTEGER DEFAULT 0, airport_change INTEGER DEFAULT 0,
 return_origin TEXT, journey_type TEXT NOT NULL DEFAULT 'round_trip',
 price_status TEXT NOT NULL DEFAULT 'cotacao_api', data_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS ix_observation_key ON observations(itinerary_key, seen_at);
CREATE INDEX IF NOT EXISTS ix_observation_date ON observations(seen_at);
CREATE TABLE IF NOT EXISTS market_snapshots (
 id INTEGER PRIMARY KEY AUTOINCREMENT, seen_at TEXT NOT NULL,
 route_key TEXT NOT NULL, origin TEXT NOT NULL, destination TEXT NOT NULL,
 departure TEXT NOT NULL, return_departure TEXT NOT NULL,
 price_couple REAL NOT NULL CHECK(price_couple > 0),
 airline TEXT, stops_out INTEGER, duration_out INTEGER,
 outbound_key TEXT NOT NULL, source TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'indicativo_sem_volta_validada',
 search_url TEXT
);
CREATE INDEX IF NOT EXISTS ix_snapshot_date ON market_snapshots(seen_at);
CREATE INDEX IF NOT EXISTS ix_snapshot_route ON market_snapshots(route_key, seen_at);
CREATE TABLE IF NOT EXISTS outbound_attempts (
 route_key TEXT NOT NULL, outbound_key TEXT NOT NULL,
 checked_at TEXT NOT NULL,
 PRIMARY KEY(route_key, outbound_key)
);
CREATE TABLE IF NOT EXISTS scan_diagnostics (
 check_id INTEGER PRIMARY KEY,
 city TEXT NOT NULL,
 mode TEXT NOT NULL,
 metrics_json TEXT NOT NULL,
 FOREIGN KEY(check_id) REFERENCES checks(id)
);
CREATE TABLE IF NOT EXISTS alerts (
 itinerary_key TEXT PRIMARY KEY, last_price REAL NOT NULL, last_sent TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS extras (
 destination TEXT NOT NULL, mode TEXT NOT NULL, target_city TEXT NOT NULL,
 couple_transfer_brl REAL, couple_baggage_brl REAL, couple_airport_brl REAL,
 hours_each_way REAL, notes TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL,
 PRIMARY KEY(destination, mode, target_city)
);
'''


class Database:
    def __init__(self, path: str):
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as conn:
            conn.executescript(SCHEMA)
            # Migração aditiva sem apagar observações da v3.
            existing = {r[1] for r in conn.execute('PRAGMA table_info(observations)')}
            if 'return_origin' not in existing:
                conn.execute('ALTER TABLE observations ADD COLUMN return_origin TEXT')
            if 'journey_type' not in existing:
                conn.execute("ALTER TABLE observations ADD COLUMN journey_type TEXT NOT NULL DEFAULT 'round_trip'")

    @contextmanager
    def connection(self):
        con = sqlite3.connect(self.path, timeout=30)
        con.row_factory = sqlite3.Row
        con.execute('PRAGMA busy_timeout=30000')
        try:
            yield con
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

    def query(self, sql, params=()):
        with self.connection() as c:
            return [dict(r) for r in c.execute(sql, params).fetchall()]

    def execute(self, sql, params=()):
        with self.connection() as c:
            return c.execute(sql, params).lastrowid

    def requests_in_30d(self) -> int:
        since = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat(timespec='seconds')
        return self.query('SELECT COUNT(*) n FROM api_requests WHERE requested_at >= ?', (since,))[0]['n']

    def reserve_request(self, kind: str):
        return self.execute('INSERT INTO api_requests(requested_at, kind) VALUES (?,?)', (utcnow(),kind))

    def settle_request(self, req_id: int, state: str):
        self.execute('UPDATE api_requests SET state=? WHERE id=?', (state, req_id))

    def record_check(self, key: str, status: str, note: str, num_requests: int,
                     city: str = '', metrics: dict | None = None):
        check_id = self.execute('INSERT INTO checks(route_key,checked_at,status,note,api_requests) VALUES (?,?,?,?,?)',
                                (key, utcnow(), status, note[:350], num_requests))
        if metrics is not None:
            self.execute('INSERT INTO scan_diagnostics(check_id,city,mode,metrics_json) VALUES (?,?,?,?)',
                         (check_id, city, 'open_jaw' if key.startswith('OJ|') else 'round_trip',
                          json.dumps(metrics, ensure_ascii=False)))
        return check_id

    def add_observation(self, offer: dict):
        columns = ('seen_at','itinerary_key','route_key','origin','destination','departure',
                   'return_departure','arrival_home','price_couple','source','airline','stops_out',
                   'stops_back','duration_out','duration_back','baggage','remarks','search_url',
                   'url_type','overnight','airport_change','price_status','data_json',
                   'return_origin','journey_type')
        values = [offer.get(k) for k in columns]
        placeholders = ','.join('?' for _ in columns)
        self.execute(f"INSERT INTO observations ({','.join(columns)}) VALUES ({placeholders})", values)

    def best_offers(self, origin='', destination='', max_price=0, departure='', limit=150):
        terms = []
        args = []
        if origin:
            terms.append('o.origin=?'); args.append(origin)
        if destination:
            terms.append('o.destination=?'); args.append(destination)
        if max_price:
            terms.append('o.price_couple<=?'); args.append(max_price)
        if departure:
            terms.append('o.departure=?'); args.append(departure)
        where = ('WHERE ' + ' AND '.join(terms)) if terms else ''
        sql = f'''SELECT o.* FROM observations o
          JOIN (SELECT itinerary_key, MAX(id) AS latest_id FROM observations GROUP BY itinerary_key) latest
          ON o.id=latest.latest_id {where} ORDER BY o.price_couple ASC LIMIT ?'''
        return self.query(sql, (*args,limit))

    def route_last_checks(self):
        return {r['route_key']: r['last_check'] for r in self.query(
            "SELECT route_key, MAX(checked_at) AS last_check FROM checks "
            "WHERE status IN ('cotado','somente_indicativo','resultados_descartados','sem_resultado','parcial') GROUP BY route_key")}

    def route_last_sequences(self):
        # IDs crescentes resolvem empate quando duas pesquisas começam no mesmo segundo.
        return {r['route_key']: r['last_sequence'] for r in self.query(
            'SELECT route_key, MAX(id) AS last_sequence FROM checks GROUP BY route_key')}

    def city_coverage(self, planned_routes):
        # Resumo das quatro cidades, distinguindo consulta de erro de fonte.
        rows = self.query('''SELECT route_key, MAX(checked_at) last_checked,
            MAX(CASE WHEN status != 'erro' THEN 1 ELSE 0 END) successfully_consulted
            FROM checks GROUP BY route_key''')
        seen = {row['route_key']: row for row in rows}
        by_city = {}
        for city, key in planned_routes:
            item = by_city.setdefault(city, {
                'city':city, 'consulted':0, 'total':0,
                'last_checked':None, 'attempted':0
            })
            item['total'] += 1
            check = seen.get(key)
            if not check:
                continue
            item['attempted'] += 1
            if check['successfully_consulted']:
                item['consulted'] += 1
            if item['last_checked'] is None or check['last_checked'] > item['last_checked']:
                item['last_checked'] = check['last_checked']
        return list(by_city.values())

    def route_coverage(self, expected_keys):
        """Cobertura de combinações agrupadas: uma consulta não verifica cada aeroporto isoladamente."""
        expected = set(expected_keys)
        checked = self.query("SELECT DISTINCT route_key FROM checks WHERE status != 'erro'")
        covered = {x['route_key'] for x in checked} & expected
        successes = self.query("SELECT DISTINCT route_key FROM checks WHERE status = 'cotado'")
        verified = {x['route_key'] for x in successes} & expected
        return {'consulted': len(covered), 'total': len(expected),
                'complete_itineraries_found_in': len(verified),
                'not_yet_consulted': len(expected - covered),
                'scope': 'combinações agrupadas, não aeroportos individualmente'}

    def recent_checks(self, limit=40):
        return self.query('SELECT * FROM checks ORDER BY id DESC LIMIT ?', (limit,))

    def history(self, limit=240):
        return self.query('SELECT seen_at, origin, destination, return_origin, journey_type, departure, return_departure, '
                          'price_couple, itinerary_key FROM observations ORDER BY id DESC LIMIT ?', (limit,))


    def add_snapshots(self, snapshots: list[dict]) -> None:
        if not snapshots:
            return
        keys = ('seen_at','route_key','origin','destination','departure','return_departure',
                'price_couple','airline','stops_out','duration_out','outbound_key',
                'source','status','search_url')
        marks = ','.join('?' for _ in keys)
        with self.connection() as con:
            con.executemany(f"INSERT INTO market_snapshots ({','.join(keys)}) VALUES ({marks})",
                            [[item.get(k) for k in keys] for item in snapshots])

    def recent_snapshots(self, limit=250):
        return self.query('SELECT * FROM market_snapshots ORDER BY id DESC LIMIT ?', (limit,))

    def snapshot_minimum(self):
        return self.query('SELECT MIN(price_couple) AS minimum FROM market_snapshots')[0]['minimum']

    def snapshot_count(self):
        return self.query('SELECT COUNT(*) AS n FROM market_snapshots')[0]['n']

    def last_snapshot_by_destination(self):
        return self.query('''SELECT destination, MIN(price_couple) AS min_price,
            COUNT(*) AS seen_options, MAX(seen_at) AS last_seen
            FROM market_snapshots GROUP BY destination ORDER BY min_price''')

    def tried_outbounds(self, route_key):
        return {r['outbound_key'] for r in self.query(
            'SELECT outbound_key FROM outbound_attempts WHERE route_key=?',(route_key,))}

    def mark_outbound_tried(self, route_key, outbound_key):
        self.execute('''INSERT INTO outbound_attempts(route_key,outbound_key,checked_at)
            VALUES (?,?,?) ON CONFLICT(route_key,outbound_key) DO UPDATE SET
            checked_at=excluded.checked_at''', (route_key,outbound_key,utcnow()))

    def scan_count(self):
        return self.query('SELECT COUNT(*) AS n FROM checks')[0]['n']

    def alert_baseline(self, key):
        items = self.query('SELECT * FROM alerts WHERE itinerary_key=?', (key,))
        return items[0] if items else None

    def alert_sent(self, key, price):
        self.execute('INSERT INTO alerts(itinerary_key,last_price,last_sent) VALUES (?,?,?) '
                     'ON CONFLICT(itinerary_key) DO UPDATE SET last_price=excluded.last_price, last_sent=excluded.last_sent',
                     (key, price, utcnow()))

    def save_extra(self, x):
        self.execute('''INSERT INTO extras(destination,mode,target_city,couple_transfer_brl,couple_baggage_brl,
          couple_airport_brl,hours_each_way,notes,updated_at) VALUES (?,?,?,?,?,?,?,?,?)
          ON CONFLICT(destination,mode,target_city) DO UPDATE SET
          couple_transfer_brl=excluded.couple_transfer_brl, couple_baggage_brl=excluded.couple_baggage_brl,
          couple_airport_brl=excluded.couple_airport_brl, hours_each_way=excluded.hours_each_way,
          notes=excluded.notes, updated_at=excluded.updated_at''',
          (x['destination'],x['mode'],x['target_city'],x.get('couple_transfer_brl'),
           x.get('couple_baggage_brl'),x.get('couple_airport_brl'),x.get('hours_each_way'),
           x.get('notes',''),utcnow()))

    def extras(self):
        return self.query('SELECT * FROM extras ORDER BY destination,mode,target_city')

    def city_attempt_counts(self, planned_routes):
        lookup = {key: city for city, key in planned_routes}
        counts = {city: 0 for city in dict(planned_routes)}
        for record in self.query('SELECT route_key, COUNT(*) AS n FROM checks GROUP BY route_key'):
            city = lookup.get(record['route_key'])
            if city is not None:
                counts[city] = counts.get(city, 0) + record['n']
        return counts

    def scan_diagnostics(self, limit=50):
        rows = self.query('''SELECT d.check_id, d.city, d.mode, d.metrics_json, c.status,
                          c.checked_at, c.api_requests FROM scan_diagnostics d
                          JOIN checks c ON c.id=d.check_id ORDER BY c.id DESC LIMIT ?''', (limit,))
        for row in rows:
            row['metrics'] = json.loads(row.pop('metrics_json'))
        return rows

    def market_reference(self):
        """Mínima/mediana/máxima da AMOSTRA, nunca do mercado inteiro."""
        snap = self.query("SELECT destination, price_couple, seen_at FROM market_snapshots WHERE route_key NOT LIKE 'OJ|%' ORDER BY id")
        verified = self.query('SELECT destination, journey_type, price_couple, seen_at FROM observations ORDER BY id')
        out = []
        for city, dests in (('Roma',('FCO',)),('Milão',('MXP','BGY','LIN')),
                            ('Barcelona',('BCN',)),('Madri',('MAD',))):
            preview = [r for r in snap if r['destination'] in dests]
            complete = [r for r in verified if r['destination'] in dests and r['journey_type']=='round_trip']
            prices = [r['price_couple'] for r in preview]
            days = sorted({str(r['seen_at'])[:10] for r in preview})
            old = [r['price_couple'] for r in preview if str(r['seen_at'])[:10] == days[0]] if days else []
            new = [r['price_couple'] for r in preview if str(r['seen_at'])[:10] == days[-1]] if days else []
            out.append({'city':city,'airports':list(dests), 'sample_size':len(preview),
                        'min_indicative':min(prices) if prices else None,
                        'median_indicative':round(median(prices),2) if prices else None,
                        'max_indicative':max(prices) if prices else None,
                        'best_complete':min((r['price_couple'] for r in complete),default=None),
                        'last_seen':max((r['seen_at'] for r in preview),default=None),
                        'days_observed':len(days),
                        'first_day_min':min(old) if old else None,
                        'latest_day_min':min(new) if new else None,
                        'change_brl':round(min(new)-min(old),2) if len(days)>1 else None})
        return out
