"""
Broadcast System Configuration
Defines limits, defaults, and anti-spam settings for the DM broadcast feature
"""

# Rate Limiting
MIN_RECURRING_INTERVAL_MINUTES = 30  # Minimum time between recurring broadcasts
DM_SEND_DELAY_SECONDS = 1.5  # Delay between individual DMs
ONE_TIME_ADMIN_COOLDOWN_MINUTES = 60  # Admin can only send one broadcast per hour

# Decay System (Prevent Long-Running Spam)
DEFAULT_DECAY_CONFIG = {
    "max_sends": 100,  # Auto-disable broadcast after this many sends
    "increase_interval_after": 50,  # Start increasing interval after this many sends
    "current_multiplier": 1.0,  # Current interval multiplier
    "multiplier_increase": 0.1,  # Increase by 10% every 10 sends
    "multiplier_every_n_sends": 10  # Apply increase every N sends
}

# DM Failure Handling
MAX_DM_FAILURES = 1  # Auto-unsubscribe after this many consecutive failures
DM_FAILURE_RESET_HOURS = 24  # Reset failure count if successful send within this time

# User Authorization
# OAuth URL with callback support - guild_id passed as state parameter for context
import os
_REDIRECT_URI = os.getenv("OAUTH_REDIRECT_URI", "http://localhost:8002/auth/callback")
USER_AUTH_URL_TEMPLATE = f"https://discord.com/oauth2/authorize?client_id={{client_id}}&scope=identify&redirect_uri={_REDIRECT_URI}&response_type=code&state={{guild_id}}"

# Anti-Spam Content Filter
BLOCKED_KEYWORDS = [
    # Advertising
    "buy now", "limited offer", "click here", "visit our website", "shop now",
    "discount code", "promo code", "affiliate", "referral link", "sponsored",
    "partnership", "brand deal", "paid promotion",

    # Crypto/NFT spam
    "crypto", "nft", "airdrop", "whitelist", "presale", "pump", "moon",
    "bitcoin", "btc", "ethereum", "eth", "token", "coin", "shitcoin",
    "investment opportunity", "passive income", "get rich",

    # External links (suspicious patterns)
    "bit.ly", "tinyurl", "t.me/", "telegram", "whatsapp",

    # Spam phrases
    "dm me for", "check dm", "check your dms", "ping everyone",
    "free nitro", "free robux", "free vbucks", "giveaway dm",
    "message me for", "add me on",

    # Generic spam
    "click link", "limited time", "act now", "special offer", "urgent",
    "congratulations you've won", "claim your prize",

    # Pyramid/MLM
    "join my team", "downline", "upline", "recruit", "business opportunity"
]

# Regex patterns for suspicious content
SUSPICIOUS_PATTERNS = [
    r"https?://(?!discord\.com|discordapp\.com|cdn\.discordapp\.com)",  # External links
    r"@everyone", r"@here",  # Mass mentions (should not be in DMs but check anyway)
    r"\b\d{4,}\s?(nitro|robux|vbucks|dollars|usd|€|£)\b",  # Scam amounts
    r"(dm|message|contact)\s+me\s+(on|at|for)",  # "DM me on telegram"
    r"\b(telegram|whatsapp|snapchat|instagram|tiktok)\s*:\s*\S+",  # External platform usernames
]

# Message Limits
MAX_BROADCAST_MESSAGE_LENGTH = 2000  # Discord's message limit
MAX_BROADCAST_NAME_LENGTH = 100
MAX_ACTIVE_BROADCASTS_PER_GUILD = 10  # Prevent abuse
MAX_CAPS_RATIO = 0.7  # Maximum percentage of uppercase characters

# Confirmation Thresholds
LARGE_BROADCAST_THRESHOLD = 50  # Require confirmation if more than this many recipients

# Audit Log Retention
AUDIT_LOG_RETENTION_DAYS = 90  # Keep audit logs for 90 days

# Default Messages
DEFAULT_OPT_IN_MESSAGE = """
✅ **Subscribed to DM alerts for {guild_name}!**

You'll receive DM notifications when admins send important broadcasts and reminders.

**What you can do:**
• Use `/alerts leave` to unsubscribe anytime
• Use `/alerts status` to check your subscription
• Click "Stop" on any DM to acknowledge and stop that specific reminder

Your privacy is important. We'll never spam you or share your information.
"""

DEFAULT_FIRST_TIME_AUTH_MESSAGE = """
**Welcome! Let's set up DM alerts.**

To receive direct messages from **{guild_name}**, you need to authorize this app once.

**Why?**
• Bypasses "Server DMs disabled" setting
• More reliable delivery
• One-time setup for all servers

**What happens next?**
1. Click "🔐 Authorize App" below
2. Accept the authorization
3. You're done! Any future servers won't require this step.

⚠️ **This is required only once.** After authorizing, joining other servers is instant.
"""

DEFAULT_ALREADY_SUBSCRIBED_MESSAGE = """
ℹ️ **You're already subscribed to DM alerts for {guild_name}!**

Use `/alerts status` to see your subscription details.
"""

DEFAULT_NOT_SUBSCRIBED_MESSAGE = """
ℹ️ **You're not subscribed to DM alerts for {guild_name}.**

Use `/alerts join` to start receiving important notifications from server admins.
"""

DEFAULT_OPT_OUT_MESSAGE = """
👋 **You've unsubscribed from DM alerts for {guild_name}.**

You won't receive any more DM notifications from this server's admins.

You can rejoin anytime with `/alerts join`.
"""

# Broadcast Control Button Labels
BUTTON_ACKNOWLEDGE = "✅ Stop This Reminder"
BUTTON_RESUME = "🔔 Resume"
BUTTON_OPT_OUT = "🚫 Unsubscribe from All"
BUTTON_REPORT_SPAM = "⚠️ Report Spam"
