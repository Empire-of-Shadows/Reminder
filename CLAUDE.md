# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Imperial Reminder** is a Discord bot that tracks and reminds users when it's time to bump their server on Discord server-listing services (Disboard, BumpIt, Bump4You, WeBump, OneBump). It monitors bump success messages, schedules reminders based on cooldown periods, and manages guild-specific configuration in MongoDB. A FastAPI web dashboard lets server admins configure the bot via Discord OAuth.

ImperialReminder follows the **shared Empire of Shadows ecosystem architecture** used by its sibling bots **TheCodex** (`Informatinal/TheCodex`) and **TheHost** (`FunEngagement/TheHost`): a thin entry point, a `utils/bot.py` bot instance, auto-discovery cog loading via `utils/sync.py`, a `storage/` manager layer attached to the bot, a standalone HTTP health endpoint, and a two-service Docker deployment (bot + dashboard) on the external `obsidian_grid` network.

## Running the Bot

### Local Development

```bash
pip install -r requirements.txt

# Provide environment variables via docker/.env (preferred) or a local .env.
# Required: DISCORD_TOKEN (or TOKEN), MONGO_URI
# Dashboard also uses: GATEKEEPER_CLIENT_ID/SECRET, DASHBOARD_SECRET_KEY, DASHBOARD_PORT

# Run the bot
python Reminder.py

# Run the dashboard (separate process)
python -m dashboard.app
```

`Reminder.py` and `dashboard/config.py` both load `docker/.env` if present, otherwise fall back to a standard `.env`.

### Docker Deployment

Docker assets live in `docker/` (mirroring TheCodex/TheHost). Deploy with the helper script:

```bash
cd docker
./reminder.sh                 # cached build of both services
./reminder.sh -n              # no-cache build
./reminder.sh -b Dev          # build a specific branch (default: Dev)
```

`reminder.sh` backs up current images, rebuilds, polls both containers' health checks, and rolls back automatically on failure. The bot exposes health on **50006**, the dashboard on **54006**.

## Architecture

### Entry Point and Lifecycle (`Reminder.py`)

`Reminder.py` mirrors TheCodex's `codex.py`:

1. Load `docker/.env` (or `.env`), then set up application-wide logging via `setup_application_logging`.
2. `start_services()`: initialize `db_manager`, start the health server on port 50006, then `bot.start(TOKEN)`.
3. `on_ready()` (registered via `bot.event`) performs **one-time init** guarded by `bot._init_done`:
   - `attach_databases()` — initialize and attach all storage managers to `bot`.
   - `load_cogs()` — auto-discover and load every cog.
   - `bot.tree.sync()` — sync global slash commands.
   - On reconnect it only refreshes presence.
4. SIGINT/SIGTERM handlers trigger `shutdown_handler()`: stop the health server, close the bot.

### Bot Instance (`utils/bot.py`)

Defines the shared `bot = commands.Bot(...)` instance and `TOKEN`. Intents: message_content, guilds, messages, members, presences, reactions, emojis. There is **no custom bot subclass** — managers are attached as attributes at runtime by `utils/sync.py` (see below). This replaces the old `shared_bot.py` / `CustomBot` design.

### Cog Loading & Manager Attachment (`utils/sync.py`)

**Auto-discovery** (no manual cog list). `load_cogs()` walks `COG_DIRECTORIES = ["./commands", "./Features"]`, importing every `.py` file that defines `setup()` (skipping `__init__.py` and already-loaded modules). To add a cog, just drop a file with `async def setup(bot)` into `commands/` or `Features/`.

`attach_databases()` initializes and attaches managers to `bot`, in order:

| Attribute | Source | Purpose |
|-----------|--------|---------|
| `bot.db_manager` | `storage.database_manager.db_manager` | MongoDB manager (must init first) |
| `bot.cache_manager` | `storage.cache` | TTL cache |
| `bot.audit_log` | `storage.audit_log` | change auditing |
| `bot.guild_config_manager` | `storage.config_manager` | per-guild config |
| `bot.setup_gatekeeper` | `storage.setup_gatekeeper` | feature gating |
| `bot.premium_manager` | `storage.premium_manager` | premium features |
| `bot.timer_handler` | `Features.time_handler.TimerHandler` | reminder scheduling |

### Directory Layout

