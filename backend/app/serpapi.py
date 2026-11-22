"""Integração documentada com SerpApi Google Flights; nenhuma raspagem direta."""
import logging
from datetime import date
from hashlib import sha256
from urllib.parse import urlparse
import json
import httpx

from .trip import Route, OpenJawRoute, ALL_ORIGINS, ALL_DESTINATIONS, is_valid_trip
from .db import utcnow

log = logging.getLogger(__name__)
BASE = 'https://serpapi.com'


class SourceError(Exception):
    pass


class SerpApi:
    def __init__(self, key: str, client: httpx.Client | None = None):
        self.key = key
        self.client = client or httpx.Client(timeout=30.0, follow_redirects=False)

    def account(self) -> dict:
        if not self.key:
            raise SourceError('SERPAPI_KEY não configurada')
        try:
            response = self.client.get(f'{BASE}/account.json', params={'api_key': self.key})
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict) or 'plan_searches_left' not in data:
                raise SourceError('Saldo da conta não disponível; consultas bloqueadas por segurança')
            # Fail closed: zero billing. Only use the explicitly free monthly plan.
            if str(data.get('plan_name','')).lower().find('free') < 0 or float(data.get('plan_monthly_price', -1)) != 0:
                raise SourceError('Conta não está no plano gratuito. Pesquisas bloqueadas.')
            return {k: data.get(k) for k in ('plan_name','searches_per_month','plan_searches_left',
                        'this_month_usage','account_rate_limit_per_hour','this_hour_searches','last_hour_searches','plan_renewal_date')}
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            raise SourceError('Não foi possível validar gratuitamente o saldo da SerpApi') from exc

    def search(self, route: Route, reserve, departure_token: str | None = None) -> dict:
        params = {'engine':'google_flights', 'adults':2, 'travel_class':1,
                  'gl':'br', 'hl':'pt', 'currency':'BRL', 'sort_by':2, 'api_key':self.key}
        if isinstance(route, OpenJawRoute):
            # Conforme documentação oficial: type=3 usa SOMENTE multi_city_json.
            # A segunda chamada envia o departure_token da primeira perna.
            params['type'] = 3
            params['multi_city_json'] = json.dumps([
                {'departure_id': ','.join(route.origins),
                 'arrival_id': ','.join(route.destinations), 'date': str(route.departure)},
                {'departure_id': ','.join(route.return_origins),
                 'arrival_id': ','.join(route.origins), 'date': str(route.return_departure)},
            ], separators=(',', ':'))
        else:
            params.update({'type':1, 'departure_id':','.join(route.origins),
                           'arrival_id':','.join(route.destinations),
                           'outbound_date':str(route.departure),
                           'return_date':str(route.return_departure)})
        if departure_token:
            params['departure_token'] = departure_token
        request_id = reserve('return' if departure_token else 'outbound')
        state = 'error'
        try:
            res = self.client.get(f'{BASE}/search.json',params=params)
            if res.status_code == 429:
                raise SourceError('Limite por hora da SerpApi alcançado')
            if res.status_code in (401, 403):
                raise SourceError('Chave de API recusada ou cota esgotada')
            res.raise_for_status()
            data = res.json()
            if not isinstance(data, dict):
                raise SourceError('Formato inesperado de resposta')
            if data.get('error'):
                raise SourceError(str(data['error']).replace(self.key, '[CHAVE OCULTA]')[:200])
            state = 'completed'
            return data
        except (httpx.HTTPError, ValueError) as exc:
            raise SourceError('Falha na consulta de voos: HTTP/rede/resposta inválida') from exc
        finally:
            # reserva pessimista conta até falhas, para nunca ultrapassar orçamento local
            reserve('settle', request_id, state)


def candidates(data: dict) -> list[dict]:
    return [f for group in ('best_flights','other_flights')
            for f in (data.get(group) or []) if isinstance(f,dict) and type(f.get('price')) in (int,float)
            and f['price'] > 0 and isinstance(f.get('flights'),list) and f['flights']
            and all(isinstance(seg,dict) for seg in f['flights'])]


def pick_outbound(data: dict) -> dict | None:
    eligible = [x for x in candidates(data) if x.get('departure_token')]
    return min(eligible, key=lambda x: x['price']) if eligible else None


def outbound_signature(choice: dict) -> str:
    segments = [{'from': s.get('departure_airport'), 'to': s.get('arrival_airport'),
                 'number':s.get('flight_number'),
                 'departure_time':(s.get('departure_airport') or {}).get('time')} for s in choice.get('flights',[])]
    return sha256(json.dumps(segments,sort_keys=True,ensure_ascii=False).encode()).hexdigest()[:32]


