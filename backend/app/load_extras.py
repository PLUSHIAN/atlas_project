"""Incorpora orçamentos MANUAIS do repositório, sem inventar valores."""
import json
from pathlib import Path
from .main import db

ALLOWED_DEST = {'BCN','MAD','ROM_MIL','MIL_ROM'}
ALLOWED_MODE = {'avião','trem','ônibus','outro'}
ALLOWED_CITY = {'Roma','Milão'}
NUMERICS = ('couple_transfer_brl','couple_baggage_brl','couple_airport_brl','hours_each_way')

def read_items(path: str = 'config/extras.json'):
    data = json.loads(Path(path).read_text(encoding='utf8'))
    if not isinstance(data, list):
        raise ValueError('extras.json precisa ser um array JSON')
    for item in data:
        if not isinstance(item, dict):
            raise ValueError('Cada entrada deve ser um objeto JSON')
        if item.get('destination') not in ALLOWED_DEST or item.get('mode') not in ALLOWED_MODE or item.get('target_city') not in ALLOWED_CITY:
            raise ValueError('Destino, modo ou cidade inválidos em extras.json')
        for field in NUMERICS:
            value=item.get(field)
            if value is not None and (type(value) not in (int,float) or value < 0):
                raise ValueError(f'{field} precisa ser >= 0 ou null')
        if not isinstance(item.get('notes',''),str) or len(item.get('notes','')) > 400:
            raise ValueError('notes inválido em extras.json')
    return data

def main():
    items=read_items()
    for item in items:
        db.save_extra(item)
    print(f'{len(items)} orçamento(s) manual(is) incorporado(s), sem consulta API')

if __name__ == '__main__':
    main()
