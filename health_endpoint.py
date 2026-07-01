"""
Health Endpoint Module for ImperialReminder Bot
Provides HTTP endpoint for centralized health monitoring

Port: 50014
"""

import http.server
import socketserver
import threading
import time
import logging
import json
import math
import os
import platform

import discord

logger = logging.getLogger(__name__)

_health_server = None
_start_time = time.time()


class ReusableTCPServer(socketserver.TCPServer):
    allow_reuse_address = True


def _safe_latency_ms(bot) -> float | None:
    try:
        latency = bot.latency
    except Exception:
        return None
    if latency is None or math.isnan(latency) or math.isinf(latency):
        return None
    return round(latency * 1000, 2)


class HealthCheckHandler(http.server.BaseHTTPRequestHandler):
    """HTTP handler for health check requests"""

    bot_instance = None
    db_manager = None

    def do_GET(self):
        if self.path != '/health':
            self.send_response(404)
            self.end_headers()
            return

        bot = self.bot_instance
        response = {
            "status": "healthy",
            "bot": "reminder",
            "service": "Discord Bump Reminder Bot",
            "timestamp": time.time(),
            "uptime": int(time.time() - _start_time),
            "pid": os.getpid(),
            "python_version": platform.python_version(),
            "discord_py_version": discord.__version__,
            "platform": f"{platform.system()} {platform.release()}",
        }

        if bot is not None:
            try:
                connected = bot.is_ready()
                latency_ms = _safe_latency_ms(bot)
                response["discord_connected"] = connected
                response["latency_ms"] = latency_ms
                if latency_ms is not None:
                    response["gateway_latency_ms"] = latency_ms
                response["guilds"] = len(bot.guilds)
                response["shard_count"] = bot.shard_count or 1
                response["cogs_loaded"] = len(bot.cogs)
                response.setdefault("checks", {})["discord"] = {
                    "status": "healthy" if connected else "unhealthy",
                    "latency_ms": latency_ms,
                }
                if not connected:
                    response["status"] = "degraded"
                try:
                    response["commands_registered"] = len(bot.tree.get_commands())
                except Exception:
                    pass
                if bot.user is not None:
                    response["bot_user"] = str(bot.user)
                    response["bot_id"] = bot.user.id
            except Exception as e:
                logger.warning(f"Failed to collect bot status: {e}")
                response["discord_connected"] = False
                response["status"] = "degraded"
                response.setdefault("checks", {})["discord"] = {"status": "unhealthy"}

            db_manager = self.db_manager or getattr(bot, "db_manager", None)
            if db_manager is not None:
                try:
                    db_ok = bool(db_manager.is_connected)
                    response["database_connected"] = db_ok
                    response.setdefault("checks", {})["database"] = {
                        "status": "healthy" if db_ok else "unhealthy"
                    }
                    if not db_ok:
                        response["status"] = "degraded"
                except Exception as e:
                    logger.warning(f"Failed to read database status: {e}")
                    response["database_connected"] = False
                    response.setdefault("checks", {})["database"] = {"status": "unhealthy"}
                    response["status"] = "degraded"

        try:
            payload = json.dumps(response).encode()
        except Exception as e:
            logger.error(f"Failed to serialize health payload: {e}")
            self.send_response(500)
            self.end_headers()
            return

        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format, *args):
        """Disable default logging to reduce noise"""
        pass


def stop_health_server():
    """Shut down the health check server if running."""
    global _health_server
    if _health_server:
        _health_server.shutdown()
        _health_server.server_close()
        _health_server = None
        logger.info("Health check server stopped")


def initialize_health_server(port=50014, bot=None, db_manager=None):
    """
    Initialize the health server in a background thread.

    Args:
        port: Port to listen on (default: 50014)
        bot: Discord bot instance.
        db_manager: Database manager (optional). Read lazily; falls back to
            ``bot.db_manager`` when not passed.
    """
    global _health_server

    HealthCheckHandler.bot_instance = bot
    HealthCheckHandler.db_manager = db_manager

    try:
        _health_server = ReusableTCPServer(("0.0.0.0", port), HealthCheckHandler)
    except Exception as e:
        logger.error(f"Failed to start health server on port {port}: {e}")
        return None

    health_thread = threading.Thread(target=_health_server.serve_forever, daemon=True, name="HealthCheckServer")
    health_thread.start()
    logger.info(f"Health check server running on port {port}")
    return health_thread
