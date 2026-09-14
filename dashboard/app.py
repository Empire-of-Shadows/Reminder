"""FastAPI application for the ImperialReminder web dashboard."""

import asyncio
import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from dashboard import db
from dashboard._engine.activity import activity_middleware, setup_dashboard_logging
from dashboard._engine.auth.csrf import csrf_endpoint, csrf_middleware
from dashboard._engine.auth.session import (
    ensure_oauth_state_ttl_index,
    ensure_session_ttl_index,
)
from dashboard.config import CORS_ORIGINS, IS_PRODUCTION
from dashboard._engine.rate_limit import rate_limit_middleware
from dashboard._engine.auth.oauth import router as auth_router
from dashboard.routers.audit_log import router as audit_log_router
from dashboard.routers.dashboard import router as dashboard_router
from dashboard.routers.member import router as member_router
from dashboard.routers.overview import router as overview_router
from dashboard.routers.settings import router as settings_router
from dashboard.routers.user_data import router as user_data_router
from storage.log import get_logger

# Configure the sinks before anything logs. Without this the process keeps
# loguru's default DEBUG handler and prints every library's debug output; with
# it the dashboard logs at INFO (LOG_LEVEL still wins) to console + logs/.
setup_dashboard_logging("dashboard-reminder")

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


# Registered last, so it is the outermost middleware and sees the final status -
# including the rate limiter's 429s and the CSRF check's 403s.
app.middleware("http")(activity_middleware)


# CSRF token + API/auth routes (registered first so they take priority over the
# static page fallback below).
app.add_api_route("/auth/csrf", csrf_endpoint, methods=["GET"])
app.include_router(auth_router, prefix="/auth")
app.include_router(dashboard_router, prefix="/api")
app.include_router(member_router, prefix="/api")
app.include_router(overview_router, prefix="/api")
app.include_router(settings_router, prefix="/api")
app.include_router(audit_log_router, prefix="/api")
app.include_router(user_data_router, prefix="/api")


# Each database gets this long to answer. Both pings run at once, so /health stays inside
# HealthCheck's 5 second poll timeout even when both are down.
_HEALTH_PING_TIMEOUT = 2.5


async def _ping(get_client, name: str) -> bool:
    """One bounded ping. The failure is logged; none of its detail reaches the response."""
    try:
        client = get_client()
        await asyncio.wait_for(client.admin.command("ping"), _HEALTH_PING_TIMEOUT)
        return True
    except Exception:
        health_logger.warning(f"Mongo health ping failed for the {name} database", exc_info=True)
        return False


@app.get("/health")
async def health():
    """Liveness plus both databases, per the fleet health contract.

    ``database`` is the bot's own data (MONGO_URI): without it no page can read or save
    a setting, so a failure is ``unhealthy`` with HTTP 503, the rule the bot's own
    endpoint follows. ``sessions`` is the shared sign-in store: without it nobody can
    sign in but the public pages still load, so on its own it is ``degraded`` with
    HTTP 200. The body carries statuses only.
    """
    from storage.settings.collections import db_manager

    data_ok, sessions_ok = await asyncio.gather(
        _ping(db_manager.get_client, "bot"),
        _ping(db._get_client, "shared sessions"),
    )
    if not data_ok:
        status = "unhealthy"
    elif not sessions_ok:
        status = "degraded"
    else:
        status = "healthy"
    response = {
        "status": status,
        "timestamp": time.time(),
        "service": "ImperialReminder Dashboard",
        "component": "ImperialReminder Dashboard - WebUI",
        "uptime": int(time.time() - _START_TIME),
        "frontend_built": os.path.isfile(_index_html),
        "database_connected": data_ok,
        "sessions_connected": sessions_ok,
        "checks": {
            "database": {"status": "healthy" if data_ok else "unhealthy"},
            "sessions": {"status": "healthy" if sessions_ok else "unhealthy"},
        },
    }
    return JSONResponse(status_code=503 if status == "unhealthy" else 200, content=response)


# Serve bundled static assets (JS/CSS/images) from the Vite build.
if os.path.isdir(_frontend_dist):
    app.mount("/assets", StaticFiles(directory=os.path.join(_frontend_dist, "assets")), name="assets")


# SPA fallback - any unmatched GET returns index.html for client-side routing.
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
    # log_config=None leaves uvicorn's own loggers propagating into our loguru
    # sinks instead of installing a second, separately-formatted handler;
    # access_log=False because activity_middleware logs the same requests with
    # the actor and guild attached.
    uvicorn.run(
        "dashboard.app:app",
        host=HOST,
        port=PORT,
        reload=not IS_PRODUCTION,
        log_config=None,
        access_log=False,
    )
