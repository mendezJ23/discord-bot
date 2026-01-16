import discord
from discord.ext import commands
import logging
import re
import json
from pathlib import Path
from typing import Optional
import asyncio

logger = logging.getLogger("discord_bot")

# Throttle between API calls to avoid hitting Discord rate limits
THROTTLE = 0.35


def _owners_file() -> Path:
    return Path(__file__).resolve().parents[1] / "house_owners.json"


def load_owners() -> dict:
    p = _owners_file()
    if not p.exists():
        return {"by_house": {}, "by_user": {}}
    try:
        with p.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"by_house": {}, "by_user": {}}


def save_owners(data: dict) -> None:
    p = _owners_file()
    try:
        with p.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Failed to save manor owners: {e}")


class HousesCog(commands.Cog):
    """Cog to manage house channels under the HOUSES category and owners."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        # load owners into memory
        self.owners = load_owners()
        # schedule an initial map update on ready
        self._map_ready = False

    async def _update_map_channel(self, guild: discord.Guild) -> None:
        """Update the #map channel to display house channel names under HOUSES."""
        houses_category = discord.utils.get(guild.categories, name="MANORS")
        if not houses_category:
            return
        # find a map channel (name contains 'map')
        map_ch = None
        for ch in guild.text_channels:
            try:
                if "map" in ch.name.lower():
                    map_ch = ch
                    break
            except Exception:
                continue

        if not map_ch:
            return

        # Build content
        lines = [f"**{c.name}** — {c.mention}" for c in houses_category.text_channels]
        content = "\n".join(lines) if lines else "No manors available."

        try:
            # delete bot messages in channel and send fresh map
            async for m in map_ch.history(limit=30):
                if m.author == self.bot.user:
                    try:
                        await m.delete()
                    except Exception:
                        pass
            await map_ch.send(f"📍 **Manor Map**\n\n{content}")
        except Exception:
            return

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel) -> None:
        try:
            guild = channel.guild
            await self._update_map_channel(guild)
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> None:
        try:
            guild = channel.guild
            await self._update_map_channel(guild)
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        # ensure map updated once after bot ready
        if self._map_ready:
            return
        self._map_ready = True
        for guild in self.bot.guilds:
            try:
                await self._update_map_channel(guild)
            except Exception:
                continue

    @commands.group(name="manor", invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    async def manor(self, ctx: commands.Context) -> None:
        await __import__("mystery").mystery_send(ctx, "Usage: .manor add <items...> | .manor delete <items...>|all | .manor setup")

    @manor.command(name="list")
    async def manor_list(self, ctx: commands.Context) -> None:
        """List all houses available in the MANORS category."""
        guild = ctx.guild
        houses_category = discord.utils.get(guild.categories, name="MANORS")
        if not houses_category:
            await __import__("mystery").mystery_send(ctx, "❌ 'MANORS' category not found")
            return

        channels = list(houses_category.text_channels)
        if not channels:
            await __import__("mystery").mystery_send(ctx, "⚠️ No manors available.")
            return

        lines = []
        for ch in channels:
            owners = self._get_owners_for_house(ch.name)
            owner_mentions = []
            for uid in owners:
                m = guild.get_member(int(uid))
                if m:
                    owner_mentions.append(m.display_name)
                else:
                    owner_mentions.append(uid)
            owners_text = ", ".join(owner_mentions) if owner_mentions else "(no owners)"
            lines.append(f"{ch.mention} — {owners_text}")

        # send in chunks if too long
        msg = "\n".join(lines)
        if len(msg) > 1900:
            # send as multiple messages
            current = ""
            for line in lines:
                if len(current) + len(line) + 1 > 1900:
                    await __import__("mystery").mystery_send(ctx, current)
                    current = line + "\n"
                else:
                    current += line + "\n"
            if current:
                await __import__("mystery").mystery_send(ctx, current)
        else:
            await __import__("mystery").mystery_send(ctx, msg)

    @manor.command(name="setup")
    @commands.has_permissions(administrator=True)
    async def manor_setup(self, ctx: commands.Context) -> None:
        """Assign all Alive players to manors with narrations."""
        # Forward to RoleChannelsCog's house_setup method
        role_channels_cog = self.bot.get_cog("RoleChannelsCog")
        if role_channels_cog and hasattr(role_channels_cog, "manor_setup"):
            await role_channels_cog.manor_setup(ctx)
        else:
            await __import__("mystery").mystery_send(ctx, "❌ Manor setup feature not available")

    @manor.command(name="add")
    @commands.has_permissions(administrator=True)
    async def manor_add(self, ctx: commands.Context, *items: str) -> None:
        """Create manors. Supports:

        - `.manor add <count>` -> create <count> sequential manors after highest numeric manor
        - `.manor add name1 name2 3 6` -> create the listed names/numbers
        - items may be comma-separated inside a token
        """
        guild = ctx.guild
        houses_category = discord.utils.get(guild.categories, name="MANORS")
        if not houses_category:
            await __import__("mystery").mystery_send(ctx, "❌ 'MANORS' category not found")
            return

        if not items:
            await __import__("mystery").mystery_send(ctx, "❌ Provide a count or names/numbers to create")
            return

        # single integer -> sequential behaviour
        if len(items) == 1 and items[0].isdigit():
            count = int(items[0])
            if count <= 0:
                await __import__("mystery").mystery_send(ctx, "❌ Count must be positive")
                return

            existing = list(houses_category.text_channels)
            nums = []
            for ch in existing:
                m = re.search(r"manor-(\d+)", ch.name.lower())
                if m:
                    try:
                        nums.append(int(m.group(1)))
                    except Exception:
                        continue

            if nums:
                start = max(nums) + 1
            else:
                start = len(existing) + 1

            targets = [f"🏰│manor-{start + i}" for i in range(count)]
        else:
            # flatten comma-separated
            tokens = []
            for it in items:
                parts = [p.strip() for p in it.split(",") if p.strip()]
                tokens.extend(parts)

            targets = []
            for tok in tokens:
                if tok.isdigit():
                    targets.append(f"🏰│manor-{int(tok)}")
                else:
                    low = tok.lower()
                    if low.startswith("🏰│"):
                        targets.append(low)
                    elif low.startswith("manor-"):
                        targets.append(f"🏰│{low}")
                    else:
                        targets.append(f"🏰│{low}")

        # dedupe preserve order
        seen = set()
        final = []
        for t in targets:
            if t not in seen:
                seen.add(t)
                final.append(t)

        existing_names = {c.name for c in houses_category.text_channels}
        collisions = [t for t in final if t in existing_names]
        to_create = [t for t in final if t not in existing_names]

        if not to_create:
            await __import__("mystery").mystery_send(ctx, f"⚠️ No new manors to create. Collisions: {', '.join(collisions)}" if collisions else "⚠️ No manors to create")
            return

        created = []
        errors = 0
        for name in to_create:
            try:
                logger.info(f"Creating manor channel {name} in guild {guild.id}")
                ch = await guild.create_text_channel(name=name, category=houses_category, reason=f"Added manor {name}")
                created.append(ch.name)
                await asyncio.sleep(THROTTLE)
            except Exception as e:
                logger.error(f"Error creating manor {name}: {e}")
                errors += 1

        parts = []
        if created:
            parts.append(f"✅ Created: {', '.join(created)}")
        if collisions:
            parts.append(f"⚠️ Skipped existing: {', '.join(collisions)}")
        if errors:
            parts.append(f"⚠️ {errors} errors occurred")

        await __import__("mystery").mystery_send(ctx, " | ".join(parts))

    @manor.command(name="delete")
    @commands.has_permissions(administrator=True)
    async def manor_delete(self, ctx: commands.Context, *items: str) -> None:
        """Delete multiple manors. Usage: `.manor delete 1 2 #channel custom-name` or `.manor delete all`"""
        guild = ctx.guild
        manors_category = discord.utils.get(guild.categories, name="MANORS")
        if not manors_category:
            await __import__("mystery").mystery_send(ctx, "❌ 'MANORS' category not found")
            return

        # flatten
        tokens = []
        for it in items:
            for p in it.split(","):
                s = p.strip()
                if s:
                    tokens.append(s)

        if not tokens:
            await __import__("mystery").mystery_send(ctx, "❌ Provide targets to delete or 'all'")
            return

        if any(t.lower() == "all" for t in tokens):
            channels = list(manors_category.text_channels)
            if not channels:
                await __import__("mystery").mystery_send(ctx, "⚠️ No manor channels to delete")
                return

            deleted = []
            errors = 0
            for ch in channels:
                try:
                    await ch.delete(reason="Deleted by .manor delete all")
                    deleted.append(ch.name)
                    await asyncio.sleep(THROTTLE)
                except Exception as e:
                    logger.error(f"Error deleting manor {ch.name}: {e}")
                    errors += 1

            msg = "✅ Deleted manors: " + (", ".join(deleted) if deleted else "none")
            if errors:
                msg += f" ({errors} errors)"
            await __import__("mystery").mystery_send(ctx, msg)
            return

        # resolve tokens to channels
        resolved = []
        not_found = []

        # use mentions first
        if ctx.message.channel_mentions:
            resolved.extend(ctx.message.channel_mentions)

        for tok in tokens:
            if tok.startswith("<#") and tok.endswith(">"):
                continue

            if tok.isdigit():
                name = f"🏰│manor-{int(tok)}"
            else:
                low = tok.lower()
                if low.startswith("🏰│"):
                    name = low
                elif low.startswith("manor-"):
                    name = f"🏰│{low}"
                else:
                    name = f"🏰│{low}"

            ch = discord.utils.get(manors_category.text_channels, name=name)
            if ch:
                resolved.append(ch)
            else:
                # try raw name
                found = None
                for c in manors_category.text_channels:
                    if c.name.lower() == tok.lower() or c.name.lower() == name:
                        found = c
                        break
                if found:
                    resolved.append(found)
                else:
                    not_found.append(tok)

        # dedupe by id
        uniq = []
        ids = set()
        for c in resolved:
            if c.id not in ids:
                ids.add(c.id)
                uniq.append(c)

        deleted = []
        errors = 0
        for ch in uniq:
            try:
                await ch.delete(reason=f"Deleted by .manor delete command by {ctx.author}")
                deleted.append(ch.name)
            except Exception as e:
                logger.error(f"Error deleting manor {ch.name}: {e}")
                errors += 1

        parts = []
        if deleted:
            parts.append(f"✅ Deleted: {', '.join(deleted)}")
        if not_found:
            parts.append(f"⚠️ Not found: {', '.join(not_found)}")
        if errors:
            parts.append(f"⚠️ {errors} errors occurred while deleting")

        await __import__("mystery").mystery_send(ctx, " | ".join(parts) if parts else "⚠️ Nothing deleted")

    # -- Owner mechanics -------------------------------------------------
    def _manor_name_from_channel(self, ch: discord.TextChannel) -> str:
        return ch.name

    def _get_owners_for_manor(self, manor_name: str) -> list:
        return self.owners.get("by_house", {}).get(manor_name, [])
    def _get_manor_for_user(self, user_id: int) -> Optional[str]:
        return self.owners.get("by_user", {}).get(str(user_id))

    def _add_owner(self, user_id: int, manor_name: str) -> None:
        # ensure user owns only one manor
        by_house = self.owners.setdefault("by_house", {})
        by_user = self.owners.setdefault("by_user", {})
        # remove from previous if exists
        prev = by_user.get(str(user_id))
        if prev and prev != manor_name:
            lst = by_house.get(prev, [])
            if str(user_id) in lst:
                lst.remove(str(user_id))
                by_house[prev] = lst
        # add to new
        lst = by_house.get(manor_name, [])
        if str(user_id) not in lst:
            lst.append(str(user_id))
            by_house[manor_name] = lst
        by_user[str(user_id)] = manor_name
        save_owners(self.owners)

    def _remove_owner(self, user_id: int, manor_name: Optional[str] = None) -> None:
        by_house = self.owners.setdefault("by_house", {})
        by_user = self.owners.setdefault("by_user", {})
        prev = by_user.get(str(user_id))
        if not prev:
            return
        if manor_name and prev != manor_name:
            return
        lst = by_house.get(prev, [])
        if str(user_id) in lst:
            lst.remove(str(user_id))
            by_house[prev] = lst
        by_user.pop(str(user_id), None)
        save_owners(self.owners)

    def _resolve_manor(self, guild: discord.Guild, token: str) -> Optional[discord.TextChannel]:
        if not token:
            return None
        manors_category = discord.utils.get(guild.categories, name="MANORS")
        if not manors_category:
            return None

        # channel mention
        if token.startswith("<#") and token.endswith(">"):
            try:
                cid = int(token[2:-1])
                ch = discord.utils.get(manors_category.text_channels, id=cid)
                if ch:
                    return ch
            except Exception:
                pass

        if token.isdigit():
            name = f"🏰│manor-{int(token)}"
        else:
            low = token.lower()
            if low.startswith("🏰│"):
                name = low
            elif low.startswith("manor-"):
                name = f"🏰│{low}"
            else:
                name = f"🏰│{low}"

        ch = discord.utils.get(manors_category.text_channels, name=name)
        if ch:
            return ch

        for c in manors_category.text_channels:
            if c.name.lower() == token.lower() or c.name.lower() == name:
                return c
        return None

    @commands.group(name="owner", invoke_without_command=True)
    async def owner(self, ctx: commands.Context, *, token: Optional[str] = None) -> None:
        """Show owners.

        - Inside a manor: shows the owners of that manor
        - `.owner {manor}`: shows owners if caller has view access
        - Inside ROLES/ALTS/DEAD RC with no args: shows the manor the player owns
        """
        guild = ctx.guild
        if not guild:
            return

        # used inside a manor channel
        if ctx.channel.category and ctx.channel.category.name == "MANORS" and token is None:
            manor_name = self._manor_name_from_channel(ctx.channel)
            owners = self._get_owners_for_manor(manor_name)
            if not owners:
                await __import__("mystery").mystery_send(ctx, "⚠️ This manor has no owners.")
                return
            mentions = []
            for uid in owners:
                m = guild.get_member(int(uid))
                mentions.append(m.display_name if m else uid)
            await __import__("mystery").mystery_send(ctx, f"Owners of {ctx.channel.mention}: {', '.join(mentions)}")
            return

        # token provided -> resolve manor and check view access
        if token:
            ch = self._resolve_manor(guild, token.strip())
            if not ch:
                await __import__("mystery").mystery_send(ctx, "❌ Manor not found")
                return
            perm = ch.permissions_for(ctx.author)
            if not perm.view_channel:
                await __import__("mystery").mystery_send(ctx, "❌ You don't have access to view that manor")
                return
            owners = self._get_owners_for_manor(ch.name)
            if not owners:
                await __import__("mystery").mystery_send(ctx, f"⚠️ {ch.mention} has no owners.")
                return
            mentions = []
            for uid in owners:
                m = guild.get_member(int(uid))
                mentions.append(m.display_name if m else uid)
            await __import__("mystery").mystery_send(ctx, f"Owners of {ch.mention}: {', '.join(mentions)}")
            return

        # If used inside ROLES/ALTS/DEAD RC, show the manor the player owns
        allowed = {"ROLES", "ALTS", "DEAD RC"}
        if ctx.channel.category and ctx.channel.category.name in allowed:
            manor = self._get_manor_for_user(ctx.author.id)
            if not manor:
                await __import__("mystery").mystery_send(ctx, "⚠️ You don't own a manor.")
                return
            manors_category = discord.utils.get(guild.categories, name="MANORS")
            ch = discord.utils.get(manors_category.text_channels, name=manor) if manors_category else None
            await __import__("mystery").mystery_send(ctx, f"🏡 You own: {ch.mention if ch else manor}")
            return

        await __import__("mystery").mystery_send(ctx, "Usage: .owner inside a manor or in ROLES/ALTS/DEAD RC or `.owner <manor>`")

    @commands.command(name="homelist")
    async def homelist(self, ctx: commands.Context) -> None:
        """Overseer-only: list all manors and their owners."""
        if not self.is_overseer(ctx.author):
            await __import__("mystery").mystery_send(ctx, "❌ Only overseers can use .homelist")
            return
        guild = ctx.guild
        manors_category = discord.utils.get(guild.categories, name="MANORS")
        if not manors_category:
            await __import__("mystery").mystery_send(ctx, "❌ 'MANORS' category not found")
            return

        parts = []
        for ch in manors_category.text_channels:
            owners = self._get_owners_for_manor(ch.name)
            if not owners:
                parts.append(f"{ch.name}: (no owners)")
            else:
                names = []
                for uid in owners:
                    m = guild.get_member(int(uid))
                    names.append(m.display_name if m else uid)
                parts.append(f"{ch.name}: {', '.join(names)}")

        if not parts:
            await __import__("mystery").mystery_send(ctx, "⚠️ No manors found")
            return
        # send in chunks if large
        out = "\n".join(parts)
        await __import__("mystery").mystery_send(ctx, f"📜 Manor list:\n{out}")
    @commands.command(name="manorlist")
    async def manorlist(self, ctx: commands.Context) -> None:
        """Alias for .homelist (legacy/alternate name)."""
        await self.homelist(ctx)

    def is_overseer(self, member: discord.Member) -> bool:
        if not member or not hasattr(member, "guild_permissions"):
            return False
        if member.guild_permissions.administrator or member.guild_permissions.manage_guild:
            return True
        for r in member.roles:
            if r.name.lower() == "overseer":
                return True
        return False

    @commands.command(name="home")
    async def home(self, ctx: commands.Context, *, token: Optional[str] = None) -> None:
        """Send the player to the manor they own.

        Usage:
        - `.home` -> send yourself home (use inside ROLES/ALTS/DEAD RC)
        - `.home @member` -> overseer-only: send that member home (must be used inside ROLES/ALTS/DEAD RC)
        - `.home all` -> overseer-only: send all players (with manors) home
        """
        guild = ctx.guild
        if not guild:
            return

        allowed = {"ROLES", "ALTS", "DEAD RC"}
        if not ctx.channel.category or ctx.channel.category.name not in allowed:
            await ctx.send("❌ .home can only be used inside ROLES, ALTS or DEAD RC channels")
            return

        # helper to move a single member home; returns (ok: bool, message: str)
        async def _move_member(member: discord.Member) -> tuple[bool, str]:
            manor_name = self._get_manor_for_user(member.id)
            if not manor_name:
                return False, f"{member.display_name} does not own a manor"
            manors_category = discord.utils.get(guild.categories, name="MANORS")
            if not manors_category:
                return False, "MANORS category not found"
            ch = discord.utils.get(manors_category.text_channels, name=manor_name)
            if not ch:
                return False, f"Manor channel for {member.display_name} not found"

            knocks = self.bot.get_cog("KnocksCog")
            try:
                if knocks and hasattr(knocks, "move_member_to_house"):
                    # set initiator/reason on the knocks cog for logging
                    try:
                        knocks._last_move_initiator = ctx.author
                        knocks._last_move_reason = "home command"
                    except Exception:
                        pass
                    try:
                        ok, err = await knocks.move_member_to_house(guild, member, ch, announce_leave=True, announce_join=True)
                    finally:
                        try:
                            knocks._last_move_initiator = None
                            knocks._last_move_reason = None
                        except Exception:
                            pass
                    if ok:
                        return True, f"Moved {member.display_name} to {ch.mention}"
                    return False, f"Failed to move {member.display_name}: {err}"

                # fallback: set permissions directly
                prev = None
                for c in manors_category.text_channels:
                    ow = c.overwrites.get(member)
                    if ow and getattr(ow, "view_channel", False):
                        prev = c
                        try:
                            await c.set_permissions(member, overwrite=None, reason="Removed member-specific overwrites (home move)")
                        except Exception:
                            pass
                await ch.set_permissions(member, view_channel=True, send_messages=True, reason="Moved to home")
                # Log the manual move to log-visits
                try:
                    log_ch = discord.utils.get(guild.text_channels, name="log-visits")
                    if log_ch:
                        parts = [f"**Move:** {member.display_name} (ID: {member.id})"]
                        # by is ctx.author in this scope
                        if ctx and ctx.author:
                            parts.append(f"**By:** {ctx.author.display_name} (ID: {ctx.author.id})")
                        if prev:
                            parts.append(f"**From:** {prev.mention if hasattr(prev, 'mention') else getattr(prev, 'name', str(prev))}")
                        parts.append(f"**To:** {ch.mention}")
                        await log_ch.send(" | ".join(parts))
                except Exception:
                    pass
                return True, f"Moved {member.display_name} to {ch.mention}"
            except Exception as e:
                logger.error(f"Error moving {member} home: {e}")
                return False, f"Error moving {member.display_name}: {e}"

        # No token -> move the caller OR, if caller is an overseer, try to target
        # the channel's primary member (so overseers can run `.home` in a player's
        # role channel to move that player).
        if not token:
            target_member = None
            if self.is_overseer(ctx.author):
                # Look for a single member-specific overwrite with view permission
                for key, ow in getattr(ctx.channel, "overwrites", {}).items():
                    try:
                        is_member = isinstance(key, discord.Member)
                    except Exception:
                        is_member = False
                    if not is_member:
                        continue
                    member = key
                    # skip the overseer themselves
                    if member.id == ctx.author.id:
                        continue
                    if getattr(ow, "view_channel", False):
                        # only consider members who own a house
                        if self._get_house_for_user(member.id):
                            target_member = member
                            break

            # if we found a target member (overseer intended target), move them
            if target_member:
                ok, msg = await _move_member(target_member)
                await ctx.send(f"✅ {msg}" if ok else f"❌ {msg}")
                return

            # otherwise default to moving the caller
            ok, msg = await _move_member(ctx.author)
            await ctx.send(f"✅ {msg}" if ok else f"❌ {msg}")
            return

        # Token provided -> overseer-only actions
        if not self.is_overseer(ctx.author):
            await ctx.send("❌ Only overseers can move other players home")
            return

        t = token.strip()
        # `.home set` -> claim the house the player is currently in.
        # This can be used inside a role/alt/dead role channel: it will find the
        # player for that role channel, detect which house they currently occupy
        # (by explicit per-member overwrites), and set them as owner of that house.
        if t.lower() == "set":
            role_allowed = {"ROLES", "ALTS", "DEAD RC"}

            # Determine target member: if used in a role channel, find that channel's player
            target_member = None
            if ctx.channel.category and ctx.channel.category.name in role_allowed:
                # if mention provided, use it; otherwise prefer channel-associated player
                if ctx.message.mentions:
                    target_member = ctx.message.mentions[0]
                else:
                    knocks = self.bot.get_cog("KnocksCog")
                    if knocks and hasattr(knocks, "find_member_for_channel"):
                        target_member = await knocks.find_member_for_channel(ctx.channel)
                    # if still not found and caller is not overseer, default to caller
                    if not target_member and not self.is_overseer(ctx.author):
                        target_member = ctx.author
            else:
                # if used inside a house channel, only allow self-claim or mentioned target
                if ctx.channel.category and ctx.channel.category.name == "MANORS":
                    if ctx.message.mentions:
                        target_member = ctx.message.mentions[0]
                    else:
                        if self.is_overseer(ctx.author):
                            await __import__("mystery").mystery_send(ctx, "❌ Overseers must mention the player to set when using `.home set` in a manor channel")
                            return
                        target_member = ctx.author
                else:
                    await __import__("mystery").mystery_send(ctx, "❌ `.home set` must be used inside a role channel or a manor channel")
                    return

            if not target_member:
                await __import__("mystery").mystery_send(ctx, "❌ Could not determine player to set as owner")
                return

            # Find which house the target_member currently occupies (explicit overwrite)
            manors_category = discord.utils.get(ctx.guild.categories, name="MANORS")
            if not manors_category:
                await __import__("mystery").mystery_send(ctx, "❌ 'MANORS' category not found")
                return

            current_house = None
            for c in manors_category.text_channels:
                ow = c.overwrites.get(target_member)
                if ow and getattr(ow, "view_channel", False):
                    # ensure they can send messages in that house
                    if getattr(ow, "send_messages", True):
                        current_house = c
                        break

            if not current_house:
                await __import__("mystery").mystery_send(ctx, "❌ The player is not currently in any manor (or lacks explicit access)")
                return

            # set as owner
            try:
                self._add_owner(target_member.id, current_house.name)
            except Exception as e:
                logger.error(f"Error adding owner for {target_member}: {e}")
                await __import__("mystery").mystery_send(ctx, f"❌ Failed to add owner: {e}")
                return

            # Log and confirm
            try:
                log_ch = discord.utils.get(ctx.guild.text_channels, name="log-visits")
                if log_ch:
                    await log_ch.send(f"**Owner Added:** {target_member.display_name} (ID: {target_member.id}) | **Manor:** {current_house.mention} | **By:** {ctx.author.display_name} (ID: {ctx.author.id}) | **Method:** home set")
            except Exception:
                pass

            await __import__("mystery").mystery_send(ctx, f"✅ {target_member.display_name} is now owner of {current_house.mention}")
            return

        # Special: `.home all` -> move all Alive players who have houses back to their homes
        if t.lower() == "all":
            if not self.is_overseer(ctx.author):
                await __import__("mystery").mystery_send(ctx, "❌ Only overseers can move all players home")
                return

            manors_category = discord.utils.get(ctx.guild.categories, name="MANORS")
            if not manors_category:
                await __import__("mystery").mystery_send(ctx, "❌ 'MANORS' category not found")
                return

            alive_role = discord.utils.get(ctx.guild.roles, name="Alive")
            if not alive_role:
                await __import__("mystery").mystery_send(ctx, "❌ 'Alive' role not found")
                return

            alive_members = [m for m in ctx.guild.members if alive_role in m.roles]
            if not alive_members:
                await __import__("mystery").mystery_send(ctx, "❌ No Alive members found to move")
                return

            moved = 0
            errors = 0
            knocks = self.bot.get_cog("KnocksCog")
            for member in alive_members:
                try:
                    house_name = self._get_house_for_user(member.id)
                    if not house_name:
                        continue
                    ch = discord.utils.get(manors_category.text_channels, name=house_name)
                    if not ch:
                        continue

                    if knocks and hasattr(knocks, "move_member_to_house"):
                        try:
                            ok, err = await knocks.move_member_to_house(ctx.guild, member, ch, announce_leave=True, announce_join=True)
                            if ok:
                                moved += 1
                            else:
                                errors += 1
                        except Exception:
                            errors += 1
                    else:
                        # fallback: clear other overwrites and set this manor
                        for c in manors_category.text_channels:
                            ow = c.overwrites.get(member)
                            if ow and getattr(ow, "view_channel", False):
                                try:
                                    await c.set_permissions(member, overwrite=None, reason="Removed member-specific overwrites (home all)")
                                except Exception:
                                    pass
                        try:
                            await ch.set_permissions(member, view_channel=True, send_messages=True, reason="Moved to home (all)")
                            moved += 1
                        except Exception:
                            errors += 1
                except Exception:
                    errors += 1

            await ctx.send(f"✅ Moved {moved} Alive players home" + (f" ({errors} errors)" if errors else ""))
            return

        # Otherwise t is a manor identifier: when overseer uses inside a role channel, set that channel's player as owner of provided manor
        # resolve manor
        target_ch = self._resolve_house(ctx.guild, t)
        if not target_ch:
            await ctx.send("❌ Manor not found")
            return

        # ensure command used inside a role/alt/dead channel to target a player
        role_allowed = {"ROLES", "ALTS", "DEAD RC"}
        if not ctx.channel.category or ctx.channel.category.name not in role_allowed:
            await ctx.send("❌ To assign a player to a manor as owner, run this command inside the player's role/alt/dead channel")
            return

        # find player for this role channel
        knocks = self.bot.get_cog("KnocksCog")
        member = None
        if knocks and hasattr(knocks, "find_member_for_channel"):
            member = await knocks.find_member_for_channel(ctx.channel)
        if not member:
            await ctx.send("❌ Could not determine player for this channel to assign")
            return

        # move the member to the target house and add as owner
        if knocks and hasattr(knocks, "move_member_to_house"):
            knocks._last_move_initiator = ctx.author
            knocks._last_move_reason = ".home assign"
            try:
                ok, err = await knocks.move_member_to_house(ctx.guild, member, target_ch, announce_leave=True, announce_join=True)
            finally:
                knocks._last_move_initiator = None
                knocks._last_move_reason = None
        else:
            # fallback permission move
            prev = None
            manors_category = discord.utils.get(ctx.guild.categories, name="MANORS")
            if manors_category:
                for c in manors_category.text_channels:
                    ow = c.overwrites.get(member)
                    if ow and getattr(ow, "view_channel", False):
                        prev = c
                        try:
                            await c.set_permissions(member, overwrite=None, reason="Removed member-specific overwrites (assign)")
                        except Exception:
                            pass
            try:
                await target_ch.set_permissions(member, view_channel=True, send_messages=True, reason="Moved to assigned manor")
                ok, err = True, None
            except Exception as e:
                ok, err = False, str(e)

        if ok:
            try:
                self._add_owner(member.id, target_ch.name)
            except Exception:
                pass
            await ctx.send(f"✅ Assigned {member.display_name} to {target_ch.mention} and made them an owner")
        else:
            await ctx.send(f"❌ Failed to assign/move: {err}")
        return
        if t.lower() == "all":
            # Move all users who own a manor
            by_user = self.owners.get("by_user", {})
            if not by_user:
                await ctx.send("⚠️ No players with manors found to move")
                return
            results = []
            for uid, house in list(by_user.items()):
                try:
                    member = guild.get_member(int(uid))
                except Exception:
                    member = None
                if not member:
                    results.append((False, f"User {uid} not in guild"))
                    continue
                ok, msg = await _move_member(member)
                results.append((ok, msg))

            moved = [m for ok, m in results if ok]
            failed = [m for ok, m in results if not ok]
            out = []
            if moved:
                out.append(f"✅ Moved: {len(moved)}")
            if failed:
                out.append(f"⚠️ Failed: {len(failed)}")
            await ctx.send(" | ".join(out) if out else "⚠️ Nothing moved")
            return

        # Try resolve a member mention/mention-like token
        member = None
        if ctx.message.mentions:
            member = ctx.message.mentions[0]
        else:
            # attempt to convert via MemberConverter
            try:
                member = await commands.MemberConverter().convert(ctx, t)
            except Exception:
                member = None

        if not member:
            await ctx.send("❌ Could not resolve a member to move. Use a mention or `.home all`.")
            return

        ok, msg = await _move_member(member)
        await ctx.send(f"✅ {msg}" if ok else f"❌ {msg}")

    # optional overseer helpers to add/remove owners
    @owner.command(name="add")
    async def owner_add(self, ctx: commands.Context, user: discord.Member, *, house_token: str) -> None:
        if not self.is_overseer(ctx.author):
            await ctx.send("❌ Only overseers can add owners")
            return
        ch = self._resolve_house(ctx.guild, house_token.strip())
        if not ch:
            await ctx.send("❌ Manor not found")
            return
        self._add_owner(user.id, ch.name)
        await ctx.send(f"✅ Added {user.display_name} as owner of {ch.mention}")

    @owner.command(name="remove")
    async def owner_remove(self, ctx: commands.Context, user: discord.Member, *, house_token: Optional[str] = None) -> None:
        if not self.is_overseer(ctx.author):
            await ctx.send("❌ Only overseers can remove owners")
            return
        if house_token:
            ch = self._resolve_house(ctx.guild, house_token.strip())
            if not ch:
                await ctx.send("❌ Manor not found")
                return
            self._remove_owner(user.id, ch.name)
            await ctx.send(f"✅ Removed {user.display_name} from owners of {ch.mention}")
        else:
            self._remove_owner(user.id, None)
            await ctx.send(f"✅ Removed {user.display_name} as owner of their manor")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(HousesCog(bot))
