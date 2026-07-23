"""Per-bot premium settings - THE seam (the only file each bot edits).

Everything premium-specific to ImperialReminder lives here: which Discord application
owns the SKUs, which SKUs map to which tier, and the operational knobs. Deployment IDs
(application, roles, channels, owners) are read from the environment so nothing secret
is committed; the SKU semantic map is code because it encodes product meaning, not a
secret.

ImperialReminder has no Discord monetization SKUs yet, so the system runs in
manual-grant-only mode (owner `/premium-admin grant`) - the same current state as
Stygian-Relay. The old staff-issued premium codes are retired; guilds that had an
active code get re-granted manually.
"""
import os


def _int_or_none(raw: str | None) -> int | None:
    raw = (raw or "").strip()
    return int(raw) if raw.isdigit() else None


def _id_list(*env_vars: str) -> list[int]:
    for var in env_vars:
        raw = os.getenv(var, "")
        ids = [int(p.strip()) for p in raw.split(",") if p.strip().isdigit()]
        if ids:
            return ids
    return []


# Discord application that owns the SKUs/entitlements (entitlements are app-scoped).
APPLICATION_ID = _int_or_none(os.getenv("PREMIUM_APPLICATION_ID") or os.getenv("APPLICATION_ID"))

# sku_id -> {name, kind, tier, consumable?}. `kind` is "subscription" or "one_time"; `tier` is
# the label the rest of the bot keys premium features off of; `consumable` (one-time only)
# marks a SKU that must be consumed after fulfilment. Empty until monetization SKUs exist.
SKUS: dict[str, dict] = {
    # "1234567890123456789": {"name": "Imperial Reminder Premium (Monthly)", "kind": "subscription", "tier": "premium"},
}

# Tier labels, best first. Orders PremiumState.tier when a scope holds several entitlements.
TIER_PRIORITY: list[str] = ["premium"]

# Optional role granted/removed in a guild when premium turns on/off, per tier.
PREMIUM_ROLE_IDS: dict[str, int] = {}

# Where premium grant/lapse/audit notices post (reminder has no per-guild log channel
# concept, so this is the only log destination; unset = no channel notices).
LOG_CHANNEL_ID = _int_or_none(os.getenv("PREMIUM_LOG_CHANNEL_ID"))

# Reconciliation loop cadence + whether to run a full pass on startup.
RECONCILE_INTERVAL_MINUTES = int(os.getenv("PREMIUM_RECONCILE_MINUTES", "60"))
RECONCILE_ON_STARTUP = os.getenv("PREMIUM_RECONCILE_ON_STARTUP", "true").strip().lower() != "false"

# Enables the `/premium test` commands and louder logging.
TEST_MODE = os.getenv("PREMIUM_TEST_MODE", "false").strip().lower() == "true"

# DM/ping configured owners on premium changes.
NOTIFY_OWNERS_ON_CHANGE = os.getenv("PREMIUM_NOTIFY_OWNERS", "false").strip().lower() == "true"

# Bot owner(s) allowed to run owner-gated premium commands (grant/revoke/test/etc). Env-first,
# falling back to the shared BOT_OWNER_ID, then the ecosystem owner.
OWNER_IDS = _id_list("PREMIUM_OWNER_IDS", "BOT_OWNER_ID", "OWNER_IDS") or [1264236749060575355]

# Guild(s) the management commands (everything except `/premium status`) register into, keeping
# them out of every other guild's command list. Empty = they register globally (runtime-gated).
ADMIN_GUILD_IDS = _id_list("PREMIUM_ADMIN_GUILD_IDS") or [1497083403453989007]
