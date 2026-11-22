"""Monitor SerpApi: prioridade Espanha, custos conhecidos e diagnósticos por rodada."""
import logging
from collections import Counter
from datetime import datetime, timedelta, timezone
from threading import Lock, Thread
from .trip import all_routes, SEARCH_CITIES
from .serpapi import (SerpApi, SourceError, candidates, eligible_outbounds,
                      outbound_signature, outbound_market_snapshots, confirmed_offers,
                      reject_reason)
from .value import transfer_key
from .emailer import send_mail

log = logging.getLogger(__name__)

# Dois slots para Espanha a cada terceiro slot para Itália. As duas cidades
# italianas e as duas direções de multidestinos NUNCA desaparecem do ciclo.
SPAIN_CYCLE = ('Barcelona', 'Madri', 'Roma',
               'Barcelona', 'Madri', 'Milão',
               'Barcelona', 'Madri', 'Roma → Milão',
               'Barcelona', 'Madri', 'Milão → Roma')
EQUAL_CYCLE = SEARCH_CITIES


class Monitor:
    def __init__(self, db, settings, provider=None):
        self.db = db
        self.settings = settings
        self.provider = provider or SerpApi(settings.serpapi_key)
        self.lock = Lock()
        self.last_error = None
        self.last_result = None

    def plan(self):
        return all_routes(include_open_jaw=self.settings.open_jaw_enabled)

    def sequence(self):
        cycle = SPAIN_CYCLE if self.settings.spain_priority else EQUAL_CYCLE
        return tuple(c for c in cycle if c in {r.city for r in self.plan()})

    def pick_route(self, destination=None):
        plan = self.plan()
        cities = {r.city for r in plan}
        if destination is not None and destination not in cities:
            raise ValueError('Destino inválido ou multidestinos desativado')
        if destination is None:
            destination = self.sequence()[self.db.scan_count() % len(self.sequence())]
        options = [r for r in plan if r.city == destination]
        attempts = self.db.route_last_sequences()
        consulted = self.db.route_last_checks()
        # Primeiro explorar quatro datas de saída, depois alternar grupos de
        # aeroportos e retornos. Evita gastar todo o início da cota na mesma data.
        untried = [r for r in options if r.key not in attempts]
        if untried:
            date_counts = Counter(r.departure for r in options if r.key in consulted)
            origin_counts = Counter(r.origins for r in options if r.key in attempts)
            return min(untried, key=lambda r: (
                date_counts[r.departure], origin_counts[r.origins],
                r.departure, r.return_departure))
        # Depois da cobertura inicial, renovar primeiro as buscas mais antigas.
        return min(options, key=lambda r: (attempts.get(r.key, 0), r.key))

    def status(self):
        checks = self.db.recent_checks(1)
        balance = None
        quota_error = None
        if self.settings.serpapi_key:
            try:
                balance = self.provider.account()
            except SourceError as exc:
                quota_error = str(exc)
        plan = self.plan()
        return {
            'enabled': self.settings.scan_enabled,
            'configured': bool(self.settings.serpapi_key),
            'running': self.lock.locked(),
            'last_check': checks[0] if checks else None,
            'last_error': self.last_error or quota_error,
            'last_result': self.last_result,
            'interval_hours': self.settings.scan_interval_hours,
            'used_requests_30d': self.db.requests_in_30d(),
            'max_requests_30d': self.settings.max_30d_requests,
            'quota': balance,
            'smtp_ready': self.settings.smtp_ready,
            'route_count': len(plan),
            'search_mode': ('Espanha 2 a cada 3 consultas; Itália e multidestinos inclusos'
                            if self.settings.spain_priority else 'Alternância igualitária'),
            'next_destination': self.pick_route().city,
            'search_cycle': list(self.sequence()),
            'city_coverage': self.db.city_coverage([(r.city, r.key) for r in plan]),
            'city_attempt_counts': self.db.city_attempt_counts([(r.city, r.key) for r in plan]),
        }

    def _credit_guard(self, num_credits):
        remaining = self.settings.max_30d_requests - self.db.requests_in_30d()
        if remaining < num_credits:
            raise SourceError('Limite local de segurança de requisições em 30 dias alcançado')
        account = self.provider.account()
        left = account.get('plan_searches_left')
        hourly_count = account.get('this_hour_searches')
        hourly_limit = account.get('account_rate_limit_per_hour')
        if not isinstance(left, (float, int)) or left < num_credits:
            raise SourceError('Cota mensal gratuita insuficiente para a próxima consulta')
        if (not isinstance(hourly_count, (float, int)) or
            not isinstance(hourly_limit, (float, int)) or hourly_limit - hourly_count < num_credits):
            raise SourceError('Cota horária insuficiente; tente na próxima execução')

    def _reserve(self, kind, request_id=None, state=None):
        if kind == 'settle':
            self.db.settle_request(request_id, state)
            return
        self._credit_guard(1)
        return self.db.reserve_request(kind)

    def _extra_for(self, offer):
        key = transfer_key(offer)
        if key is None:
            return None
        for item in self.db.extras():
            if item['destination'] != key:
                continue
            parts = [item.get(k) for k in ('couple_transfer_brl', 'couple_baggage_brl', 'couple_airport_brl')]
            if all(value is not None for value in parts):
                return dict(item, additional_total=sum(parts),
                            estimated_total=offer['price_couple'] + sum(parts),
                            basis='estimativa_manual')
        return {'estimated_total': None, 'basis': 'indisponivel'}

    def _should_alert(self, offer):
        if offer['price_couple'] > 8000:
            return False
        existing = self.db.alert_baseline(offer['itinerary_key'])
        if not existing:
            return True
        drop = existing['last_price'] - offer['price_couple']
        return (drop >= self.settings.alert_min_drop_brl and
                drop / existing['last_price'] * 100 >= self.settings.alert_min_drop_pct)

    def scan_once(self, destination=None):
        if not self.lock.acquire(blocking=False):
            return {'status': 'ocupado', 'message': 'Já existe uma pesquisa em execução'}
        route = None
        initial_count = self.db.requests_in_30d()
        try:
            if not self.settings.serpapi_key:
                raise SourceError('Configure SERPAPI_KEY no .env para consultar cotações reais')
            route = self.pick_route(destination)
            last = self.db.route_last_checks().get(route.key)
            if last and datetime.fromisoformat(last) > datetime.now(timezone.utc) - timedelta(hours=self.settings.cache_hours):
                # Registra cache como verificação sem consumo, para mover a fila na rodada seguinte.
                result = {'status': 'cache', 'destination': route.city, 'message': 'Combinação já consultada dentro da janela de cache', 'offers': 0}
                self.db.record_check(route.key, 'cache', result['message'], 0, route.city,
                                     {'cache_hit': True})
                self.last_result = result
                return result
            self._credit_guard(1)
            first = self.provider.search(route, self._reserve)
            raw_count = len(candidates(first))
            snapshots = outbound_market_snapshots(first, route)
            self.db.add_snapshots(snapshots)
            outbounds = eligible_outbounds(first, route)
            selected = []
            seen_signatures = set()
            tried = self.db.tried_outbounds(route.key)
            for item in sorted(outbounds, key=lambda x: (outbound_signature(x) in tried, x['price'])):
                signature = outbound_signature(item)
                if signature not in seen_signatures:
                    selected.append(item)
                    seen_signatures.add(signature)
            # Em uma de cada 4 rodadas, usar um retorno extra, se a cota permitir.
            followups = min(1 + int((self.db.scan_count() + 1) % 4 == 0),
                            self.settings.max_return_checks_per_scan)
            completed = []
            discarded = Counter()
            attempted = 0
            return_count = 0
            error = None
            for outbound in selected[:followups]:
                try:
                    self._credit_guard(1)
                    self.db.mark_outbound_tried(route.key, outbound_signature(outbound))
                    second = self.provider.search(route, self._reserve, outbound['departure_token'])
                    attempted += 1
                    options = candidates(second)
                    return_count += len(options)
                    for item in options:
                        reason = reject_reason(outbound, item, route)
                        if reason:
                            discarded[reason] += 1
                    completed.extend(confirmed_offers(outbound, second, route, first))
                except SourceError as exc:
                    error = str(exc)
                    log.warning('Preço indicativo salvo, mas volta não validada: %s', error)
                    break
            deduplicated = {}
            for offer in completed:
                key = offer['itinerary_key']
                if key not in deduplicated or offer['price_couple'] < deduplicated[key]['price_couple']:
                    deduplicated[key] = offer
            offers = sorted(deduplicated.values(), key=lambda x: x['price_couple'])
            for offer in offers:
                self.db.add_observation(offer)
                if self._should_alert(offer) and self.settings.smtp_ready:
                    try:
                        send_mail(self.settings, offer, self._extra_for(offer))
                    except Exception as exc:
                        log.warning('Não foi possível enviar alerta: %s', type(exc).__name__)
                    else:
                        self.db.alert_sent(offer['itinerary_key'], offer['price_couple'])
            if offers:
                status = 'cotado'
            elif error:
                status = 'parcial'
            elif snapshots:
                status = 'somente_indicativo'
            elif raw_count:
                status = 'resultados_descartados'
            else:
                status = 'sem_resultado'
            metrics = {'received_first_stage': raw_count,
                       'indicative_prices_recorded': len(snapshots),
                       'eligible_outbounds': len(outbounds),
                       'outbounds_with_followup': attempted,
                       'return_candidates': return_count,
                       'complete_itineraries': len(offers),
                       'rejections': dict(discarded),
                       'followup_error': error,
                       'route_key': route.key}
            message = (f'{raw_count} resultados iniciais; {len(snapshots)} prévias salvas; '
                       f'{attempted} ida(s) analisada(s); {return_count} opções de volta; '
                       f'{len(offers)} viagens completas. ' + (error or ''))
            result = {'status': status, 'destination': route.city, 'message': message,
                      'offers': len(offers), 'min_price': min((x['price_couple'] for x in offers), default=None),
                      'preview_count': len(snapshots),
                      'min_preview': min((x['price_couple'] for x in snapshots), default=None),
                      'raw_outbound_count': raw_count, 'return_options': return_count,
                      'outbounds_verified': attempted, 'rejections': dict(discarded)}
            self.last_result = result
            self.last_error = None
            self.db.record_check(route.key, status, message,
                                 self.db.requests_in_30d() - initial_count, route.city, metrics)
            return result
        except SourceError as exc:
            self.last_error = str(exc)
            result = {'status': 'erro', 'destination': route.city if route else destination,
                      'message': str(exc)}
            if route:
                self.db.record_check(route.key, 'erro', str(exc),
                                     self.db.requests_in_30d() - initial_count, route.city,
                                     {'error': str(exc)})
            log.warning('Pesquisa cancelada: %s', str(exc))
            return result
        except Exception:
            log.exception('Falha inesperada, pesquisa interrompida')
            self.last_error = 'Erro interno; veja logs/monitor.log'
            if route:
                self.db.record_check(route.key, 'erro', self.last_error,
                                     self.db.requests_in_30d() - initial_count, route.city,
                                     {'error': 'Falha inesperada'})
            return {'status': 'erro', 'message': self.last_error}
        finally:
            self.lock.release()

    def start_async(self, destination=None) -> bool:
        if self.lock.locked():
            return False
        Thread(target=self.scan_once, kwargs={'destination': destination},
               name='manual-scan', daemon=True).start()
        return True
