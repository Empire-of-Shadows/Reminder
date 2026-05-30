import discord
from discord.ext import commands
from discord.ui import Select, Button, View, Modal, TextInput
import secrets
import string
from datetime import datetime, timedelta, timezone
import os

from utils.env import load_project_env
from utils.logger import get_logger

logger = get_logger("AdminPanel")
load_project_env()

OWNER_IDS = [int(id.strip()) for id in os.getenv("OWNER_IDS", "").split(",") if id.strip()]

class AdminPanel(commands.Cog):
    """Hidden admin panel for premium management - DM only."""

    def __init__(self, bot):
        self.bot = bot

    def is_owner(self, user_id: int) -> bool:
        return user_id in OWNER_IDS

    @commands.command(name="admin")
    async def admin_panel(self, ctx: commands.Context):
        if ctx.guild is not None:
            try: await ctx.message.delete()
            except: pass
            return

        if not self.is_owner(ctx.author.id):
            await ctx.send("🚫 Access denied.")
            return

        logger.info(f"Admin panel accessed by user {ctx.author.id}")
        view = AdminMenuView(self.bot, ctx.author.id)
        embed = create_admin_menu_embed()
        await ctx.send(embed=embed, view=view)

def create_admin_menu_embed() -> discord.Embed:
    embed = discord.Embed(title="🔐 Admin Panel", description="Premium code management", color=0xFF0000)
    embed.add_field(name="Actions", value="Generate, View, Deactivate", inline=False)
    return embed

def generate_code(length=8) -> str:
    return ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(length))

class AdminMenuView(View):
    def __init__(self, bot, admin_id: int):
        super().__init__(timeout=600)
        self.bot = bot
        self.admin_id = admin_id
        self.add_item(AdminActionSelect(self))

    async def show_main_menu(self, interaction: discord.Interaction):
        self.clear_items()
        self.add_item(AdminActionSelect(self))
        await interaction.response.edit_message(embed=create_admin_menu_embed(), view=self)

class AdminActionSelect(Select):
    def __init__(self, parent_view):
        self.parent_view = parent_view
        options = [
            discord.SelectOption(label="Generate Code", value="generate"),
            discord.SelectOption(label="View Codes", value="view_codes"),
            discord.SelectOption(label="Deactivate", value="deactivate"),
        ]
        super().__init__(placeholder="Action...", options=options)

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "generate":
            await interaction.response.send_modal(GenerateCodeModal(self.parent_view))
        elif self.values[0] == "view_codes":
            await self.parent_view.show_codes_list(interaction)
        elif self.values[0] == "deactivate":
            await interaction.response.send_modal(DeactivatePremiumModal(self.parent_view))

    async def show_codes_list(self, interaction: discord.Interaction):
        await interaction.response.defer()
        # Using new storage
        codes_col = self.parent_view.bot.db_manager.premium_codes
        codes = await codes_col.find_many({}, sort=[("created_at", -1)])
        
        embed = discord.Embed(title="📋 Codes", description=f"Total: {len(codes)}", color=0xFF0000)
        # Show a few
        for c in codes[:10]:
            embed.add_field(name=c["code"], value=f"Type: {c['type']} | Linked: {c.get('linked_guild', 0)}", inline=False)
        
        self.parent_view.clear_items()
        self.parent_view.add_item(BackToMenuButton(self.parent_view))
        await interaction.followup.edit_message(message_id=interaction.message.id, embed=embed, view=self.parent_view)

class GenerateCodeModal(Modal):
    def __init__(self, parent_view):
        super().__init__(title="Generate Code")
        self.parent_view = parent_view
        self.type = TextInput(label="Type (trial, monthly)", default="trial")
        self.days = TextInput(label="Duration (days)", default="7")
        self.add_item(self.type)
        self.add_item(self.days)

    async def on_submit(self, interaction: discord.Interaction):
        code = generate_code()
        expiry = datetime.now(timezone.utc) + timedelta(days=int(self.days.value))
        
        await self.parent_view.bot.db_manager.premium_codes.create_one({
            "code": code,
            "type": self.type.value,
            "expires_at": expiry.isoformat(),
            "linked_guild": 0,
            "issued_to": 0,
            "expired": False,
            "created_by": interaction.user.id
        })
        
        await interaction.response.send_message(f"✅ Generated: `{code}`", ephemeral=True)

class DeactivatePremiumModal(Modal):
    def __init__(self, parent_view):
        super().__init__(title="Deactivate")
        self.parent_view = parent_view
        self.guild_id = TextInput(label="Guild ID")
        self.add_item(self.guild_id)

    async def on_submit(self, interaction: discord.Interaction):
        gid = int(self.guild_id.value)
        await self.parent_view.bot.guild_config_manager.set_value(gid, "premium.enabled", False)
        await self.parent_view.bot.db_manager.premium_codes.update_one({"linked_guild": str(gid)}, {"$set": {"linked_guild": 0}})
        await interaction.response.send_message(f"✅ Deactivated {gid}", ephemeral=True)

class BackToMenuButton(Button):
    def __init__(self, parent_view):
        super().__init__(label="Back", style=discord.ButtonStyle.secondary)
        self.parent_view = parent_view
    async def callback(self, interaction: discord.Interaction):
        await self.parent_view.show_main_menu(interaction)

async def setup(bot):
    await bot.add_cog(AdminPanel(bot))
