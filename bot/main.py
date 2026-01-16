import discord
from discord.ext import commands
from dotenv import load_dotenv
import os
import logging
import asyncio
import time
import functools
from config import BOT_PREFIX

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("discord_bot")

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN not found in environment variables")

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=BOT_PREFIX, intents=intents)

# Global guard: wrap Guild.create_text_channel to add logging and a small throttle
_orig_create_text_channel = discord.Guild.create_text_channel
_create_last: dict[int, float] = {}
_CREATE_THROTTLE = 0.35

async def _safe_create_text_channel(self, *args, **kwargs):
    try:
        guild_id = getattr(self, "id", None)
        name = args[0] if args else kwargs.get("name")
        logging.getLogger("discord_bot").info(f"[global] create_text_channel called for '{name}' in guild {guild_id}")
        # enforce minimal throttle per guild
        now = time.time()
        last = _create_last.get(guild_id)
        if last:
            wait = _CREATE_THROTTLE - (now - last)
            if wait > 0:
                await asyncio.sleep(wait)
        res = await _orig_create_text_channel(self, *args, **kwargs)
        _create_last[guild_id] = time.time()
        return res
    except Exception:
        # log and re-raise to preserve behavior
        logging.getLogger("discord_bot").exception("Error in global create_text_channel wrapper")
        raise

# Monkeypatch
discord.Guild.create_text_channel = _safe_create_text_channel

@bot.event
async def setup_hook() -> None:
    """Automatically load all cogs from the cogs directory."""
    cog_dir = "cogs"
    if not os.path.isdir(cog_dir):
        logger.error(f"Cogs directory '{cog_dir}' not found")
        return 
    
    for file in os.listdir(cog_dir):
        if file.endswith(".py") and not file.startswith("__"):
            cog_name = f"cogs.{file[:-3]}"
            try:
                await bot.load_extension(cog_name)
                logger.info(f"Loaded cog: {cog_name}")
            except commands.ExtensionError as e:
                logger.error(f"Failed to load cog {cog_name}: {e}")
            except Exception as e:
                logger.error(f"Unexpected error loading cog {cog_name}: {e}")

@bot.event
async def on_ready() -> None:
    """Log when the bot is ready and display guild information."""
    logger.info(f"Logged in as {bot.user} (ID: {bot.user.id})")
    logger.info(f"Connected to {len(bot.guilds)} guild(s)")
    # Log registered commands for debugging (helps verify commands like 'setup')
    try:
        registered = sorted({c.name for c in bot.commands if c.name})
        logger.info(f"Registered commands: {registered}")
    except Exception:
        logger.exception("Failed to enumerate registered commands")
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="Chilling with OgPirate"))
    
    # Send startup message to each guild
    for guild in bot.guilds:
        # Try to find commands channel first, then general
        commands_channel = discord.utils.get(guild.text_channels, name="commands")
        if commands_channel:
            try:
                await commands_channel.send("✅ Bot is online and ready!")
            except discord.Forbidden:
                logger.warning(f"Permission denied posting startup message in {guild.name}")
        else:
            general = discord.utils.get(guild.text_channels, name="general")
            if general:
                try:
                    await general.send("✅ Bot is online and ready!")
                except discord.Forbidden:
                    logger.warning(f"Permission denied posting startup message in {guild.name}")

@bot.event
async def on_error(event: str, *args, **kwargs) -> None:
    """Log unhandled exceptions in events."""
    logger.exception(f"Error in event {event}")

if __name__ == "__main__":
    bot.run(TOKEN)
