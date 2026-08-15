
import re
from urllib.parse import urlparse
from fastapi.testclient import TestClient
from app.main import app
from app.seed import run

run()

ACCOUNTS=[
    ("admin@ragab-seddik.local","ChangeMe123!","admin"),
    ("student@ragab-seddik.local","Student123!","student"),
    ("parent@ragab-seddik.local","Parent12345!","parent"),
]
SKIP_PREFIX=("/logout", "/static/", "/manifest", "/sw.js")
BAD={404,500,502,503}

def login(c,email,pw):
    r=c.get("/login")
    csrf=re.search(r'name="csrf" value="([^"]+)"',r.text).group(1)
    r=c.post("/login",data={"email":email,"password":pw,"csrf":csrf},follow_redirects=False)
    assert r.status_code==303

for email,pw,role in ACCOUNTS:
    c=TestClient(app)
    login(c,email,pw)
    starts={"admin":"/admin","student":"/dashboard","parent":"/parent"}[role]
    r=c.get(starts,follow_redirects=False)
    assert r.status_code in (200,303), (role,starts,r.status_code)
    if r.status_code==303:
        r=c.get(r.headers["location"],follow_redirects=False)
    html=r.text
    hrefs=set(re.findall(r'href=["\']([^"\']+)["\']',html))
    checked=0
    for href in sorted(hrefs):
        if not href.startswith("/") or href.startswith(SKIP_PREFIX) or "{" in href or "#" == href:
            continue
        path=urlparse(href).path
        rr=c.get(path,follow_redirects=False)
        assert rr.status_code not in BAD, (role,path,rr.status_code)
        checked+=1
    print(role, "menu links checked:", checked)
print("FULL MENU RENDER CHECK OK")
