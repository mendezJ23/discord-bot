import discord
from discord.ext import commands
import json
import os
import logging
import random
from typing import Optional
from datetime import datetime
import config

logger = logging.getLogger("discord_bot")
PHASES_FILE = "phases.json"
PHASE_ORDER = ["pregame", "night", "day", "postgame"]

class PhasesCog(commands.Cog):
    """Manage game phases and apply channel access rules."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.phases = self._load_phases()

    def _load_phases(self):
        if os.path.exists(PHASES_FILE):
            try:
                with open(PHASES_FILE, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                    # normalize old format (guild_id -> phase_str) to new format
                    out = {}
                    for gid, val in raw.items():
                        if isinstance(val, str):
                            out[gid] = {"phase": val, "count": 1}
                        elif isinstance(val, dict):
                            phase = val.get("phase") or val.get("current") or "pregame"
                            count = int(val.get("count", 1)) if val.get("count") is not None else 1
                            out[gid] = {"phase": phase, "count": count}
                        else:
                            out[gid] = {"phase": "pregame", "count": 1}
                    return out
            except Exception as e:
                logger.error(f"Failed to load phases: {e}")
        return {}

    def _save_phases(self):
        try:
            with open(PHASES_FILE, "w", encoding="utf-8") as f:
                json.dump(self.phases, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save phases: {e}")

    def _get_phase_record(self, guild_id: int) -> tuple[str, int]:
        """Return (phase_token, count) for the guild, with sensible defaults."""
        rec = self.phases.get(str(guild_id))
        if not rec:
            return "pregame", 1
        if isinstance(rec, dict):
            return rec.get("phase", "pregame"), int(rec.get("count", 1))
        # fallback if something odd
        return str(rec), 1

    def _get_phase_for_guild(self, guild_id: int) -> str:
        """Return display string like 'Night 1' or 'Day 2'."""
        phase, count = self._get_phase_record(guild_id)
        if phase in ("day", "night"):
            return f"{phase.title()} {count}"
        return phase

    def _set_phase_for_guild(self, guild_id: int, phase: str) -> None:
        """Set the phase token for the guild and update the counter.

        Counting rule: Day/Night share the same numeric count. When transitioning
        from Night -> Day the count increments (Day 2 after Night 1). Initial
        transitions from pregame -> Day/Night set count to 1.
        """
        gid = str(guild_id)
        old_phase, old_count = self._get_phase_record(guild_id)
        phase = phase.lower() if phase else "pregame"
        new_count = old_count
        if phase not in ("day", "night"):
            # non-day/night phases reset to count 1
            new_count = 1
        else:
            if old_phase not in ("day", "night"):
                # starting day/night series
                new_count = 1
            else:
                # if moving from night -> day, increment count
                if old_phase == "night" and phase == "day":
                    new_count = old_count + 1
                else:
                    # day->night or same phase: keep count
                    new_count = old_count

        self.phases[gid] = {"phase": phase, "count": new_count}
        self._save_phases()

    def get_display_phase(self, guild_id: int) -> str:
        """Public helper to get display phase for other cogs."""
        return self._get_phase_for_guild(guild_id)

    def get_phase_token(self, guild_id: int) -> str:
        p, _ = self._get_phase_record(guild_id)
        return p

    def reset_phase_count(self, guild_id: int) -> None:
        """Reset the numeric counter to 1 for the guild (does not change token)."""
        gid = str(guild_id)
        phase, _ = self._get_phase_record(guild_id)
        self.phases[gid] = {"phase": phase, "count": 1}
        self._save_phases()

    async def apply_phase_permissions(self, guild: discord.Guild, phase: str) -> None:
        """Apply basic write access rules based on phase.

        Day: allow sending in day-discussion, megaphone, vote sessions.
        Night: lock those channels for default role.
        Pregame/Postgame: default locked.
        """
        # derive tokens for DAYCHAT from config.SERVER_STRUCTURE if present
        raw = []
        try:
            raw = config.SERVER_STRUCTURE.get("DAYCHAT", [])
        except Exception:
            raw = []

        tokens = []
        for label in raw:
            if "│" in label:
                token = label.split("│", 1)[1].strip().lower()
            else:
                token = label.strip().lower()
            tokens.append(token)

        # fallback tokens
        if not tokens:
            tokens = ["day-discussion", "megaphone", "meetings", "vote-session", "leader-election", "vote-count"]

        default_role = guild.default_role
        alive_role = discord.utils.get(guild.roles, name="Alive")
        sponsor_role = discord.utils.get(guild.roles, name="Sponsor")

        for ch in guild.text_channels:
            try:
                lname = ch.name.lower()
                if any(tok in lname for tok in tokens):
                    if phase == "day":
                        # Do NOT modify view permissions here; only control send access for phases.
                        try:
                            await ch.set_permissions(default_role, send_messages=False, reason=f"Phase {phase}")
                        except Exception:
                            pass

                        # keep vote-count read-only for everyone
                        if "vote-count" in lname:
                            continue

                        if alive_role:
                            try:
                                await ch.set_permissions(alive_role, send_messages=True, reason=f"Phase {phase}")
                            except Exception:
                                pass
                        if sponsor_role:
                            try:
                                await ch.set_permissions(sponsor_role, send_messages=True, reason=f"Phase {phase}")
                            except Exception:
                                pass
                    else:
                        # non-day phases: lock writing for default role (do not change view)
                        try:
                            await ch.set_permissions(default_role, send_messages=False, reason=f"Phase {phase}")
                        except Exception:
                            pass
                        if alive_role:
                            try:
                                await ch.set_permissions(alive_role, send_messages=False, reason=f"Phase {phase}")
                            except Exception:
                                pass
                        if sponsor_role:
                            try:
                                await ch.set_permissions(sponsor_role, send_messages=False, reason=f"Phase {phase}")
                            except Exception:
                                pass
            except Exception as e:
                logger.warning(f"Could not set permissions for {ch.name}: {e}")

    async def announce_phase(self, guild: discord.Guild, phase: str) -> None:
        """Send a short announcement with a GIF to each DAYCHAT channel when phase changes.

        Only announce for 'day' and 'night' phases per user request.
        """
        if phase not in ("day", "night"):
            return

        # derive tokens for DAYCHAT from config.SERVER_STRUCTURE if present
        raw = []
        try:
            raw = config.SERVER_STRUCTURE.get("DAYCHAT", [])
        except Exception:
            raw = []

        tokens = []
        for label in raw:
            if "│" in label:
                token = label.split("│", 1)[1].strip().lower()
            else:
                token = label.strip().lower()
            tokens.append(token)

        # fallback tokens if config not present
        if not tokens:
            tokens = ["day-discussion", "megaphone", "meetings", "vote-session", "vote-count"]

        # choose a random gif from configured directory if available
        gif_path = None
        gif_url = None
        try:
            gif_dir = config.GIFS_DIRECTORY.get("day" if phase == "day" else "night")
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

        # fallback to configured single URL if no local file
        if not gif_path:
            gif_url = config.DAY_GIF_URL if phase == "day" else config.NIGHT_GIF_URL

        # include numeric count in titles: e.g., 'Night 1'
        try:
            count = 1
            rec = self.phases.get(str(guild.id))
            if isinstance(rec, dict):
                count = int(rec.get("count", 1))
        except Exception:
            count = 1
        display = f"{phase.title()} {count}"
        embed = discord.Embed(title=f"Phase: {display}")
        is_local = False
        attachment_name = None
        if gif_path and os.path.isfile(gif_path):
            is_local = True
            attachment_name = os.path.basename(gif_path)
            embed.set_image(url=f"attachment://{attachment_name}")
        elif gif_url:
            embed.set_image(url=gif_url)

        for ch in guild.text_channels:
            try:
                lname = ch.name.lower()
                if any(tok in lname for tok in tokens):
                    # skip vote-count channel for announcements
                    if "vote-count" in lname:
                        continue
                    if is_local:
                        try:
                            await ch.send(embed=embed, file=discord.File(gif_path))
                        except Exception:
                            # if sending attachment fails, try fallback URL
                            if gif_url:
                                await ch.send(gif_url)
                    elif gif_url:
                        await ch.send(embed=embed)
                    else:
                        await ch.send("Phase changed.")
            except Exception as e:
                logger.warning(f"Could not announce phase in {ch.name}: {e}")

    @commands.group(name="phase", invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    async def phase(self, ctx: commands.Context) -> None:
        """Show current phase or manipulate phases. Use subcommands: set/get/next/list"""
        current = self._get_phase_for_guild(ctx.guild.id)
        await __import__("mystery").mystery_send(ctx, f"Current phase: **{current}**")

    @phase.command(name="set")
    @commands.has_permissions(administrator=True)
    async def phase_set(self, ctx: commands.Context, phase: str) -> None:
        phase = phase.lower()
        if phase not in PHASE_ORDER:
            await __import__("mystery").mystery_send(ctx, f"Unknown phase. Valid phases: {', '.join(PHASE_ORDER)}")
            return
        self._set_phase_for_guild(ctx.guild.id, phase)
        await self.apply_phase_permissions(ctx.guild, phase)
        await self.announce_phase(ctx.guild, phase)
        # sync ActionQueueCog if present
        try:
            aq = self.bot.get_cog("ActionQueueCog")
            if aq and hasattr(aq, "set_phase"):
                await aq.set_phase(self._get_phase_for_guild(ctx.guild.id))
        except Exception:
            pass
        # Update VisitCountCog inventories for day/night phases if present
        try:
            visit_cog = self.bot.get_cog("VisitCountCog")
            if visit_cog:
                if phase == "night":
                    visit_cog.reset_night(ctx.guild.id)
                    visit_cog.set_phase(ctx.guild.id, "night")
                elif phase == "day":
                    visit_cog.reset_day(ctx.guild.id)
                    visit_cog.set_phase(ctx.guild.id, "day")
        except Exception:
            pass

        await __import__("mystery").mystery_send(ctx, f"✅ Phase set to **{self._get_phase_for_guild(ctx.guild.id)}**")

    @phase.command(name="get")
    async def phase_get(self, ctx: commands.Context) -> None:
        current = self._get_phase_for_guild(ctx.guild.id)
        await __import__("mystery").mystery_send(ctx, f"Current phase: **{current}**")

    @phase.command(name="next")
    @commands.has_permissions(administrator=True)
    async def phase_next(self, ctx: commands.Context) -> None:
        current = self._get_phase_for_guild(ctx.guild.id)
        # determine token version of current (strip number if present)
        try:
            token = self.get_phase_token(ctx.guild.id)
            idx = PHASE_ORDER.index(token)
        except Exception:
            idx = 0
        next_idx = (idx + 1) % len(PHASE_ORDER)
        next_phase = PHASE_ORDER[next_idx]
        self._set_phase_for_guild(ctx.guild.id, next_phase)
        await self.apply_phase_permissions(ctx.guild, next_phase)
        await self.announce_phase(ctx.guild, next_phase)
        # Update VisitCountCog inventories for day/night transitions
        try:
            visit_cog = self.bot.get_cog("VisitCountCog")
            if visit_cog:
                if next_phase == "night":
                    visit_cog.reset_night(ctx.guild.id)
                    visit_cog.set_phase(ctx.guild.id, "night")
                elif next_phase == "day":
                    visit_cog.reset_day(ctx.guild.id)
                    visit_cog.set_phase(ctx.guild.id, "day")
        except Exception:
            pass

        await __import__("mystery").mystery_send(ctx, f"✅ Phase advanced to **{self._get_phase_for_guild(ctx.guild.id)}**")

    @phase.command(name="list")
    async def phase_list(self, ctx: commands.Context) -> None:
        await __import__("mystery").mystery_send(ctx, f"Valid phases: {', '.join(PHASE_ORDER)}")

    @phase.command(name="reset")
    @commands.has_permissions(administrator=True)
    async def phase_reset(self, ctx: commands.Context) -> None:
        """Reset the numeric phase counter for this guild to 1."""
        self.reset_phase_count(ctx.guild.id)
        # sync ActionQueueCog if present
        try:
            aq = self.bot.get_cog("ActionQueueCog")
            if aq and hasattr(aq, "set_phase"):
                await aq.set_phase(self._get_phase_for_guild(ctx.guild.id))
        except Exception:
            pass
        await __import__("mystery").mystery_send(ctx, f"✅ Phase counter reset to **{self._get_phase_for_guild(ctx.guild.id)}**")

    # Convenience short commands
    @commands.command(name="day")
    @commands.has_permissions(administrator=True)
    async def set_day(self, ctx: commands.Context) -> None:
        """Set phase to day (convenience)."""
        phase = "day"
        self._set_phase_for_guild(ctx.guild.id, phase)
        await self.apply_phase_permissions(ctx.guild, phase)
        await self.announce_phase(ctx.guild, phase)
        try:
            visit_cog = self.bot.get_cog("VisitCountCog")
            if visit_cog:
                visit_cog.reset_day(ctx.guild.id)
                visit_cog.set_phase(ctx.guild.id, "day")
        except Exception:
            pass

        await __import__("mystery").mystery_send(ctx, f"✅ Phase set to **{phase}**")

    @commands.command(name="night")
    @commands.has_permissions(administrator=True)
    async def set_night(self, ctx: commands.Context) -> None:
        """Set phase to night (convenience)."""
        phase = "night"
        self._set_phase_for_guild(ctx.guild.id, phase)
        await self.apply_phase_permissions(ctx.guild, phase)
        await self.announce_phase(ctx.guild, phase)
        try:
            visit_cog = self.bot.get_cog("VisitCountCog")
            if visit_cog:
                visit_cog.reset_night(ctx.guild.id)
                visit_cog.set_phase(ctx.guild.id, "night")
        except Exception:
            pass

        await __import__("mystery").mystery_send(ctx, f"✅ Phase set to **{phase}**")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(PhasesCog(bot))
