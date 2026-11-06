from fastapi.testclient import TestClient
from app.main import app
c=TestClient(app)
def h():return {'Authorization':'Bearer '+c.post('/auth/token',data={'username':'admin@example.com','password':'change-me-now'}).json()['access_token']}
def test_run_and_ciphertext_boundary():
    x=h();r=c.post('/workflows',headers=x,json={'name':'demo','tasks':[{'id':'a','command':'echo a','payload':{'secret':'hidden'}},{'id':'b','command':'echo b','depends_on':['a']}]});assert r.status_code==201 and 'hidden' not in r.text
    assert c.post('/workflows/'+r.json()['id']+'/run',headers=x).json()['status']=='SUCCEEDED'
def test_cycle():
    assert c.post('/workflows',headers=h(),json={'name':'bad','tasks':[{'id':'a','command':'a','depends_on':['b']},{'id':'b','command':'b','depends_on':['a']}]}).status_code==422
