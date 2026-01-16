import discord
from discord.ext import commands
import logging
from typing import Optional

logger = logging.getLogger("discord_bot")


class KnocksCog(commands.Cog):
    """Implements .knock, .move and .stealth commands and handles open/refuse replies."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        # pending knock msg id -> info
        self.pending = {}

    def is_overseer(self, member: discord.Member) -> bool:
        if not member or not hasattr(member, "guild_permissions"):
            return False
        if member.guild_permissions.administrator or member.guild_permissions.manage_guild:
            return True
        for r in member.roles:
            if r.name.lower() == "overseer":
                return True
        return False

    def resolve_manor(self, guild: discord.Guild, token: str) -> Optional[discord.TextChannel]:
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

        # digit -> manor-N
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

        # fallback raw match
        for c in manors_category.text_channels:
            if c.name.lower() == token.lower() or c.name.lower() == name:
                return c
        return None

    # Backwards-compatible alias: some code expects `resolve_house`
    def resolve_house(self, guild: discord.Guild, token: str) -> Optional[discord.TextChannel]:
        return self.resolve_manor(guild, token)

    async def find_member_for_channel(self, channel: discord.TextChannel) -> Optional[discord.Member]:
        # Prefer the member who currently has the Alive role and can view this channel.
        # This keeps identification accurate after role swaps (Alive <-> Sponsor).
        guild = channel.guild
        alive_role = discord.utils.get(guild.roles, name="Alive")
        if alive_role:
            for m in guild.members:
                try:
                    if alive_role in m.roles and channel.permissions_for(m).view_channel:
                        return m
                except Exception:
                    continue

        # Fallback: Find first member who has explicit view permission on this role channel
        for target, ow in channel.overwrites.items():
            if isinstance(target, discord.Member):
                if getattr(ow, 'view_channel', False) is True:
                    return target
        return None

    async def move_member_to_house(self, guild: discord.Guild, member: discord.Member, target_house: discord.TextChannel, announce_leave: bool = True, announce_join: bool = True):
        """Move `member` to `target_house` and optionally announce.

        Optional keyword-only params:
        - by: discord.Member who initiated the move (for logging)
        - reason: short string describing the reason
        """
        manors_category = discord.utils.get(guild.categories, name="MANORS")
        if not manors_category:
            return False, "MANORS category not found"

        # remove from other manors
        prev = None
        for ch in manors_category.text_channels:
            if member in ch.overwrites and ch.overwrites[member].view_channel:
                prev = ch
                try:
                    await ch.set_permissions(member, overwrite=None, reason="Removed member-specific overwrites (move)")
                except Exception as e:
                    logger.warning(f"Could not remove permissions for {member} in {ch.name}: {e}")

        # grant access to target
        try:
            await target_house.set_permissions(member, view_channel=True, send_messages=True, reason="Moved/joined manor")
        except Exception as e:
            logger.error(f"Could not set permissions for {member} in {target_house.name}: {e}")
            return False, str(e)

        # If this member has a sponsor, move the sponsor as well so they follow.
        try:
            role_channels = self.bot.get_cog("RoleChannelsCog")
            sponsors = []
            if role_channels and hasattr(role_channels, "find_sponsor_for_member"):
                try:
                    sponsors = await role_channels.find_sponsor_for_member(guild, member) or []
                except Exception:
                    sponsors = []
        except Exception:
            sponsors = []

        if sponsors:
            for sponsor in sponsors:
                if not sponsor or sponsor.id == member.id:
                    continue
                # remove sponsor from other manors (clear member-specific overwrites)
                for ch in manors_category.text_channels:
                    try:
                        if sponsor in ch.overwrites and getattr(ch.overwrites[sponsor], "view_channel", False):
                            await ch.set_permissions(sponsor, overwrite=None, reason="Removed sponsor-specific overwrites (move)")
                    except Exception:
                        pass
                # grant sponsor access to target
                try:
                    await target_house.set_permissions(sponsor, view_channel=True, send_messages=True, reason=f"Sponsor follows {member.display_name}")
                except Exception:
                    pass

        # announce
        try:
            if announce_leave and prev:
                await prev.send(f"📤 {member.display_name} has left the manor.")
            if announce_join:
                await target_house.send(f"📥 {member.display_name} has joined the manor.")
        except Exception:
            # non-fatal
            pass

        # Log the move in #log-visits if possible
        try:
            log_ch = discord.utils.get(guild.text_channels, name="log-visits")
            if log_ch:
                mover = getattr(member, "display_name", str(member))
                by = None
                # try to find initiator in stack or kwargs (best-effort)
                # callers may set `self._last_move_initiator` temporarily; otherwise unknown
                initiator = getattr(self, "_last_move_initiator", None)
                reason = getattr(self, "_last_move_reason", None)
                parts = []
                parts.append(f"**Move:** {member.display_name} (ID: {member.id})")
                if initiator and isinstance(initiator, discord.Member):
                    parts.append(f"**By:** {initiator.display_name} (ID: {initiator.id})")
                if prev:
                    parts.append(f"**From:** {prev.mention if hasattr(prev, 'mention') else getattr(prev, 'name', str(prev))}")
                parts.append(f"**To:** {target_house.mention}")
                if reason:
                    parts.append(f"**Reason:** {reason}")
                await log_ch.send(" | ".join(parts))
        except Exception:
            # non-fatal
            pass

        return True, None

    @commands.command(name="knock")
    async def knock(self, ctx: commands.Context, *, args: str) -> None:
        """Knock on a manor. Optional leading enchantments: 'stealth' and/or 'forced'.

        Examples:
        - .knock manor-2
        - .knock stealth manor-2
        - .knock stealth forced manor-2

        Overseers can trigger a knock on behalf of the player in the channel.
        If enchantments are provided they will be consumed immediately and the
        knock will be executed (forced/stealth move). A normal knock posts a
        narration and uses one visit when opened.
        """
        if not ctx.guild:
            return

        allowed = {"ROLES", "ALTS", "DEAD RC"}
        if not ctx.channel.category or ctx.channel.category.name not in allowed:
            await __import__("mystery").mystery_send(ctx, "❌ .knock can only be used inside channels in categories ROLES, ALTS or DEAD RC")
            return

        raw = args.strip()
        if not raw:
            await __import__("mystery").mystery_send(ctx, "❌ Usage: .knock [stealth|forced ...] <target>")
            return

        # tokenize, allow commas and braces
        toks = [t.strip() for t in raw.replace(',', ' ').replace('{', ' ').replace('}', ' ').split() if t.strip()]
        enchants = []
        while toks and toks[0].lower() in ("stealth", "forced"):
            enchants.append(toks.pop(0).lower())

        target = " ".join(toks).strip()
        if not target:
            await __import__("mystery").mystery_send(ctx, "❌ No target manor specified.")
            return

        # decide which member is knocking
        initiator_is_overseer = self.is_overseer(ctx.author)
        if initiator_is_overseer:
            member = await self.find_member_for_channel(ctx.channel)
            if not member:
                await __import__("mystery").mystery_send(ctx, "❌ Could not determine player for this channel to knock on their behalf")
                return
        else:
            member = ctx.author

        # resolve target channel
        target_ch = self.resolve_house(ctx.guild, target.strip())
        if not target_ch:
            await __import__("mystery").mystery_send(ctx, "❌ Target manor not found")
            return

        visit_cog = self.bot.get_cog("VisitCountCog")

        # If enchantments present: consume them and perform immediate move
        if enchants:
            consumed = {}
            ok = True
            initiator_is_overseer = self.is_overseer(ctx.author)
            for e in enchants:
                # Overseers may apply enchantments without consuming inventory
                if initiator_is_overseer:
                    got = True
                else:
                    if visit_cog:
                        try:
                            got = visit_cog.consume_visit(ctx.guild.id, member.id, e)
                        except Exception:
                            got = False
                    else:
                        got = True
                consumed[e] = got
                if not got:
                    ok = False

            if not ok:
                missing = ", ".join([e for e, v in consumed.items() if not v])
                await __import__("mystery").mystery_send(ctx, f"❌ {member.display_name} lacks required enchantment(s): {missing}")
                return

            # determine announce flags (stealth suppresses narrations)
            announce = True
            if "stealth" in enchants:
                announce = False

            # perform move
            self._last_move_initiator = ctx.author
            self._last_move_reason = f".knock with enchantments: {', '.join(enchants)}"
            try:
                ok_move, err = await self.move_member_to_house(ctx.guild, member, target_ch, announce_leave=announce, announce_join=announce)
                if not ok_move and visit_cog and not initiator_is_overseer:
                    # refund consumed enchantments on failure
                    for e in enchants:
                        try:
                            visit_cog.add_visits(ctx.guild.id, member.id, e, 1)
                        except Exception:
                            pass
            finally:
                self._last_move_initiator = None
                self._last_move_reason = None

            if ok_move:
                await __import__("mystery").mystery_send(ctx, f"✅ Knock (enchanted) executed: moved {member.display_name} to {target_ch.mention}")
            else:
                await __import__("mystery").mystery_send(ctx, f"❌ Enchanted knock failed: {err}")

            return

        # No enchantments: behave like a standard knock (post narration, pending open/refuse)
        # ensure player has a visit for current phase
        phase = "night"
        try:
            if visit_cog:
                phase = visit_cog.get_phase(ctx.guild.id)
        except Exception:
            phase = "night"

        if visit_cog and not initiator_is_overseer and not visit_cog.has_visit(ctx.guild.id, member.id, phase):
            await __import__("mystery").mystery_send(ctx, f"❌ {member.display_name} has no {phase} visits remaining.")
            return

        # ping roles
        alive = discord.utils.get(ctx.guild.roles, name="Alive")
        sponsor = discord.utils.get(ctx.guild.roles, name="Sponsor")
        mentions = []
        if alive:
            mentions.append(alive.mention)
        if sponsor:
            mentions.append(sponsor.mention)
        mention_str = " ".join(mentions) if mentions else ""

        narr = f"🔔 A knock: {member.display_name} is knocking! {mention_str}\nReply to this message with 'open' or 'refuse'."
        try:
            msg = await target_ch.send(narr)
            # track pending (mark if initiated by overseer so opening won't consume visits)
            self.pending[msg.id] = {
                "origin_channel": ctx.channel.id,
                "player_id": member.id,
                "target_id": target_ch.id,
                "initiator_is_overseer": initiator_is_overseer,
            }
            await __import__("mystery").mystery_send(ctx, f"✅ Knock sent to {target_ch.mention}")
        except Exception as e:
            logger.error(f"Error sending knock narration: {e}")
            await __import__("mystery").mystery_send(ctx, f"❌ Error sending knock: {e}")

    @commands.command(name="forced")
    async def forced(self, ctx: commands.Context, *, target: str) -> None:
        """Deprecated wrapper: use `.knock forced <target>`. Delegates to `.knock`."""
        if not ctx.guild:
            return
        try:
            await __import__("mystery").mystery_send(ctx, "⚠️ Deprecated command: use `.knock forced <target>`; delegating...")
        except Exception:
            pass
        await self.knock(ctx, args=f"forced {target}")

    @commands.command(name="move")
    @commands.has_permissions(administrator=True)
    async def move(self, ctx: commands.Context, *, target: str) -> None:
        """Alias for .forced (admin-only): move the player immediately to target manor (announces leave/join)."""
        try:
            await __import__("mystery").mystery_send(ctx, "⚠️ Deprecated command: use `.knock forced <target>`; delegating...")
        except Exception:
            pass
        await self.knock(ctx, args=f"forced {target}")

    @commands.command(name="stealth")
    async def stealth(self, ctx: commands.Context, *, target: str) -> None:
        """Deprecated wrapper: use `.knock stealth <target>`. Delegates to `.knock`."""
        if not ctx.guild:
            return
        try:
            await __import__("mystery").mystery_send(ctx, "⚠️ Deprecated command: use `.knock stealth <target>`; delegating...")
        except Exception:
            pass
        await self.knock(ctx, args=f"stealth {target}")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        # ignore bot messages
        if message.author.bot:
            return
        if not message.reference or not message.reference.message_id:
            return
        ref = message.reference.message_id
        info = self.pending.get(ref)
        if not info:
            return

        # only allow replies inside the target manor channel
        if message.channel.id != info.get("target_id"):
            return

        content = message.content.lower().strip()
        if "open" in content:
            # open the knock: move player
            guild = message.guild
            player = guild.get_member(info.get("player_id")) if guild else None
            target_ch = guild.get_channel(info.get("target_id")) if guild else None
            origin_ch = guild.get_channel(info.get("origin_channel")) if guild else None
            if not player or not target_ch:
                await message.channel.send("❌ Cannot resolve player or target for this knock.")
                self.pending.pop(ref, None)
                return

            # consume a visit (based on guild phase) then perform move
            visit_cog = self.bot.get_cog("VisitCountCog")
            phase = "night"
            try:
                if visit_cog:
                    phase = visit_cog.get_phase(guild.id)
            except Exception:
                phase = "night"

            if visit_cog:
                ok_consume = visit_cog.consume_visit(guild.id, player.id, phase)
                if not ok_consume:
                    await message.channel.send(f"❌ {player.display_name} has no {phase} visits remaining to open the knock.")
                    self.pending.pop(ref, None)
                    return

            # announce opening and perform move
            await message.channel.send(f"✅ The knock is opened by {message.author.display_name}.")
            self._last_move_initiator = message.author
            self._last_move_reason = "knock opened"
            try:
                ok, err = await self.move_member_to_house(guild, player, target_ch, announce_leave=True, announce_join=True)
            finally:
                self._last_move_initiator = None
                self._last_move_reason = None

            if ok:
                if origin_ch:
                    await origin_ch.send(f"🔔 Your knock on {target_ch.mention} was opened. {player.display_name} moved.")
            else:
                await message.channel.send(f"❌ Failed to move: {err}")

            self.pending.pop(ref, None)
            return

        if "refuse" in content:
            guild = message.guild
            player = guild.get_member(info.get("player_id")) if guild else None
            target_ch = guild.get_channel(info.get("target_id")) if guild else None
            origin_ch = guild.get_channel(info.get("origin_channel")) if guild else None
            await message.channel.send(f"⛔ The knock was refused by {message.author.display_name}.")
            if origin_ch and player:
                await origin_ch.send(f"🔔 Your knock on {target_ch.mention} was refused.")
            self.pending.pop(ref, None)
            return


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(KnocksCog(bot))
