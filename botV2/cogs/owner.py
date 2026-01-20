import discord
from discord.ext import commands
import logging
from typing import Optional

logger = logging.getLogger("discord_bot")


class OwnerSelfCog(commands.Cog):
    """Allows players to move into a manor and become an owner when they
    have write permission in that manor.
    """

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.command(name="movein")
    async def movein(self, ctx: commands.Context, *, token: Optional[str] = None) -> None:
        """Claim ownership of a manor.

        Usage:
        - `.movein` when used inside a manor channel -> claim that manor (you must have send permission there)
        - `.movein <manor>` -> claim the named manor (you must have send permission in that manor)
        """
        guild = ctx.guild
        if not guild:
            return

        manors_cog = self.bot.get_cog("ManorsCog")
        if not manors_cog:
            await __import__("mystery").mystery_send(ctx, "❌ Manors cog not loaded on the bot")
            return

        # resolve target channel
        ch: Optional[discord.TextChannel] = None
        if not token:
            # must be used inside a manor channel
            if not ctx.channel.category or ctx.channel.category.name != "MANORS":
                await __import__("mystery").mystery_send(ctx, "❌ Use `.movein` inside a manor channel or provide a manor name/mention")
                return
            ch = ctx.channel
        else:
            ch = manors_cog._resolve_manor(guild, token.strip())
            if not ch:
                await __import__("mystery").mystery_send(ctx, "❌ Manor not found")
                return

        # check write permission in that manor
        perms = ch.permissions_for(ctx.author)
        if not perms.send_messages:
            await __import__("mystery").mystery_send(ctx, "❌ You need write permission in that manor to claim ownership. Be present in the manor or ask an overseer to grant you send permission.")
            return

        # add as owner
        try:
            manors_cog._add_owner(ctx.author.id, ch.name)
            await __import__("mystery").mystery_send(ctx, f"✅ You are now an owner of {ch.mention}")
        except Exception as e:
            logger.error(f"Error adding owner for {ctx.author}: {e}")
            await __import__("mystery").mystery_send(ctx, f"❌ Failed to add owner: {e}")
            return

        # log to log-visits (best-effort)
        try:
            log_ch = discord.utils.get(guild.text_channels, name="log-visits")
            if log_ch:
                await log_ch.send(f"**Owner Added:** {ctx.author.display_name} (ID: {ctx.author.id}) | **Manor:** {ch.mention} | **By:** self (movein)")
        except Exception:
            pass


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(OwnerSelfCog(bot))
import logging
from discord.ext import commands

logger = logging.getLogger("discord_bot")


async def setup(bot: commands.Bot) -> None:
    logger.info("Loaded placeholder cog: cogs.owner")