def eligible_outbounds(data: dict, route: Route) -> list[dict]:
    # Apenas opções de ida nas datas/aeroportos procurados e com token de volta.
    return sorted((c for c in candidates(data)
                   if c.get('departure_token') and
                   _checks_leg(c.get('flights'),set(route.origins),
                               set(route.destinations),route.departure)),
                  key=lambda c: c['price'])


def outbound_market_snapshots(data: dict, route: Route) -> list[dict]:
    """Preços retornados na primeira chamada NÃO são passagens completas validadas.
    Nunca usar essas linhas para disparar alertas."""
    metadata = data.get('search_metadata') or {}
    source_url = metadata.get('google_flights_url')
    if not _is_safe_url(source_url):
        source_url = 'https://www.google.com/travel/flights?hl=pt-BR'
    collected = []
    distinct = set()
    for item in sorted(candidates(data), key=lambda x:x['price']):
        legs = item.get('flights', [])
        if not _checks_leg(legs,set(route.origins),set(route.destinations),route.departure):
            continue
        signature = outbound_signature(item)
        if signature in distinct:
            continue
        distinct.add(signature)
        collected.append({
            'seen_at':utcnow(), 'route_key':route.key,
            'origin':_loc(legs[0]['departure_airport']),
            'destination':_loc(legs[-1]['arrival_airport']),
            'departure':str(route.departure),'return_departure':str(route.return_departure),
            'price_couple':float(item['price']),
            'airline':', '.join(dict.fromkeys(str(x.get('airline','Não informada')) for x in legs)),
            'stops_out':len(legs)-1,'duration_out':item.get('total_duration'),
            'outbound_key':signature,'source':'SerpApi / Google Flights',
            'status':'indicativo_sem_volta_validada','search_url':source_url,
        })
    return collected


def _local_date(endpoint) -> date | None:
    try:
        return date.fromisoformat(str(endpoint['time'])[:10])
    except (TypeError,ValueError,KeyError):
        return None


def _loc(endpoint):
    return str(endpoint.get('id','')) if isinstance(endpoint,dict) else ''


def _is_safe_url(url):
    if not isinstance(url,str):
        return False
    p = urlparse(url)
    return p.scheme == 'https' and p.hostname in ('www.google.com', 'google.com') and p.path.startswith('/travel/flights')


def _checks_leg(segments, airports_origin, airports_dest, desired_departure):
    if not segments or not isinstance(segments,list):
        return False
    first, last = segments[0],segments[-1]
    if not isinstance(first,dict) or not isinstance(last,dict):
        return False
    return (_loc(first.get('departure_airport',{})) in airports_origin and
            _loc(last.get('arrival_airport',{})) in airports_dest and
            _local_date(first.get('departure_airport',{})) == desired_departure)


def _connection_flags(choice):
    segments = choice.get('flights', [])
    layovers = choice.get('layovers', []) or []
    unsafe = any(isinstance(x,dict) and isinstance(x.get('duration'),(int,float)) and x['duration'] < 60
                 for x in layovers)
    overnight = any(isinstance(x,dict) and x.get('overnight') for x in layovers)
    switch = any(_loc(a.get('arrival_airport',{})) != _loc(b.get('departure_airport',{}))
                 for a,b in zip(segments,segments[1:]))
    # Uma troca aeroportuária durante conexão curta precisa de confirmação manual.
    return unsafe, bool(overnight), bool(switch)


def reject_reason(outbound, return_choice, route):
    """Motivo de rejeição, para auditar uma resposta real sem divulgar tokens ou credenciais."""
    outbound_legs, return_legs = outbound.get('flights', []), return_choice.get('flights', [])
    if not _checks_leg(outbound_legs, set(route.origins), set(route.destinations), route.departure):
        return 'ida_fora_da_rota'
    origin_group = route.return_origins if isinstance(route, OpenJawRoute) else route.destinations
    if not _checks_leg(return_legs, set(origin_group), set(route.origins), route.return_departure):
        return 'volta_fora_da_rota_ou_data'
    arrival = _local_date(return_legs[-1].get('arrival_airport', {}))
    if not arrival:
        return 'chegada_nao_informada'
    if not is_valid_trip(route.departure, arrival):
        return 'nao_completa_17_dias'
    price = return_choice.get('price')
    if isinstance(price, bool) or not isinstance(price, (float, int)) or price <= 0:
        return 'preco_invalido'
    if _connection_flags(outbound)[0] or _connection_flags(return_choice)[0]:
        return 'conexao_inferior_a_60_minutos'
    return None


