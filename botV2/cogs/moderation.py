import discord
from discord.ext import commands
from datetime import timedelta
import re
import logging
from typing import Optional, List, Dict

logger = logging.getLogger("discord_bot")

class ModerationCog(commands.Cog):
    """Moderation commands: purge, broom, kick, ban, timeout, mute, unmute, unban, untimeout, role management."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def _log_moderation_action(self, ctx: commands.Context, action: str, details: str) -> None:
        """Send a short log to the #✏️│edit-and-del-logs channel if it exists."""
        try:
            log_channel = discord.utils.get(ctx.guild.text_channels, name="✏️│edit-and-del-logs")
            if log_channel:
                await log_channel.send(f"**{action}** by {ctx.author.mention} in {ctx.channel.mention}: {details}")
        except Exception:
            logger.exception("Failed to send moderation log")

    # Purge messages
    @commands.command(name="purge", usage="<number|'all'> or reply to message")
    @commands.has_permissions(manage_messages=True)
    async def purge(self, ctx, amount_or_all: str = None):
        if ctx.message.reference:
            replied = ctx.message.reference.resolved
            deleted = await ctx.channel.purge(limit=None, before=ctx.message, after=replied.created_at)
            await ctx.send(f"🗑 Deleted {len(deleted)} messages up to {replied.id}.", delete_after=5)
            try:
                await self._log_moderation_action(ctx, "Purge", f"Deleted {len(deleted)} messages up to {replied.id}")
            except Exception:
                pass
            return

        if amount_or_all is None:
            raise commands.MissingRequiredArgument('amount_or_all')

        if amount_or_all.lower() == "all":
            deleted = await ctx.channel.purge(limit=None)
            await ctx.send(f"🗑 Deleted all messages ({len(deleted)})", delete_after=5)
            try:
                await self._log_moderation_action(ctx, "Purge", f"Deleted all messages ({len(deleted)}) in {ctx.channel.mention}")
            except Exception:
                pass
            return

        else:
            amount = int(amount_or_all)
            if amount < 1:
                raise commands.BadArgument("Amount must be at least 1.")
            deleted = await ctx.channel.purge(limit=amount + 1)
            await ctx.send(f"🗑 Deleted {len(deleted)-1} messages.", delete_after=5)
        try:
            await self._log_moderation_action(ctx, "Purge", f"Deleted {max(0, len(deleted)-1)} messages in {ctx.channel.mention}")
        except Exception:
            pass

    # Broom command
    @commands.command(name="broom", usage="<number|'all'> or reply to message")
    @commands.has_permissions(manage_messages=True)
    async def broom(self, ctx, amount_or_all: str = None):
        def not_pinned(m): return not m.pinned

        if ctx.message.reference:
            replied = ctx.message.reference.resolved
            deleted = await ctx.channel.purge(limit=None, before=ctx.message, after=replied.created_at, check=not_pinned)
            await ctx.send(f"🧹 Deleted {len(deleted)} messages up to {replied.id} (skipped pinned).", delete_after=5)
            try:
                await self._log_moderation_action(ctx, "Broom", f"Deleted {len(deleted)} messages up to {replied.id} (skipped pinned) in {ctx.channel.mention}")
            except Exception:
                pass
            return

        if amount_or_all is None:
            raise commands.MissingRequiredArgument('amount_or_all')

        if amount_or_all.lower() == "all":
            deleted = await ctx.channel.purge(limit=None, check=not_pinned)
            await ctx.send(f"🧹 Deleted all messages ({len(deleted)}) ignoring pinned.", delete_after=5)
            try:
                await self._log_moderation_action(ctx, "Broom", f"Deleted all messages ({len(deleted)}) ignoring pinned in {ctx.channel.mention}")
            except Exception:
                pass
            return
        else:
            amount = int(amount_or_all)
            if amount < 1:
                raise commands.BadArgument("Amount must be at least 1.")
            deleted = await ctx.channel.purge(limit=amount + 1, check=not_pinned)
            await ctx.send(f"🧹 Deleted {len(deleted)-1} messages (skipped pinned).", delete_after=5)
        try:
            await self._log_moderation_action(ctx, "Broom", f"Deleted {max(0, len(deleted)-1)} messages (skipped pinned) in {ctx.channel.mention}")
        except Exception:
            pass

    # Wipe: same as purge but do NOT leave logs
    @commands.command(name="wipe", usage="<number|'all'> or reply to message")
    @commands.has_permissions(manage_messages=True)
    async def wipe(self, ctx, amount_or_all: str = None):
        if ctx.message.reference:
            replied = ctx.message.reference.resolved
            deleted = await ctx.channel.purge(limit=None, before=ctx.message, after=replied.created_at)
            await ctx.send(f"🗑 Deleted {len(deleted)} messages up to {replied.id}.", delete_after=5)
            return

        if amount_or_all is None:
            raise commands.MissingRequiredArgument('amount_or_all')

        if amount_or_all.lower() == "all":
            deleted = await ctx.channel.purge(limit=None)
            await ctx.send(f"🗑 Deleted all messages ({len(deleted)})", delete_after=5)
        else:
            amount = int(amount_or_all)
            if amount < 1:
                raise commands.BadArgument("Amount must be at least 1.")
            deleted = await ctx.channel.purge(limit=amount + 1)
            await ctx.send(f"🗑 Deleted {len(deleted)-1} messages.", delete_after=5)

    # Kick member
    @commands.command(name="kick", usage="<@member> [reason]")
    @commands.has_permissions(kick_members=True)
    async def kick(self, ctx, member: discord.Member, *, reason: str = None):
        await member.kick(reason=reason)
        await __import__("mystery").mystery_send(ctx, f"👢 {member.mention} has been kicked. Reason: {reason or 'No reason provided'}")

    # Ban member
    @commands.command(name="ban", usage="<@member> [reason]")
    @commands.has_permissions(ban_members=True)
    async def ban(self, ctx, member: discord.Member, *, reason: str = None):
        await member.ban(reason=reason)
        await __import__("mystery").mystery_send(ctx, f"⛔ {member.mention} has been banned. Reason: {reason or 'No reason provided'}")

    # Timeout
    @commands.command(name="timeout", usage="<@member> <duration> [reason]")
    @commands.has_permissions(moderate_members=True)
    async def timeout(self, ctx, member: discord.Member, duration: str, *, reason: str = None):
        """
        Time out a member.
        Duration format: <number><unit>
        Units:
          m = minutes
          h = hours
          d = days
        Examples:
          .timeout @user 30m
          .timeout @user 2h
          .timeout @user 1d
        """
        unit = duration[-1].lower()
        if unit not in ("m", "h", "d"):
            raise commands.BadArgument("Invalid duration unit. Use 'm', 'h', or 'd'.")

        try:
            value = int(duration[:-1])
        except ValueError:
            raise commands.BadArgument("Invalid duration value. Must be an integer.")

        if value < 1:
            raise commands.BadArgument("Duration must be at least 1.")

        if unit == "m":
            delta = timedelta(minutes=value)
        elif unit == "h":
            delta = timedelta(hours=value)
        else:  # 'd'
            delta = timedelta(days=value)

        until = discord.utils.utcnow() + delta
        await member.edit(timed_out_until=until, reason=reason)
        await __import__("mystery").mystery_send(ctx, f"⏱ {member.mention} has been timed out for {duration}. Reason: {reason or 'No reason provided'}")


    # Mute member
    @commands.command(name="mute", usage="<@member>")
    @commands.has_permissions(manage_roles=True)
    async def mute(self, ctx: commands.Context, member: discord.Member) -> None:
        """Mute a member by applying the Muted role."""
        guild = ctx.guild
        muted_role = discord.utils.get(guild.roles, name="Muted")
        if not muted_role:
            try:
                muted_role = await guild.create_role(name="Muted", reason="Created for muting members.")
                for channel in guild.text_channels:
                    try:
                        await channel.set_permissions(muted_role, send_messages=False, add_reactions=False)
                    except (discord.Forbidden, discord.HTTPException):
                        pass
            except (discord.Forbidden, discord.HTTPException) as e:
                logger.error(f"Failed to create mute role in {guild.id}: {e}")
                await ctx.send("❌ Failed to create Muted role.")
                return
        if muted_role in member.roles:
            raise commands.BadArgument(f"{member} is already muted.")
        await member.add_roles(muted_role, reason="Muted by command")
        await __import__("mystery").mystery_send(ctx, f"🔇 {member.mention} has been muted.")

    # Unmute member
    @commands.command(name="unmute", usage="<@member>")
    @commands.has_permissions(manage_roles=True)
    async def unmute(self, ctx: commands.Context, member: discord.Member) -> None:
        """Unmute a member by removing the Muted role."""
        guild = ctx.guild
        muted_role = discord.utils.get(guild.roles, name="Muted")
        if not muted_role or muted_role not in member.roles:
            raise commands.BadArgument(f"{member} is not muted.")
        await member.remove_roles(muted_role, reason="Unmuted by command")
        await __import__("mystery").mystery_send(ctx, f"🔊 {member.mention} has been unmuted.")

    # Unban member
    @commands.command(name="unban", usage="<Username#1234>")
    @commands.has_permissions(ban_members=True)
    async def unban(self, ctx, user: str):
        banned_users = await ctx.guild.bans()
        name, discrim = user.split("#")
        for ban_entry in banned_users:
            if ban_entry.user.name == name and ban_entry.user.discriminator == discrim:
                await ctx.guild.unban(ban_entry.user)
                await __import__("mystery").mystery_send(ctx, f"✅ {user} has been unbanned.")
                return
        raise commands.BadArgument(f"User {user} not found in ban list.")

    # Untimeout member
    @commands.command(name="untimeout", usage="<@member>")
    @commands.has_permissions(moderate_members=True)
    async def untimeout(self, ctx, member: discord.Member):
        if member.timed_out_until is None:
            raise commands.BadArgument(f"{member} is not currently timed out.")
        await member.edit(timed_out_until=None, reason="Untimeout command")
        await __import__("mystery").mystery_send(ctx, f"✅ {member.mention} has been removed from timeout.")

    @commands.group(name="role", invoke_without_command=True)
    @commands.has_permissions(manage_roles=True)
    async def role(self, ctx, channel: Optional[discord.TextChannel] = None):
        """Show usage or, when called without subcommand, display the first pinned message.

        Usage:
          - `.role` -> shows first pinned message in the current channel
          - `.role #channel` -> shows first pinned message in that channel
        """
        # determine target channel
        target = channel or ctx.channel

        try:
            pins = await target.pins()
        except Exception:
            await __import__("mystery").mystery_send(ctx, "❌ Could not retrieve pinned messages for that channel.")
            return

        if not pins:
            await __import__("mystery").mystery_send(ctx, "⚠️ No pinned messages in that channel.")
            return

        # choose the oldest pinned message as "first"
        first = sorted(pins, key=lambda m: m.created_at)[0]

        # Build a safe embed display of the pinned message (truncate long content)
        author = first.author.display_name if first.author else "Unknown"
        content = first.content or "(no text content)"
        ts = first.created_at.strftime("%Y-%m-%d %H:%M:%S UTC") if first.created_at else ""

        # Truncate content to avoid 2000-char message limit and embed field limits
        MAX_FIELD = 1000
        content_preview = content if len(content) <= MAX_FIELD else content[:MAX_FIELD] + "... (truncated)"

        # attachments: include up to first 5 URLs, truncated if necessary
        attachments_list = [a.url for a in first.attachments] if first.attachments else []
        attachments_preview = "\n".join(attachments_list[:5])
        if len(attachments_list) > 5:
            attachments_preview += f"\n...and {len(attachments_list)-5} more attachments"

        embed = discord.Embed(title=f"📌 First pinned in {target.name}", color=discord.Color.blurple())
        embed.add_field(name="Author", value=author, inline=True)
        embed.add_field(name="Time", value=ts or "", inline=True)
        embed.add_field(name="Content", value=content_preview, inline=False)
        if attachments_preview:
            att_val = attachments_preview if len(attachments_preview) <= 1000 else attachments_preview[:1000] + "..."
            embed.add_field(name="Attachments", value=att_val, inline=False)

        try:
            await ctx.send(embed=embed)
        except Exception:
            # fallback: send a minimal text response
            try:
                await __import__("mystery").mystery_send(ctx, f"📌 First pinned in {target.mention} — {author} — {ts}")
            except Exception:
                pass

    def _resolve_role(self, guild: discord.Guild, name: str) -> Optional[discord.Role]:
        """Resolve a role from a mention, ID, or name (case-insensitive)."""
        # Try role mention format <@&ID>
        m = re.match(r"<@&(\d+)>", name)
        if m:
            return guild.get_role(int(m.group(1)))
        # Try role ID
        if name.isdigit():
            return guild.get_role(int(name))
        # Try exact name match
        role = discord.utils.get(guild.roles, name=name)
        if role:
            return role
        # Try case-insensitive match
        for r in guild.roles:
            if r.name.lower() == name.lower():
                return r
        return None

    @role.command(name="add")
    @commands.has_permissions(manage_roles=True)
    async def role_add(self, ctx, role_name: str, *targets: str):
        """Add a role to one or more members. Use 'Everyone' to assign to all non-bot members."""
        guild = ctx.guild
        role = self._resolve_role(guild, role_name)
        if not role:
            await __import__("mystery").mystery_send(ctx, f"❌ Role '{role_name}' not found.")
            return

        if not targets:
            await __import__("mystery").mystery_send(ctx, "❌ You must provide at least one target (member or 'Everyone').")
            return

        added, skipped, failed = [], [], []

        # track processed members to avoid duplicates when multiple targets overlap
        processed_ids = set()

        if len(targets) == 1 and targets[0].lower() in ("everyone", "all", "@everyone"):
            members = [m for m in guild.members if not m.bot]
            for member in members:
                if member.id in processed_ids:
                    continue
                processed_ids.add(member.id)
                if role in member.roles:
                    skipped.append(member.display_name)
                    continue
                try:
                    await member.add_roles(role, reason=f"Assigned by {ctx.author}")
                    added.append(member.display_name)
                except Exception:
                    failed.append(member.display_name)
        else:
            for t in targets:
                # If target matches a role name/mention/ID, apply to members who have that role
                target_role = self._resolve_role(guild, t)
                if target_role:
                    members = [m for m in guild.members if (target_role in m.roles) and not m.bot]
                    for member in members:
                        if member.id in processed_ids:
                            continue
                        processed_ids.add(member.id)
                        if role in member.roles:
                            skipped.append(member.display_name)
                            continue
                        try:
                            await member.add_roles(role, reason=f"Assigned by {ctx.author}")
                            added.append(member.display_name)
                        except Exception:
                            failed.append(member.display_name)
                    continue

                member = None
                m = re.match(r"<@!?(\d+)>", t)
                if m:
                    member = guild.get_member(int(m.group(1)))
                elif t.isdigit():
                    member = guild.get_member(int(t))
                else:
                    member = discord.utils.find(lambda mm: mm.name.lower() == t.lower() or (mm.display_name and mm.display_name.lower() == t.lower()), guild.members)

                if not member:
                    failed.append(t)
                    continue

                if member.id in processed_ids:
                    continue
                processed_ids.add(member.id)

                if role in member.roles:
                    skipped.append(member.display_name)
                    continue
                try:
                    await member.add_roles(role, reason=f"Assigned by {ctx.author}")
                    added.append(member.display_name)
                except Exception:
                    failed.append(member.display_name)

        parts = []
        if added:
            parts.append(f"✅ Added role '{role.name}' to: {', '.join(added)}")
        if skipped:
            parts.append(f"⚠ Already had role: {', '.join(skipped)}")
        if failed:
            parts.append(f"❌ Failed to add to: {', '.join(failed)}")

        await __import__("mystery").mystery_send(ctx, "\n".join(parts) if parts else "No changes were made.")

    @role.command(name="remove")
    @commands.has_permissions(manage_roles=True)
    async def role_remove(self, ctx, role_name: str, *targets: str):
        """Remove a role from one or more members. Use 'Everyone' to remove from all non-bot members."""
        guild = ctx.guild
        role = self._resolve_role(guild, role_name)
        if not role:
            await ctx.send(f"❌ Role '{role_name}' not found.")
            return

        if not targets:
            await ctx.send("❌ You must provide at least one target (member or 'Everyone').")
            return

        removed, skipped, failed = [], [], []
        processed_ids = set()

        if len(targets) == 1 and targets[0].lower() in ("everyone", "all", "@everyone"):
            members = [m for m in guild.members if not m.bot]
            for member in members:
                if member.id in processed_ids:
                    continue
                processed_ids.add(member.id)
                if role not in member.roles:
                    skipped.append(member.display_name)
                    continue
                try:
                    await member.remove_roles(role, reason=f"Removed by {ctx.author}")
                    removed.append(member.display_name)
                except Exception:
                    failed.append(member.display_name)
        else:
            for t in targets:
                # If t matches a role, remove from members who have that role
                target_role = self._resolve_role(guild, t)
                if target_role:
                    members = [m for m in guild.members if (target_role in m.roles) and not m.bot]
                    for member in members:
                        if member.id in processed_ids:
                            continue
                        processed_ids.add(member.id)
                        if role not in member.roles:
                            skipped.append(member.display_name)
                            continue
                        try:
                            await member.remove_roles(role, reason=f"Removed by {ctx.author}")
                            removed.append(member.display_name)
                        except Exception:
                            failed.append(member.display_name)
                    continue

                member = None
                m = re.match(r"<@!?(\d+)>", t)
                if m:
                    member = guild.get_member(int(m.group(1)))
                elif t.isdigit():
                    member = guild.get_member(int(t))
                else:
                    member = discord.utils.find(lambda mm: mm.name.lower() == t.lower() or (mm.display_name and mm.display_name.lower() == t.lower()), guild.members)

                if not member:
                    failed.append(t)
                    continue

                if member.id in processed_ids:
                    continue
                processed_ids.add(member.id)

                if role not in member.roles:
                    skipped.append(member.display_name)
                    continue
                try:
                    await member.remove_roles(role, reason=f"Removed by {ctx.author}")
                    removed.append(member.display_name)
                except Exception:
                    failed.append(member.display_name)

        parts = []
        if removed:
            parts.append(f"✅ Removed role '{role.name}' from: {', '.join(removed)}")
        if skipped:
            parts.append(f"⚠ Did not have role: {', '.join(skipped)}")
        if failed:
            parts.append(f"❌ Failed to remove from: {', '.join(failed)}")

        await __import__("mystery").mystery_send(ctx, "\n".join(parts) if parts else "No changes were made.")

    # ------------------------
    # Pin message
    # ------------------------
    @commands.command(name="pin", usage="[reply to message]")
    @commands.has_permissions(manage_messages=True)
    async def pin(self, ctx):
        """
        Pins a message in the channel.
        Usage:
          - Reply to a message and type .pin to pin that message
        """
        # Determine which message to pin
        if ctx.message.reference:
            message_to_pin = ctx.message.reference.resolved
            if not isinstance(message_to_pin, discord.Message):
                raise commands.BadArgument("Cannot resolve replied message.")
        else:
            # If no reply, pin the command message itself
            message_to_pin = ctx.message

        await message_to_pin.pin(reason=f"Pinned by {ctx.author}")
        await ctx.send(f"📌 Message by {message_to_pin.author.mention} has been pinned.", delete_after=5)

    # ------------------------
    # Unpin message
    # ------------------------
    @commands.command(name="unpin", usage="[reply to message]")
    @commands.has_permissions(manage_messages=True)
    async def unpin(self, ctx):
        """
        Unpins a message in the channel.
        Usage:
          - Reply to a message and type .unpin to unpin that message
        """
        # Determine which message to unpin
        if ctx.message.reference:
            message_to_unpin = ctx.message.reference.resolved
            if not isinstance(message_to_unpin, discord.Message):
                raise commands.BadArgument("Cannot resolve replied message.")
        else:
            # If no reply, unpin the command message itself
            message_to_unpin = ctx.message

        await message_to_unpin.unpin(reason=f"Unpinned by {ctx.author}")
        await ctx.send(f"📌 Message by {message_to_unpin.author.mention} has been unpinned.", delete_after=5)



# Loader
async def setup(bot):
    await bot.add_cog(ModerationCog(bot))