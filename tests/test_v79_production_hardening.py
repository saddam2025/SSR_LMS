import os
os.environ.setdefault("ENV", "test")
os.environ.setdefault("APP_SECRET", "test-secret-change-this")

from fastapi.testclient import TestClient
from app.main import app
from app.observability import snapshot

client = TestClient(app)

r = client.get("/health", headers={"X-Request-ID": "v79-check-123"})
assert r.status_code == 200
assert r.headers.get("X-Request-ID") == "v79-check-123"
assert r.json().get("version") == "V79"

r2 = client.get("/ready")
assert r2.status_code == 200, r2.text
assert r2.json().get("database") == "ok"

rows = snapshot()
assert any("GET /health 200" == row["route"] for row in rows), rows
assert any("GET /ready 200" == row["route"] for row in rows), rows

seen = set()
for route in app.routes:
    methods = getattr(route, "methods", None)
    path = getattr(route, "path", None)
    if not methods or not path:
        continue
    for method in methods:
        if method in {"HEAD", "OPTIONS"}:
            continue
        key = (method, path)
        assert key not in seen, f"duplicate route: {key}"
        seen.add(key)

print("V79 PRODUCTION HARDENING TEST OK", {"routes": len(seen), "metrics": len(rows)})
