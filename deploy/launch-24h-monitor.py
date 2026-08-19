#!/usr/bin/env python3
"""V87 first-24-hours launch monitor. Read-only HTTP checks; no remediation."""
from __future__ import annotations
import argparse, json, time, urllib.request, urllib.error
from pathlib import Path

def probe(url: str, timeout: int=15) -> dict:
    started=time.time()
    try:
        req=urllib.request.Request(url, headers={"User-Agent":"Mostashar-V87-LaunchMonitor/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            code=r.status
        return {"url":url,"ok":200 <= code < 400,"status":code,"latency_ms":round((time.time()-started)*1000,2)}
    except Exception as e:
        return {"url":url,"ok":False,"status":None,"latency_ms":round((time.time()-started)*1000,2),"error":type(e).__name__}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--api", default="https://ragab-seddik.com")
    ap.add_argument("--frontend", default="https://ragab-seddik.com")
    ap.add_argument("--iterations", type=int, default=1)
    ap.add_argument("--interval-seconds", type=int, default=300)
    ap.add_argument("--output", type=Path, default=Path("artifacts/v87-launch-monitor.json"))
    a=ap.parse_args()
    samples=[]
    for i in range(max(1,a.iterations)):
        sample={"timestamp":int(time.time()),"health":probe(a.api.rstrip("/")+"/health"),
                "ready":probe(a.api.rstrip("/")+"/ready"),
                "frontend":probe(a.frontend.rstrip("/")+"/")}
        samples.append(sample)
        print(f"sample={i+1} health={sample['health'].get('status')} ready={sample['ready'].get('status')} frontend={sample['frontend'].get('status')}")
        if i+1<a.iterations: time.sleep(max(1,a.interval_seconds))
    failed=sum(1 for s in samples for k in ("health","ready","frontend") if not s[k]["ok"])
    report={"version":"V87","samples":samples,"failed_probes":failed,"go":failed==0,
            "safety":{"read_only":True,"dns_changed":False,"deployment_performed":False}}
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n")
    return 0 if failed==0 else 1
if __name__=="__main__": raise SystemExit(main())
