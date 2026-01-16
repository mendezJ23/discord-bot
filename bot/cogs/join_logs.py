import discord
from discord.ext import commands
from datetime import datetime
from typing import Optional
import logging
import asyncio

logger = logging.getLogger("discord_bot")

# Throttle between API calls to avoid hitting Discord rate limits
THROTTLE = 0.35

class JoinLeaveLogger(commands.Cog):
    """Logs member join and leave events to #🚪│join-leave-logs."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def ensure_channel(self, guild: discord.Guild) -> Optional[discord.TextChannel]:
        """Ensure 🚪│join-leave-logs channel exists, creating if necessary."""
        channel = discord.utils.get(guild.text_channels, name="🚪│join-leave-logs")
        if not channel:
            try:
                logger.info(f"Creating 🚪│join-leave-logs channel in guild {guild.id}")
                channel = await guild.create_text_channel("🚪│join-leave-logs", reason="Created for join/leave logs")
                logger.info(f"Created 🚪│join-leave-logs channel in guild {guild.id}")
                await asyncio.sleep(THROTTLE)
            except discord.Forbidden:
                logger.error(f"Permission denied creating channel in guild {guild.id}")
                return None
            except Exception as e:
                logger.error(f"Failed to create 🚪│join-leave-logs channel in {guild.id}: {e}")
                return None
        return channel

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        """Log when a member joins the guild."""
        if member.bot:
            return
        guild = member.guild
        channel = await self.ensure_channel(guild)
        if not channel:
            logger.warning(f"Could not log join for {member} in {guild.id}")
            return
        ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        try:
            await channel.send(f"✅ **{member}** joined (ID: {member.id}) — {ts}")
        except discord.Forbidden:
            logger.error(f"Permission denied posting join log in {guild.id}")

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        """Log when a member leaves the guild."""
        if member.bot:
            return
        guild = member.guild
        channel = await self.ensure_channel(guild)
        if not channel:
            logger.warning(f"Could not log leave for {member} in {guild.id}")
            return
        ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        try:
            await channel.send(f"⛔ **{member}** left (ID: {member.id}) — {ts}")
        except discord.Forbidden:
            logger.error(f"Permission denied posting leave log in {guild.id}")


async def setup(bot: commands.Bot):
    await bot.add_cog(JoinLeaveLogger(bot))
