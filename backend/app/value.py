"""Rankings explicáveis, sem estimativas fictícias nem conversão de prévias em ofertas."""


def transfer_key(offer: dict) -> str | None:
    if offer.get('journey_type') == 'open_jaw':
        return 'ROM_MIL' if offer.get('destination') == 'FCO' else 'MIL_ROM'
    return offer.get('destination') if offer.get('destination') in ('BCN', 'MAD') else None


def itinerary_warnings(offer: dict) -> list[str]:
    warnings = []
    if (offer.get('stops_out') or 0) >= 2 or (offer.get('stops_back') or 0) >= 2:
        warnings.append('Duas ou mais escalas em um dos trechos')
    if any(isinstance(offer.get(field), (int, float)) and offer[field] > 20 * 60
           for field in ('duration_out', 'duration_back')):
        warnings.append('Um dos trechos dura mais de 20 horas')
    if offer.get('overnight'):
        warnings.append('Conexão com possível pernoite')
    if offer.get('airport_change'):
        warnings.append('Troca de aeroporto em conexão ou aeroporto de chegada diferente no Brasil')
    baggage = str(offer.get('baggage') or '')
    if not baggage or 'não informad' in baggage.lower():
        warnings.append('Franquia de bagagem não confirmada')
    if offer.get('journey_type') == 'open_jaw':
        warnings.append('Deslocamento entre Roma e Milão NÃO incluído no bilhete internacional')
    elif offer.get('destination') in ('BCN', 'MAD'):
        warnings.append('Espanha–Itália exige bilhetes separados e tempo de conexão seguro')
    return warnings


def enrich_offer(offer: dict, extras: list[dict]) -> dict:
    item = dict(offer)
    item['extras'] = extras
    item['warnings'] = itinerary_warnings(item)
    item['price_individual_calculated'] = round(item['price_couple'] / 2, 2)
    if transfer_key(item):
        valid = [e['estimated_total'] for e in extras if e.get('estimated_total') is not None]
        item['comparable_total'] = min(valid) if valid else None
        item['total_basis'] = 'passagem_internacional_mais_estimativa_manual' if valid else 'transporte_adicional_indisponivel'
    else:
        item['comparable_total'] = item['price_couple']
        item['total_basis'] = 'somente_passagem_internacional'
    item['price_label'] = 'Cotação histórica: confirmar tarifa, taxas e bagagem antes da compra'
    return item


def value_ranking(offers: list[dict]) -> list[dict]:
    """Pontuação baseada em preço relativo + inconvenientes; nunca 'preço justo' do mercado.

    Escalas não são custos monetários. Com gastos adicionais desconhecidos, não há nota.
    """
    known = [o['comparable_total'] for o in offers if o.get('comparable_total') is not None]
    floor = min(known) if known else None
    result = []
    for entry in offers:
        row = dict(entry)
        total = row.get('comparable_total')
        warnings = list(row.get('warnings') or [])
        if total is None or floor is None:
            row.update(value_score=None, value_reasons=['Transporte adicional ainda sem preço'],
                       value_basis='indisponivel_ate_completar_custos')
            result.append(row)
            continue
        penalty = min(45, round((total - floor) / 100))
        reasons = ([f'Custo conhecido R$ {total-floor:,.0f} acima do menor da amostra'] if penalty else [])
        penalty += min(int(row.get('stops_out') or 0), 3) * 5
        penalty += min(int(row.get('stops_back') or 0), 3) * 5
        if row.get('overnight'):
            penalty += 14
        if row.get('airport_change'):
            penalty += 12
        if any((row.get(key) or 0) > 1200 for key in ('duration_out', 'duration_back')):
            penalty += 10
        if any('bagagem não confirmada' in w.lower() for w in warnings):
            penalty += 8
        if row.get('total_basis') == 'passagem_internacional_mais_estimativa_manual':
            reasons.append('Adicional manual, não cotado pela API')
        row.update(value_score=max(0, 100 - penalty),
                   value_reasons=reasons + warnings,
                   value_basis='heuristica_preco_conexoes_duracao_bagagem')
        result.append(row)
    return result
