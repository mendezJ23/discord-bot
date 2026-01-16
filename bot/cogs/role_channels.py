import discord
from discord.ext import commands
import logging
import re
import asyncio
from typing import Optional, Union
import os
import random
import config

logger = logging.getLogger("discord_bot")

# Throttle between API calls to avoid hitting Discord rate limits
THROTTLE = 0.35


class RoleChannelsCog(commands.Cog):
    """Cog for assigning players with 'Alive' role to their own role channels."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.command(name="rc")
    @commands.has_permissions(administrator=True)
    async def assign_role_channels(self, ctx: commands.Context) -> None:
        guild = ctx.guild
        alive_role = discord.utils.get(guild.roles, name="Alive")
        if not alive_role:
            await __import__("mystery").mystery_send(ctx, "❌ 'Alive' role not found")
            return

        roles_category = discord.utils.get(guild.categories, name="ROLES")
        if not roles_category:
            await __import__("mystery").mystery_send(ctx, "❌ 'ROLES' category not found")
            return

        alive_members = [m for m in guild.members if alive_role in m.roles]
        if not alive_members:
            await __import__("mystery").mystery_send(ctx, "❌ No members with 'Alive' role found")
            return

        await __import__("mystery").mystery_send(ctx, f"⏳ Assigning {len(alive_members)} members to role channels...")

        existing_channels = list(roles_category.text_channels)
        if len(existing_channels) < len(alive_members):
            await __import__("mystery").mystery_send(ctx, f"❌ Not enough role channels exist. Found {len(existing_channels)}, need {len(alive_members)}")
            return

        assigned = 0
        errors = 0
        for idx, member in enumerate(alive_members):
            try:
                channel = existing_channels[idx]
                new_name = member.display_name.lower().replace(" ", "-")
                if channel.name != new_name:
                    await channel.edit(name=new_name, reason=f"Assigned to player {member.name}")
                    logger.info(f"Renamed channel to '{new_name}' for {member}")

                await channel.set_permissions(member, view_channel=True, send_messages=True, reason=f"Assigned to {member.name}")
                # Log assignment
                try:
                    log_ch = discord.utils.get(guild.text_channels, name="log-visits")
                    if log_ch:
                        await log_ch.send(f"**Move:** {member.display_name} (ID: {member.id}) | **By:** {ctx.author.display_name} (ID: {ctx.author.id}) | **To:** {channel.mention} | **Reason:** assign_role_channels")
                except Exception:
                    pass
                for other in alive_members:
                    if other != member:
                        try:
                            await channel.set_permissions(other, overwrite=None, reason="Removed member-specific overwrites (role channels)")
                        except Exception:
                            pass
                assigned += 1
                await asyncio.sleep(THROTTLE)
            except Exception as e:
                logger.error(f"Error assigning {member} to role channel: {e}")
                errors += 1

        msg = f"✅ Assigned {assigned}/{len(alive_members)} members to role channels"
        if errors:
            msg += f" ({errors} errors)"
        await __import__("mystery").mystery_send(ctx, msg)

    @commands.command(name="rcrefresh")
    @commands.has_permissions(administrator=True)
    async def refresh_role_channels(self, ctx: commands.Context) -> None:
        guild = ctx.guild
        alive_role = discord.utils.get(guild.roles, name="Alive")
        if not alive_role:
            await __import__("mystery").mystery_send(ctx, "❌ 'Alive' role not found")
            return

        roles_category = discord.utils.get(guild.categories, name="ROLES")
        if not roles_category:
            await __import__("mystery").mystery_send(ctx, "❌ 'ROLES' category not found")
            return

        alive_members = [m for m in guild.members if alive_role in m.roles]
        await __import__("mystery").mystery_send(ctx, f"⏳ Refreshing role channels for {len(alive_members)} members...")

        updated = 0
        errors = 0
        existing_channels = list(roles_category.text_channels)
        for channel in existing_channels:
            try:
                should_have_access = []
                for member in alive_members:
                    if member in channel.overwrites and channel.overwrites[member].view_channel is False:
                        continue
                    should_have_access.append(member)

                for member in alive_members:
                    if member not in should_have_access and member in channel.overwrites:
                        try:
                            await channel.set_permissions(member, overwrite=None, reason="Removed member-specific overwrites (role channels)")
                        except Exception as e:
                            logger.warning(f"Could not remove permissions for {member}: {e}")
                updated += 1
                await asyncio.sleep(THROTTLE)
            except Exception as e:
                logger.error(f"Error processing channel {channel.name}: {e}")
                errors += 1

        msg = f"✅ Refreshed {updated} role channels"
        if errors:
            msg += f" ({errors} errors)"
        await __import__("mystery").mystery_send(ctx, msg)

    def _get_house_number(self, house_channel: discord.TextChannel) -> str:
        """Extract manor number from channel name (e.g., 'manor-1' -> '1')."""
        import re
        match = re.search(r'manor-(\d+)', house_channel.name.lower())
        return match.group(1) if match else house_channel.name

    async def _send_narration(self, house_channel: discord.TextChannel, member: discord.Member) -> None:
        """Send a narration when a player joins a manor."""
        house_num = self._get_house_number(house_channel)
        narration = f"🏠 **{member.display_name}** has joined Manor {house_num}."
        try:
            await house_channel.send(narration)
        except Exception as e:
            logger.warning(f"Could not send narration in {house_channel.name}: {e}")

    async def find_sponsor_for_member(self, guild: discord.Guild, member: discord.Member) -> list:
        """Find all sponsors (members with the 'Sponsor' role) that have access
        to one of the role channels that the given player can view.

        Returns a list of discord.Member (may be empty).
        """
        roles_category = discord.utils.get(guild.categories, name="ROLES")
        if not roles_category:
            return []

        sponsor_role = discord.utils.get(guild.roles, name="Sponsor")
        sponsors = []

        for ch in roles_category.text_channels:
            try:
                # check effective permission for the member (covers role-based overwrites)
                if not ch.permissions_for(member).view_channel:
                    continue
            except Exception:
                continue

            for potential in guild.members:
                try:
                    if potential.id == member.id:
                        continue
                    if sponsor_role and sponsor_role in potential.roles and ch.permissions_for(potential).view_channel:
                        if potential not in sponsors:
                            sponsors.append(potential)
                except Exception:
                    continue

        return sponsors

    @commands.command(name="setupmanors")
    @commands.has_permissions(administrator=True)
    async def setup_manors(self, ctx: commands.Context) -> None:
        """Deprecated: use .manor setup instead."""
        await __import__("mystery").mystery_send(ctx, "ℹ️ Use `.manor setup` instead of `.setupmanors`.")
        # Forward to the new command for backwards compatibility
        await self.manor_setup(ctx)

    async def manor_setup(self, ctx: commands.Context) -> None:
        """Assign all Alive players to manors with narrations."""
        import random
        guild = ctx.guild
        alive_role = discord.utils.get(guild.roles, name="Alive")
        if not alive_role:
            await __import__("mystery").mystery_send(ctx, "❌ 'Alive' role not found")
            return

        alive_members = [m for m in guild.members if alive_role in m.roles]
        if not alive_members:
            await __import__("mystery").mystery_send(ctx, "❌ No members with 'Alive' role found")
            return

        manors_category = discord.utils.get(guild.categories, name="MANORS")
        if not manors_category:
            await __import__("mystery").mystery_send(ctx, "❌ 'MANORS' category not found")
            return

        house_channels = list(manors_category.text_channels)
        if not house_channels:
            await __import__("mystery").mystery_send(ctx, "❌ No manor channels found in MANORS category")
            return

        await __import__("mystery").mystery_send(ctx, f"⏳ Assigning {len(alive_members)} players to {len(house_channels)} manors...")

        assigned = 0
        errors = 0
        for idx, member in enumerate(alive_members):
            try:
                if idx < len(house_channels):
                    house_channel = house_channels[idx]
                else:
                    house_channel = random.choice(house_channels)

                for ch in house_channels:
                    if ch != house_channel:
                        try:
                            await ch.set_permissions(member, overwrite=None, reason="Removed member-specific overwrites (manor assignment)")
                        except Exception:
                            pass

                await house_channel.set_permissions(member, view_channel=True, send_messages=True, reason=f"Assigned to {house_channel.name}")
                logger.info(f"Assigned {member} to {house_channel.name}")

                # Send narration when player joins manor
                await self._send_narration(house_channel, member)

                # Log manor assignment
                try:
                    log_ch = discord.utils.get(guild.text_channels, name="log-visits")
                    if log_ch:
                        await log_ch.send(f"**Move:** {member.display_name} (ID: {member.id}) | **By:** {ctx.author.display_name} (ID: {ctx.author.id}) | **To:** {house_channel.mention} | **Reason:** manor setup")
                except Exception:
                    pass
                # make the player an owner of the manor if ManorsCog is loaded
                try:
                    manors_cog = self.bot.get_cog("ManorsCog")
                    if manors_cog and hasattr(manors_cog, "_add_owner"):
                        manors_cog._add_owner(member.id, house_channel.name)
                except Exception as e:
                    logger.warning(f"Could not add owner for {member}: {e}")

                # If this player has a sponsor assigned in their role channel,
                # also grant the sponsor access to the same manor so they follow.
                try:
                    sponsors = await self.find_sponsor_for_member(guild, member) or []
                    for sponsor in sponsors:
                        if not sponsor or sponsor.id == member.id:
                            continue
                        # remove sponsor from other manors
                        for ch in house_channels:
                            if ch != house_channel:
                                try:
                                    await ch.set_permissions(sponsor, overwrite=None, reason="Removed sponsor-specific overwrites (manor move)")
                                except Exception:
                                    pass
                        try:
                            await house_channel.set_permissions(sponsor, view_channel=True, send_messages=True, reason=f"Sponsor assigned to follow {member.display_name}")
                        except Exception:
                            pass
                except Exception:
                    pass

                assigned += 1
                await asyncio.sleep(THROTTLE)
            except Exception as e:
                logger.error(f"Error assigning {member} to manor: {e}")
                errors += 1

        msg = f"✅ Assigned {assigned}/{len(alive_members)} players to manors"
        if errors:
            msg += f" ({errors} errors)"
        await __import__("mystery").mystery_send(ctx, msg)

    @commands.command(name="addmanor")
    @commands.has_permissions(administrator=True)
    async def add_manor(self, ctx: commands.Context, *, name: str) -> None:
        guild = ctx.guild
        houses_category = discord.utils.get(guild.categories, name="MANORS")
        if not houses_category:
            await __import__("mystery").mystery_send(ctx, "❌ 'MANORS' category not found")
            return

        raw = name.strip()
        if raw.isdigit():
            channel_name = f"🏰│manor-{int(raw)}"
        else:
            low = raw.lower()
            if low.startswith("🏰│"):
                channel_name = low
            elif low.startswith("manor-"):
                channel_name = f"🏰│{low}"
            else:
                channel_name = f"🏰│{low}"

        if discord.utils.get(houses_category.text_channels, name=channel_name):
            await __import__("mystery").mystery_send(ctx, f"❌ Manor '{channel_name}' already exists")
            return

        try:
            logger.info(f"Creating manor channel {channel_name} in guild {guild.id}")
            ch = await guild.create_text_channel(name=channel_name, category=houses_category, reason=f"Added manor {channel_name}")
            logger.info(f"Created manor channel '{channel_name}'")
            await asyncio.sleep(THROTTLE)
            await __import__("mystery").mystery_send(ctx, f"✅ Manor '{channel_name}' created successfully")
        except Exception as e:
            logger.error(f"Error creating manor {channel_name}: {e}")
            await __import__("mystery").mystery_send(ctx, f"❌ Error creating manor: {e}")

    @commands.command(name="delmanor")
    @commands.has_permissions(administrator=True)
    async def delete_manor(self, ctx: commands.Context, *, target: str) -> None:
        guild = ctx.guild
        houses_category = discord.utils.get(guild.categories, name="MANORS")
        if not houses_category:
            await __import__("mystery").mystery_send(ctx, "❌ 'MANORS' category not found")
            return

        # prefer mention
        if ctx.message.channel_mentions:
            ch = ctx.message.channel_mentions[0]
            try:
                await ch.delete(reason=f"Deleted manor {ch.name}")
                await __import__("mystery").mystery_send(ctx, f"✅ {ch.name} deleted successfully")
            except Exception as e:
                logger.error(f"Error deleting manor '{ch.name}': {e}")
                await __import__("mystery").mystery_send(ctx, f"❌ Error deleting manor: {e}")
            return

        raw = target.strip()
        if raw.isdigit():
            channel_name = f"🏰│manor{int(raw)}"
        else:
            low = raw.lower()
            if low.startswith("🏰│"):
                channel_name = low
            elif low.startswith("manor-"):
                channel_name = f"🏰│{low}"
            else:
                channel_name = f"🏰│{low}"

        ch = discord.utils.get(houses_category.text_channels, name=channel_name)
        if not ch:
            for c in houses_category.text_channels:
                if c.name.lower() == raw.lower():
                    ch = c
                    break

        if not ch:
            await __import__("mystery").mystery_send(ctx, "❌ Manor not found")
            return

        try:
            await ch.delete(reason=f"Deleted manor {ch.name}")
            await __import__("mystery").mystery_send(ctx, f"✅ {ch.name} deleted successfully")
        except Exception as e:
            logger.error(f"Error deleting manor '{ch.name}': {e}")
            await __import__("mystery").mystery_send(ctx, f"❌ Error deleting manor: {e}")
    @commands.command(name="addrole")
    @commands.has_permissions(administrator=True)
    async def add_role_channel(self, ctx: commands.Context, *, name: str) -> None:
        guild = ctx.guild
        roles_category = discord.utils.get(guild.categories, name="ROLES")
        if not roles_category:
            await __import__("mystery").mystery_send(ctx, "❌ 'ROLES' category not found")
            return

        role_channel = discord.utils.get(roles_category.text_channels, name=name.lower())
        if role_channel:
            await __import__("mystery").mystery_send(ctx, f"❌ Role channel '{name}' already exists")
            return

        try:
            logger.info(f"Creating role channel {name.lower()} in guild {guild.id}")
            channel = await guild.create_text_channel(name=name.lower(), category=roles_category, reason=f"Added role channel {name}")
            logger.info(f"Created role channel '{name}'")
            await asyncio.sleep(THROTTLE)
            await __import__("mystery").mystery_send(ctx, f"✅ Role channel '{name}' created successfully")
        except Exception as e:
            logger.error(f"Error creating role channel '{name}': {e}")
            await __import__("mystery").mystery_send(ctx, f"❌ Error creating role channel: {e}")

    @commands.command(name="delrole")
    @commands.has_permissions(administrator=True)
    async def delete_role_channel(self, ctx: commands.Context, *, name: str) -> None:
        guild = ctx.guild
        roles_category = discord.utils.get(guild.categories, name="ROLES")
        if not roles_category:
            await __import__("mystery").mystery_send(ctx, "❌ 'ROLES' category not found")
            return

        role_channel = discord.utils.get(roles_category.text_channels, name=name.lower())
        if not role_channel:
            await __import__("mystery").mystery_send(ctx, f"❌ Role channel '{name}' not found")
            return

        alive_role = discord.utils.get(guild.roles, name="Alive")
        sponsor_role = discord.utils.get(guild.roles, name="Sponsor")

        removed = 0
        errors = 0
        try:
            for member, overwrite in role_channel.overwrites.items():
                if isinstance(member, discord.Member):
                    try:
                        if alive_role and alive_role in member.roles:
                            await member.remove_roles(alive_role)
                            removed += 1
                        if sponsor_role and sponsor_role in member.roles:
                            await member.remove_roles(sponsor_role)
                            removed += 1
                        logger.info(f"Removed roles from {member} due to role channel deletion")
                    except Exception as e:
                        logger.warning(f"Could not remove roles from {member}: {e}")
                        errors += 1

            await role_channel.delete(reason=f"Deleted role channel {name}")
            logger.info(f"Deleted role channel '{name}'")
            msg = f"✅ Role channel '{name}' deleted successfully"
            if removed > 0:
                msg += f" (removed roles from {removed} players"
                if errors > 0:
                    msg += f", {errors} errors"
                msg += ")"
            await __import__("mystery").mystery_send(ctx, msg)
        except Exception as e:
            logger.error(f"Error deleting role channel '{name}': {e}")
            await __import__("mystery").mystery_send(ctx, f"❌ Error deleting role channel: {e}")

    @commands.command(name="public")
    @commands.has_permissions(manage_channels=True)
    async def make_public(self, ctx: commands.Context, channel: discord.TextChannel = None) -> None:
        """Make a channel visible to everyone but prevent non-inside players from writing.

        Default: operate on `ctx.channel` if no `channel` provided.
        """
        guild = ctx.guild
        # resolve channel from string path/name/mention or default to ctx.channel
        target = channel
        if not isinstance(channel, discord.TextChannel):
            # channel may be a string when discord doesn't convert; try to resolve
            resolved = await self._resolve_channel(ctx, channel)
            if not resolved:
                await __import__("mystery").mystery_send(ctx, "❌ Could not find the specified channel.")
                return
            target = resolved

        try:
            await target.set_permissions(
                guild.default_role,
                view_channel=True,
                send_messages=False,
                reason=f"Made public by {ctx.author}",
            )
            await __import__("mystery").mystery_send(
                ctx, f"✅ {target.mention} is now public (view-only for non-inside members)."
            )

            # Announce in announcements channel if present
            try:
                announcements = discord.utils.get(guild.text_channels, name="❗│announcements")
                if not announcements:
                    for ch in guild.text_channels:
                        if "announcements" in ch.name.lower():
                            announcements = ch
                            break
                if announcements:
                    # try to send a local gif from config, fallback to configured URL
                    gif_path = None
                    gif_url = None
                    try:
                        gif_dir = config.GIFS_DIRECTORY.get("public")
                        if gif_dir:
                            if not os.path.isabs(gif_dir):
                                base = os.path.dirname(os.path.dirname(__file__))
                                gif_dir = os.path.normpath(os.path.join(base, gif_dir))
                            if os.path.isdir(gif_dir):
                                files = [
                                    f
                                    for f in os.listdir(gif_dir)
                                    if f.lower().endswith((".gif", ".png", ".jpg", ".jpeg", "mp4"))
                                ]
                                if files:
                                    gif_path = os.path.join(gif_dir, random.choice(files))
                    except Exception:
                        gif_path = None

                    if not gif_path:
                        gif_url = config.DAY_GIF_URL if hasattr(config, "DAY_GIF_URL") else None

                    embed = discord.Embed(title=f"📣 {target.mention} is now public")
                    if gif_path:
                        attachment_name = os.path.basename(gif_path)
                        embed.set_image(url=f"attachment://{attachment_name}")
                        try:
                            await announcements.send(embed=embed, file=discord.File(gif_path))
                        except Exception:
                            if gif_url:
                                embed.set_image(url=gif_url)
                                await announcements.send(embed=embed)
                            else:
                                await announcements.send(f"📣 {target.mention} is now public")
                    elif gif_url:
                        embed.set_image(url=gif_url)
                        await announcements.send(embed=embed)
                    else:
                        await announcements.send(f"📣 {target.mention} is now public")
            except Exception:
                pass
        except Exception as e:
            logger.error(f"Error making channel public: {e}")
            await __import__("mystery").mystery_send(ctx, f"❌ Could not make channel public: {e}")

    @commands.command(name="private")
    @commands.has_permissions(manage_channels=True)
    async def make_private(self, ctx: commands.Context, channel: Optional[Union[discord.TextChannel, str]] = None) -> None:
        """Make a channel private (hidden) for @everyone."""
        guild = ctx.guild
        target = channel
        if not isinstance(channel, discord.TextChannel):
            resolved = await self._resolve_channel(ctx, channel)
            if not resolved:
                await __import__("mystery").mystery_send(ctx, "❌ Could not find the specified channel.")
                return
            target = resolved

        try:
            await target.set_permissions(guild.default_role, view_channel=False, send_messages=False, reason=f"Made private by {ctx.author}")
            await __import__("mystery").mystery_send(ctx, f"✅ {target.mention} is now private.")
            # Announce in announcements channel if present
            try:
                announcements = discord.utils.get(guild.text_channels, name="❗│announcements")
                if not announcements:
                    for ch in guild.text_channels:
                        if "announcements" in ch.name.lower():
                            announcements = ch
                            break
                if announcements:
                    # try to send a local gif from config, fallback to configured URL
                    gif_path = None
                    gif_url = None
                    try:
                        gif_dir = config.GIFS_DIRECTORY.get("private")
                        if gif_dir:
                            if not os.path.isabs(gif_dir):
                                base = os.path.dirname(os.path.dirname(__file__))
                                gif_dir = os.path.normpath(os.path.join(base, gif_dir))
                            if os.path.isdir(gif_dir):
                                files = [f for f in os.listdir(gif_dir) if f.lower().endswith((".gif", ".png", ".jpg", ".jpeg", "mp4"))]
                                if files:
                                    gif_path = os.path.join(gif_dir, random.choice(files))
                    except Exception:
                        gif_path = None

                    if not gif_path:
                        gif_url = config.NIGHT_GIF_URL if hasattr(config, 'NIGHT_GIF_URL') else None

                    embed = discord.Embed(title=f"🔒 {target.mention} is now private")
                    if gif_path and os.path.isfile(gif_path):
                        attachment_name = os.path.basename(gif_path)
                        embed.set_image(url=f"attachment://{attachment_name}")
                        try:
                            await announcements.send(embed=embed, file=discord.File(gif_path))
                        except Exception:
                            if gif_url:
                                embed.set_image(url=gif_url)
                                await announcements.send(embed=embed)
                            else:
                                await announcements.send(f"🔒 {target.mention} is now private")
                    elif gif_url:
                        embed.set_image(url=gif_url)
                        await announcements.send(embed=embed)
                    else:
                        await announcements.send(f"🔒 {target.mention} is now private")
            except Exception:
                pass
        except Exception as e:
            logger.error(f"Error making channel private: {e}")
            await __import__("mystery").mystery_send(ctx, f"❌ Could not make channel private: {e}")

    async def _resolve_channel(self, ctx: commands.Context, channel_arg: Optional[str]) -> Optional[discord.TextChannel]:
        """Resolve a channel from a string (mention, id, name, or config path).

        Supports:
        - Channel mention: <#123456>
        - Channel ID: 123456
        - Path: CATEGORY/chan-name or config token names from `config.SERVER_STRUCTURE`
        - Channel name or substring
        """
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
                if cat.name.lower() == cat_part.lower() or cat.name.upper() == cat_part.upper():
                    for ch in cat.text_channels:
                        if ch.name.lower() == chan_part.lower() or chan_part.lower() in ch.name.lower():
                            return ch

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

    @commands.command(name="add")
    @commands.has_permissions(manage_channels=True)
    async def add_member_to_channel(self, ctx: commands.Context, channel: discord.TextChannel, member: discord.Member) -> None:
        """Give a member view/send permissions for a channel. Usage: .add #channel @member"""
        try:
            await channel.set_permissions(member, view_channel=True, send_messages=True, reason=f"Added by {ctx.author}")
            await __import__("mystery").mystery_send(ctx, f"✅ {member.mention} can now access {channel.mention}")
        except Exception as e:
            logger.error(f"Error adding member to channel: {e}")
            await __import__("mystery").mystery_send(ctx, f"❌ Could not add member to channel: {e}")

    @commands.command(name="remove")
    @commands.has_permissions(manage_channels=True)
    async def remove_member_from_channel(self, ctx: commands.Context, channel: discord.TextChannel, member: discord.Member) -> None:
        """Remove a member's access to a channel. Usage: .remove #channel @member"""
        try:
            await channel.set_permissions(member, overwrite=None, reason=f"Removed by {ctx.author}")
            await __import__("mystery").mystery_send(ctx, f"✅ {member.mention} can no longer access {channel.mention}")
        except Exception as e:
            logger.error(f"Error removing member from channel: {e}")
            await __import__("mystery").mystery_send(ctx, f"❌ Could not remove member from channel: {e}")

    @commands.command(name="disappear")
    @commands.has_permissions(manage_channels=True)
    async def disappear(self, ctx: commands.Context, channel: discord.TextChannel = None, member: discord.Member = None) -> None:
        """Move a channel to THE SHADOW REALM category and restrict visibility to a single player.

        Usage: `.disappear` (operate on ctx.channel) or `.disappear #channel @player`
        """
        guild = ctx.guild
        if channel is None:
            channel = ctx.channel

        disappeared_cat = discord.utils.get(guild.categories, name="THE SHADOW REALM")
        if not disappeared_cat:
            try:
                disappeared_cat = await guild.create_category("THE SHADOW REALM")
            except Exception:
                await __import__("mystery").mystery_send(ctx, "❌ Could not create or find THE SHADOW REALM category")
                return

        try:
            await channel.edit(category=disappeared_cat, reason=f"Disappeared by {ctx.author}")
        except Exception as e:
            logger.error(f"Error moving channel to THE SHADOW REALM: {e}")
            await __import__("mystery").mystery_send(ctx, f"❌ Could not move channel: {e}")
            return

        # Make channel hidden to everyone by default
        try:
            await channel.set_permissions(guild.default_role, view_channel=False, send_messages=False, reason="Disappeared: hide from everyone")
        except Exception:
            pass

        # Clear existing member-specific overwrites
        try:
            for target in list(channel.overwrites.keys()):
                if isinstance(target, discord.Member):
                    try:
                        await channel.set_permissions(target, overwrite=None, reason="Disappeared: clearing old overwrites")
                    except Exception:
                        pass
        except Exception:
            pass

        target_member = member
        if not target_member:
            # attempt to infer a single member previously attached to the channel
            for t, ow in channel.overwrites.items():
                try:
                    if isinstance(t, discord.Member) and getattr(ow, "view_channel", False):
                        target_member = t
                        break
                except Exception:
                    continue

        if target_member:
            try:
                await channel.set_permissions(target_member, view_channel=True, send_messages=True, reason="Disappeared: grant sole access")
            except Exception:
                pass

        await __import__("mystery").mystery_send(ctx, f"✅ {channel.mention} moved to {disappeared_cat.name} and restricted to {target_member.display_name if target_member else 'no one'}.")

    @commands.command(name="world")
    @commands.has_permissions(manage_channels=True)
    async def world(self, ctx: commands.Context, member: discord.Member = None) -> None:
        """Grant a player access to all channels in the DISAPPEARED category.

        If used inside a role channel without a mention, the player for that RC will be targeted.
        """
        guild = ctx.guild
        # determine target member if not given (use channel's assigned player)
        target = member
        if not target:
            for key, ow in getattr(ctx.channel, "overwrites", {}).items():
                try:
                    if isinstance(key, discord.Member) and getattr(ow, "view_channel", False):
                        target = key
                        break
                except Exception:
                    continue

        if not target:
            await __import__("mystery").mystery_send(ctx, "❌ Could not determine player to grant world access. Mention them or run this inside their RC.")
            return

        disappeared_cat = discord.utils.get(guild.categories, name="THE SHADOW REALM")
        if not disappeared_cat:
            await __import__("mystery").mystery_send(ctx, "❌ THE SHADOW REALM category not found")
            return

        gave = 0
        for ch in disappeared_cat.text_channels:
            try:
                await ch.set_permissions(target, view_channel=True, send_messages=True, reason=f"World access granted by {ctx.author}")
                gave += 1
            except Exception:
                continue

        await __import__("mystery").mystery_send(ctx, f"✅ Granted {target.display_name} access to {gave} disappeared channels")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(RoleChannelsCog(bot))
