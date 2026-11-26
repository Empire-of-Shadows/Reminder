# VENDORED from dashboard_engine/ - DO NOT EDIT HERE.
# Edit the master at EmpireSystems/dashboard_engine/ and run:
#     python EmpireSystems/tools/sync_dashboard_engine.py
# Drift is enforced by:
#     python EmpireSystems/tools/sync_dashboard_engine.py --check
"""Lightweight in-process per-IP rate limiting for public/auth endpoints.

Fixed-window counter, no external dependency. Sufficient for a single-worker
uvicorn deployment. If the dashboard is ever scaled to multiple workers or
hosts, swap the in-memory store for a shared one (Redis/Mongo).

Only a small set of unauthenticated, internet-facing routes are limited; the
authenticated API is already gated by session auth and the bot-token Discord
calls are token-bucketed elsewhere.

The route table is seam-configured: ``config.RATE_LIMITS`` is an ordered list of
``(path-prefix, bucket, max_requests, window_seconds)`` tuples (first match wins,
so more specific prefixes must come before their parents).
"""

import ipaddress
import time

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from dashboard import config as _config
from dashboard.config import RATE_LIMITS as _LIMITS

# Reverse proxies whose X-Forwarded-For header may be trusted for client-IP
# resolution. OPTIONAL seam value (``config.TRUSTED_PROXY_IPS``, an iterable of
# peer IPs) - like the admin engine's optional bindings, a config that omits it
# still loads; the limiter then keys on the socket address only.
_TRUSTED_PROXIES = frozenset(getattr(_config, "TRUSTED_PROXY_IPS", ()) or ())

# key -> (window_start_epoch, count)
_buckets: dict[str, tuple[float, int]] = {}
_last_sweep = 0.0
_SWEEP_INTERVAL = 300.0


def _is_ip(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False


def _client_ip(request: Request) -> str:
    # Forwarding headers are attacker-controlled unless the immediate peer is a
    # trusted reverse proxy; trusting them blindly hands every client a fresh
    # rate-limit bucket per request. Only honor them from TRUSTED_PROXY_IPS,
    # otherwise use the socket address.
    #
    # From a trusted proxy: Cloudflare's CF-Connecting-IP first (the fleet's
    # tunnel sets it and replaces any copy a visitor sends), then the RIGHT-most
    # X-Forwarded-For entry, the one the proxy itself appended. Entries to its
    # left are whatever the visitor sent, so the left-most (used until
    # 2026-11-23) let anyone pick their own bucket. A value that is not an IP
    # address counts the proxy. The production gateway the tunnel connects from
    # is 172.18.0.1 (vault: Production Host Map).
    peer = request.client.host if request.client else "unknown"
    if peer in _TRUSTED_PROXIES:
        cf = request.headers.get("cf-connecting-ip", "").strip()
        if _is_ip(cf):
            return cf
        xff = request.headers.get("x-forwarded-for")
        if xff:
            last = xff.split(",")[-1].strip()
            if _is_ip(last):
                return last
    return peer


def _match_limit(path: str) -> tuple[str, int, int] | None:
    for prefix, bucket, max_requests, window in _LIMITS:
        if path.startswith(prefix):
            return bucket, max_requests, window
    return None


def _sweep(now: float) -> None:
    global _last_sweep
    if now - _last_sweep < _SWEEP_INTERVAL:
        return
    _last_sweep = now
    stale = [k for k, (start, _) in _buckets.items() if now - start > 3600]
    for k in stale:
        _buckets.pop(k, None)


def _consume(request: Request, bucket: str, max_requests: int, window: int):
    """Fixed-window per-IP accounting shared by the middleware and the dependency.
    Returns a Retry-After (seconds) if the limit is exceeded, else None."""
    now = time.time()
    _sweep(now)
    key = f"{_client_ip(request)}:{bucket}"
    start, count = _buckets.get(key, (now, 0))
    if now - start >= window:
        start, count = now, 0
    count += 1
    _buckets[key] = (start, count)
    if count > max_requests:
        return max(1, int(window - (now - start)))
    return None


def rate_limit_dependency(bucket: str, max_requests: int, window: int):
    """A FastAPI dependency applying the same per-IP fixed-window limit as the
    middleware, for routes the prefix matcher can't target -- e.g. the per-guild
    stats route, whose path has a dynamic ``{guild_id}`` segment. The security
    standard calls for auth AND stats routes to be rate-limited."""
    async def _dep(request: Request):
        retry_after = _consume(request, bucket, max_requests, window)
        if retry_after is not None:
            raise HTTPException(
                status_code=429,
                detail="Too many requests. Please slow down.",
                headers={"Retry-After": str(retry_after)},
            )
    return _dep


async def rate_limit_middleware(request: Request, call_next):
    limit = _match_limit(request.url.path)
    if limit is None:
        return await call_next(request)

    bucket, max_requests, window = limit
    now = time.time()
    _sweep(now)

    key = f"{_client_ip(request)}:{bucket}"
    start, count = _buckets.get(key, (now, 0))

    if now - start >= window:
        # Window elapsed - reset.
        start, count = now, 0

    count += 1
    _buckets[key] = (start, count)

    if count > max_requests:
        retry_after = max(1, int(window - (now - start)))
        return JSONResponse(
            status_code=429,
            content={"detail": "Too many requests. Please slow down."},
            headers={"Retry-After": str(retry_after)},
        )

    return await call_next(request)
