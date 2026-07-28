# Changelog

All notable, community-facing changes to ImperialReminder are recorded here in plain language.
For the technical, commit-level history, see git.

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
