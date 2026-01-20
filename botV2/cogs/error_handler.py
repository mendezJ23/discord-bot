import discord
from discord.ext import commands
import logging
import os

# Ensure logs directory exists
os.makedirs("logs", exist_ok=True)

# Create a logger
logger = logging.getLogger("discord_bot")
logger.setLevel(logging.INFO)

file_handler = logging.FileHandler(
    filename="logs/errors.log", encoding="utf-8", mode="a"
)
file_handler.setFormatter(
    logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
)
logger.addHandler(file_handler)
# Dedicated logger for benign command-not-found entries (avoid spamming error logs/console)
commands_logger = logging.getLogger("discord_bot.commands")
commands_logger.setLevel(logging.INFO)
cmd_file = logging.FileHandler(filename="logs/commands.log", encoding="utf-8", mode="a")
cmd_file.setFormatter(
    logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
)
commands_logger.addHandler(cmd_file)

class ErrorHandlerCog(commands.Cog):
    """Centralized command error handler with logging and user-friendly messages."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        # Log the error to file with full context
        # Avoid calling str() on ctx.command (some Command implementations may
        # expose attributes that raise when accessed). Use the safe name.
        # Safely derive a command name without calling potentially unsafe __str__/__repr__
        cmd_name = None
        try:
            if ctx.command is not None:
                cmd_name = getattr(ctx.command, "name", None)
        except Exception:
            cmd_name = None
        if not cmd_name:
            try:
                if ctx.command is not None:
                    cmd_name = getattr(ctx.command, "qualified_name", None)
            except Exception:
                cmd_name = None
        if not cmd_name:
            try:
                cmd_name = ctx.command.__class__.__name__
            except Exception:
                cmd_name = "<unknown>"

        # Safely stringify actor and guild for logging
        try:
            actor = f"{ctx.author} ({getattr(ctx.author, 'id', 'unknown')})"
        except Exception:
            actor = str(getattr(ctx, 'author', '<unknown>'))
        try:
            guild_str = str(ctx.guild)
        except Exception:
            guild_str = '<unknown>'

        # Log CommandNotFound separately at INFO to avoid filling error logs/console
        if isinstance(error, commands.CommandNotFound):
            try:
                commands_logger.info(f"Unknown command invoked: '{getattr(ctx.message, 'content', '<no content>')}' by {actor} in {guild_str}")
            except Exception:
                # fallback to main logger at debug level
                logger.debug(f"Unknown command invoked and failed to log properly: {error}")
        else:
            logger.error(
                f"Error in command '{cmd_name}' invoked by {actor} in {guild_str}: {error}",
                exc_info=True
            )

        # User-friendly feedback
        if isinstance(error, commands.CommandNotFound):
            await __import__("mystery").mystery_send(ctx, "⚠ Command not found.")
        elif isinstance(error, commands.MissingRequiredArgument):
            usage = getattr(ctx.command, "usage", "") or ""
            await __import__("mystery").mystery_send(ctx, f"⚠ Missing argument. Usage: `{ctx.prefix}{cmd_name} {usage}`")
        elif isinstance(error, commands.BadArgument):
            usage = getattr(ctx.command, "usage", "") or ""
            await __import__("mystery").mystery_send(ctx, f"⚠ Invalid argument. Usage: `{ctx.prefix}{cmd_name} {usage}`")
        elif isinstance(error, commands.MissingPermissions):
            await __import__("mystery").mystery_send(ctx, "❌ You do not have permission to use this command.")
        elif isinstance(error, commands.BotMissingPermissions) or isinstance(error, discord.Forbidden):
            await __import__("mystery").mystery_send(ctx, "❌ I do not have the required permissions to execute this command.")
        else:
            # Fallback for unexpected errors
            try:
                await __import__("mystery").mystery_send(ctx, "❌ An unexpected error occurred. The staff has been notified.")
            except (discord.Forbidden, discord.NotFound):
                # If we can't send to the channel, try DM or just log it
                logger.warning(f"Could not send error message in {ctx.channel}")
                try:
                    await ctx.author.send("❌ An unexpected error occurred. The staff has been notified.")
                except discord.Forbidden:
                    logger.warning(f"Could not DM error notification to {ctx.author}")

# Loader
async def setup(bot):
    await bot.add_cog(ErrorHandlerCog(bot))
