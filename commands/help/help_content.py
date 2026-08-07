"""
Category content for the /help command.

Plain data module (no setup(), so the cog loader leaves it alone). The view
and cog live in help_commands.py.

TextDisplay formatting rules (verified against live rendering):
  - Bold (**text**) does NOT auto-newline. Append \\n explicitly after every
    bold header.
  - Use unicode bullets instead of dash list markers.
  - Keep each body well under the 4000-char TextDisplay limit.
"""

from dataclasses import dataclass
from typing import Optional

import discord

DASHBOARD_URL = "https://reminder.eosofficial.club"
PRIVACY_URL = "https://eosofficial.club/privacy"


@dataclass(frozen=True)
class HelpCategory:
    key: str
    label: str
    description: str  # select-option description, max 100 chars
    emoji: str
    accent: int
    thumbnail: Optional[str]  # asset filename; None = bot avatar
    admin_only: bool
    blurb: str  # short line beside the thumbnail
    body: str


OVERVIEW = HelpCategory(
    key="overview",
    label="Overview",
    description="What this bot does and how to use this help",
    emoji="\N{BOOKS}",
    accent=discord.Color.blue().value,
    thumbnail=None,
    admin_only=False,
    blurb="Automatic bump reminders, with nothing for you to run.",
    body=(
        "**What this bot does**\n"
        "It keeps track of when this server can be bumped again on the server-listing "
        "sites it is set up for, and pings the bump role when the wait is over.\n"
        "\n"
        "**How it works for you**\n"
        "\N{BULLET} Bump the server as normal in the server's bump channel\n"
        "\N{BULLET} The bot sees the listing bot's success message and starts a countdown\n"
        "\N{BULLET} A status message shows how long is left, or which bots are ready now\n"
        "\N{BULLET} When the cooldown ends, the bump role gets pinged in that channel\n"
        "\n"
        "There is nothing to run and nothing to sign up for. All of that happens on its "
        "own, so the only thing that keeps the server bumped is somebody bumping it.\n"
        "\n"
        "**Using this help**\n"
        "Pick a category from the dropdown below. Only you can see this message.\n"
        "\n"
        f"Server admins can configure everything at {DASHBOARD_URL} or with `/admin panel`."
    ),
)

REMINDERS = HelpCategory(
    key="reminders",
    label="Bump Reminders",
    description="How the countdown, the status message, and the ping work",
    emoji="\N{ALARM CLOCK}",
    accent=discord.Color(0x7603FF).value,  # matches the timer status embed
    thumbnail=None,
    admin_only=False,
    blurb="The part that runs without anyone asking it to.",
    body=(
        "**Listing bots it can track**\n"
        "Disboard, BumpIt, Bump4You, WeBump, OneBump, and Unfocused. Default waits are "
        "2 hours, except BumpIt at 1 hour. An admin chooses which of them this server "
        "actually uses, and can change the wait for each one.\n"
        "\n"
        "**What counts as a bump**\n"
        "Only a success message from one of those listing bots, posted in the server's "
        "bump channel. The bot checks who sent it, so typing \"bump done\" yourself does "
        "nothing, and messages in other channels are ignored.\n"
        "\n"
        "**The reminder**\n"
        "\N{BULLET} Only the bump role is ever pinged - never everyone, never you directly\n"
        "\N{BULLET} If two listing bots come due together, you get one message covering both\n"
        "\N{BULLET} On premium servers the wording can be customized by an admin\n"
        "\n"
        "**The status message**\n"
        "A few seconds after a bump, the bot posts a status message in the bump channel "
        "with a live countdown per listing bot and anything that is ready now. It replaces "
        "the previous one instead of piling up, and an admin can turn it off.\n"
        "\n"
        "**If the bot restarts**\n"
        "Countdowns are rebuilt from the last bump, so nothing is lost. A reminder that "
        "came due while the bot was offline still arrives, and only once."
    ),
)

PREMIUM = HelpCategory(
    key="premium",
    label="Premium",
    description="Check this server's premium status and what it unlocks",
    emoji="\N{GEM STONE}",
    accent=discord.Color.gold().value,
    thumbnail=None,
    admin_only=False,
    blurb="Optional extras for a server, not for individual members.",
    body=(
        "**`/premium status`**\n"
        "Shows whether this server has premium, which tier, and when it expires. The "
        "answer is only visible to you.\n"
        "\n"
        "**What premium adds**\n"
        "\N{BULLET} Custom wording on the reminder message instead of the standard one\n"
        "\N{BULLET} Reminders delivered through a server webhook\n"
        "\N{BULLET} Shorter waits on the listing bots that support them - OneBump can drop "
        "to 30 minutes and Unfocused to 90 minutes\n"
        "\n"
        "Premium applies to a whole server, so it changes nothing about your own account. "
        "It is granted by Empire of Shadows staff.\n"
        "\n"
        f"The bot's privacy policy is at {PRIVACY_URL}"
    ),
)

ADMIN = HelpCategory(
    key="admin",
    label="Admin",
    description="Setup and configuration tools",
    emoji="\N{WRENCH}",
    accent=discord.Color.red().value,
    thumbnail=None,
    admin_only=True,
    blurb="Configuration and setup. Manage Server permission required.",
    body=(
        "**`/admin panel`**\n"
        "The configuration panel for this server:\n"
        "\N{BULLET} **Core Setup** - bump channel, bump role, timers channel\n"
        "\N{BULLET} **Panel Access Roles** - which roles may open this panel and use the "
        "dashboard\n"
        "\N{BULLET} **Bump Bots** - which listing bots to watch, and the wait for each\n"
        "\N{BULLET} **Messages** - custom reminder wording (premium) and the status "
        "message on/off\n"
        "\N{BULLET} **Premium** - the server's live premium state\n"
        "\n"
        "**First-time setup**\n"
        "Set a **Bump Channel** and a **Bump Role** under Core Setup. Nothing runs until "
        "both are set, and the other sections stay locked. If somebody bumps before that "
        "is done, the bot posts a one-time notice explaining what is missing.\n"
        "\n"
        "The bot needs Send Messages and Embed Links in the bump channel.\n"
        "\n"
        "**Who can open the panel**\n"
        "Anyone with Manage Server, plus any role added under Panel Access Roles. Those "
        "roles get the same full access on the web dashboard.\n"
        "\n"
        "**Web dashboard**\n"
        f"The same settings are available in the browser at {DASHBOARD_URL} - sign in with "
        "Discord. One login covers every Empire of Shadows dashboard."
    ),
)


CATEGORIES: dict[str, HelpCategory] = {
    c.key: c for c in (OVERVIEW, REMINDERS, PREMIUM, ADMIN)
}
CATEGORY_ORDER: list[str] = list(CATEGORIES)
DEFAULT_CATEGORY = OVERVIEW.key
