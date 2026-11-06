import argparse,time,statistics,httpx
p=argparse.ArgumentParser();p.add_argument('--base-url',default='http://localhost:8000');a=p.parse_args();c=httpx.Client(base_url=a.base_url);t=c.post('/auth/token',data={'username':'admin@example.com','password':'change-me-now'}).json()['access_token'];h={'Authorization':'Bearer '+t}
for name,n in [('low',10),('medium',50),('high',100)]:
 d=[];ok=0
 for i in range(n):
  s=time.perf_counter();r=c.post('/workflows',headers=h,json={'name':name,'tasks':[{'id':'one','command':'echo ok'}]});ok+=r.is_success and c.post('/workflows/'+r.json()['id']+'/run',headers=h).is_success;d.append(time.perf_counter()-s)
 print(name,n,ok,round(statistics.mean(d),4),round(sorted(d)[int(.95*n)-1],4))
