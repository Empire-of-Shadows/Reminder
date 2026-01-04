"""
Imperial Reminder Web Dashboard & OAuth Server
Provides a web interface for managing bot settings and handles Discord OAuth2 callbacks
"""

import os
import asyncio
from pathlib import Path
from string import Template
from aiohttp import web, ClientSession
from utils.logger import get_logger

logger = get_logger("OAuthServer")


class OAuthServer:
    """Web dashboard and OAuth server for Imperial Reminder bot configuration"""

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

        # Template directory
        self.template_dir = Path(__file__).parent.parent / "dashboard" / "templates"

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

    def _load_template(self, template_name: str, **kwargs) -> str:
        """
        Load and render a template file

        Args:
            template_name: Name of the template file (e.g., "dashboard.html")
            **kwargs: Variables to substitute in the template (use $varname in templates)

        Returns:
            Rendered HTML string
        """
        template_path = self.template_dir / template_name
        try:
            with open(template_path, "r", encoding="utf-8") as f:
                template_content = f.read()

            # Use string.Template which uses $varname syntax (won't conflict with CSS braces)
            if kwargs:
                template = Template(template_content)
                return template.safe_substitute(**kwargs)
            else:
                return template_content

        except FileNotFoundError:
            logger.error(f"Template not found: {template_path}")
            return f"<h1>Template Error</h1><p>Template {template_name} not found.</p>"
        except Exception as e:
            logger.error(f"Error loading template {template_name}: {e}", exc_info=True)
            return f"<h1>Template Error</h1><p>Error loading template: {e}</p>"

    async def start(self):
        """Start the OAuth web server"""
        try:
            self.app = web.Application()

            # Dashboard routes
            self.app.router.add_get("/", self.handle_dashboard)
            self.app.router.add_get("/settings", self.handle_settings)

            # OAuth routes
            self.app.router.add_get("/auth/callback", self.handle_callback)

            # Utility routes
            self.app.router.add_get("/health", self.handle_health)

            self.runner = web.AppRunner(self.app)
            await self.runner.setup()

            self.site = web.TCPSite(self.runner, self.host, self.port)
            await self.site.start()

            logger.info(f"Dashboard & OAuth server started on {self.host}:{self.port}")
            logger.info(f"Dashboard URL: http://{self.host}:{self.port}")
            logger.info(f"OAuth Callback URL: {self.redirect_uri}")

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
            "redirect_uri": self.redirect_uri,
            "dashboard_enabled": True
        })

    async def handle_dashboard(self, request):
        """Main dashboard landing page"""
        return web.Response(
            text=self._load_template("dashboard.html"),
            content_type="text/html"
        )

    async def handle_settings(self, request):
        """Settings preview page"""
        return web.Response(
            text=self._load_template("settings.html"),
            content_type="text/html"
        )

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
                    text=self._load_template(
                        "error.html",
                        title="Authorization Cancelled",
                        message="You cancelled the authorization. You can close this window and try again with /alerts join."
                    ),
                    content_type="text/html"
                )

            # Get authorization code
            code = request.query.get("code")
            if not code:
                logger.error("No authorization code in callback")
                return web.Response(
                    text=self._load_template(
                        "error.html",
                        title="Invalid Callback",
                        message="No authorization code provided. Please try again."
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
                    text=self._load_template(
                        "error.html",
                        title="Authorization Failed",
                        message="Failed to verify your Discord account. Please try again."
                    ),
                    content_type="text/html"
                )

            user_id = int(user_data["id"])

            # Mark user as authorized globally
            await self.storage.create_user_authorization(user_id, guild_id or 0)

            logger.info(f"User {user_id} successfully authorized (guild: {guild_id or 'unknown'})")

            return web.Response(
                text=self._load_template("success.html", username=user_data["username"]),
                content_type="text/html"
            )

        except Exception as e:
            logger.error(f"Error handling OAuth callback: {e}", exc_info=True)
            return web.Response(
                text=self._load_template(
                    "error.html",
                    title="Server Error",
                    message="An unexpected error occurred. Please try again later."
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
