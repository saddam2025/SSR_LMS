
import os, re, gzip
from fastapi.testclient import TestClient
from app.main import app
from app.seed import run
from app.db import SessionLocal
from app.models import User
from app.security import hash_password

run()
db=SessionLocal()
su=db.query(User).filter_by(email="superadmin@ragab-seddik.local").first()
if not su:
    su=User(name="Super Admin", email="superadmin@ragab-seddik.local", password_hash=hash_password("SuperAdmin123!"), role="super_admin", is_active=True)
    db.add(su); db.commit()
db.close()

c=TestClient(app)
r=c.get("/login")
csrf=re.search(r'name="csrf" value="([^"]+)"',r.text).group(1)
r=c.post("/login",data={"email":"superadmin@ragab-seddik.local","password":"SuperAdmin123!","csrf":csrf},follow_redirects=False)
assert r.status_code==303
assert c.get("/admin").status_code==200

r=c.get("/static/style.css",headers={"accept-encoding":"gzip"})
assert r.status_code==200
assert "public" in r.headers.get("cache-control","")
assert "max-age=3600" in r.headers.get("cache-control","")
assert "stale-while-revalidate=86400" in r.headers.get("cache-control","")

# user-specific support pages must never be cached
assert c.get("/support").headers.get("cache-control")=="no-store"
print("PERMISSIONS + CACHE REGRESSION OK")
