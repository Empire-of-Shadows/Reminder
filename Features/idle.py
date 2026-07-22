import discord
from discord.ext import commands, tasks
import random

from storage.logging import get_logger

logger = get_logger("Idle")

class IdleStatus(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.testing_mode = False  # Toggle to switch to testing statuses

        self.playing_statuses = [
            "hide and seek with /bump",
            "tag—you’re bumped!",
            "90% uptime simulator",
            "with the bots code"
        ]
        self.watching_statuses = [
            "for /bump commands",
            "you configure /admin panel",
            "every /bump like a hawk",
            "users ignore the timer",
            "for frequent restarts"
        ]
        self.listening_statuses = [
            "bump reminders",
            "feedback from users",
            "bump cooldown complaints",
            "bug reports and praises",
            "late night bumps",
            "your inner thoughts... maybe"
        ]

        self.testing_statuses = [
            ("playing", "in ⚠️ mode — stability not guaranteed"),
            ("listening", "💇‍♂️ bumpers panic in real-time"),
            ("playing", "🪖 patching the code like it's war"),
            ("listening", "👨‍🔧 gears grinding... slowly... painfully"),
            ("playing", "a round of ⚠️ 'What broke this time?'"),
            ("watching", "🪖 deploy logs flood in"),
            ("listening", "users scream 💇‍♂️ into the void"),
            ("playing", "hotfix roulette 👨‍🔧"),
            ("listening", "bumpers brave enough to test 🪖"),
            ("playing", "tag, you're unstable ⚠️"),
            ("listening", "thank yous buried in bug reports 💙"),
            ("playing", "👨‍🔧 engineer mode: chaotic neutral"),
            ("watching", "for life signs in the bump thread ⚠️"),
            ("playing", "💇‍♂️ debug dance of the doomed"),
            ("watching", "users cope — some even thrive 🪖"),
            ("listening", "👂 whispers of a stable release... soon"),
        ]

        self.rotate_status.start()

    def cog_unload(self):
        self.rotate_status.cancel()

    @tasks.loop(seconds=30)
    async def rotate_status(self):
        if self.testing_mode:
            # Use testing statuses
            type_str, message = random.choice(self.testing_statuses)
            activity_type = getattr(discord.ActivityType, type_str)
        else:
            # Use normal statuses
            activity_type = random.choice([
                discord.ActivityType.playing,
                discord.ActivityType.watching,
                discord.ActivityType.listening
            ])

            if activity_type == discord.ActivityType.playing:
                message = random.choice(self.playing_statuses)
            elif activity_type == discord.ActivityType.watching:
                message = random.choice(self.watching_statuses)
            else:
                message = random.choice(self.listening_statuses)

        await self.bot.change_presence(
            status=discord.Status.idle,
            activity=discord.Activity(type=activity_type, name=message)
        )

    @rotate_status.before_loop
    async def before_rotate_status(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(IdleStatus(bot))
