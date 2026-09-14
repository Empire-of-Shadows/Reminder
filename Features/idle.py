"""Idle presence seam for ImperialReminder (bot-owned, NOT vendored).

The rotation machinery (loop, jitter, no-repeat queues, lifecycle) lives in the
vendored runtime engine at ``startup/presence.py``; this file supplies only
reminder's DATA: the bump-flavored phrase pools and its presence defaults.
Attached as ``bot.idle_manager`` in ``attach_databases`` and started from
``on_ready``; the old joke "testing" pool and the hardcoded testing_mode flag
are gone.

No ``setup()`` here on purpose - this is a manager, not a cog (the auto-loader
skips files without ``setup``).
"""

import discord

from startup.presence import PresenceRotator

# Activity pools by ActivityType name: playing, watching, listening.
POOLS = {
    "playing": [
        "hide and seek with the bump timer",
        "tag - you're bumped!",
        "90% uptime simulator",
        "with the bots code",
    ],
    "watching": [
        "for bump messages",
        "you configure /admin panel",
        "every bump like a hawk",
        "users ignore the timer",
        "for frequent restarts",
    ],
    "listening": [
        "bump reminders",
        "feedback from users",
        "bump cooldown complaints",
        "bug reports and praises",
        "late night bumps",
        "your inner thoughts... maybe",
    ],
}


class IdleManager(PresenceRotator):
    """Reminder's presence rotator: the engine mechanics over reminder's pools.

    Status is deliberately ``idle`` (the bot mostly waits on cooldowns); the
    Status Setup phase's ``online`` only covers the window before rotation starts.
    """

    def __init__(self, bot: discord.Client):
        super().__init__(
            bot,
            POOLS,
            rotation_interval=30.0,
            interval_jitter=3.0,
            status=discord.Status.idle,
        )
        # The activity the rotation last chose. Discord forgets presence when the
        # gateway reconnects, and discord.py does not re-send it, so the reconnect
        # path restores this instead of leaving the bot Online with no activity.
        self.last_activity = None

    async def _compute_next_activity(self):
        activity, status = await super()._compute_next_activity()
        if activity is not None:
            self.last_activity = activity
        return activity, status

    async def restore_presence(self) -> None:
        """Re-send the rotation's status and last activity (used after a reconnect)."""
        await self.bot.change_presence(status=self.default_status, activity=self.last_activity)
