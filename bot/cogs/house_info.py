import logging
from discord.ext import commands

logger = logging.getLogger("discord_bot")


async def setup(bot: commands.Bot) -> None:
    logger.info("Loaded placeholder cog: cogs.house_info")
