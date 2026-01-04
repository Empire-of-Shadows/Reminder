# Python
"""
Hidden Admin Panel for Premium Management
DM-only interface for bot owners to manage premium codes
"""

import discord
from discord.ext import commands
from discord.ui import Select, Button, View, Modal, TextInput
import secrets
import string
from datetime import datetime, timedelta
import pytz
import os
from dotenv import load_dotenv

from cogs.bump.storage.database import BumpStorage
from utils.logger import get_logger

logger = get_logger("AdminPanel")
load_dotenv()

# Bot owner user IDs (comma-separated in .env)
OWNER_IDS = [int(id.strip()) for id in os.getenv("OWNER_IDS", "").split(",") if id.strip()]


class AdminPanel(commands.Cog):
    """Hidden admin panel for premium management - DM only."""

    def __init__(self, bot):
        self.bot = bot
        self.db = BumpStorage().db
        self.codes_collection = self.db["codes"]

    def is_owner(self, user_id: int) -> bool:
        """Check if user is a bot owner."""
        return user_id in OWNER_IDS

    @commands.command(name="admin")
    async def admin_panel(self, ctx: commands.Context):
        """
        Secret admin panel command - DM only, owner only.
        Usage: -admin (in DMs with the bot)
        """
        # Check if in DMs
        if ctx.guild is not None:
            await ctx.message.delete()  # Delete command in servers
            return

        # Check if user is owner
        if not self.is_owner(ctx.author.id):
            logger.warning(f"Unauthorized admin panel access attempt by user {ctx.author.id}")
            await ctx.send("🚫 Access denied.")
            return

        logger.info(f"Admin panel accessed by user {ctx.author.id}")

        # Create admin menu view
        view = AdminMenuView(self.bot, self.codes_collection, ctx.author.id)
        embed = create_admin_menu_embed()

        await ctx.send(embed=embed, view=view)


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def create_admin_menu_embed() -> discord.Embed:
    """Create main admin panel menu embed."""
    embed = discord.Embed(
        title="🔐 Admin Panel",
        description="Premium code management system\n\nSelect an option from the dropdown below:",
        color=0xFF0000
    )
    embed.add_field(
        name="Available Actions",
        value=(
            "**Generate Code** - Create new premium codes\n"
            "**View Codes** - List all generated codes\n"
            "**Deactivate Premium** - Remove premium from a guild\n"
            "**Code Statistics** - View usage stats"
        ),
        inline=False
    )
    embed.set_footer(text="⚠️ Owner-only interface • All actions are logged")
    return embed


def generate_code(length=8) -> str:
    """Generate a random alphanumeric premium code."""
    return ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(length))


# ============================================================================
# UI COMPONENTS - ADMIN MENU
# ============================================================================

class AdminMenuView(View):
    """Main admin panel view with dropdown navigation."""

    def __init__(self, bot, codes_collection, admin_id: int):
        super().__init__(timeout=600)  # 10 minute timeout
        self.bot = bot
        self.codes_collection = codes_collection
        self.admin_id = admin_id
        self.message = None

        self.add_item(AdminActionSelect(self))

    async def show_main_menu(self, interaction: discord.Interaction):
        """Return to main admin menu."""
        self.clear_items()
        self.add_item(AdminActionSelect(self))

        embed = create_admin_menu_embed()
        await interaction.response.edit_message(embed=embed, view=self)


