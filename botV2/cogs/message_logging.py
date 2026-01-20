import discord
from discord.ext import commands
import logging
from datetime import datetime
from typing import Optional
import asyncio

logger = logging.getLogger("discord_bot")

# Throttle between API calls to avoid hitting Discord rate limits
THROTTLE = 0.35

class MessageLoggingCog(commands.Cog):
    """Logs deleted and edited messages to #✏️│edit-and-del-logs."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def ensure_logs_channel(self, guild: discord.Guild) -> Optional[discord.TextChannel]:
        """Ensure ✏️│edit-and-del-logs channel exists."""
        channel = discord.utils.get(guild.text_channels, name="✏️│edit-and-del-logs")
        if not channel:
            try:
                logger.info(f"Creating edit-and-del-logs channel in guild {guild.id}")
                channel = await guild.create_text_channel(
                    "✏️│edit-and-del-logs",
                    reason="Created for message edit/delete logging"
                )
                logger.info(f"Created ✏️│edit-and-del-logs channel in {guild.id}")
                await asyncio.sleep(THROTTLE)
            except discord.Forbidden:
                logger.error(f"Permission denied creating channel in {guild.id}")
                return None
            except Exception as e:
                logger.error(f"Failed to create ✏️│edit-and-del-logs in {guild.id}: {e}")
                return None
        return channel

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message) -> None:
        """Log deleted messages."""
        # Ignore bot messages and messages without content
        if message.author.bot or not message.content:
            return

        guild = message.guild
        if not guild:
            return

        channel = await self.ensure_logs_channel(guild)
        if not channel:
            return

        ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        
        embed = discord.Embed(
            title="🗑 Message Deleted",
            color=discord.Color.red(),
            description=message.content[:1024],  # Limit to 1024 chars
            timestamp=datetime.utcnow()
        )
        embed.add_field(name="Author", value=f"{message.author} (ID: {message.author.id})", inline=False)
        embed.add_field(name="Channel", value=f"{message.channel.mention}", inline=False)
        
        if message.attachments:
            attachments = ", ".join([a.filename for a in message.attachments])
            embed.add_field(name="Attachments", value=attachments, inline=False)

        try:
            await channel.send(embed=embed)
        except discord.Forbidden:
            logger.error(f"Permission denied posting delete log in {guild.id}")

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message) -> None:
        """Log edited messages."""
        # Ignore bot messages
        if before.author.bot:
            return

        # Ignore if content didn't change (e.g., embeds were added/removed)
        if before.content == after.content:
            return

        guild = before.guild
        if not guild:
            return

        channel = await self.ensure_logs_channel(guild)
        if not channel:
            return

        embed = discord.Embed(
            title="✏️ Message Edited",
            color=discord.Color.orange(),
            timestamp=datetime.utcnow()
        )
        embed.add_field(name="Author", value=f"{before.author} (ID: {before.author.id})", inline=False)
        embed.add_field(name="Channel", value=f"{before.channel.mention}", inline=False)
        
        # Show before and after content
        embed.add_field(
            name="Before",
            value=before.content[:512] or "(no content)",
            inline=False
        )
        embed.add_field(
            name="After",
            value=after.content[:512] or "(no content)",
            inline=False
        )
        
        embed.add_field(name="Jump to message", value=f"[Click here]({after.jump_url})", inline=False)

        try:
            await channel.send(embed=embed)
        except discord.Forbidden:
            logger.error(f"Permission denied posting edit log in {guild.id}")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MessageLoggingCog(bot))