def make_offer(outbound: dict, return_choice: dict, route: Route | OpenJawRoute, first_response: dict) -> dict | None:
    if reject_reason(outbound, return_choice, route):
        return None
    out_legs, back_legs = outbound.get('flights',[]), return_choice.get('flights',[])
    if not _checks_leg(out_legs, set(route.origins),set(route.destinations),route.departure):
        return None
    return_origin_group = route.return_origins if isinstance(route, OpenJawRoute) else route.destinations
    if not _checks_leg(back_legs,set(return_origin_group),set(route.origins),route.return_departure):
        return None
    arrival = _local_date(back_legs[-1].get('arrival_airport',{}))
    if not arrival or not is_valid_trip(route.departure,arrival):
        return None
    price = return_choice.get('price')
    if isinstance(price,bool) or not isinstance(price,(float,int)) or price <= 0:
        return None
    unsafe_out, overnight_out, switched_out = _connection_flags(outbound)
    unsafe_back, overnight_back, switched_back = _connection_flags(return_choice)
    if unsafe_out or unsafe_back:
        return None
    origin = _loc(out_legs[0].get('departure_airport',{}))
    destination = _loc(out_legs[-1].get('arrival_airport',{}))
    back_arrival_airport = _loc(back_legs[-1].get('arrival_airport',{}))
    back_origin_airport = _loc(back_legs[0].get('departure_airport',{}))
    if origin not in ALL_ORIGINS or destination not in ALL_DESTINATIONS:
        return None
    airlines = list(dict.fromkeys(str(s.get('airline','Não informado')) for s in out_legs+back_legs))
    extensions = [str(v) for r in (outbound,return_choice) for v in (r.get('extensions') or [])]
    baggage = '; '.join(e for e in extensions if any(w in e.lower() for w in ('bag','mala','bagagem'))) or 'Não informada pela fonte'
    remarks = []
    if switched_out or switched_back:
        remarks.append('Troca de aeroporto em conexão: conferir tempo e custos')
    if origin != back_arrival_airport:
        remarks.append(f'Volta aterrissa em {back_arrival_airport}; ida parte de {origin}')
    if overnight_out or overnight_back:
        remarks.append('Há conexão noturna/pernoite: conferir hospedagem')
    if isinstance(route, OpenJawRoute):
        remarks.append('Multi-city: transporte interno entre cidades italianas NÃO incluído')
    remarks.append('Valor para 2 adultos informado pela fonte; taxas/bagagem e preço final sujeitos à confirmação')
    meta_url = (first_response.get('search_metadata') or {}).get('google_flights_url')
    url = meta_url if _is_safe_url(meta_url) else 'https://www.google.com/travel/flights?hl=pt-BR'
    signature = [{'dep':f.get('departure_airport'), 'arr':f.get('arrival_airport'),
                  'flight':f.get('flight_number')} for f in out_legs+back_legs]
    key = sha256(json.dumps(signature,sort_keys=True,ensure_ascii=False).encode()).hexdigest()[:32]
    return {
        'seen_at': utcnow(), 'itinerary_key':key, 'route_key':route.key,
        'origin':origin, 'destination':destination,
        'return_origin':back_origin_airport,
        'journey_type':'open_jaw' if isinstance(route, OpenJawRoute) else 'round_trip',
        'departure':str(route.departure),
        'return_departure':str(route.return_departure),'arrival_home':str(arrival),
        'price_couple':float(price), 'source':'SerpApi / Google Flights',
        'airline':', '.join(airlines), 'stops_out':max(0,len(out_legs)-1),
        'stops_back':max(0,len(back_legs)-1),
        'duration_out':outbound.get('total_duration'), 'duration_back':return_choice.get('total_duration'),
        'baggage':baggage, 'remarks':'; '.join(remarks), 'search_url':url,
        'url_type':'pesquisa_do_google_flights' if _is_safe_url(meta_url) else 'pesquisa_geral',
        'overnight':int(overnight_out or overnight_back),
        'airport_change':int(switched_out or switched_back or origin!=back_arrival_airport),
        'price_status':'cotacao_api',
        'data_json': json.dumps({'outbound':outbound,'return':return_choice},ensure_ascii=False),
    }


def confirmed_offers(outbound, followup, route, first_response):
    """Apenas retornos com voos completos; preços de saída não são ofertas completas."""
    result = []
    for item in sorted(candidates(followup),key=lambda o:o['price']):
        offer = make_offer(outbound,item,route,first_response)
        if offer:
            result.append(offer)
    return result
