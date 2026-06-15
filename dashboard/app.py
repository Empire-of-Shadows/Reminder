"""FastAPI application for the ImperialReminder web dashboard."""

import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from dashboard import db
from dashboard.auth.csrf import csrf_endpoint, csrf_middleware
from dashboard.auth.session import (
    ensure_oauth_state_ttl_index,
    ensure_session_ttl_index,
)
from dashboard.config import CORS_ORIGINS, IS_PRODUCTION
from dashboard.rate_limit import rate_limit_middleware
from dashboard.auth.oauth import router as auth_router
from dashboard.routers.dashboard import router as dashboard_router
from dashboard.routers.settings import router as settings_router
from utils.logger import get_logger

startup_logger = get_logger("dashboard.startup")
health_logger = get_logger("dashboard.health")

_frontend_dist = os.path.abspath(os.path.join(os.path.dirname(__file__), "frontend", "dist"))
_frontend_public = os.path.abspath(os.path.join(os.path.dirname(__file__), "frontend", "public"))
_index_html = os.path.join(_frontend_dist, "index.html")
_START_TIME = time.time()

# CSP matched to the Vite SPA: bundled JS/CSS from self, Google Fonts, and images
# from any https origin. No inline scripts are emitted by the build, so script-src
# is 'self' with no 'unsafe-inline'.
_CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com data:; "
    "img-src 'self' data: https:; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "object-src 'none'"
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    startup_logger.info("Dashboard starting up")
    await db.connect()
    await ensure_oauth_state_ttl_index()
    await ensure_session_ttl_index()
    startup_logger.info("Dashboard ready (frontend_built=%s)", os.path.isfile(_index_html))
    yield
    startup_logger.info("Dashboard shutting down")
    await db.close()


app = FastAPI(title="ImperialReminder Dashboard", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.middleware("http")(csrf_middleware)
app.middleware("http")(rate_limit_middleware)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = _CSP
    if IS_PRODUCTION:
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )
    return response


# CSRF token + API/auth routes (registered first so they take priority over the
# static page fallback below).
app.add_api_route("/auth/csrf", csrf_endpoint, methods=["GET"])
app.include_router(auth_router, prefix="/auth")
app.include_router(dashboard_router, prefix="/api")
app.include_router(settings_router, prefix="/api")


@app.get("/health")
async def health():
    response = {
        "status": "healthy",
        "timestamp": time.time(),
        "service": "ImperialReminder Dashboard",
        "component": "ImperialReminder Dashboard - WebUI",
        "uptime": int(time.time() - _START_TIME),
        "frontend_built": os.path.isfile(_index_html),
    }
    try:
        client = db._get_client()
        await client.admin.command("ping")
        response["database_connected"] = True
        response["checks"] = {"database": {"status": "healthy"}}
    except Exception:
        health_logger.warning("Mongo health ping failed", exc_info=True)
        response["database_connected"] = False
        response["checks"] = {"database": {"status": "unhealthy"}}
        response["status"] = "degraded"
    return response


# Serve bundled static assets (JS/CSS/images) from the Vite build.
if os.path.isdir(_frontend_dist):
    app.mount("/assets", StaticFiles(directory=os.path.join(_frontend_dist, "assets")), name="assets")


# SPA fallback — any unmatched GET returns index.html for client-side routing.
# Real files shipped in dist/ or public/ (favicons, brand images, robots.txt)
# are served directly first so the fallback doesn't swallow them.
@app.get("/{path:path}")
async def spa_fallback(request: Request, path: str):
    if path and ".." not in path:
        for root in (_frontend_dist, _frontend_public):
            candidate = os.path.normpath(os.path.join(root, path))
            if candidate.startswith(root) and os.path.isfile(candidate):
                return FileResponse(candidate)
    if os.path.isfile(_index_html):
        return FileResponse(_index_html)
    return {"error": "Frontend not built. Run: cd dashboard/frontend && npm run build"}


if __name__ == "__main__":
    import uvicorn
    from dashboard.config import HOST, PORT

    # Reload (file-watching, extra process) only in development. The container
    # entrypoint is `python -m dashboard.app`, so this path runs in production.
    uvicorn.run("dashboard.app:app", host=HOST, port=PORT, reload=not IS_PRODUCTION)
