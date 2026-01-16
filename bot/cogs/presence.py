import discord
from discord.ext import commands
from typing import Optional
import logging

logger = logging.getLogger("discord_bot")


class PresenceCog(commands.Cog):
    """Provides `.who` and `.where` utilities.

    - `.who` shows everyone with send permission in the current channel (excluding overseers).
      Overseers may pass a manor token to inspect any manor channel: `.who 3` or `.who manor-3`.

    - `.where` (usable inside role channels by players) shows the current manor location of the player.
      Overseers can pass an argument to check any player: `.where playername` or mention.
    """

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    def is_overseer(self, member: discord.Member) -> bool:
        if not member or not hasattr(member, "guild_permissions"):
            return False
        if member.guild_permissions.administrator or member.guild_permissions.manage_guild:
            return True
        for r in member.roles:
            if r.name.lower() == "overseer":
                return True
        return False

    async def _resolve_channel(self, ctx: commands.Context, token: str) -> Optional[discord.TextChannel]:
        # prefer ManorsCog resolver if available
        manors = self.bot.get_cog("ManorsCog")
        if manors and hasattr(manors, "_resolve_manor"):
            ch = manors._resolve_manor(ctx.guild, token)
            if ch:
                return ch
        # fallback: try mention or name
        if token.startswith("<#") and token.endswith(">"):
            try:
                cid = int(token[2:-1])
                return ctx.guild.get_channel(cid)
            except Exception:
                pass
        # try numeric manor id style
        for c in ctx.guild.text_channels:
            if c.name.lower() == token.lower() or c.name.lower().endswith(token.lower()):
                return c
        return None

    @commands.command(name="who")
    async def who(self, ctx: commands.Context, *, token: Optional[str] = None) -> None:
        """Show everyone with write access in this channel (excludes overseers).

        Overseers may pass a manor identifier to inspect that manor: `.who 3` or `.who manor-3`.
        """
        guild = ctx.guild
        if not guild:
            return

        target_ch: Optional[discord.TextChannel] = None
        if token:
            if not self.is_overseer(ctx.author):
                await __import__("mystery").mystery_send(ctx, "❌ Only overseers can query other channels")
                return
            target_ch = await self._resolve_channel(ctx, token.strip())
            if not target_ch:
                await __import__("mystery").mystery_send(ctx, "❌ Channel/manor not found")
                return
        else:
            target_ch = ctx.channel

        people = []
        for m in guild.members:
            if m.bot:
                continue
            if self.is_overseer(m):
                continue
            try:
                perms = target_ch.permissions_for(m)
            except Exception:
                continue
            if perms.send_messages:
                people.append(m.mention)

        if not people:
            await __import__("mystery").mystery_send(ctx, "⚠️ No non-overseer members have write access in this channel")
            return

        out = ", ".join(people)
        await __import__("mystery").mystery_send(ctx, f"Players in {target_ch.mention}: {out}")

    @commands.command(name="where")
    async def where(self, ctx: commands.Context, *, token: Optional[str] = None) -> None:
        """Show the current manor location of the player.

        - Players: use inside their role channel to check their location (`.where`).
        - Overseers: may pass a player argument to check any player (`.where @Player` or `.where #role-channel`).
        """
        guild = ctx.guild
        if not guild:
            return

        role_allowed = {"ROLES", "ALTS", "DEAD RC"}

        # resolve target member
        member: Optional[discord.Member] = None
        if token:
            if not self.is_overseer(ctx.author):
                await __import__("mystery").mystery_send(ctx, "❌ Only overseers can query other players' locations")
                return
            # try mentions first
            if ctx.message.mentions:
                member = ctx.message.mentions[0]
            # try channel mentions for role channels
            elif ctx.message.channel_mentions:
                target_ch = ctx.message.channel_mentions[0]
                # Try to find a member with view access in this channel
                for m in guild.members:
                    try:
                        perms = target_ch.permissions_for(m)
                        if perms.view_channel and not m.bot:
                            member = m
                            break
                    except Exception:
                        continue
                if not member:
                    await __import__("mystery").mystery_send(ctx, f"❌ Could not find a member with access to {target_ch.mention}")
                    return
            else:
                # try MemberConverter
                try:
                    member = await commands.MemberConverter().convert(ctx, token.strip())
                except Exception:
                    member = None
            if not member:
                await __import__("mystery").mystery_send(ctx, "❌ Could not resolve member")
                return
        else:
            # no token -> must be used inside role channel to check caller.
            # If caller is an overseer, try to resolve the player associated with
            # this role channel and report *their* location instead.
            if not ctx.channel.category or ctx.channel.category.name not in role_allowed:
                await __import__("mystery").mystery_send(ctx, "❌ Use `.where` inside a role/alt/dead channel to check that player's location")
                return

            if self.is_overseer(ctx.author):
                # try KnocksCog helper first
                knocks = self.bot.get_cog("KnocksCog")
                member = None
                if knocks and hasattr(knocks, "find_member_for_channel"):
                    member = await knocks.find_member_for_channel(ctx.channel)
                else:
                    # fallback: inspect explicit member overwrites on the channel
                    for target, ow in getattr(ctx.channel, "overwrites", {}).items():
                        try:
                            is_member = isinstance(target, discord.Member)
                        except Exception:
                            is_member = False
                        if not is_member:
                            continue
                        if getattr(ow, "view_channel", False):
                            member = target
                            break

                if not member:
                    await __import__("mystery").mystery_send(ctx, "❌ Could not determine player for this channel")
                    return
            else:
                member = ctx.author

        # find manor where member has explicit send/view permission
        manors_category = discord.utils.get(guild.categories, name="MANORS")
        if not manors_category:
            await __import__("mystery").mystery_send(ctx, "❌ 'MANORS' category not found")
            return

        loc = None
        for c in manors_category.text_channels:
            ow = c.overwrites.get(member)
            if ow and getattr(ow, "view_channel", False) and getattr(ow, "send_messages", True):
                loc = c
                break

        if not loc:
            await __import__("mystery").mystery_send(ctx, f"⚠️ {member.display_name} is not currently in any manor")
            return

        await __import__("mystery").mystery_send(ctx, f"📍 {member.display_name} is currently in {loc.mention}")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(PresenceCog(bot))
