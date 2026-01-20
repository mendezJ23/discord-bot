import re
import os
import discord
from discord.ext import commands
from typing import Optional, Union
import config


class NarrateCog(commands.Cog):
    """Send a narration/message into another channel via the bot.

    Usage:
    - .narrate #channel message
    - .narrate channel-name message
    - .narrate category/channel-name message
    - .narrate 123456789012345678 message
    If channel is omitted the command sends in the invoking channel.
    Requires `manage_channels` permission.
    """

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.command(name="narrate")
    @commands.has_permissions(manage_channels=True)
    async def narrate(self, ctx: commands.Context, channel: Optional[Union[discord.TextChannel, str]] = None, *, message: str = "") -> None:
        """Send `message` into `channel`. If channel omitted, use current channel."""
        # resolve target channel
        target: Optional[discord.TextChannel]
        guild = ctx.guild
        if isinstance(channel, discord.TextChannel):
            target = channel
        else:
            target = await self._resolve_channel(ctx, channel)

        if not target:
            await __import__("mystery").mystery_send(ctx, "❌ Could not resolve target channel.")
            return

        if not message:
            await __import__("mystery").mystery_send(ctx, "❌ No message provided.")
            return

        try:
            await target.send(message)
            await __import__("mystery").mystery_send(ctx, f"✅ Sent narration to {target.mention}.")
        except Exception as e:
            await __import__("mystery").mystery_send(ctx, f"❌ Failed to send message: {e}")

    async def _resolve_channel(self, ctx: commands.Context, channel_arg: Optional[str]) -> Optional[discord.TextChannel]:
        """Resolve a channel from a string (mention, id, name, or config path)."""
        guild = ctx.guild
        if channel_arg is None:
            return ctx.channel

        # mention like <#123>
        m = re.match(r"^<#!?(\d+)>$", channel_arg) or re.match(r"^<#(\d+)>$", channel_arg)
        if m:
            ch = guild.get_channel(int(m.group(1)))
            if isinstance(ch, discord.TextChannel):
                return ch

        # numeric id
        if channel_arg.isdigit():
            ch = guild.get_channel(int(channel_arg))
            if isinstance(ch, discord.TextChannel):
                return ch

        # path like CATEGORY/chan
        if "/" in channel_arg:
            cat_part, chan_part = channel_arg.split("/", 1)
            for cat in guild.categories:
                try:
                    if cat.name.lower() == cat_part.lower():
                        for ch in cat.text_channels:
                            if ch.name.lower() == chan_part.lower() or chan_part.lower() in ch.name.lower():
                                return ch
                except Exception:
                    continue

        # try config.SERVER_STRUCTURE tokens
        name = channel_arg.lower()
        for key, items in config.SERVER_STRUCTURE.items():
            for label in items:
                token = label.split("│", 1)[1].strip().lower() if "│" in label else label.strip().lower()
                if token == name or name in token:
                    for ch in guild.text_channels:
                        if ch.name.lower() == token or token in ch.name.lower():
                            return ch

        # fallback: direct match or substring in channel names
        for ch in guild.text_channels:
            if ch.name.lower() == name or name in ch.name.lower():
                return ch

        return None


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(NarrateCog(bot))
