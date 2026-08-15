import json, os, time
from datetime import datetime
try:
    import redis
except Exception:
    redis=None

QUEUE_KEY='lms:tasks'

def enqueue(name: str, payload: dict):
    url=os.getenv('REDIS_URL','').strip()
    job={'name':name,'payload':payload,'queued_at':datetime.utcnow().isoformat()+'Z'}
    if redis and url:
        c=redis.Redis.from_url(url,decode_responses=True)
        c.rpush(QUEUE_KEY,json.dumps(job,ensure_ascii=False))
        return True
    return False

def run_worker(handlers: dict):
    url=os.getenv('REDIS_URL','').strip()
    if not (redis and url):
        raise RuntimeError('REDIS_URL required for worker')
    c=redis.Redis.from_url(url,decode_responses=True)
    while True:
        item=c.blpop(QUEUE_KEY,timeout=5)
        if not item: continue
        _,raw=item
        try:
            job=json.loads(raw)
            fn=handlers.get(job.get('name'))
            if fn: fn(job.get('payload') or {})
        except Exception as e:
            c.rpush('lms:tasks:dead',json.dumps({'raw':raw,'error':str(e)},ensure_ascii=False))
            time.sleep(.2)
