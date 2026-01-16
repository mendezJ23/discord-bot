from discord.ext import commands
import os
import logging
from typing import Dict

logger = logging.getLogger("discord_bot")

class AdminCog(commands.Cog):
    """Cog for dynamic bot management: load, unload, reload, and list cogs."""

    PROTECTED_COGS = ["cogs.admin"]

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    def cog_map(self) -> Dict[str, str]:
        """Create a mapping of cog names to their full module paths."""
        return {c.split(".")[-1]: c for c in self.bot.extensions.keys()}
    
    @commands.command(name="reload")
    @commands.has_permissions(administrator=True)
    async def reload_cog(self, ctx: commands.Context, name: str) -> None:
        mapping = self.cog_map()

        if name.lower() == "all":
            reloaded, failed = [], []
            for simple, full in mapping.items():
                if full in self.PROTECTED_COGS:
                    continue
                try:
                    await self.bot.reload_extension(full)
                    reloaded.append(simple)
                except Exception as e:
                    failed.append(f"{simple}: {e}")

            msg = []
            if reloaded:
                msg.append(f"♻ Reloaded: {', '.join(reloaded)}")
            if failed:
                msg.append(f"❌ Failed:\n" + "\n".join(failed))
            if not msg:
                msg.append("No cogs were reloaded.")
            return await __import__("mystery").mystery_send(ctx, "\n".join(msg))

        if name not in mapping:
            return await __import__("mystery").mystery_send(ctx, f"❌ Cog `{name}` not found.")

        full = mapping[name]
        if full in self.PROTECTED_COGS:
            return await __import__("mystery").mystery_send(ctx, f"❌ Cog `{name}` is protected.")

        try:
            await self.bot.reload_extension(full)
            await __import__("mystery").mystery_send(ctx, f"♻ Reloaded `{name}` successfully.")
        except Exception as e:
            await __import__("mystery").mystery_send(ctx, f"❌ Reload failed for `{name}`:\n{e}")

    @commands.command(name="unload")
    @commands.has_permissions(administrator=True)
    async def unload_cog(self, ctx: commands.Context, name: str) -> None:
        mapping = self.cog_map()

        if name not in mapping:
            return await __import__("mystery").mystery_send(ctx, f"❌ Cog `{name}` not found.")

        full = mapping[name]
        if full in self.PROTECTED_COGS:
            return await __import__("mystery").mystery_send(ctx, f"❌ Cog `{name}` is protected.")

        try:
            await self.bot.unload_extension(full)
            await __import__("mystery").mystery_send(ctx, f"🗑 Unloaded `{name}` successfully.")
        except Exception as e:
            await __import__("mystery").mystery_send(ctx, f"❌ Unload failed for `{name}`:\n{e}")

    @commands.command(name="load")
    @commands.has_permissions(administrator=True)
    async def load_cog(self, ctx: commands.Context, name: str) -> None:
        full = f"cogs.{name}"
        if full in self.bot.extensions:
            return await __import__("mystery").mystery_send(ctx, f"⚠ Cog `{name}` is already loaded.")

        try:
            await self.bot.load_extension(full)
            await __import__("mystery").mystery_send(ctx, f"📥 Loaded `{name}` successfully.")
        except Exception as e:
            await __import__("mystery").mystery_send(ctx, f"❌ Load failed for `{name}`:\n{e}")
    @commands.group(name="cogs", invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    async def list_cogs(self, ctx: commands.Context) -> None:
        """List all currently loaded cogs."""
        mapping = self.cog_map()
        if mapping:
            await __import__("mystery").mystery_send(ctx, f"🧩 Loaded cogs: {', '.join(sorted(mapping.keys()))}")
        else:
            await __import__("mystery").mystery_send(ctx, "No cogs loaded.")

    @list_cogs.command(name="available")
    @commands.has_permissions(administrator=True)
    async def cogs_available(self, ctx: commands.Context) -> None:
        """List all cogs in the folder that are not currently loaded."""
        loaded = set(self.bot.extensions.keys())
        available = []

        for file in os.listdir("cogs"):
            if file.endswith(".py") and not file.startswith("__"):
                cog_name = f"cogs.{file[:-3]}"
                if cog_name not in loaded:
                    available.append(file[:-3])

        if available:
            await __import__("mystery").mystery_send(ctx, f"📂 Available cogs to load: {', '.join(sorted(available))}")
        else:
            await __import__("mystery").mystery_send(ctx, "📂 No unloaded cogs found. All cogs are loaded.")


async def setup(bot):
    await bot.add_cog(AdminCog(bot))
