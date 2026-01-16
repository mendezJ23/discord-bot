import re
import io
import asyncio
import logging
from typing import Optional

import discord
from discord.ext import commands

logger = logging.getLogger("discord_bot")
THROTTLE = 0.25


class SimpleLog(commands.Cog):
    """Simple `.log` command that collects a message range, writes a text file, and sends it to the current channel."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    def _parse(self, raw: str) -> Optional[tuple[int, int]]:
        blocks = re.findall(r"\{([^}]*)\}", raw)
        if len(blocks) >= 2:
            a = blocks[0].strip()
            b = blocks[1].strip()
        else:
            parts = raw.split()
            if len(parts) < 2:
                return None
            def s(t: str) -> str:
                return t.strip().strip("{}").strip()
            a = s(parts[0]); b = s(parts[1])
        try:
            return int(a), int(b)
        except Exception:
            return None

    @commands.command(name="log")
    async def log_range(self, ctx: commands.Context, *, _raw: str = "") -> None:
        raw = ctx.message.content
        try:
            prefix = ctx.prefix
            cmd = ctx.invoked_with
            raw = raw.split(prefix + cmd, 1)[1].strip()
        except Exception:
            raw = _raw or raw

        parsed = self._parse(raw)
        if not parsed:
            await __import__("mystery").mystery_send(ctx, "❌ Usage: .log {start_message_id} {end_message_id}")
            return

        start_id, end_id = parsed
        channel = ctx.channel

        try:
            start_msg = await channel.fetch_message(start_id)
            end_msg = await channel.fetch_message(end_id)
        except Exception as e:
            await __import__("mystery").mystery_send(ctx, f"❌ Could not fetch boundary messages: {e}")
            return

        if start_msg.id > end_msg.id:
            start_msg, end_msg = end_msg, start_msg

        collected = []
        try:
            async for m in channel.history(limit=None, after=start_msg, before=end_msg):
                collected.append(m)
        except Exception as e:
            await __import__("mystery").mystery_send(ctx, f"❌ Could not fetch history: {e}")
            return

        messages = [start_msg] + list(reversed(collected)) + [end_msg]

        # build text content
        parts = []
        for m in messages:
            header = f"{m.author.display_name} ({m.author.id}) at {m.created_at.isoformat()}"
            content = m.content or ""
            if m.attachments:
                att = "\n".join(a.url for a in m.attachments)
                content = f"{content}\n{att}" if content else att
            parts.append(header)
            parts.append(content)
            parts.append("-" * 40)

        final = "\n".join(parts)

        # send as a text file attachment
        try:
            fp = io.BytesIO(final.encode("utf-8"))
            filename = f"log_{start_id}_{end_id}.txt"
            fp.seek(0)
            discord_file = discord.File(fp, filename=filename)
            await channel.send(file=discord_file)
        except Exception as e:
            logger.warning(f"Failed to send log file: {e}")
            await channel.send(f"❌ Failed to send log file: {e}")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(SimpleLog(bot))
