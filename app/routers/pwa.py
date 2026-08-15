import os
from fastapi import APIRouter
from fastapi.responses import FileResponse

router = APIRouter(tags=["pwa"])
APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR = os.path.join(APP_DIR, "static")


@router.get("/app-version.json", include_in_schema=False)
def app_version_manifest():
    response = FileResponse(os.path.join(STATIC_DIR, "app-version.json"), media_type="application/json")
    response.headers["Cache-Control"] = "no-store"
    return response


@router.get("/manifest.webmanifest", include_in_schema=False)
def pwa_manifest():
    return FileResponse(os.path.join(STATIC_DIR, "manifest.webmanifest"), media_type="application/manifest+json")


@router.get("/sw.js", include_in_schema=False)
def pwa_service_worker():
    response = FileResponse(os.path.join(STATIC_DIR, "sw.js"), media_type="application/javascript")
    response.headers["Service-Worker-Allowed"] = "/"
    response.headers["Cache-Control"] = "no-cache"
    return response
