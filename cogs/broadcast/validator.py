"""
Content Validation & Anti-Spam Filter
Validates broadcast messages to prevent spam, ads, and malicious content
"""

import re
from typing import Tuple
from utils.logger import get_logger
from .config import (
    BLOCKED_KEYWORDS,
    SUSPICIOUS_PATTERNS,
    MAX_BROADCAST_MESSAGE_LENGTH,
    MAX_CAPS_RATIO
)

logger = get_logger("BroadcastValidator")


async def validate_broadcast_content(
    content: str,
    admin_id: int,
    guild_id: int,
    storage
) -> Tuple[bool, str]:
    """
    Validate broadcast content for spam/ads/malicious content

    Args:
        content: Message content to validate
        admin_id: ID of admin creating the broadcast
        guild_id: Guild ID where broadcast is being created
        storage: BroadcastStorage instance for logging

    Returns:
        Tuple of (is_valid: bool, reason_if_blocked: str)
    """

    # Check message length
    if len(content) > MAX_BROADCAST_MESSAGE_LENGTH:
        reason = f"❌ **Blocked**: Message too long (max {MAX_BROADCAST_MESSAGE_LENGTH} characters)"
        await _log_blocked(storage, admin_id, guild_id, content, "Message too long")
        return False, reason

    # Check for empty content
    if not content.strip():
        return False, "❌ **Blocked**: Message cannot be empty"

    content_lower = content.lower()

    # Check blocked keywords
    for keyword in BLOCKED_KEYWORDS:
        if keyword in content_lower:
            reason = f"❌ **Blocked**: Message contains prohibited keyword: `{keyword}`\n\n" \
                     f"**Why?** This keyword is commonly used in spam/ads. If you believe this is a mistake, " \
                     f"please rephrase your message."
            await _log_blocked(storage, admin_id, guild_id, content, f"Blocked keyword: {keyword}")
            logger.warning(f"Broadcast blocked (guild {guild_id}, admin {admin_id}): keyword '{keyword}'")
            return False, reason

    # Check suspicious patterns
    for pattern in SUSPICIOUS_PATTERNS:
        match = re.search(pattern, content, re.IGNORECASE)
        if match:
            matched_text = match.group(0) if match else pattern
            reason = f"❌ **Blocked**: Message contains suspicious pattern\n\n" \
                     f"**Detected**: `{matched_text}`\n" \
                     f"**Why?** External links, mass mentions, and suspicious formats are blocked to prevent spam."
            await _log_blocked(storage, admin_id, guild_id, content, f"Suspicious pattern: {pattern}")
            logger.warning(f"Broadcast blocked (guild {guild_id}, admin {admin_id}): pattern '{pattern}'")
            return False, reason

    # Check for excessive caps
    if len(content) > 20:  # Only check if message is long enough
        caps_count = sum(1 for c in content if c.isupper())
        caps_ratio = caps_count / len(content)

        if caps_ratio > MAX_CAPS_RATIO:
            reason = f"❌ **Blocked**: Excessive caps lock detected ({int(caps_ratio * 100)}%)\n\n" \
                     f"**Why?** Messages with >70% uppercase characters are often spam. Please use normal capitalization."
            await _log_blocked(storage, admin_id, guild_id, content, f"Excessive caps: {caps_ratio:.1%}")
            logger.warning(f"Broadcast blocked (guild {guild_id}, admin {admin_id}): {caps_ratio:.1%} caps")
            return False, reason

    # Check for repetitive characters (e.g., "HEYYYYYY")
    if _has_excessive_repetition(content):
        reason = "❌ **Blocked**: Excessive character repetition detected\n\n" \
                 "**Why?** Repeated characters like 'HEYYYYYY' or '!!!!!!!' are spam indicators. " \
                 "Please use normal text formatting."
        await _log_blocked(storage, admin_id, guild_id, content, "Excessive repetition")
        logger.warning(f"Broadcast blocked (guild {guild_id}, admin {admin_id}): excessive repetition")
        return False, reason

    # All checks passed
    logger.info(f"Broadcast content validated (guild {guild_id}, admin {admin_id})")
    return True, ""


