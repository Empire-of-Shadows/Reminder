"""
OAuth Callback Server for User Authorization
Handles Discord OAuth2 callback to verify users can receive DMs
"""

import os
import asyncio
from aiohttp import web, ClientSession
from utils.logger import get_logger

logger = get_logger("OAuthServer")


class OAuthServer:
    """Web server to handle Discord OAuth callbacks for user authorization"""

    def __init__(self, bot, storage):
        """
        Initialize OAuth server

        Args:
            bot: Discord bot instance
            storage: BroadcastStorage instance
        """
        self.bot = bot
        self.storage = storage
        self.app = None
        self.runner = None
        self.site = None

        # Get OAuth credentials from environment
        self.client_id = str(bot.application_id)
        self.client_secret = os.getenv("DISCORD_CLIENT_SECRET")
        self.redirect_uri = os.getenv("OAUTH_REDIRECT_URI", "http://localhost:8002/auth/callback")
        self.host = os.getenv("OAUTH_HOST", "0.0.0.0")
        self.port = int(os.getenv("OAUTH_PORT", "8002"))

        if not self.client_secret:
            logger.warning(
                "DISCORD_CLIENT_SECRET not set! OAuth callbacks will fail. "
                "Set this in .env for the authorization flow to work."
            )

    async def start(self):
        """Start the OAuth web server"""
        try:
            self.app = web.Application()
            self.app.router.add_get("/auth/callback", self.handle_callback)
            self.app.router.add_get("/health", self.handle_health)

            self.runner = web.AppRunner(self.app)
            await self.runner.setup()

            self.site = web.TCPSite(self.runner, self.host, self.port)
            await self.site.start()

            logger.info(f"OAuth server started on {self.host}:{self.port}")
            logger.info(f"Callback URL: {self.redirect_uri}")

        except Exception as e:
            logger.error(f"Failed to start OAuth server: {e}", exc_info=True)
            raise

    async def stop(self):
        """Stop the OAuth web server"""
        try:
            if self.site:
                await self.site.stop()
            if self.runner:
                await self.runner.cleanup()
            logger.info("OAuth server stopped")
        except Exception as e:
            logger.error(f"Error stopping OAuth server: {e}", exc_info=True)

    async def handle_health(self, request):
        """Health check endpoint"""
        return web.json_response({
            "status": "ok",
            "bot_ready": self.bot.is_ready(),
            "redirect_uri": self.redirect_uri
        })

    async def handle_callback(self, request):
        """
        Handle OAuth callback from Discord

        Expected query params:
        - code: Authorization code from Discord
        - state: Optional state parameter (can contain guild_id)
        - error: Error if user denied authorization
        """
        try:
            # Check for errors
            if "error" in request.query:
                error = request.query["error"]
                logger.warning(f"OAuth authorization denied: {error}")
                return web.Response(
                    text=self._render_error_page(
                        "Authorization Cancelled",
                        "You cancelled the authorization. You can close this window and try again with /alerts join."
                    ),
                    content_type="text/html"
                )

            # Get authorization code
            code = request.query.get("code")
            if not code:
                logger.error("No authorization code in callback")
                return web.Response(
                    text=self._render_error_page(
                        "Invalid Callback",
                        "No authorization code provided. Please try again."
                    ),
                    content_type="text/html"
                )

            # Extract guild_id from state if present
            state = request.query.get("state", "")
            guild_id = None
            if state.isdigit():
                guild_id = int(state)

            # Exchange code for access token
            user_data = await self._exchange_code(code)
            if not user_data:
                return web.Response(
                    text=self._render_error_page(
                        "Authorization Failed",
                        "Failed to verify your Discord account. Please try again."
                    ),
                    content_type="text/html"
                )

            user_id = int(user_data["id"])

            # Mark user as authorized globally
            await self.storage.create_user_authorization(user_id, guild_id or 0)

            logger.info(f"User {user_id} successfully authorized (guild: {guild_id or 'unknown'})")

            return web.Response(
                text=self._render_success_page(user_data["username"]),
                content_type="text/html"
            )

        except Exception as e:
            logger.error(f"Error handling OAuth callback: {e}", exc_info=True)
            return web.Response(
                text=self._render_error_page(
                    "Server Error",
                    "An unexpected error occurred. Please try again later."
                ),
                content_type="text/html"
            )

    async def _exchange_code(self, code: str) -> dict | None:
        """
        Exchange authorization code for user info

        Args:
            code: Authorization code from Discord

        Returns:
            User data dict or None if failed
        """
        if not self.client_secret:
            logger.error("Cannot exchange code: DISCORD_CLIENT_SECRET not set")
            return None

        try:
            data = {
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self.redirect_uri
            }

            headers = {"Content-Type": "application/x-www-form-urlencoded"}

            async with ClientSession() as session:
                # Exchange code for access token
                async with session.post(
                    "https://discord.com/api/v10/oauth2/token",
                    data=data,
                    headers=headers
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"Token exchange failed: {response.status} - {error_text}")
                        return None

                    token_data = await response.json()
                    access_token = token_data.get("access_token")

                    if not access_token:
                        logger.error("No access token in response")
                        return None

                # Fetch user info with access token
                async with session.get(
                    "https://discord.com/api/v10/users/@me",
                    headers={"Authorization": f"Bearer {access_token}"}
                ) as user_response:
                    if user_response.status != 200:
                        error_text = await user_response.text()
                        logger.error(f"User fetch failed: {user_response.status} - {error_text}")
                        return None

                    user_data = await user_response.json()
                    return user_data

        except Exception as e:
            logger.error(f"Error exchanging OAuth code: {e}", exc_info=True)
            return None

    def _render_success_page(self, username: str) -> str:
        """Render success HTML page"""
        return f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Authorization Successful</title>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
            margin: 0;
        }}
        .container {{
            background: white;
            padding: 40px;
            border-radius: 12px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
            text-align: center;
            max-width: 500px;
        }}
        .success-icon {{
            font-size: 64px;
            color: #10b981;
            margin-bottom: 20px;
        }}
        h1 {{
            color: #1f2937;
            margin-bottom: 10px;
        }}
        p {{
            color: #6b7280;
            line-height: 1.6;
            margin: 10px 0;
        }}
        .username {{
            color: #667eea;
            font-weight: bold;
        }}
        .close-btn {{
            margin-top: 30px;
            padding: 12px 30px;
            background: #667eea;
            color: white;
            border: none;
            border-radius: 6px;
            font-size: 16px;
            cursor: pointer;
            transition: background 0.3s;
        }}
        .close-btn:hover {{
            background: #5568d3;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="success-icon">✅</div>
        <h1>Authorization Successful!</h1>
        <p>Welcome, <span class="username">{username}</span>!</p>
        <p>You're now authorized to receive DM alerts from Imperial Reminder.</p>
        <p>You can now return to Discord and use <strong>/alerts join</strong> in any server.</p>
        <button class="close-btn" onclick="window.close()">Close This Window</button>
    </div>
</body>
</html>
"""

    def _render_error_page(self, title: str, message: str) -> str:
        """Render error HTML page"""
        return f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
            margin: 0;
        }}
        .container {{
            background: white;
            padding: 40px;
            border-radius: 12px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
            text-align: center;
            max-width: 500px;
        }}
        .error-icon {{
            font-size: 64px;
            color: #ef4444;
            margin-bottom: 20px;
        }}
        h1 {{
            color: #1f2937;
            margin-bottom: 10px;
        }}
        p {{
            color: #6b7280;
            line-height: 1.6;
            margin: 10px 0;
        }}
        .close-btn {{
            margin-top: 30px;
            padding: 12px 30px;
            background: #6b7280;
            color: white;
            border: none;
            border-radius: 6px;
            font-size: 16px;
            cursor: pointer;
            transition: background 0.3s;
        }}
        .close-btn:hover {{
            background: #4b5563;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="error-icon">❌</div>
        <h1>{title}</h1>
        <p>{message}</p>
        <button class="close-btn" onclick="window.close()">Close This Window</button>
    </div>
</body>
</html>
"""
