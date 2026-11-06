import base64, json, os, secrets, time, uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, Field
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import Response

app=FastAPI(title='Dependency-Aware Cloud Task Orchestrator',version='1.0.0')
oauth=OAuth2PasswordBearer(tokenUrl='/auth/token'); pwd=CryptContext(schemes=['bcrypt'],deprecated='auto')
SECRET=os.getenv('JWT_SECRET','dev-only-change-me'); MASTER=bytes.fromhex(os.getenv('ORCHESTRATOR_MASTER_KEY','00'*32))
USERS={'admin@example.com':(pwd.hash('change-me-now'),'admin'),'operator@example.com':(pwd.hash('operator-pass'),'operator')}
WF={}; EVENTS={}; FAILURE=False
RUNS=Counter('orchestrator_runs_total','Workflow runs',['status']); TASKS=Counter('orchestrator_tasks_total','Task attempts',['status']); LATENCY=Histogram('orchestrator_task_latency_seconds','Task latency')

class Task(BaseModel):
    id:str=Field(pattern=r'^[A-Za-z0-9_-]{1,64}$'); command:str=Field(min_length=1,max_length=1000); depends_on:list[str]=[]; payload:dict[str,Any]={}; max_retries:int=Field(2,ge=0,le=10)
class Workflow(BaseModel): name:str=Field(min_length=1,max_length=120); tasks:list[Task]=Field(min_length=1,max_length=200)

def enc(v):
    n=secrets.token_bytes(12); return base64.urlsafe_b64encode(n+AESGCM(MASTER).encrypt(n,json.dumps(v).encode(),None)).decode()
def dec(v):
    b=base64.urlsafe_b64decode(v); return json.loads(AESGCM(MASTER).decrypt(b[:12],b[12:],None))
def current(token=Depends(oauth)):
    try:
        e=jwt.decode(token,SECRET,algorithms=['HS256'])['sub']; pw,role=USERS[e]; return {'email':e,'role':role}
    except (JWTError,KeyError): raise HTTPException(401,'Invalid or expired token')
def operator(u=Depends(current)):
    if u['role'] not in ('admin','operator'): raise HTTPException(403,'Operator role required')
    return u
def audit(w,e,**x): EVENTS.setdefault(w,[]).append({'timestamp':datetime.now(timezone.utc).isoformat(),'event':e,**x})
def validate(ts):
    ids={t.id for t in ts}
    if len(ids)!=len(ts): raise HTTPException(422,'Task IDs must be unique')
    g={t.id:t.depends_on for t in ts}; seen=set(); stack=set()
    def visit(n):
        if n in stack: raise HTTPException(422,'Dependency cycle detected')
        if n in seen:return
        stack.add(n)
        for d in g[n]:
            if d not in ids: raise HTTPException(422,f'Unknown dependency: {d}')
            visit(d)
        stack.remove(n);seen.add(n)
    for n in ids:visit(n)
def public(w): return {**w,'tasks':[ {k:v for k,v in t.items() if k!='encrypted_payload'} for t in w['tasks'].values()]}

@app.get('/health')
def health(): return {'status':'ok'}
@app.post('/auth/token')
def login(f:OAuth2PasswordRequestForm=Depends()):
    a=USERS.get(f.username)
    if not a or not pwd.verify(f.password,a[0]): raise HTTPException(401,'Incorrect username or password')
    return {'access_token':jwt.encode({'sub':f.username,'exp':datetime.now(timezone.utc)+timedelta(hours=1)},SECRET,algorithm='HS256'),'token_type':'bearer'}
@app.post('/workflows',status_code=201)
def create(body:Workflow,u=Depends(operator)):
    validate(body.tasks); i=str(uuid.uuid4())
    WF[i]={'id':i,'name':body.name,'owner':u['email'],'status':'DRAFT','tasks':{t.id:{'id':t.id,'command':t.command,'depends_on':t.depends_on,'encrypted_payload':enc(t.payload),'max_retries':t.max_retries,'attempts':0,'status':'PENDING'} for t in body.tasks}}
    audit(i,'workflow.created',actor=u['email']);return public(WF[i])
@app.get('/workflows/{i}')
def get(i,u=Depends(current)):
    if i not in WF:raise HTTPException(404,'Workflow not found')
    return public(WF[i])
@app.post('/workflows/{i}/run')
def run(i,u=Depends(operator)):
    if i not in WF:raise HTTPException(404,'Workflow not found')
    w=WF[i];w['status']='RUNNING';done=set();remaining=set(w['tasks'])
    while remaining:
        ready=[x for x in remaining if set(w['tasks'][x]['depends_on'])<=done]
        if not ready:
            w['status']='FAILED';RUNS.labels('failed').inc();return public(w)
        for x in ready:
            t=w['tasks'][x];ok=False
            for a in range(t['max_retries']+1):
                t['attempts']=a+1;start=time.perf_counter()
                if FAILURE or 'FAIL' in t['command']:TASKS.labels('failed').inc();continue
                dec(t['encrypted_payload']);LATENCY.observe(time.perf_counter()-start);TASKS.labels('succeeded').inc();ok=True;break
            if not ok:t['status']='FAILED';w['status']='FAILED';RUNS.labels('failed').inc();audit(i,'task.failed',task_id=x);return public(w)
            t['status']='SUCCEEDED';done.add(x);remaining.remove(x);audit(i,'task.succeeded',task_id=x)
    w['status']='SUCCEEDED';RUNS.labels('succeeded').inc();audit(i,'workflow.succeeded');return public(w)
@app.post('/workflows/{i}/cancel')
def cancel(i,u=Depends(operator)):
    if i not in WF:raise HTTPException(404,'Workflow not found')
    WF[i]['status']='CANCELLED';audit(i,'workflow.cancelled',actor=u['email']);return public(WF[i])
@app.get('/workflows/{i}/events')
def events(i,u=Depends(current)):
    if i not in WF:raise HTTPException(404,'Workflow not found')
    return {'workflow_id':i,'events':EVENTS.get(i,[])}
@app.post('/admin/failure-injection')
def inject(enabled:bool,u=Depends(current)):
    global FAILURE
    if u['role']!='admin':raise HTTPException(403,'Admin role required')
    FAILURE=enabled;return {'failure_injection':FAILURE}
@app.get('/metrics')
def metrics():return Response(generate_latest(),media_type=CONTENT_TYPE_LATEST)