```
Reminder.py            # entry point
health_endpoint.py     # standalone HTTP health server (port 50006)
utils/                 # bot.py, sync.py, logger.py, health_endpoint_template.py
storage/               # data layer (see below)
Features/              # event-driven cogs (auto-loaded)
  start_up.py          # schedules timers for all guilds on ready
  time_handler.py      # TimerHandler
  idle.py              # status rotation cog
  bump/detection/handler.py     # BumpHandler (message detection + scheduling)
  bump/display/embed_manager.py # timer display embeds
  core/guild_lifecycle.py       # on_guild_join / on_guild_remove
  premium/
commands/              # slash-command cogs (auto-loaded)
  admin/               # /admin panel — unified config panel (ported from TheHost/TheCodex)
    admin_cog.py       # AdminCog + /admin panel command; PanelNode navigation engine
    panel_configs.py   # MAIN_PANEL tree (Core Setup, Bump Bots, Messages, Premium)
    panel_branding.py  # panel title/description/setup-guide text
    role_auth.py       # access tier: MANAGE_GUILD -> "admin", else "none"
    permission_checks.py
    views/             # base.py (containers/cid), panel_engine.py (PanelNode + builders), panel_views.py (PanelSession)
dashboard/             # FastAPI web dashboard (separate service)
docker/                # Dockerfile, Dockerfile.dashboard, docker-compose.yml, reminder.sh, .env
```

### Storage Layer (`storage/`)

- **`database_manager.py`** — `DatabaseManager` (with `core/connection_pool.py`, `core/collection_manager.py`, `core/collection_config.py`). Module-level singleton `db_manager`. `storage/__init__.py` re-exports the key symbols.
- **`config_manager.py`** — `GuildConfig` **dataclass** + `GuildConfigManager`. Access config via attributes, not dict keys:
  ```python
  config = await bot.guild_config_manager.get_config(guild_id)
  if not config.bump_channel or not config.bump_role:
      return
  delay = config.bot_delay.get(bot_name, DEFAULT_DELAY)
  ts = config.timestamps.get(f"{bot_name}_timestamp")
  ```
  `GuildConfig` fields: `enabled_bots`, `bump_channel`, `bump_role`, `timers_channel`, `timers_message`, `custom_message`, `premium`, `bot_delay`, `timestamps`, plus `extra_data` for dynamic keys like `timer_message_{channel_id}`. `to_dict()`/`from_dict()` handle (de)serialization.
- **`sub_systems/bump_config.py`** — bump-bot constants: `DEFAULT_GUILD_CONFIG`, `BUMP_BOTS_INFO`, `BUMP_BOTS`, `BUMP_BOTS_PREMIUM`, `BUMP_BOTS_CHOICES`, `SUCCESS_KEYWORDS`, and per-bot IDs/keywords.
- **`cache.py`, `audit_log.py`, `premium_manager.py`, `setup_gatekeeper.py`** — feature managers.

### TimerHandler (`Features/time_handler.py`)

Production-grade scheduler for all reminders. **One instance** is created in `attach_databases()` and stored at `bot.timer_handler` — never create another (duplication breaks cancellation and remaining-time math).

- Monotonic time tracking; jitter to avoid thundering herd; exponential-backoff retries; callback timeouts.
- Timer dedup via `replace_if_sooner_than`; scope-based cancellation by guild/channel/type; pause/resume.
- Timer ID format: `{guild_id}:{channel_id}:{timer_type}:{name}`.

```python
await bot.timer_handler.run_timer(
    channel_id=channel.id, guild_id=guild.id, name="disboard",
    delay=7200.0, callback=self._send_bump_reminder, timer_type="bump",
    args=(channel.id, guild.id, role_id, "disboard"),
    jitter=3.0, max_retries=2, backoff=5.0, callback_timeout=10.0,
    replace_if_sooner_than=2.0,
)
```

### BumpHandler (`Features/bump/detection/handler.py`)

Most complex cog; detects bump-success messages and schedules reminders.

