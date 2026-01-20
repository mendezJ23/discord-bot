import discord
from discord.ext import commands
import logging
import re
import mystery

logger = logging.getLogger("discord_bot")

class SwitchCog(commands.Cog):
    """Swap a player and their sponsor: swap `Alive` and `Sponsor` roles and reassign role channel."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.command(name="switch", aliases=["swap"])
    @commands.has_permissions(administrator=True)
    async def switch(self, ctx: commands.Context) -> None:
        """Used inside a role channel: makes the player become the sponsor and the sponsor become the player (swap Alive <-> Sponsor).

        Behavior:
        - Detect the player for the current channel (KnocksCog.find_member_for_channel or channel overwrites).
        - Detect the sponsor for that player (RoleChannelsCog.find_sponsor_for_member or channel overwrites).
        - Swap roles: player loses `Alive` and gains `Sponsor`; sponsor loses `Sponsor` and gains `Alive`.
        - Reassign the role channel so the new player (previous sponsor) becomes the channel owner (give view/send), and remove view/send for the old player.
        """
        guild = ctx.guild
        channel = ctx.channel

        # Ensure we're in a role channel (category name ROLES)
        if not channel.category or channel.category.name != "ROLES":
            await __import__("mystery").mystery_send(ctx, "❌ This command must be used inside a role channel (inside the ROLES category).")
            return

        # Find the player for this channel
        player = None
        knocks = self.bot.get_cog("KnocksCog")
        if knocks and hasattr(knocks, "find_member_for_channel"):
            try:
                player = await knocks.find_member_for_channel(channel)
            except Exception:
                player = None

        if not player:
            # fallback: look for a member-specific overwrite with view=True
            for target, ow in channel.overwrites.items():
                try:
                    if isinstance(target, discord.Member) and getattr(ow, "view_channel", False):
                        player = target
                        break
                except Exception:
                    continue

        if not player:
            await __import__("mystery").mystery_send(ctx, "❌ Could not determine the player for this role channel.")
            return

        # Find sponsors for this player (may be multiple)
        sponsors = []
        role_cog = self.bot.get_cog("RoleChannelsCog")
        if role_cog and hasattr(role_cog, "find_sponsor_for_member"):
            try:
                sponsors = await role_cog.find_sponsor_for_member(guild, player) or []
            except Exception:
                sponsors = []

        # If none found, fallback to similar single-sponsor detection (preserve behaviour)
        if not sponsors:
            sponsor_role = discord.utils.get(guild.roles, name="Sponsor")
            if sponsor_role:
                # First try any other member with an explicit overwrite granting view access
                for target, ow in channel.overwrites.items():
                    try:
                        if not isinstance(target, discord.Member) or target.id == player.id:
                            continue
                        if getattr(ow, "view_channel", False):
                            sponsors = [target]
                            break
                    except Exception:
                        continue

                # Next prefer members who actually have the Sponsor role and view access
                if not sponsors:
                    for target, ow in channel.overwrites.items():
                        try:
                            if not isinstance(target, discord.Member) or target.id == player.id:
                                continue
                            if sponsor_role in target.roles and getattr(ow, "view_channel", False):
                                sponsors = [target]
                                break
                        except Exception:
                            continue

                # If still not found, check any guild member with Sponsor role who can view this channel
                if not sponsors:
                    for m in guild.members:
                        try:
                            if m.id == player.id:
                                continue
                            if sponsor_role in m.roles and channel.permissions_for(m).view_channel:
                                sponsors = [m]
                                break
                        except Exception:
                            continue

        if not sponsors:
            await __import__("mystery").mystery_send(ctx, "❌ Could not find a sponsor for the player in this role channel.")
            return

        # remove any accidental self-reference
        sponsors = [s for s in sponsors if s and s.id != player.id]
        if not sponsors:
            await __import__("mystery").mystery_send(ctx, "❌ Player and sponsor are the same member; cannot switch.")
            return

        # Roles
        alive_role = discord.utils.get(guild.roles, name="Alive")
        sponsor_role = discord.utils.get(guild.roles, name="Sponsor")

        if not alive_role or not sponsor_role:
            await __import__("mystery").mystery_send(ctx, "❌ Required roles 'Alive' or 'Sponsor' not found in this guild.")
            return

        # Swap roles
        try:
            # remove Alive from player if they have it, add Sponsor
            if alive_role in player.roles:
                await player.remove_roles(alive_role, reason="Switched to sponsor via .switch")
            if sponsor_role not in player.roles:
                await player.add_roles(sponsor_role, reason="Switched to sponsor via .switch")

            # remove Sponsor from all sponsors, add Alive
            for s in sponsors:
                try:
                    if sponsor_role in s.roles:
                        await s.remove_roles(sponsor_role, reason="Switched to player via .switch")
                    if alive_role not in s.roles:
                        await s.add_roles(alive_role, reason="Switched to player via .switch")
                except Exception:
                    pass
        except Exception as e:
            sponsor_names = ", ".join([s.display_name for s in sponsors]) if sponsors else "<none>"
            logger.error(f"Error swapping roles between {player} and {sponsor_names}: {e}")
            await __import__("mystery").mystery_send(ctx, f"❌ Failed to swap roles: {e}")
            return

        # Reassign role channel ownership: give sponsor (now player) access.
        # Ensure the member who becomes Sponsor (old player) retains access as Sponsor
        try:
            # grant all new players (previous sponsors) view/send on this channel
            for s in sponsors:
                try:
                    await channel.set_permissions(s, view_channel=True, send_messages=True, reason="Switched to be player via .switch")
                except Exception:
                    pass

            # preserve old player's access so they can still view/send as Sponsor
            try:
                await channel.set_permissions(player, view_channel=True, send_messages=True, reason="Retain access after switching to Sponsor")
            except Exception:
                pass
        except Exception as e:
            logger.warning(f"Could not update channel overwrites during switch: {e}")

        # Rename the role channel to reflect the new player and sponsor: {player}-{sponsor}
        try:
            # sponsor is now the player; player is now the sponsor
            def _clean(name: str) -> str:
                n = name.lower()
                n = re.sub(r"\s+", "-", n)
                n = re.sub(r"[^a-z0-9\-]", "", n)
                return n[:90]

            # For naming, choose the first sponsor as representative if multiple
            rep_sponsor = sponsors[0]
            new_player_part = _clean(rep_sponsor.display_name)
            new_sponsor_part = _clean(player.display_name)
            new_name = f"{new_player_part}-{new_sponsor_part}" if new_player_part and new_sponsor_part else (new_player_part or new_sponsor_part or channel.name)
            # Debug: report computed names so we can diagnose rename failures
            try:
                await __import__("mystery").mystery_send(ctx, f"🔧 Debug rename: current='{channel.name}' computed='{new_name}'")
            except Exception:
                pass
            if channel.name != new_name:
                try:
                    # check bot permissions
                    me = guild.me or guild.get_member(self.bot.user.id)
                    if not me or not getattr(me.guild_permissions, "manage_channels", False):
                        msg = f"❌ Cannot rename channel: bot lacks Manage Channels permission (tried {channel.name} -> {new_name})"
                        logger.warning(msg)
                        await __import__("mystery").mystery_send(ctx, msg)
                    else:
                        await channel.edit(name=new_name, reason="Rename role channel after .switch/.swap")
                        logger.info(f"Renamed channel {channel.name} to {new_name}")
                        await __import__("mystery").mystery_send(ctx, f"🔁 Renamed role channel to {new_name}")
                except Exception as e:
                    logger.warning(f"Could not rename channel {channel.name} to {new_name}: {e}")
                    try:
                        await __import__("mystery").mystery_send(ctx, f"❌ Could not rename channel: {e}")
                    except Exception:
                        pass
        except Exception:
            pass
        # Final summary message
        try:
            sponsor_names = ", ".join([s.display_name for s in sponsors])
            await __import__("mystery").mystery_send(
                ctx,
                f"🔁 Switched roles: {player.display_name} → Sponsor, {sponsor_names} → Alive. Role channel reassigned to {rep_sponsor.display_name}.",
            )
        except Exception:
            pass


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(SwitchCog(bot))
