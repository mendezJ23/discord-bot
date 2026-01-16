import discord
from discord.ext import commands
import asyncio
import logging
import os
import random
import config

logger = logging.getLogger("discord_bot")

class HouseAdminCog(commands.Cog):
    """Admin commands for house and player management."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.command(name="deadrole")
    @commands.has_permissions(administrator=True)
    async def deadrole(self, ctx: commands.Context):
        """Remove all roles from members with write access to this channel (except admins), then assign 'Dead' role."""
        guild = ctx.guild
        channel = ctx.channel
        dead_role = discord.utils.get(guild.roles, name="Dead")
        if not dead_role:
            await ctx.send("❌ 'Dead' role not found.")
            return
        affected = []
        for member in channel.members:
            if member.bot or member.guild_permissions.administrator:
                continue
            perms = channel.permissions_for(member)
            if perms.send_messages:
                try:
                    await member.edit(roles=[], reason="Deadrole command used")
                    await member.add_roles(dead_role, reason="Marked as Dead")
                    affected.append(member.display_name)
                except Exception as e:
                    logger.warning(f"Could not update {member.display_name}: {e}")
        await ctx.send(f"☠️ Marked as Dead: {', '.join(affected) if affected else 'No members affected.'}")

    @commands.command(name="dead")
    @commands.has_permissions(administrator=True)
    async def dead(self, ctx: commands.Context):
        """List all players with write access to this channel, and make them and their sponsors exit all locations except their role channel (which is moved to DEAD RC)."""
        guild = ctx.guild
        channel = ctx.channel
        role_channels_cat = discord.utils.get(guild.categories, name="ROLES")
        dead_rc_cat = discord.utils.get(guild.categories, name="DEAD RC")
        if not role_channels_cat or not dead_rc_cat:
            await ctx.send("❌ ROLES or DEAD RC category not found.")
            return
        houses_cat = discord.utils.get(guild.categories, name="MANORS")
        private_cat = discord.utils.get(guild.categories, name="PRIVATE CHANNELS")

        affected = []
        processed = set()

        # helper to clear member from houses and private channels (but not their role channel)
        async def _clear_member_locations(member: discord.Member) -> None:
            # remove access from houses
            if houses_cat:
                for h in houses_cat.text_channels:
                    try:
                        ow = h.overwrites.get(member)
                        if ow and getattr(ow, "view_channel", False):
                            await h.set_permissions(member, overwrite=None, reason="Removed due to death")
                    except Exception as e:
                        logger.warning(f"Could not remove {member} from manor {h.name}: {e}")
            # remove access from private channels
            if private_cat:
                for p in private_cat.text_channels:
                    try:
                        ow = p.overwrites.get(member)
                        if ow and getattr(ow, "view_channel", False):
                            await p.set_permissions(member, overwrite=None, reason="Removed due to death")
                    except Exception as e:
                        logger.warning(f"Could not remove {member} from private {p.name}: {e}")

        # Get RoleChannelsCog for sponsor lookup if available
        role_cog = self.bot.get_cog("RoleChannelsCog")

        for member in list(channel.members):
            if member.bot or member.guild_permissions.administrator:
                continue
            perms = channel.permissions_for(member)
            if not perms.send_messages:
                continue

            # Move the member's role channel to DEAD RC if found
            moved_role_channel = None
            try:
                for ch in role_channels_cat.text_channels:
                    ow = ch.overwrites.get(member)
                    if ow and getattr(ow, "view_channel", False):
                        try:
                            await ch.edit(category=dead_rc_cat, reason="Moved to DEAD RC by dead command")
                            moved_role_channel = ch
                            logger.info(f"Moved role channel {ch.name} for {member} to DEAD RC")
                        except Exception as e:
                            logger.warning(f"Could not move role channel {ch.name} for {member}: {e}")
                        break
            except Exception:
                pass

            # Clear member from houses and private channels
            await _clear_member_locations(member)

            affected.append(member.display_name)
            processed.add(member.id)

            # Also process sponsors if any (support multiple sponsors)
            try:
                sponsors = []
                if role_cog and hasattr(role_cog, "find_sponsor_for_member"):
                    try:
                        sponsors = await role_cog.find_sponsor_for_member(guild, member) or []
                    except Exception:
                        sponsors = []

                for sponsor in sponsors:
                    try:
                        if not sponsor or sponsor.id in processed or sponsor.bot or sponsor.guild_permissions.administrator:
                            continue
                        # move sponsor's role channel to DEAD RC
                        try:
                            for ch in role_channels_cat.text_channels:
                                ow = ch.overwrites.get(sponsor)
                                if ow and getattr(ow, "view_channel", False):
                                    try:
                                        await ch.edit(category=dead_rc_cat, reason="Moved sponsor to DEAD RC by dead command")
                                        logger.info(f"Moved sponsor role channel {ch.name} for {sponsor} to DEAD RC")
                                    except Exception as e:
                                        logger.warning(f"Could not move sponsor role channel {ch.name} for {sponsor}: {e}")
                                    break
                        except Exception:
                            pass
                        # clear sponsor locations
                        await _clear_member_locations(sponsor)
                        affected.append(f"{sponsor.display_name} (sponsor)")
                        processed.add(sponsor.id)
                    except Exception as e:
                        logger.warning(f"Error processing sponsor {sponsor} for {member}: {e}")
            except Exception as e:
                logger.warning(f"Error retrieving sponsors for {member}: {e}")

        await ctx.send(f"💀 Dead players and sponsors processed: {', '.join(affected) if affected else 'No members affected.'}")

    @commands.command(name="destroy")
    @commands.has_permissions(administrator=True)
    async def destroy(self, ctx: commands.Context):
        """Make every player with write access to this channel leave it with a narration, then move the channel to INACCESSIBLE HOUSES. Announce in #announcements."""
        guild = ctx.guild
        channel = ctx.channel
        inaccessible_cat = discord.utils.get(guild.categories, name="INACCESSIBLE MANORS")
        announcements = discord.utils.get(guild.text_channels, name="❗│announcements")
        if not inaccessible_cat or not announcements:
            await ctx.send("❌ INACCESSIBLE MANORS category or #announcements not found.")
            return
        affected = []
        for member in channel.members:
            if member.bot or member.guild_permissions.administrator:
                continue
            perms = channel.permissions_for(member)
            if perms.send_messages:
                try:
                    await channel.set_permissions(member, overwrite=None, reason="Manor destroyed")
                    await channel.send(f"{member.mention} was forced to leave the manor as it was destroyed!")
                    affected.append(member.display_name)
                except Exception as e:
                    logger.warning(f"Could not remove {member.display_name}: {e}")
        await channel.edit(category=inaccessible_cat, reason="Manor destroyed")
        # choose a random destroyed gif from config directory if available
        gif_path = None
        try:
            gif_dir = config.GIFS_DIRECTORY.get("destroy")
            if gif_dir:
                if not os.path.isabs(gif_dir):
                    base = os.path.dirname(os.path.dirname(__file__))
                    gif_dir = os.path.normpath(os.path.join(base, gif_dir))
                if os.path.isdir(gif_dir):
                    files = [f for f in os.listdir(gif_dir) if f.lower().endswith(('.gif','.png','.jpg','.jpeg','mp4'))]
                    if files:
                        gif_path = os.path.join(gif_dir, random.choice(files))
        except Exception:
            gif_path = None

        # fallback to URL if no local file
        gif_url = None
        if not gif_path:
            gif_url = config.NIGHT_GIF_URL if hasattr(config, 'NIGHT_GIF_URL') else "https://media.giphy.com/media/3o6Zt481isNVuQI1l6/giphy.gif"

        embed = discord.Embed(title=f"🏰 Manor {channel.name} was destroyed!")
        is_local = False
        attachment_name = None
        if gif_path and os.path.isfile(gif_path):
            is_local = True
            attachment_name = os.path.basename(gif_path)
            embed.set_image(url=f"attachment://{attachment_name}")
        else:
            embed.set_image(url=gif_url)

        try:
            if is_local:
                await announcements.send(embed=embed, file=discord.File(gif_path))
            else:
                await announcements.send(embed=embed)
        except Exception:
            await announcements.send(f"🏰 Manor {channel.name} was destroyed!\n{gif_url}")
        await ctx.send(f"🏰 Manor destroyed and moved to INACCESSIBLE MANORS. Players removed: {', '.join(affected) if affected else 'None.'}")

    @commands.command(name="rebuild")
    @commands.has_permissions(administrator=True)
    async def rebuild(self, ctx: commands.Context):
        """Move this channel to the HOUSES category and announce rebuild in #announcements."""
        guild = ctx.guild
        channel = ctx.channel
        houses_cat = discord.utils.get(guild.categories, name="MANORS")
        announcements = discord.utils.get(guild.text_channels, name="❗│announcements")
        if not houses_cat or not announcements:
            await ctx.send("❌ MANORS category or #announcements not found.")
            return
        await channel.edit(category=houses_cat, reason="Manor rebuilt")
        # choose a random rebuild gif from config directory if available
        gif_path = None
        try:
            gif_dir = config.GIFS_DIRECTORY.get("rebuild")
            if gif_dir:
                if not os.path.isabs(gif_dir):
                    base = os.path.dirname(os.path.dirname(__file__))
                    gif_dir = os.path.normpath(os.path.join(base, gif_dir))
                if os.path.isdir(gif_dir):
                    files = [f for f in os.listdir(gif_dir) if f.lower().endswith(('.gif','.png','.jpg','.jpeg','mp4'))]
                    if files:
                        gif_path = os.path.join(gif_dir, random.choice(files))
        except Exception:
            gif_path = None

        # fallback to URL if no local file
        gif_url = None
        if not gif_path:
            gif_url = config.DAY_GIF_URL if hasattr(config, 'DAY_GIF_URL') else "https://media.giphy.com/media/3o6Zt481isNVuQI1l6/giphy.gif"

        embed = discord.Embed(title=f"🏰 Manor {channel.name} was rebuilt!")
        is_local = False
        attachment_name = None
        if gif_path and os.path.isfile(gif_path):
            is_local = True
            attachment_name = os.path.basename(gif_path)
            embed.set_image(url=f"attachment://{attachment_name}")
        else:
            embed.set_image(url=gif_url)

        try:
            if is_local:
                await announcements.send(embed=embed, file=discord.File(gif_path))
            else:
                await announcements.send(embed=embed)
        except Exception:
            await announcements.send(f"🏰 Manor {channel.name} was rebuilt!\n{gif_url}")
        await ctx.send(f"🏰 Manor rebuilt and moved to MANORS category.")

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(HouseAdminCog(bot))
