from datetime import date
from app.trip import routes, days_inclusive, is_valid_trip, classification

def test_dates():
    assert days_inclusive(date(2027,9,8),date(2027,9,24)) == 17
    assert is_valid_trip(date(2027,9,11),date(2027,9,27))
    assert not is_valid_trip(date(2027,9,11),date(2027,9,28))
    assert not is_valid_trip(date(2027,9,8),date(2027,9,23))
    assert len(routes()) == 64
    assert {r.city for r in routes()} == {'Roma','Milão','Barcelona','Madri'}
    assert {a for r in routes() for a in r.origins} == {'GRU','CGH','VCP','GIG','SDU'}
    assert {a for r in routes() for a in r.destinations} == {'FCO','MXP','LIN','BGY','BCN','MAD'}

def test_budget():
    assert classification(6000)=='EXCELENTE OPORTUNIDADE'
    assert classification(6000.01)=='DENTRO DO ORÇAMENTO'
    assert classification(8000)=='DENTRO DO ORÇAMENTO'
    assert classification(8000.01)=='ACIMA DO ORÇAMENTO'
