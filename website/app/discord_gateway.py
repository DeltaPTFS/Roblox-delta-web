"""Discord Gateway listeners and staff commands for the SkyMiles website.

The module imports discord.py lazily so local web development can still start
without the optional bot integration being configured.
"""

import asyncio

from sqlalchemy import select

from .config import Settings
from .database import SessionLocal
from .models import AuditLog, Status, Transaction, User


class DiscordGateway:
    def __init__(self, bot, task: asyncio.Task):
        self.bot = bot
        self.task = task

    async def close(self) -> None:
        await self.bot.close()
        self.task.cancel()


def _staff_role_ids(settings: Settings) -> set[str]:
    return (
        settings.ids(settings.owner_discord_role_ids)
        | settings.ids(settings.admin_discord_role_ids)
        | settings.ids(settings.staff_discord_role_ids)
    )


def _button_role_ids(settings: Settings) -> set[str]:
    """Roles authorized to publish persistent link-button messages."""
    return settings.ids(settings.button_command_role_ids)


async def start_discord_gateway(settings: Settings) -> DiscordGateway | None:
    """Start member-join automation and the secured `/skymiles-add` command."""
    if not settings.discord_bot_token or not settings.discord_guild_id:
        return None

    import discord
    from discord import app_commands

    intents = discord.Intents.none()
    intents.guilds = True
    intents.members = True
    bot = discord.Client(intents=intents)
    tree = app_commands.CommandTree(bot)
    guild = discord.Object(id=int(settings.discord_guild_id))

    async def send_log(title: str, description: str) -> None:
        if not settings.discord_log_channel_id:
            return
        try:
            channel = bot.get_channel(int(settings.discord_log_channel_id))
            channel = channel or await bot.fetch_channel(int(settings.discord_log_channel_id))
            await channel.send(embed=discord.Embed(title=title, description=description, color=0xD7193F), allowed_mentions=discord.AllowedMentions.none())
        except Exception:
            # Logging outages must never undo a role or database update.
            return

    @bot.event
    async def on_ready():
        await tree.sync(guild=guild)

    @bot.event
    async def on_member_join(member):
        if str(member.guild.id) != settings.discord_guild_id:
            return
        role = member.guild.get_role(int(settings.discord_unverified_role_id)) if settings.discord_unverified_role_id else None
        role = role or next((item for item in member.guild.roles if item.name.casefold() == "unverified"), None)
        if role:
            await member.add_roles(role, reason="New member awaiting SkyMiles authentication")
            await send_log("Member awaiting verification", f"{member} joined and received **{role.name}**.")

    @tree.command(name="skymiles-add", description="Add SkyMiles to a verified member account", guild=guild)
    @app_commands.describe(member="Discord member", amount="SkyMiles to add", reason="Required audit reason")
    async def skymiles_add(interaction, member: discord.Member, amount: int, reason: str):
        invoker_roles = {str(role.id) for role in interaction.user.roles}
        if not invoker_roles & _staff_role_ids(settings):
            await interaction.response.send_message("You are not authorized to adjust SkyMiles.", ephemeral=True)
            return
        reason = reason.strip()
        if amount < 1 or amount > 1_000_000 or not reason:
            await interaction.response.send_message("Enter 1–1,000,000 SkyMiles and a reason.", ephemeral=True)
            return
        with SessionLocal() as db:
            actor = db.scalar(select(User).where(User.discord_user_id == str(interaction.user.id)))
            target = db.scalar(select(User).where(User.discord_user_id == str(member.id)).with_for_update())
            if not actor or not target or target.account_status != Status.ACTIVE:
                await interaction.response.send_message("Both staff and member must have active linked SkyMiles accounts.", ephemeral=True)
                return
            before = target.miles_balance
            target.miles_balance += amount
            target.lifetime_miles += amount
            db.add(Transaction(user_id=target.id, type="MILES_ADDED", description=reason, reference="DISCORD-COMMAND", miles_change=amount, balance_before=before, balance_after=target.miles_balance, created_by=actor.id))
            db.add(AuditLog(staff_user_id=actor.id, target_user_id=target.id, action="MILES_ADDED", old_value={"balance": before}, new_value={"balance": target.miles_balance}, reason=reason, security_metadata={"source": "discord_slash_command"}))
            db.commit()
            balance = target.miles_balance
        await interaction.response.send_message(f"SkyMiles applied! {member.mention} received **{amount:,}** miles. New balance: **{balance:,}**.", ephemeral=True)
        await send_log("SkyMiles applied", f"{interaction.user} added **{amount:,}** SkyMiles to {member}.\nReason: {reason}")

    @tree.command(name="create-button", description="Publish an approved link button", guild=guild)
    @app_commands.describe(label="Text displayed on the button", url="Secure destination URL", message="Message shown above the button", emoji="Optional Unicode or custom emoji", hex_color="Optional six-digit embed color")
    async def create_button(interaction, label: str, url: str, message: str, emoji: str = "", hex_color: str = "5865F2"):
        invoker_roles = {str(role.id) for role in interaction.user.roles}
        allowed_roles = _button_role_ids(settings)
        if not invoker_roles & allowed_roles:
            allowed = " ".join(f"<@&{role_id}>" for role_id in sorted(allowed_roles)) or "the configured Ownership role"
            await interaction.response.send_message(f"Only {allowed} may create button messages.", ephemeral=True, allowed_mentions=discord.AllowedMentions.none())
            return
        label, url, message = label.strip(), url.strip(), message.strip()
        if not (1 <= len(label) <= 80 and 1 <= len(message) <= 2000 and url.startswith("https://")):
            await interaction.response.send_message("Use a 1–80 character label, a message, and a secure `https://` URL.", ephemeral=True)
            return
        try:
            color_text = hex_color.strip().removeprefix("#")
            if len(color_text) != 6:
                raise ValueError
            color = int(color_text, 16)
        except ValueError:
            await interaction.response.send_message("The color must be a six-digit hex value such as `5865F2`.", ephemeral=True)
            return
        button_kwargs = {"label": label, "url": url, "style": discord.ButtonStyle.link}
        if emoji.strip():
            button_kwargs["emoji"] = discord.PartialEmoji.from_str(emoji.strip())
        view = discord.ui.View(timeout=None)
        try:
            view.add_item(discord.ui.Button(**button_kwargs))
            await interaction.channel.send(embed=discord.Embed(description=message, color=color), view=view, allowed_mentions=discord.AllowedMentions.none())
        except (TypeError, ValueError):
            await interaction.response.send_message("That emoji is not valid for this bot. Try a standard emoji or an installed custom emoji.", ephemeral=True)
            return
        await interaction.response.send_message("Button message published successfully.", ephemeral=True)
        await send_log("Button message published", f"{interaction.user} published **{label}** in {interaction.channel.mention}.\nDestination: {url}")

    return DiscordGateway(bot, asyncio.create_task(bot.start(settings.discord_bot_token)))
