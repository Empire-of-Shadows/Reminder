# Changelog

All notable, community-facing changes to ImperialReminder are recorded here in plain language.
For the technical, commit-level history, see git.

## [Unreleased] - 2026-08-05

### Added
- **Create roles and channels straight from the picker.** Every role and channel picker in the
  admin panel now carries a Create button: type a name and the new role or channel is created and
  selected in one step, without leaving the panel. The button first checks that the bot itself is
  allowed to create it and tells you which permission is missing instead of failing afterwards.
  Text channel names follow Discord's rules (lowercase letters, digits and dashes), and a rejected
  name comes back with a Try Again button that keeps what you typed.
- **Pick a category when creating a channel.** The Create Channel button in the admin panel now
  lets you choose which category the new channel goes under - or leave the picker empty to create
  it at the top of the channel list. If something goes wrong, Try Again keeps both the name you
  typed and the category you picked.

### Changed
- **The panel now refuses roles that would not actually work.** The pickers that decide who can
  open the admin panel no longer accept @everyone or roles managed by an integration (bot roles,
  booster roles) - membership of those is outside the server's control, so allowing them would
  open the panel wider than intended. Regular admin roles still work, including ones that sit
  above the bot. Every refusal explains itself.

## [Unreleased] - 2026-08-02

### Added
- **There is now a `/help` command.** Imperial Reminder mostly works in the background, which
  made it hard to tell what it was doing or whether it was doing anything at all. `/help` opens a
  short guide you can page through with a dropdown: what the bot does, how a bump turns into a
  countdown and then into a ping, which listing sites it can watch, and what premium adds. Only
  you can see it, and there is a button straight to the web dashboard.
- Server admins see an extra **Admin** section in that guide covering `/admin panel`, what each
  part of the panel is for, and the two settings - a bump channel and a bump role - that have to
  be set before any reminders run.

## [Unreleased] - 2026-08-01

### Fixed
- **The privacy policy said the bot does not read your messages. That was not true.** Imperial
  Reminder has to read messages in your bump channel - that is the only way it can spot a bump
  bot's "bump done" message and start the timer. It reads nothing outside that one channel, it
  never puts that text in its database, and it still does not track individual members. The policy
  now says exactly that instead of claiming the bot reads nothing, and it also notes that the text
  it reads shows up in the operational log used for troubleshooting.

### Changed
- **The policy you agree to when you sign in now covers every Empire of Shadows service.** One
  login signs you in to all of the bot dashboards, but the login screen only ever pointed at
  Imperial Reminder's own privacy policy, which does not describe what the other bots do with
  your data. Signing in now points you to a single combined Empire of Shadows privacy policy
  covering every bot, dashboard and tool. Imperial Reminder's own privacy page has not gone
  anywhere - it is linked from the same line and from the footer, and still holds the detail
  specific to this bot.

## [Unreleased] - 2026-07-27

### Added
- **The bot now speaks up when it has not been set up.** Until today, a server that added
  Imperial Reminder but never picked a bump channel got complete silence - people would bump,
  nothing would happen, and there was no message, no error and nothing to explain why. Now, when
  a bump goes through on a server that has not finished setup, the bot posts once to say it saw
  the bump, that no reminder was scheduled, and exactly where to fix it: `/admin panel` ->
  **Core Setup**.
- That message also says **who** can fix it. On a server that has not handed out panel access
  yet, only the owner and people with Manage Server can open the panel, so the message names the
  owner rather than telling everyone else to run a command they cannot use - and points the owner
  at **Panel Access** so they can let their staff help.
- It cannot become nagging. The notice appears at most once per day per server, only after a real
  bump from a bump bot the bot recognises (a message that merely says "bump done" can never
  trigger it), and it stays quiet if it lacks permission to post in that channel. Once a bump
  channel is set, it never appears again.

## [Unreleased] - 2026-07-26

### Fixed
- The `/admin` panel's setup progress was counting things you cannot actually configure. Screens
  and buttons that only show information or run an action - such as the premium **Status** view -
  were being added to each category's "X of Y configured" total, so a category could never read
  as finished no matter how much you set up. Only real settings count now, and a category that
  holds nothing but action screens just shows its name instead of a meaningless total.
- A list you had not put anything in yet was being counted as configured. An empty list now
  correctly reads as still needing setup.

## [Unreleased] - 2026-07-23

### Added
- The dashboard's Privacy page is now a real account-control page, matching the one on TheHost.
  You can pick whether to work across all your servers or just one, download a JSON copy of
  everything the bot holds against your Discord account, and erase yourself from it. Imperial
  Reminder still tracks servers rather than members, so what that covers is the audit entries
  written when you change a server's settings, plus any premium grants involving your account.
  Erasing strips your name and Discord ID from those entries while leaving the server's record
  that a setting changed - admins keep their history, and it no longer points at you.

- The Settings home page is now the same "Web of Servers" view the Codex and Host dashboards use:
  your servers are drawn as a live network around the Empire sigil, colour-coded by whether you
  are an admin or a mod there, with a side panel that opens settings for whichever one you pick.
  Servers the bot has not joined yet show an invite link instead.

### Fixed
- Restarting the bot no longer re-pings your bump role. Previously, any cooldown that had already
  run out got announced again every time the bot restarted or reconnected to Discord, so a quiet
  server could be pinged repeatedly for the same bump. The bot now remembers which bump it has
  already reminded you about: a reminder that was missed because the bot was offline still arrives,
  but only once.
- The dashboard's public stats endpoint crashed on every request, so the sign-in page showed no
  server or bump-bot counts.

### Changed
- The dashboard now keeps a readable activity log. Every settings change, sign-in and rejected
  request is recorded with who did it, which server it was for, whether it worked and how long
  it took - so an admin can look back and see what happened. Ordinary page loads stay out of the
  log unless you ask for them (set `DASHBOARD_LOG_READS=1`).
- The dashboard had been running with debug logging left on, which buried anything useful under
  a constant stream of internal chatter. It now logs at the normal level, to both the console and
  a rotating file under `logs/`. Set `LOG_LEVEL=DEBUG` if you ever need the extra detail back.
