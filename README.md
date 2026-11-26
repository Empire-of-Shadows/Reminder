<div align="center">

# Imperial Reminder

**Pings your bump team the moment each server-listing cooldown runs out, so your server stays visible.**

[![Add to Discord](https://img.shields.io/badge/Add_to-Discord-5865F2?style=for-the-badge&logo=discord&logoColor=white)](https://discord.com/oauth2/authorize?client_id=1374835282284777513)
[![Dashboard](https://img.shields.io/badge/Dashboard-reminder.eosofficial.club-7603FF?style=for-the-badge)](https://reminder.eosofficial.club)
[![Docs](https://img.shields.io/badge/Docs-Wiki-7603FF?style=for-the-badge)](https://wiki.eosofficial.club/bots/imperialreminder)
[![Support](https://img.shields.io/badge/Support-Server-5865F2?style=for-the-badge&logo=discord&logoColor=white)](https://discord.gg/x4Y6j764Zk)

[![Python](https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white)](https://www.python.org)
[![discord.py](https://img.shields.io/badge/discord.py-2.7-5865F2?logo=discord&logoColor=white)](https://github.com/Rapptz/discord.py)
[![MongoDB](https://img.shields.io/badge/MongoDB-pymongo_async-47A248?logo=mongodb&logoColor=white)](https://www.mongodb.com)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black)](https://react.dev)
[![Price](https://img.shields.io/badge/Price-100%25_free-2EA043)](#free)

</div>

Listing sites like Disboard only keep your server near the top if someone bumps it every time the
cooldown ends. Imperial Reminder watches your bump channel, notices each successful bump, and
pings your bump role the moment that site is ready again.

## Contents

- [Supported listing sites](#supported-listing-sites)
- [How it works](#how-it-works)
- [Commands](#commands)
- [Getting started](#getting-started)
- [Dashboard](#dashboard)
- [Permissions and intents](#permissions-and-intents)
- [Development](#development)
- [Links](#links)

## Supported listing sites

| Site | Default cooldown | Shorter option |
|---|---|---|
| Disboard | 2 hours | - |
| BumpIt | 1 hour | - |
| Bump4You | 2 hours | - |
| WeBump | 2 hours | - |
| OneBump | 2 hours | 30 minutes |
| GuildFinder (formerly Unfocused) | 2 hours | 90 minutes |
| The Bannerhall (thebannerhall.com, `/bump`) | 2 hours | - |

Turn each site on or off, and pick its cooldown, per server.

## How it works

- **It checks who posted, not just what was said.** A timer starts only when the success message
  genuinely came from that listing bot. A member typing "Bump done!" cannot trigger it.
- **It catches late messages.** Some listing bots post an empty message and fill it in a moment
  later, so the bot watches edits too and re-reads a message whose content arrived late.
- **Reminders survive restarts.** Timers are rebuilt from stored times when the bot comes back,
  and anything that came due while it was down fires straight away.
- **One ping, not six.** Sites that come ready within a few seconds of each other are combined
  into a single reminder.
- **A live countdown.** An optional timer message shows every site's remaining cooldown and
  replaces itself instead of stacking up.
- **Your wording.** Write your own reminder text with `{bump_role}` and `{bots}` placeholders.
- **Pings are locked down.** The bot cannot mention anyone by default. Each reminder allows
  exactly one mention: your bump role.
- **It tells you when something is off.** A real bump in a server that has not finished setup,
  or from a site you have not switched on, gets a short notice (at most once a day) instead of
  silence. Deleted channels and roles are cleared from the settings automatically.

### Free

Every feature, custom wording and the shorter cooldowns included, is free for every server.
There is no premium tier.

## Commands

| Command | Who can use it | What it does |
|---|---|---|
| `/admin panel` | Manage Server or a panel admin role | Configure the bot for this server. |
| `/help` | Everyone | How the bot works. |

Everything else happens automatically in your bump channel.

## Getting started

1. [Add Imperial Reminder to your server](https://discord.com/oauth2/authorize?client_id=1374835282284777513).
2. Run `/admin panel` and open **Core Setup**: set the bump channel, the bump role to ping, and
   optionally a timers channel for the live countdown. The bump role must be mentionable.
3. Open **Bump Bots**: switch on the sites you use and pick their cooldowns.
4. Optionally open **Messages** to write your own reminder text or hide the countdown.
5. Bump once by hand so the bot sees a success message and starts its first timer.

## Dashboard

[reminder.eosofficial.club](https://reminder.eosofficial.club) signs you in with Discord, using the
same login as every Empire of Shadows site. Settings, the server overview and the change history are
for admins (Manage Server or a panel admin role). The Privacy page lets anyone export or erase the
record of changes they made. Imperial Reminder tracks nothing about members, so there is nothing
else to export.

## Permissions and intents

| Permission | Why |
|---|---|
| View Channel, Send Messages | See the bump channel and post reminders. |
| Embed Links | The live countdown. |
| Read Message History | Re-reading a bump message that filled in late, and replacing the old countdown instead of stacking a new one. Without it both fail silently. |

Pinging the bump role needs no extra permission, because the panel only accepts a mentionable
role. The optional "create the role for me" button needs Manage Roles, which is not in the
invite; grant it if you want to use that button.

**Intents:** Guilds, Guild Messages and Message Content. Message Content is needed to read the
listing bots' success messages; only the bump channel you choose is examined.

## Development

<details>
<summary><b>Running it locally</b></summary>

<br>

Requires Python 3.13 and MongoDB. Configuration is read from `docker/.env`, with an optional
`docker/.env.local` override (`DISCORD_TOKEN`, `MONGO_URI`, plus the shared dashboard login values).

```bash
pip install -r requirements.txt
python Reminder.py              # the bot, health endpoint on :50014
python -m dashboard.app         # the dashboard API, :54014

cd dashboard/frontend
npm install && npm run build    # the React front end
```

`docker/reminder.sh` backs up the current images, rebuilds both services, checks their health and
rolls back on failure.

</details>

<details>
<summary><b>How the code is organised</b></summary>

<br>

| Path | What it is |
|---|---|
| `Reminder.py` | Entry point: database, health endpoint, then the bot. |
| `startup/` | Bot construction and cog discovery. |
| `Features/bump/` | Detecting successful bumps, sending reminders, the countdown message. |
| `Features/time_handler.py` | The one timer scheduler: retries with backoff, safe restarts. |
| `storage/` | Database layer. Shared storage engine plus Imperial Reminder's settings and the listing-site table in `storage/sub_systems/bump_config.py`. |
| `admin/` | The `/admin panel`. Shared admin engine plus Imperial Reminder's panel tree in `admin/settings/`. |
| `dashboard/` | FastAPI backend and React front end. |

To support a new listing site, add it to `storage/sub_systems/bump_config.py`.

Files that start with a `# VENDORED ... DO NOT EDIT HERE` banner are copied in from the shared
engines in the `EmpireSystems` repository. Change them there and re-sync; never edit the copy.

Tests and migrations live outside this repository, in the ecosystem's
`TestsAndMigrations/ImperialReminder/` folder.

</details>

## Links

- [Changelog](CHANGELOG.md) - what changed, in plain language
- [Imperial Reminder on the wiki](https://wiki.eosofficial.club/bots/imperialreminder)
- [All six bots](https://wiki.eosofficial.club/bots) and [the main site](https://eosofficial.club)
- [Support server](https://discord.gg/x4Y6j764Zk) for help and bug reports
- [Community server](https://discord.gg/xx86YEhaYF), where the bots were built and are played

## Contributing, security and license

Contributions are welcome under the terms in [CONTRIBUTING.md](CONTRIBUTING.md). Please report
security problems privately as described in [SECURITY.md](SECURITY.md), not in a public issue.

Copyright (c) 2025-2026 Empire of Shadows. All rights reserved; see [LICENSE](LICENSE).

<div align="center">
<sub>Part of the <a href="https://eosofficial.club">Empire of Shadows</a> ecosystem</sub>
</div>
