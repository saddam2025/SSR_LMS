#!/usr/bin/env python3
from __future__ import annotations
import subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def main():
    failures=[]
    version=(ROOT/"VERSION").read_text().strip()
    if version!="V89": failures.append(f"VERSION is {version}, expected V89")

    main_py=(ROOT/"app"/"main.py").read_text(encoding="utf-8")
    for verb in ("get","post","put","patch","delete"):
        if f"@app.{verb}(" in main_py:
            failures.append("main.py contains application routes")

    forbidden=[]
    mutable_suffixes={".db",".sqlite",".sqlite3",".log",".pid",".pem",".key",".p12",".pfx"}
    for p in ROOT.rglob("*"):
        if not p.is_file(): continue
        rel=p.relative_to(ROOT)
        if any(x in rel.parts for x in (".git","node_modules",".venv","venv","__pycache__",".pytest_cache","artifacts")):
            continue
        n=p.name.lower()
        if n in (".env",".env.production",".env.staging") or p.suffix.lower() in mutable_suffixes:
            forbidden.append(rel.as_posix())
    if forbidden:
        failures.append("mutable/secret artifacts present: "+", ".join(forbidden[:15]))

    # Production must not silently fall back to SQLite.
    db=(ROOT/"app"/"db.py").read_text(encoding="utf-8")
    if 'DATABASE_URL is required in production' not in db:
        failures.append("production DATABASE_URL fail-closed guard missing")

    manifest=ROOT/"RELEASE-MANIFEST-V89.json"
    if not manifest.exists():
        failures.append("V89 manifest missing")
    else:
        proc=subprocess.run([sys.executable,str(ROOT/"deploy"/"verify-release-manifest.py"),
            "--manifest",str(manifest)],cwd=ROOT,capture_output=True,text=True,timeout=120)
        if proc.returncode:
            failures.append("manifest verification failed")

    if failures:
        print("V89 RELEASE CANDIDATE: FAIL")
        for f in failures: print("[FAIL]",f)
        return 1
    print("V89 RELEASE CANDIDATE: PASS")
    print("Immutable production artifact contains no runtime DB/log/key files.")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
