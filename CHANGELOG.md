# Changelog

All notable, community-facing changes to ImperialReminder are recorded here in plain language.
For the technical, commit-level history, see git.

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
