"""
Health Endpoint Template
Copy this code to your other Discord bots to add health checking capability

Add to your main bot file:
1. Copy the HealthCheckHandler class and helper functions
2. Call initialize_health_server() in your main() function
3. Update docker-compose.yml to expose the health port
4. Add bot to central-health-monitor.py configuration
"""

import http.server
import socketserver
import threading
import time
import logging

logger = logging.getLogger(__name__)


class HealthCheckHandler(http.server.BaseHTTPRequestHandler):
    """Simple HTTP handler for health checks"""

    def do_GET(self):
        if self.path == '/health':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()

            # Customize this response with your bot's specific health info
            response = {
                "status": "healthy",
                "timestamp": time.time(),
                "bot": "your-bot-name",
                # Add more details if needed:
                # "discord_connected": bot.is_ready(),
                # "database_connected": db_manager.is_connected(),
                # "guilds": len(bot.guilds),
            }

            import json
            self.wfile.write(json.dumps(response).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        """Disable default logging to reduce noise"""
        pass


def start_health_server(port=8090):
    """Start a health check server"""
    try:
        with socketserver.TCPServer(("0.0.0.0", port), HealthCheckHandler) as httpd:
            logger.info(f"✅ Health check server running on port {port}")
            httpd.serve_forever()
    except Exception as e:
        logger.error(f"❌ Failed to start health server: {e}")


def initialize_health_server(port=8090):
    """Initialize the health server in a background thread"""

    def delayed_start():
        time.sleep(2)  # Wait for bot to initialize
        start_health_server(port)

    health_thread = threading.Thread(target=delayed_start, daemon=True)
    health_thread.start()
    return health_thread


# ============================================
# USAGE IN YOUR BOT FILE:
# ============================================

"""
# At the top of your bot file:
from health_endpoint import initialize_health_server

# In your main() function, before bot.run():
def main():
    # ... your existing setup ...

    # Start health endpoint
    health_thread = initialize_health_server(port=8091)  # Use different port per bot

    # ... start your bot ...
    bot.run(TOKEN)
"""

# ============================================
# DOCKER-COMPOSE.YML UPDATE:
# ============================================

"""
services:
  your-bot:
    # ... existing config ...
    ports:
      - "8091:8091"  # Expose health port (use unique port per bot)
    healthcheck:
      test: ["CMD-SHELL", "curl -f http://localhost:8091/health || exit 1"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
"""

# ============================================
# DOCKERFILE UPDATE:
# ============================================

"""
# Add curl to your Dockerfile:
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*
"""
