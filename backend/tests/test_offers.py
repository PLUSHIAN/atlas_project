from datetime import date
from app.trip import Route
from app.serpapi import pick_outbound,confirmed_offers

route = Route(('GRU','CGH','VCP'),('FCO',),date(2027,9,8),date(2027,9,23))

def segment(origin,destination,leave,arrive):
    return {'departure_airport':{'id':origin,'time':leave},'arrival_airport':{'id':destination,'time':arrive},
            'airline':'Companhia de teste','flight_number':'TST100'}

def test_only_return_confirmed_and_17_days():
    departure={'price':7400,'departure_token':'token_falso_somente_em_teste',
               'flights':[segment('GRU','FCO','2027-09-08 18:00','2027-09-09 12:00')],
               'total_duration':900}
    ret={'price':7600,'flights':[segment('FCO','GRU','2027-09-23 19:00','2027-09-24 04:00')],
         'total_duration':750}
    assert pick_outbound({'best_flights':[departure]}) == departure
    assert confirmed_offers(departure,{'best_flights':[ret]},route,{})[0]['price_couple']==7600
    late=dict(ret,flights=[segment('FCO','GRU','2027-09-23 19:00','2027-09-25 04:00')])
    assert confirmed_offers(departure,{'best_flights':[late]},route,{})==[]
    assert confirmed_offers(departure,{'best_flights':[]},route,{})==[]
    assert pick_outbound({'best_flights':[{'price':4000,'flights':departure['flights']}]}) is None
