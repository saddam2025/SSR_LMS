#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
def sha256(p):
    h=hashlib.sha256()
    with p.open("rb") as f:
        for c in iter(lambda:f.read(1024*1024), b""): h.update(c)
    return h.hexdigest()
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--manifest", type=Path, default=ROOT/f"RELEASE-MANIFEST-{(ROOT/'VERSION').read_text().strip()}.json")
    a=ap.parse_args()
    d=json.loads(a.manifest.read_text())
    failures=[]
    for item in d.get("files",[]):
        p=ROOT/item["path"]
        if not p.is_file(): failures.append(f"missing: {item['path']}")
        elif p.stat().st_size != item["size"]: failures.append(f"size: {item['path']}")
        elif sha256(p) != item["sha256"]: failures.append(f"sha256: {item['path']}")
    if failures:
        print(f"{(ROOT/'VERSION').read_text().strip()} RELEASE MANIFEST: FAIL")
        for x in failures[:50]: print("[FAIL]",x)
        return 1
    print(f"{(ROOT/'VERSION').read_text().strip()} RELEASE MANIFEST: PASS ({len(d.get('files',[]))} files)")
    return 0
if __name__=="__main__": raise SystemExit(main())
