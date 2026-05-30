<div align="center">

# ⏰ Imperial Reminder

### Never Miss a Server Bump Again

[![Discord](https://img.shields.io/badge/Discord-Bot-5865F2?style=for-the-badge&logo=discord&logoColor=white)](https://discord.com)
[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![MongoDB](https://img.shields.io/badge/MongoDB-Database-47A248?style=for-the-badge&logo=mongodb&logoColor=white)](https://www.mongodb.com/)
[![License](https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge)](LICENSE.md)

</div>

---

## 📖 About

**Imperial Reminder** is a powerful Discord bot that automatically tracks and reminds you when it's time to bump your server on popular Discord listing services. Keep your server at the top of the listings without constantly checking the clock!

The bot intelligently detects successful bumps across multiple platforms, tracks cooldown periods, and sends timely reminders to ensure you never miss an opportunity to promote your server.

## ✨ Features

### 🎯 Multi-Platform Support
Track bumps across all major Discord server listing services:
- **Disboard** (2-hour cooldown)
- **BumpIt** (1-hour cooldown)
- **Bump4You** (2-hour cooldown)
- **WeBump** (2-hour cooldown)
- **OneBump** (2-hour cooldown, 30-min premium)

### 🔔 Smart Reminders
- **Automatic Detection**: Instantly recognizes when you successfully bump on any supported platform
- **Timely Notifications**: Get reminded exactly when your cooldown expires
- **Role Mentions**: Configure custom bump roles to notify your team
- **Batch Notifications**: Combines multiple ready-to-bump reminders to reduce spam

### ⚙️ Highly Configurable
- **Per-Server Settings**: Each server gets its own independent configuration
- **Custom Delays**: Override default cooldown periods for each bump service
- **Custom Messages**: Personalize reminder messages with role and bot mentions
- **Flexible Channels**: Separate channels for bump commands and timer displays

### 💎 Premium Features
- **Webhook Integration**: Send reminders via custom webhooks for a branded experience
- **Reduced Cooldowns**: OneBump cooldown reduced to 30 minutes (where applicable)
- **Priority Support**: Get help faster with premium status

### 📊 Timer Display
- **Live Status Board**: Real-time embed showing all bump cooldowns and remaining times
- **Visual Indicators**: Quickly see which services are ready to bump
- **Auto-Updates**: Timer board refreshes automatically as cooldowns expire

## 🎮 Commands

### `/admin panel`
The single, unified configuration panel (Discord Components v2). Requires the
**Manage Server** permission. Sections:

- **Core Setup** — Bump Channel, Bump Role, Timers Channel
- **Bump Bots** — choose which bump bots to track, and tune each bot's cooldown
- **Messages** — custom reminder text (`{bump_role}` / `{bots}` placeholders) and the live timer embed toggle
- **Premium** — premium status and premium-code activation

Bump Bots / Messages stay locked until a Bump Channel and Bump Role are set.

> Premium code generation/management is owner-only via the hidden `!admin` DM command.

## 🛠️ Technology Stack

- **Discord.py 2.5+** - Modern async Discord bot framework
- **MongoDB** - Persistent storage for guild configurations and timestamps
- **Docker** - Containerized deployment for easy hosting
- **Custom Timer System** - Robust, production-ready scheduling with jitter and retry logic

## 🌟 Highlights

### Intelligent Message Detection
The bot uses a **four-layer detection system** to catch bump success messages:
1. Real-time message monitoring
2. Message edit tracking (for async embeds)
3. Raw gateway event parsing
4. Webhook message detection

This ensures reliable detection even with Discord's inconsistent event delivery.

### Production-Ready Timer System
- **Monotonic time tracking** prevents drift from system clock changes
- **Exponential backoff** with configurable retries
- **Jitter support** prevents thundering herd issues
- **Graceful shutdown** preserves timer state across restarts

## 📝 License

This project is licensed under the MIT License - see the [LICENSE.md](LICENSE.md) file for details.

## 🤝 Contributing

Contributions are welcome! Please feel free to open an issue or submit a pull request.

---

<div align="center">

**Built with ❤️ for the Empire of Shadows community**

</div>
