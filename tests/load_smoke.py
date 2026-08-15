"""Lightweight local concurrency smoke test. Start the app, then: python tests/load_smoke.py"""
import concurrent.futures, os, time, urllib.request
BASE=os.getenv('LOAD_BASE_URL','http://127.0.0.1:8000')
N=int(os.getenv('LOAD_REQUESTS','100'))
C=int(os.getenv('LOAD_CONCURRENCY','20'))

def hit(i):
    t=time.perf_counter()
    try:
        with urllib.request.urlopen(BASE+'/health',timeout=5) as r:
            ok=r.status==200
    except Exception:
        ok=False
    return ok,(time.perf_counter()-t)*1000

start=time.perf_counter()
with concurrent.futures.ThreadPoolExecutor(max_workers=C) as ex:
    rows=list(ex.map(hit,range(N)))
elapsed=time.perf_counter()-start
ok=sum(1 for x,_ in rows if x)
lat=sorted(ms for _,ms in rows)
p95=lat[min(len(lat)-1,int(len(lat)*.95))] if lat else 0
print({'ok':ok,'total':N,'seconds':round(elapsed,2),'rps':round(N/max(elapsed,.001),1),'p95_ms':round(p95,1)})
if ok != N: raise SystemExit(1)
