"""
Health Endpoint Module for ImperialReminder Bot
Provides HTTP endpoint for centralized health monitoring

Port: 50006
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
            "uptime_seconds": round(time.time() - _start_time, 2),
            "pid": os.getpid(),
            "python_version": platform.python_version(),
            "discord_py_version": discord.__version__,
            "platform": f"{platform.system()} {platform.release()}",
        }

        if bot is not None:
            try:
                response["discord_connected"] = bot.is_ready()
                response["latency_ms"] = _safe_latency_ms(bot)
                response["guilds"] = len(bot.guilds)
                response["shard_count"] = bot.shard_count or 1
                response["cogs_loaded"] = len(bot.cogs)
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

            db_manager = getattr(bot, "db_manager", None)
            if db_manager is not None:
                try:
                    response["database_connected"] = bool(db_manager.is_connected)
                except Exception as e:
                    logger.warning(f"Failed to read database status: {e}")
                    response["database_connected"] = False

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


def initialize_health_server(port=50006, bot=None):
    """
    Initialize the health server in a background thread.

    Args:
        port: Port to listen on (default: 50006)
        bot: Discord bot instance.
    """
    global _health_server

    HealthCheckHandler.bot_instance = bot

    try:
        _health_server = ReusableTCPServer(("0.0.0.0", port), HealthCheckHandler)
    except Exception as e:
        logger.error(f"Failed to start health server on port {port}: {e}")
        return None

    health_thread = threading.Thread(target=_health_server.serve_forever, daemon=True, name="HealthCheckServer")
    health_thread.start()
    logger.info(f"Health check server running on port {port}")
    return health_thread
