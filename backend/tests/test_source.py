from app.serpapi import SerpApi, SourceError

class Response:
    def __init__(self,payload): self.payload=payload
    def raise_for_status(self): pass
    def json(self): return self.payload

class Client:
    def __init__(self,payload): self.payload=payload
    def get(self,*args,**kwargs): return Response(self.payload)

def test_free_only_account():
    free=SerpApi('fake_for_test',Client({'plan_name':'Free Plan','plan_monthly_price':0,'plan_searches_left':250}))
    assert free.account()['plan_searches_left']==250
    paid=SerpApi('fake_for_test',Client({'plan_name':'Starter','plan_monthly_price':25,'plan_searches_left':100}))
    try:
        paid.account()
    except SourceError:
        pass
    else:
        assert False,'Plano pago não pode pesquisar'
