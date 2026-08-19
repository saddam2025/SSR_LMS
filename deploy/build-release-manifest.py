#!/usr/bin/env python3
"""Build immutable release manifest + SHA-256 checksums for the current VERSION.

Never includes .env files, credentials, caches, VCS metadata, or generated evidence.
"""
from __future__ import annotations
import argparse, hashlib, json, os, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_PARTS = {".git", "__pycache__", ".pytest_cache", "node_modules", ".venv", "venv", "artifacts"}
EXCLUDED_NAMES = {".env", ".env.production", ".env.staging"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".key", ".pem", ".p12", ".pfx", ".db", ".sqlite", ".sqlite3", ".log", ".pid", ".tmp"}

def allowed(p: Path) -> bool:
    rel = p.relative_to(ROOT)
    if any(part in EXCLUDED_PARTS for part in rel.parts):
        return False
    if p.name in EXCLUDED_NAMES or p.suffix.lower() in EXCLUDED_SUFFIXES:
        return False
    if p.name.startswith(".env.") and p.name not in {".env.example", ".env.railway.example"}:
        return False
    return p.is_file()

def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", type=Path, default=ROOT/f"RELEASE-MANIFEST-{(ROOT/'VERSION').read_text().strip()}.json")
    ap.add_argument("--checksums", type=Path, default=ROOT/f"SHA256SUMS-{(ROOT/'VERSION').read_text().strip()}.txt")
    args = ap.parse_args()
    files = []
    for p in sorted(ROOT.rglob("*")):
        if allowed(p) and p.resolve() not in {args.output.resolve(), args.checksums.resolve()}:
            files.append({"path": p.relative_to(ROOT).as_posix(), "size": p.stat().st_size, "sha256": sha256(p)})
    version = (ROOT/"VERSION").read_text().strip()
    manifest = {
        "schema": 1, "release": version, "created_at_unix": int(time.time()),
        "file_count": len(files), "files": files,
        "safety": {"secrets_included": False, "dns_mutation": False, "deployment_performed": False}
    }
    args.output.write_text(json.dumps(manifest, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
    args.checksums.write_text("".join(f"{x['sha256']}  {x['path']}\n" for x in files), encoding="utf-8")
    print(f"{version} manifest: {len(files)} files")
    print(args.output)
    print(args.checksums)
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
