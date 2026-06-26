# Changelog

All notable changes to ImperialReminder will be documented in this file.

**The contents of this file should never be overwritten.**

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased] - 2026-06-08

### Added
- A new public **Privacy Policy** page (at `/privacy`, linked from the footer and the sign-in screen) that you can read without signing in. It explains in plain language that Imperial Reminder doesn't read or store your messages and doesn't track individual members — it only keeps each server's bump setup, plus premium info. Contact is **support@eosofficial.club**.

## [Unreleased] - 2026-06-03

### Added
- The dashboard now has the same three pages as the other Empire of Shadows bots: **Stats**, **Privacy**, and **Settings**.
- **Privacy page**: explains in plain language that the bot doesn't track individual members — it only stores each server's bump setup.
- **Settings page** now lets you grant dashboard access by role: **Admin** roles can change a server's settings, and **Mod** roles can view them (read-only). Previously only people with Manage Server could open settings at all.

### Changed
- The top menu link to your servers is now called **Stats** (it shows each server's live bump status), and there's a new **Settings** menu that lists the servers you can manage.
- When you pick a server the bot isn't in yet, you now get a clear "Invite the bot" link to click instead of a pop-up window opening on its own.
