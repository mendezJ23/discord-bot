import discord
from discord.ext import commands
import logging
from pathlib import Path
import json
from typing import Optional

logger = logging.getLogger("discord_bot")

DATA_FILE = Path(__file__).resolve().parents[1] / "lawsuit.json"


def _load_data() -> dict:
    if not DATA_FILE.exists():
        return {"guilds": {}}
    try:
        with DATA_FILE.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"guilds": {}}


def _save_data(data: dict) -> None:
    try:
        with DATA_FILE.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Failed to save lawsuit data: {e}")


class LawsuitCog(commands.Cog):
    """Handle lawsuits: .sue, .prosecution, .defense, .endcase and related behavior."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.data = _load_data()

    def _guild_data(self, guild: discord.Guild) -> dict:
        g = self.data.setdefault("guilds", {})
        return g.setdefault(str(guild.id), {"active_case": None, "dead_from_cases": [], "blocked_users": []})

    def _is_overseer(self, member: discord.Member) -> bool:
        if not member or not hasattr(member, "guild_permissions"):
            return False
        if member.guild_permissions.administrator or member.guild_permissions.manage_guild:
            return True
        for r in member.roles:
            if r.name.lower() == "overseer":
                return True
        return False

    async def _find_rc_channel_for(self, guild: discord.Guild, member: discord.Member) -> Optional[discord.TextChannel]:
        roles_cat = discord.utils.get(guild.categories, name="ROLES")
        if not roles_cat:
            return None
        for ch in roles_cat.text_channels:
            ow = ch.overwrites.get(member)
            if ow and getattr(ow, "view_channel", False):
                return ch
        return None

    @commands.command(name="sue")
    async def sue(self, ctx: commands.Context, defendant: discord.Member = None) -> None:
        """Start a lawsuit against a player. Use in the 🫵│lawsuit channel."""
        guild = ctx.guild
        if not guild:
            return
        chan_name = ctx.channel.name.lower() if ctx.channel and getattr(ctx.channel, 'name', None) else ""
        if "lawsuit" not in chan_name:
            await __import__("mystery").mystery_send(ctx, "❌ Use .sue in the 🫵│lawsuit channel")
            return
        if defendant is None:
            await __import__("mystery").mystery_send(ctx, "❌ Mention the player you wish to sue: `.sue @player`")
            return

        # Cannot sue yourself
        if defendant.id == ctx.author.id:
            await __import__("mystery").mystery_send(ctx, "❌ You cannot sue yourself")
            return

        # Only allow suing players who currently have the Alive role
        alive_role = discord.utils.get(guild.roles, name="Alive")
        if not alive_role:
            await __import__("mystery").mystery_send(ctx, "❌ 'Alive' role not found; cannot perform lawsuits")
            return
        if alive_role not in defendant.roles:
            await __import__("mystery").mystery_send(ctx, "❌ You may only sue players with the @Alive role")
            return

        gd = self._guild_data(guild)
        # blocked users cannot use lawsuit commands or be sued
        blocked = gd.setdefault("blocked_users", [])
        if str(ctx.author.id) in blocked:
            await __import__("mystery").mystery_send(ctx, "❌ You are blocked from using the lawsuit module")
            return
        if gd.get("active_case"):
            await __import__("mystery").mystery_send(ctx, "❌ A case is already ongoing in this guild")
            return

        dead_list = gd.setdefault("dead_from_cases", [])
        if str(defendant.id) in dead_list:
            await __import__("mystery").mystery_send(ctx, "❌ This player has already died from a case and cannot be sued")
            return
        if str(defendant.id) in blocked:
            await __import__("mystery").mystery_send(ctx, "❌ This player is blocked from being involved in lawsuits")
            return

        plaintiff = ctx.author

        # Ensure roles exist
        plaintiff_role = discord.utils.get(guild.roles, name="Plaintiff")
        defendant_role = discord.utils.get(guild.roles, name="Defendant")
        try:
            if not plaintiff_role:
                plaintiff_role = await guild.create_role(name="Plaintiff", colour=discord.Colour(int("dfca46", 16)))
            if not defendant_role:
                defendant_role = await guild.create_role(name="Defendant", colour=discord.Colour(int("652dd5", 16)))
        except Exception as e:
            logger.warning(f"Could not ensure Plaintiff/Defendant roles: {e}")

        # Assign roles to plaintiff and defendant if possible
        try:
            if plaintiff_role:
                await plaintiff.add_roles(plaintiff_role, reason="Assigned as Plaintiff")
            if defendant_role:
                await defendant.add_roles(defendant_role, reason="Assigned as Defendant")
        except Exception:
            pass

        # create thread in objection channel
        objection_ch = None
        for ch in guild.text_channels:
            try:
                if "objection" in ch.name.lower():
                    objection_ch = ch
                    break
            except Exception:
                continue
        if not objection_ch:
            try:
                objection_ch = await guild.create_text_channel("👨‍⚖️│objection")
            except Exception:
                pass

        thread_id = None
        if objection_ch:
            try:
                msg = await objection_ch.send(f"⚖️ Case opened: {plaintiff.mention} vs {defendant.mention}")
                try:
                    thread = await msg.create_thread(name=f"Case: {plaintiff.display_name} vs {defendant.display_name}")
                    thread_id = thread.id
                except Exception:
                    thread_id = None
            except Exception:
                pass

        gd["active_case"] = {
            "plaintiff": str(plaintiff.id),
            "defendant": str(defendant.id),
            "prosecution": [],
            "defense": [],
            "thread_id": thread_id,
        }
        _save_data(self.data)

        await __import__("mystery").mystery_send(ctx, f"✅ Case opened: {plaintiff.mention} has sued {defendant.mention}. Attorneys may join with `.prosecution` or `.defense` (max 3 per side).")

    @commands.command(name="prosecution")
    async def prosecution(self, ctx: commands.Context) -> None:
        """Join the prosecution (plaintiff's) team for the current case. Use in 🫵│lawsuit."""
        guild = ctx.guild
        chan_name = ctx.channel.name.lower() if ctx.channel and getattr(ctx.channel, 'name', None) else ""
        if "lawsuit" not in chan_name:
            await __import__("mystery").mystery_send(ctx, "❌ Use this command in the 🫵│lawsuit channel")
            return
        gd = self._guild_data(guild)
        blocked = gd.setdefault("blocked_users", [])
        if str(ctx.author.id) in blocked:
            await __import__("mystery").mystery_send(ctx, "❌ You are blocked from using the lawsuit module")
            return
        case = gd.get("active_case")
        if not case:
            await __import__("mystery").mystery_send(ctx, "❌ No active case to join")
            return
        uid = str(ctx.author.id)
        if uid == case.get("plaintiff") or uid == case.get("defendant"):
            await __import__("mystery").mystery_send(ctx, "⚠️ The plaintiff/defendant cannot join a team as attorney")
            return
        if uid in case.get("prosecution", []) or uid in case.get("defense", []):
            await __import__("mystery").mystery_send(ctx, "⚠️ You have already joined this case")
            return
        if len(case.get("prosecution", [])) >= 3:
            await __import__("mystery").mystery_send(ctx, "⚠️ Prosecution team is full (3)")
            return
        case["prosecution"].append(uid)
        _save_data(self.data)
        await __import__("mystery").mystery_send(ctx, f"✅ {ctx.author.mention} joined the prosecution team")

    @commands.command(name="defense")
    async def defense(self, ctx: commands.Context) -> None:
        """Join the defense (defendant's) team for the current case. Use in 🫵│lawsuit."""
        guild = ctx.guild
        chan_name = ctx.channel.name.lower() if ctx.channel and getattr(ctx.channel, 'name', None) else ""
        if "lawsuit" not in chan_name:
            await __import__("mystery").mystery_send(ctx, "❌ Use this command in the 🫵│lawsuit channel")
            return
        gd = self._guild_data(guild)
        blocked = gd.setdefault("blocked_users", [])
        if str(ctx.author.id) in blocked:
            await __import__("mystery").mystery_send(ctx, "❌ You are blocked from using the lawsuit module")
            return
        case = gd.get("active_case")
        if not case:
            await __import__("mystery").mystery_send(ctx, "❌ No active case to join")
            return
        uid = str(ctx.author.id)
        if uid == case.get("plaintiff") or uid == case.get("defendant"):
            await __import__("mystery").mystery_send(ctx, "⚠️ The plaintiff/defendant cannot join a team as attorney")
            return
        if uid in case.get("prosecution", []) or uid in case.get("defense", []):
            await __import__("mystery").mystery_send(ctx, "⚠️ You have already joined this case")
            return
        if len(case.get("defense", [])) >= 3:
            await __import__("mystery").mystery_send(ctx, "⚠️ Defense team is full (3)")
            return
        case["defense"].append(uid)
        _save_data(self.data)
        await __import__("mystery").mystery_send(ctx, f"✅ {ctx.author.mention} joined the defense team")

    @commands.command(name="endcase")
    async def endcase(self, ctx: commands.Context, winner: str = None) -> None:
        """Overseer-only: end the current case in favor of `prosecution` or `defense`."""
        if not self._is_overseer(ctx.author):
            await __import__("mystery").mystery_send(ctx, "❌ Only overseers can end cases")
            return
        guild = ctx.guild
        gd = self._guild_data(guild)
        case = gd.get("active_case")
        if not case:
            await __import__("mystery").mystery_send(ctx, "❌ No active case to end")
            return
        if not winner or winner.lower() not in {"prosecution", "defense"}:
            await __import__("mystery").mystery_send(ctx, "❌ Usage: .endcase prosecution|defense")
            return
        win_side = winner.lower()

        plaintiff_id = int(case.get("plaintiff"))
        defendant_id = int(case.get("defendant"))
        prosecution_ids = [int(x) for x in case.get("prosecution", [])]
        defense_ids = [int(x) for x in case.get("defense", [])]

        overseer_role = discord.utils.get(guild.roles, name="Overseer")
        overseer_mention = overseer_role.mention if overseer_role else "@Overseer"

        # helper to send narration into a player's RC
        async def send_rc_narration(member_id: int, text: str) -> None:
            try:
                member = guild.get_member(member_id)
                if not member:
                    return
                rc = await self._find_rc_channel_for(guild, member)
                if rc:
                    await rc.send(text)
            except Exception:
                pass

        if win_side == "prosecution":
            # defendant dies
            dead_list = gd.setdefault("dead_from_cases", [])
            if str(defendant_id) not in dead_list:
                dead_list.append(str(defendant_id))

            # Award attorneys and plaintiff
            for aid in prosecution_ids:
                await send_rc_narration(aid, f"{overseer_mention} will give you $2000 for winning the case")
            await send_rc_narration(plaintiff_id, f"{overseer_mention} will give you $2500 for winning the case")

            result_text = f"⚖️ Case ended: Prosecution wins. Defendant (ID: {defendant_id}) has died from the case."
        else:
            # defense wins
            for aid in defense_ids:
                await send_rc_narration(aid, f"{overseer_mention} will give you $2000 for winning the case")
            await send_rc_narration(defendant_id, f"{overseer_mention} will give you $2500 for winning the case")
            result_text = f"⚖️ Case ended: Defense wins. Defendant (ID: {defendant_id}) survives and receives restitution."

        # cleanup roles (remove Plaintiff/Defendant)
        try:
            plaintiff_role = discord.utils.get(guild.roles, name="Plaintiff")
            defendant_role = discord.utils.get(guild.roles, name="Defendant")
            try:
                p = guild.get_member(plaintiff_id)
                if p and plaintiff_role:
                    await p.remove_roles(plaintiff_role, reason="Case ended")
                d = guild.get_member(defendant_id)
                if d and defendant_role:
                    await d.remove_roles(defendant_role, reason="Case ended")
            except Exception:
                pass
        except Exception:
            pass

        # try to close thread
        try:
            tid = case.get("thread_id")
            if tid:
                thread = guild.get_channel(tid)
                if thread:
                    try:
                        await thread.send(result_text)
                        await thread.edit(archived=True)
                    except Exception:
                        try:
                            await thread.delete()
                        except Exception:
                            pass
        except Exception:
            pass

        # clear active case
        gd["active_case"] = None
        _save_data(self.data)

        await __import__("mystery").mystery_send(ctx, f"✅ {result_text}")

    @commands.command(name="blocksue")
    async def blocksue(self, ctx: commands.Context, member: discord.Member = None) -> None:
        """Overseer-only: block a player from using the lawsuit module."""
        if not self._is_overseer(ctx.author):
            await ctx.send("❌ Only overseers can block players")
            return
        if member is None:
            await ctx.send("❌ Mention the player to block: `.blocksue @player`")
            return
        gd = self._guild_data(ctx.guild)
        blocked = gd.setdefault("blocked_users", [])
        uid = str(member.id)
        if uid in blocked:
            await ctx.send(f"⚠️ {member.mention} is already blocked")
            return
        blocked.append(uid)
        _save_data(self.data)
        await ctx.send(f"✅ {member.mention} is now blocked from using the lawsuit module")

    @commands.command(name="unblocksue")
    async def unblocksue(self, ctx: commands.Context, member: discord.Member = None) -> None:
        """Overseer-only: unblock a player from using the lawsuit module."""
        if not self._is_overseer(ctx.author):
            await ctx.send("❌ Only overseers can unblock players")
            return
        if member is None:
            await ctx.send("❌ Mention the player to unblock: `.unblocksue @player`")
            return
        gd = self._guild_data(ctx.guild)
        blocked = gd.setdefault("blocked_users", [])
        uid = str(member.id)
        if uid not in blocked:
            await ctx.send(f"⚠️ {member.mention} is not blocked")
            return
        try:
            blocked.remove(uid)
        except ValueError:
            pass
        _save_data(self.data)
        await ctx.send(f"✅ {member.mention} is no longer blocked from using the lawsuit module")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(LawsuitCog(bot))
