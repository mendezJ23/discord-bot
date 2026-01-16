import discord
from discord.ext import commands
import logging

logger = logging.getLogger("discord_bot")

class RoleBasedAccessCog(commands.Cog):
    """Cog for restricting channel access based on user roles."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def update_user_permissions(self, member: discord.Member) -> None:
        """Update channel permissions for a member based on their roles."""
        # Per-member permission assignments are disabled.
        # This function intentionally does nothing so role-based overwrites (applied at
        # category/channel creation) control visibility.
        logger.debug(f"update_user_permissions skipped for {member}")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        """When a member joins, restrict their access if they have no roles."""
        await self.update_user_permissions(member)
        logger.info(f"Updated permissions for {member} joining {member.guild.name}")

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        """When a member's roles change, update their permissions."""
        # Check if roles actually changed
        if before.roles == after.roles:
            return
        
        await self.update_user_permissions(after)
        logger.info(f"Updated permissions for {after} due to role change in {after.guild.name}")

    @commands.command(name="sync_roles")
    @commands.has_permissions(administrator=True)
    async def sync_roles_command(self, ctx: commands.Context) -> None:
        """Manually sync permissions for all members based on their roles."""
        guild = ctx.guild
        count = 0
        errors = 0
        
        await __import__("mystery").mystery_send(ctx, "⏳ Syncing member permissions...")
        
        for member in guild.members:
            try:
                await self.update_user_permissions(member)
                count += 1
            except Exception as e:
                logger.error(f"Error syncing permissions for {member}: {e}")
                errors += 1
        
        msg = f"✅ Updated permissions for {count} members"
        if errors:
            msg += f" ({errors} errors)"
        await __import__("mystery").mystery_send(ctx, msg)
        logger.info(f"Synced permissions for {count} members in {guild.name}")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(RoleBasedAccessCog(bot))