def _has_excessive_repetition(content: str) -> bool:
    """
    Check for excessive character repetition

    Returns True if any character is repeated more than 5 times consecutively
    (e.g., "YESSSS!!!!!" or "heyyyy")
    """
    pattern = r"(.)\1{5,}"  # Same character 6+ times in a row
    return bool(re.search(pattern, content))


async def _log_blocked(
    storage,
    admin_id: int,
    guild_id: int,
    content: str,
    reason: str
):
    """Log blocked broadcast attempt to audit trail"""
    try:
        await storage.log_audit_action(
            broadcast_id="N/A",
            guild_id=guild_id,
            admin_id=admin_id,
            action="blocked",
            message_content=content[:500],  # Store first 500 chars only
            blocked_reason=reason
        )
    except Exception as e:
        logger.error(f"Failed to log blocked broadcast: {e}", exc_info=True)


def is_mention_spam(content: str) -> bool:
    """
    Check if content contains mention spam patterns

    Returns True if content contains @everyone, @here, or excessive role/user mentions
    """
    # Check for @everyone or @here
    if re.search(r"@(everyone|here)", content, re.IGNORECASE):
        return True

    # Check for excessive mentions (>5 mentions)
    mention_count = len(re.findall(r"<@[!&]?\d+>", content))
    if mention_count > 5:
        return True

    return False


def extract_urls(content: str) -> list[str]:
    """
    Extract all URLs from content

    Returns list of URLs found
    """
    url_pattern = r"https?://[^\s<>\"\{\}|\\^`\[\]]+"
    return re.findall(url_pattern, content, re.IGNORECASE)


def is_discord_url(url: str) -> bool:
    """Check if URL is a Discord domain (allowed)"""
    discord_domains = [
        "discord.com",
        "discordapp.com",
        "cdn.discordapp.com",
        "media.discordapp.net"
    ]

    url_lower = url.lower()
    return any(domain in url_lower for domain in discord_domains)


async def validate_broadcast_name(name: str) -> Tuple[bool, str]:
    """
    Validate broadcast name

    Args:
        name: Broadcast name

    Returns:
        Tuple of (is_valid: bool, error_message: str)
    """
    from .config import MAX_BROADCAST_NAME_LENGTH

    if not name or not name.strip():
        return False, "❌ Broadcast name cannot be empty"

    if len(name) > MAX_BROADCAST_NAME_LENGTH:
        return False, f"❌ Broadcast name too long (max {MAX_BROADCAST_NAME_LENGTH} characters)"

    # Check for valid characters (alphanumeric, spaces, hyphens, underscores)
    if not re.match(r"^[a-zA-Z0-9\s\-_]+$", name):
        return False, "❌ Broadcast name can only contain letters, numbers, spaces, hyphens, and underscores"

    return True, ""


async def get_validation_report(content: str) -> dict:
    """
    Get detailed validation report for debugging

    Returns dict with validation details without blocking
    """
    report = {
        "length": len(content),
        "caps_ratio": sum(1 for c in content if c.isupper()) / max(len(content), 1),
        "blocked_keywords_found": [],
        "suspicious_patterns_found": [],
        "urls_found": [],
        "mentions_count": len(re.findall(r"<@[!&]?\d+>", content)),
        "has_repetition": _has_excessive_repetition(content),
        "is_mention_spam": is_mention_spam(content)
    }

    content_lower = content.lower()

    # Find blocked keywords
    for keyword in BLOCKED_KEYWORDS:
        if keyword in content_lower:
            report["blocked_keywords_found"].append(keyword)

    # Find suspicious patterns
    for pattern in SUSPICIOUS_PATTERNS:
        if re.search(pattern, content, re.IGNORECASE):
            report["suspicious_patterns_found"].append(pattern)

    # Extract URLs
    report["urls_found"] = extract_urls(content)

    return report