class AdminActionSelect(Select):
    """Dropdown menu for selecting admin actions."""

    def __init__(self, parent_view):
        self.parent_view = parent_view
        options = [
            discord.SelectOption(
                label="Generate Premium Code",
                value="generate",
                emoji="✨",
                description="Create a new premium activation code"
            ),
            discord.SelectOption(
                label="View All Codes",
                value="view_codes",
                emoji="📋",
                description="List all generated premium codes"
            ),
            discord.SelectOption(
                label="Deactivate Premium",
                value="deactivate",
                emoji="🚫",
                description="Remove premium from a guild"
            ),
            discord.SelectOption(
                label="Code Statistics",
                value="stats",
                emoji="📊",
                description="View code usage statistics"
            ),
        ]
        super().__init__(
            placeholder="Select an action...",
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        action = self.values[0]

        if action == "generate":
            await self.parent_view.show_generate_code(interaction)
        elif action == "view_codes":
            await self.parent_view.show_codes_list(interaction)
        elif action == "deactivate":
            await self.parent_view.show_deactivate_premium(interaction)
        elif action == "stats":
            await self.parent_view.show_statistics(interaction)


# ============================================================================
# ADMIN VIEW METHODS
# ============================================================================

    async def show_generate_code(self, interaction: discord.Interaction):
        """Show code generation modal."""
        modal = GenerateCodeModal(self)
        await interaction.response.send_modal(modal)

    async def show_codes_list(self, interaction: discord.Interaction):
        """Display list of all premium codes."""
        await interaction.response.defer()

        try:
            codes = await self.codes_collection.find({}).sort("created_at", -1).to_list(length=None)

            if not codes:
                embed = discord.Embed(
                    title="📋 Premium Codes",
                    description="No codes have been generated yet.",
                    color=0xFF0000
                )
            else:
                embed = discord.Embed(
                    title="📋 Premium Codes",
                    description=f"Total codes: **{len(codes)}**",
                    color=0xFF0000
                )

                # Group by status
                active = [c for c in codes if not c.get("expired", False) and c.get("linked_guild", 0) == 0]
                used = [c for c in codes if c.get("linked_guild", 0) != 0]
                expired = [c for c in codes if c.get("expired", False)]

                if active:
                    active_text = ""
                    for code in active[:10]:  # Show first 10
                        expires = datetime.fromisoformat(code.get("expires_at", ""))
                        active_text += f"`{code.get('code', 'UNKNOWN')}` - {code.get('type', 'unknown')} (expires {expires.strftime('%Y-%m-%d')})\n"
                    if len(active) > 10:
                        active_text += f"*...and {len(active) - 10} more*"
                    embed.add_field(name=f"✅ Active ({len(active)})", value=active_text, inline=False)

                if used:
                    used_text = ""
                    for code in used[:5]:
                        used_text += f"`{code.get('code', 'UNKNOWN')}` - Guild {code.get('linked_guild', 0)}\n"
                    if len(used) > 5:
                        used_text += f"*...and {len(used) - 5} more*"
                    embed.add_field(name=f"🔗 Used ({len(used)})", value=used_text, inline=False)

                if expired:
                    embed.add_field(name=f"⏰ Expired ({len(expired)})", value=f"{len(expired)} expired codes", inline=False)

            # Add back button
            self.clear_items()
            self.add_item(BackToMenuButton(self))

            await interaction.followup.edit_message(
                message_id=interaction.message.id,
                embed=embed,
                view=self
            )

        except Exception as e:
            logger.error(f"Failed to list codes: {e}", exc_info=True)
            embed = discord.Embed(
                title="❌ Error",
                description="Failed to retrieve codes. Check logs.",
                color=discord.Color.red()
            )
            await interaction.followup.edit_message(
                message_id=interaction.message.id,
                embed=embed
            )

    async def show_deactivate_premium(self, interaction: discord.Interaction):
        """Show premium deactivation modal."""
        modal = DeactivatePremiumModal(self)
        await interaction.response.send_modal(modal)

    async def show_statistics(self, interaction: discord.Interaction):
        """Show code usage statistics."""
        await interaction.response.defer()

        try:
            total_codes = await self.codes_collection.count_documents({})
            active_codes = await self.codes_collection.count_documents({
                "expired": False,
                "linked_guild": 0
            })
            used_codes = await self.codes_collection.count_documents({
                "linked_guild": {"$ne": 0}
            })
            expired_codes = await self.codes_collection.count_documents({
                "expired": True
            })

            # Count by type
            trial_count = await self.codes_collection.count_documents({"type": "trial"})
            monthly_count = await self.codes_collection.count_documents({"type": "monthly"})
            yearly_count = await self.codes_collection.count_documents({"type": "yearly"})
            lifetime_count = await self.codes_collection.count_documents({"type": "lifetime"})

            embed = discord.Embed(
                title="📊 Code Statistics",
                color=0xFF0000
            )

            embed.add_field(
                name="Overview",
                value=(
                    f"**Total Codes:** {total_codes}\n"
                    f"**Active:** {active_codes}\n"
                    f"**Used:** {used_codes}\n"
                    f"**Expired:** {expired_codes}"
                ),
                inline=False
            )

            embed.add_field(
                name="By Type",
                value=(
                    f"**Trial:** {trial_count}\n"
                    f"**Monthly:** {monthly_count}\n"
                    f"**Yearly:** {yearly_count}\n"
                    f"**Lifetime:** {lifetime_count}"
                ),
                inline=False
            )

            # Add back button
            self.clear_items()
            self.add_item(BackToMenuButton(self))

            await interaction.followup.edit_message(
                message_id=interaction.message.id,
                embed=embed,
                view=self
            )

        except Exception as e:
            logger.error(f"Failed to get statistics: {e}", exc_info=True)
            embed = discord.Embed(
                title="❌ Error",
                description="Failed to retrieve statistics. Check logs.",
                color=discord.Color.red()
            )
            await interaction.followup.edit_message(
                message_id=interaction.message.id,
                embed=embed
            )


# Add methods to AdminMenuView
AdminMenuView.show_generate_code = AdminActionSelect.show_generate_code
AdminMenuView.show_codes_list = AdminActionSelect.show_codes_list
AdminMenuView.show_deactivate_premium = AdminActionSelect.show_deactivate_premium
AdminMenuView.show_statistics = AdminActionSelect.show_statistics


# ============================================================================
# UI COMPONENTS - MODALS
# ============================================================================

class GenerateCodeModal(Modal):
    """Modal for generating a new premium code."""

    def __init__(self, parent_view):
        super().__init__(title="Generate Premium Code")
        self.parent_view = parent_view

        self.code_type = TextInput(
            label="Code Type",
            placeholder="trial, monthly, yearly, or lifetime",
            style=discord.TextStyle.short,
            max_length=10,
            required=True
        )
        self.add_item(self.code_type)

        self.duration_days = TextInput(
            label="Duration (days)",
            placeholder="7 for trial, 30 for monthly, 365 for yearly, 36500 for lifetime",
            style=discord.TextStyle.short,
            max_length=6,
            required=True
        )
        self.add_item(self.duration_days)

    async def on_submit(self, interaction: discord.Interaction):
        code_type = self.code_type.value.strip().lower()
        try:
            duration = int(self.duration_days.value.strip())
        except ValueError:
            await interaction.response.send_message(
                "❌ Invalid duration. Must be a number.",
                ephemeral=True
            )
            return

        # Validate code type
        valid_types = ["trial", "monthly", "yearly", "lifetime"]
        if code_type not in valid_types:
            await interaction.response.send_message(
                f"❌ Invalid code type. Must be one of: {', '.join(valid_types)}",
                ephemeral=True
            )
            return

        await interaction.response.defer()

        try:
            # Generate unique code
            code = generate_code()

            # Calculate expiry date
            now = datetime.now(pytz.utc)
            expires_at = now + timedelta(days=duration)

            # Create code document
            code_doc = {
                "code": code,
                "type": code_type,
                "created_at": now.isoformat(),
                "expires_at": expires_at.isoformat(),
                "linked_guild": 0,
                "issued_to": 0,
                "expired": False,
                "created_by": interaction.user.id
            }

            await self.parent_view.codes_collection.insert_one(code_doc)

            embed = discord.Embed(
                title="✅ Code Generated",
                description=f"Premium code created successfully!",
                color=discord.Color.green()
            )
            embed.add_field(name="Code", value=f"`{code}`", inline=False)
            embed.add_field(name="Type", value=code_type.capitalize(), inline=True)
            embed.add_field(name="Duration", value=f"{duration} days", inline=True)
            embed.add_field(name="Expires", value=expires_at.strftime('%Y-%m-%d %H:%M UTC'), inline=False)

            logger.info(f"Premium code generated: {code} ({code_type}, {duration} days) by admin {interaction.user.id}")

            # Add back button
            self.parent_view.clear_items()
            self.parent_view.add_item(BackToMenuButton(self.parent_view))

            await interaction.followup.edit_message(
                message_id=interaction.message.id,
                embed=embed,
                view=self.parent_view
            )

        except Exception as e:
            logger.error(f"Failed to generate code: {e}", exc_info=True)
            embed = discord.Embed(
                title="❌ Generation Failed",
                description="Failed to generate code. Check logs.",
                color=discord.Color.red()
            )
            await interaction.followup.edit_message(
                message_id=interaction.message.id,
                embed=embed
            )


class DeactivatePremiumModal(Modal):
    """Modal for deactivating premium for a guild."""

    def __init__(self, parent_view):
        super().__init__(title="Deactivate Premium")
        self.parent_view = parent_view

        self.guild_id_input = TextInput(
            label="Guild ID",
            placeholder="Enter the guild ID to deactivate premium...",
            style=discord.TextStyle.short,
            max_length=20,
            required=True
        )
        self.add_item(self.guild_id_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            guild_id = int(self.guild_id_input.value.strip())
        except ValueError:
            await interaction.response.send_message(
                "❌ Invalid guild ID. Must be a number.",
                ephemeral=True
            )
            return

        await interaction.response.defer()

        try:
            bump_storage = BumpStorage()

            # Check if guild has premium
            config = await bump_storage.get_guild(guild_id)
            if not config.get("premium", {}).get("enabled", False):
                embed = discord.Embed(
                    title="❌ Not Premium",
                    description=f"Guild `{guild_id}` does not have premium activated.",
                    color=discord.Color.red()
                )
                self.parent_view.clear_items()
                self.parent_view.add_item(BackToMenuButton(self.parent_view))
                await interaction.followup.edit_message(
                    message_id=interaction.message.id,
                    embed=embed,
                    view=self.parent_view
                )
                return

            # Deactivate premium
            await bump_storage.set_value(guild_id, "premium.enabled", False)
            await bump_storage.set_value(guild_id, "premium.activated_by", 0)
            await bump_storage.set_value(guild_id, "premium.guild_webhook", 0)

            # Unlink code
            await self.parent_view.codes_collection.update_one(
                {"linked_guild": guild_id},
                {"$set": {"linked_guild": 0}}
            )

            embed = discord.Embed(
                title="✅ Premium Deactivated",
                description=f"Premium has been removed from guild `{guild_id}`.",
                color=discord.Color.green()
            )

            logger.info(f"Premium deactivated for guild {guild_id} by admin {interaction.user.id}")

            # Add back button
            self.parent_view.clear_items()
            self.parent_view.add_item(BackToMenuButton(self.parent_view))

            await interaction.followup.edit_message(
                message_id=interaction.message.id,
                embed=embed,
                view=self.parent_view
            )

        except Exception as e:
            logger.error(f"Failed to deactivate premium: {e}", exc_info=True)
            embed = discord.Embed(
                title="❌ Deactivation Failed",
                description="Failed to deactivate premium. Check logs.",
                color=discord.Color.red()
            )
            await interaction.followup.edit_message(
                message_id=interaction.message.id,
                embed=embed
            )


class BackToMenuButton(Button):
    """Button to return to main admin menu."""

    def __init__(self, parent_view):
        super().__init__(label="Back to Menu", emoji="◀️", style=discord.ButtonStyle.secondary)
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        await self.parent_view.show_main_menu(interaction)


async def setup(bot):
    await bot.add_cog(AdminPanel(bot))
