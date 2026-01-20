import discord
from discord.ext import commands
import config
import logging
from typing import Optional

logger = logging.getLogger("discord_bot")


class ChannelSetCog(commands.Cog):
    """Set a different channel to act as a canonical server channel (rules, vote-count, etc.).

    Usage:
    - .channelset rules #new-rules
    - .channelset vote-count (when run inside the desired channel)
    This will rename/move the target channel to the canonical name defined in
    `config.SERVER_STRUCTURE` and then reapply the server permissions via
    `ServerSetupCog.set_channel_permissions` if that cog is loaded.
    """

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.command(name="channelset")
    @commands.has_permissions(administrator=True)
    async def channelset(self, ctx: commands.Context, name: str, channel: Optional[discord.TextChannel] = None) -> None:
        """Assign `channel` (or current channel) to the canonical `name` token."""
        guild = ctx.guild
        if channel is None:
            target = ctx.channel
        else:
            target = channel

        token = name.strip().lower()

        # find canonical channel name and category from config
        canonical_name = None
        canonical_cat = None
        for cat_name, channels in config.SERVER_STRUCTURE.items():
            for ch_name in channels:
                token_part = ch_name.split("│", 1)[1].strip().lower() if "│" in ch_name else ch_name.strip().lower()
                if token == token_part or token in token_part or token_part in token:
                    canonical_name = ch_name
                    canonical_cat = cat_name
                    break
            if canonical_name:
                break

        if not canonical_name:
            await __import__("mystery").mystery_send(ctx, f"❌ Could not find a canonical channel for '{name}' in config.SERVER_STRUCTURE.")
            return

        # check for existing channel with canonical name (other than target)
        existing = discord.utils.get(guild.text_channels, name=canonical_name)
        if existing and existing.id != target.id:
            await __import__("mystery").mystery_send(ctx, f"❌ A channel named '{canonical_name}' already exists ({existing.mention}). Delete or rename it before using this command.")
            return

        # move to canonical category if exists
        try:
            cat_obj = discord.utils.get(guild.categories, name=canonical_cat) if canonical_cat else None
            await target.edit(name=canonical_name, category=cat_obj, reason=f"Set as canonical {token} via channelset by {ctx.author}")
        except Exception as e:
            logger.warning(f"Could not rename/move channel: {e}")
            await __import__("mystery").mystery_send(ctx, f"❌ Failed to rename/move channel: {e}")
            return

        # Reapply server setup permissions and initialize canonical content if ServerSetupCog is loaded
        try:
            setup_cog = self.bot.get_cog("ServerSetupCog")
            if setup_cog:
                if hasattr(setup_cog, "set_channel_permissions"):
                    await setup_cog.set_channel_permissions(guild)
                # try running initialization helper if available
                if hasattr(setup_cog, "initialize_canonical_channel"):
                    try:
                        await setup_cog.initialize_canonical_channel(guild, token, target)
                    except Exception:
                        # older setup cog may not have helper; ignore
                        pass
        except Exception as e:
            logger.warning(f"Could not reapply permissions via ServerSetupCog: {e}")

        await __import__("mystery").mystery_send(ctx, f"✅ {target.mention} is now set as '{canonical_name}' in category '{canonical_cat or 'unknown'}'. Permissions reapplied.")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ChannelSetCog(bot))