**Four-layer detection** (Discord's events are inconsistent for webhook messages): `on_message` → `on_message_edit` → `on_raw_message_edit` → `on_socket_raw_receive`.

**Text extraction** (`extract_all_text`): aggregates embeds (title/description/fields/footer/author), content, components, attachments, stickers, referenced messages; refetches up to 3× (0.3/0.6/0.9s) for async embed population; `channel.history()` fallback; force-refetch for WeBump on edit; normalizes (lowercase, strip zero-width, collapse whitespace).

**Bot detection** (`_resolve_bot_info`): matches `author_id` / `webhook_id` / `application_id` against `BUMP_BOTS_INFO`.

**Success flow**: detect bot + keyword → save timestamp (`timestamps.{bot_name}_timestamp`) → read guild config delay → compute active/expired timers → schedule embed update → schedule reminder via `bot.timer_handler`. Reminders are batched in a 10s window per channel; custom messages support `{bump_role}` / `{bots}`; premium guilds can send via webhook.

### StartUp (`Features/start_up.py`)

On `on_ready`, for each guild: load config via `bot.guild_config_manager`, skip if no bump channel/role, call `bump_handler.get_timers(config)`, and reschedule each active timer with remaining = `end_time - time.time()`.

### Dashboard (`dashboard/`)

FastAPI app (`dashboard/app.py`, run via `python -m dashboard.app`), architecturally aligned with TheCodex's dashboard.

**Shared login (SSO)** — the dashboard uses the **shared GateKeeper Discord app** and **shared session store** common to TheHost/TheCodex/EcomBackend/ImperialReminder:
- OAuth creds: `GATEKEEPER_CLIENT_ID` / `GATEKEEPER_CLIENT_SECRET` (identical across all dashboards).
- Two Mongo connections (like TheHost/TheCodex): **`MONGO_URI`** = ImperialReminder bot data (guild config), **`SHARED_SESSIONS_URI`** = the shared login store holding **`WebSessions.SharedSessions`** + **`WebSessions.OAuthStates`** (`dashboard/db.py`). Point `SHARED_SESSIONS_URI` at the same Mongo the other dashboards use; it may equal `MONGO_URI` on a single cluster.
- Session token is an opaque `token_urlsafe(48)` with a locked schema (`auth/session.py`); the cookie is the token signed by itsdangerous with salt `eos-session` (`auth/signing.py`). Cookie name `eos_session`; `DASHBOARD_SECRET_KEY` must be **identical** across services so a login on one dashboard is valid on all.
- In production set `COOKIE_DOMAIN=.eosofficial.club` for cross-subdomain SSO.

**Security infra** (mirrors Codex): `auth/csrf.py` (per-session CSRF token, `X-CSRF-Token` header enforced on POST/PUT/PATCH/DELETE via `csrf_middleware` + `verify_csrf` dependency; `GET /auth/csrf` issues it), `rate_limit.py` (in-process per-IP fixed-window limiter on `/auth/discord*` and `/api/stats`), and a `security_headers` middleware adding CSP / `X-Frame-Options: DENY` / `X-Content-Type-Options` / HSTS (prod).

**Routes**: OAuth (`/auth/discord`, `/auth/discord/callback`, `/auth/logout`), API (`/api/...` from `routers/dashboard.py` + `routers/settings.py`, gated by `get_current_user` / `require_guild_manage`), `GET /health`. Config in `dashboard/config.py` (loads `docker/.env`, fails fast on missing creds); server bound to `DASHBOARD_HOST`/`DASHBOARD_PORT` (54006 in Docker).

**Frontend stack** — same as TheCodex/TheHost: a **React 19 + TypeScript + Vite 6** SPA (`react-router-dom`) in `dashboard/frontend/` (`npm run build` → `tsc -b && vite build`), styled with the shared `eos-tokens.css` / `discord-theme.css`. `src/api/client.ts` is a CSRF-aware fetch wrapper (auto-fetches `/auth/csrf`, retries on stale token, redirects to `/login` on 401). Pages: `LoginPage`, `DashboardPage` (guild picker via `/api/me` + `/api/guilds` + `/api/bot-invite-url`), `SettingsPage` (`/settings/:guildId` — bump config form populated from `/api/guilds/{id}/channels`, `/roles`, `/bump-bots`). `app.py` serves the built SPA from `frontend/dist` (mounts `/assets`, falls back to `index.html` for client-side routes). The Vite build runs in **stage 1 of `docker/Dockerfile.dashboard`** (node:22) and is copied into the Python image; `node_modules/` and `frontend/dist/` are gitignored.

**Backend API endpoints** (`routers/dashboard.py`, Discord calls cached with TTL + single-flight): `/api/me`, `/api/guilds` (session guilds where the user has MANAGE_GUILD, with bot-present/has-config flags), `/api/bot-invite-url`, `/api/bump-bots`, `/api/guilds/{id}/channels`, `/api/guilds/{id}/roles`, `/api/stats/public`. `routers/settings.py`: `GET`/`PUT /api/guilds/{id}/settings` (PUT requires CSRF). Access uses MANAGE_GUILD only (no admin/mod panel-role concept).

### Logging (`utils/logger.py`)

`get_logger(module_name)` factory: colored console + rotating file handlers, optional JSON/indented formatters, `PerformanceLogger`, singleton `LoggerManager`. `setup_application_logging(...)` is called once in `Reminder.py`. Logs land in `log/`.

## Supported Bump Bots

Configured in `storage/sub_systems/bump_config.py`:

| Bot | ID | Default Cooldown | Premium Cooldown |
|-----|-----|------------------|------------------|
| Disboard | 302050872383242240 | 2 hours | - |
| BumpIt | 1006190394415005788 | 1 hour | - |
| Bump4You | 1089935069927456849 | 2 hours | - |
| WeBump | 1154077045903593555 | 2 hours | - |
| OneBump | 1028956609382199346 | 2 hours | 30 minutes |

**Success keywords** live in `SUCCESS_KEYWORDS`; the bot matches them in content/embeds/components after normalization.

## Common Development Tasks

### Add a new cog
Drop a file defining `async def setup(bot)` into `commands/` or `Features/`. It is auto-loaded on next start. Use `bot.guild_config_manager`, `bot.timer_handler`, etc. — do not re-instantiate managers.

### Add a new bump bot
In `storage/sub_systems/bump_config.py`: add to `BUMP_BOTS_INFO` (`ID: ("name", default_delay)`), `BUMP_BOTS`, `DEFAULT_GUILD_CONFIG["bot_delay"]` and `["timestamps"]`, `SUCCESS_KEYWORDS` (if distinct), and `BUMP_BOTS_CHOICES` for the slash-command UI.

### Database schema changes
Add fields to `GuildConfig` / `DEFAULT_GUILD_CONFIG`; additive changes need no migration (defaults fill in via `from_dict`). For breaking changes, write a migration using the collection manager.

### Debugging message detection
Watch `[extract_all_text]`, `[on_message]`, `[on_message_edit]`, `[on_raw_message_edit]` log entries to see which listener fired and the normalized text.

## Important Notes

- **TimerHandler singleton**: exactly one instance at `bot.timer_handler` (created in `attach_databases()`).
- **WeBump**: sends empty messages then edits ~1s later — handled by force-refetch on edit + raw gateway parsing.
- **Health ports**: bot 50006, dashboard 54006 (sequential after Codex 50002/54002 and Host 50003/54003).
- **MongoDB conventions**: guild IDs stored as strings (`_id`); timestamps as integer Unix seconds; nested updates via dot notation (`timestamps.disboard_timestamp`); dynamic fields prefixed `timer_message_{channel_id}`.

### Environment Variables

Required (bot): `DISCORD_TOKEN` (or `TOKEN`), `MONGO_URI` (bot data).
Dashboard: `GATEKEEPER_CLIENT_ID`, `GATEKEEPER_CLIENT_SECRET`, `GATEKEEPER_REDIRECT_URI`, `DASHBOARD_SECRET_KEY`, `SHARED_SESSIONS_URI` (shared login store), `DASHBOARD_HOST`, `DASHBOARD_PORT`, `ENVIRONMENT`. See `docker/.env`.

## Testing Locally

1. Populate `docker/.env`, run `python Reminder.py`; confirm logs show DB init, all managers attached, cogs loaded (including `Features.idle`), commands synced, and the health server on port 50006.
2. `curl http://localhost:50006/health` → `status: healthy`.
3. `/admin panel` → **Core Setup** to set bump channel + role; trigger a real bump bot; verify `Timer started: {guild_id}:{channel_id}:bump:{bot_name}` in logs.
4. Dashboard: `python -m dashboard.app`, then `curl http://localhost:54006/health`.
