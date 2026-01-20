import json
import os
import logging
from typing import Dict, Any, Optional

from discord.ext import commands

logger = logging.getLogger("discord_bot")

VISITS_FILE = "visit_counts.json"


class VisitCountCog(commands.Cog):
    """Track visit counts for players: night, day, forced and stealth.

    Stores per-player counts and per-player incomes for night/day. Provides
    admin commands to give visits, set incomes, and reset nightly/daytime
    visits (to be called by a scheduler or manually).
    """

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.data = self._load()

    def _load(self) -> Dict[str, Any]:
        if os.path.exists(VISITS_FILE):
            try:
                with open(VISITS_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load visit counts: {e}")
        return {"counts": {}, "income": {}, "phase": {}}

    def _save(self) -> None:
        try:
            with open(VISITS_FILE, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save visit counts: {e}")

    def _key(self, guild_id: int, member_id: int) -> str:
        return f"{guild_id}_{member_id}"

    def get_counts(self, guild_id: int, member_id: int) -> Dict[str, int]:
        k = self._key(guild_id, member_id)
        return self.data.setdefault("counts", {}).get(k, {"night": 0, "day": 0, "forced": 0, "stealth": 0}).copy()

    def set_counts(self, guild_id: int, member_id: int, counts: Dict[str, int]) -> None:
        k = self._key(guild_id, member_id)
        self.data.setdefault("counts", {})[k] = {
            "night": int(counts.get("night", 0)),
            "day": int(counts.get("day", 0)),
            "forced": int(counts.get("forced", 0)),
            "stealth": int(counts.get("stealth", 0)),
        }
        self._save()

    def add_visits(self, guild_id: int, member_id: int, kind: str, amount: int) -> None:
        if kind not in ("night", "day", "forced", "stealth"):
            raise ValueError("invalid visit kind")
        k = self._key(guild_id, member_id)
        counts = self.data.setdefault("counts", {}).setdefault(k, {"night": 0, "day": 0, "forced": 0, "stealth": 0})
        counts[kind] = counts.get(kind, 0) + int(amount)
        self._save()

    def set_income(self, guild_id: int, member_id: int, night_income: int, day_income: int) -> None:
        k = self._key(guild_id, member_id)
        self.data.setdefault("income", {})[k] = {
            "night_income": int(night_income),
            "day_income": int(day_income),
        }
        self._save()

    def get_income(self, guild_id: int, member_id: int) -> Dict[str, int]:
        k = self._key(guild_id, member_id)
        return self.data.setdefault("income", {}).get(k, {"night_income": 0, "day_income": 0}).copy()

    def reset_night(self, guild_id: int) -> None:
        # For each stored player in this guild, set night count to configured income
        prefix = f"{guild_id}_"
        for k, income in self.data.setdefault("income", {}).items():
            if not k.startswith(prefix):
                continue
            member_id = int(k.split("_", 1)[1])
            night_income = int(income.get("night_income", 0))
            counts = self.data.setdefault("counts", {}).setdefault(k, {"night": 0, "day": 0, "forced": 0, "stealth": 0})
            counts["night"] = night_income
        self._save()

    def reset_day(self, guild_id: int) -> None:
        prefix = f"{guild_id}_"
        for k, income in self.data.setdefault("income", {}).items():
            if not k.startswith(prefix):
                continue
            member_id = int(k.split("_", 1)[1])
            day_income = int(income.get("day_income", 0))
            counts = self.data.setdefault("counts", {}).setdefault(k, {"night": 0, "day": 0, "forced": 0, "stealth": 0})
            counts["day"] = day_income
        self._save()

    def get_phase(self, guild_id: int) -> str:
        return self.data.setdefault("phase", {}).get(str(guild_id), "night")

    def set_phase(self, guild_id: int, phase: str) -> None:
        if phase not in ("night", "day"):
            raise ValueError("phase must be 'night' or 'day'")
        self.data.setdefault("phase", {})[str(guild_id)] = phase
        self._save()

    def has_visit(self, guild_id: int, member_id: int, kind: str) -> bool:
        counts = self.get_counts(guild_id, member_id)
        return counts.get(kind, 0) > 0

    def consume_visit(self, guild_id: int, member_id: int, kind: str) -> bool:
        k = self._key(guild_id, member_id)
        counts = self.data.setdefault("counts", {}).setdefault(k, {"night": 0, "day": 0, "forced": 0, "stealth": 0})
        cur = counts.get(kind, 0)
        if cur and cur > 0:
            counts[kind] = cur - 1
            self._save()
            return True
        return False

    # ----------------- Commands -----------------
    @commands.group(name="visits", invoke_without_command=True)
    async def visits(self, ctx: commands.Context) -> None:
        await __import__("mystery").mystery_send(ctx, "Usage: .visits show|give|set-income|reset-night|reset-day|set-phase")

    @visits.command(name="show")
    async def visits_show(self, ctx: commands.Context, member: Optional[commands.MemberConverter] = None) -> None:
        member = member or ctx.author
        counts = self.get_counts(ctx.guild.id, member.id)
        income = self.get_income(ctx.guild.id, member.id)
        await __import__("mystery").mystery_send(ctx, f"Visits for {member.display_name}: night={counts.get('night',0)}, day={counts.get('day',0)}, forced={counts.get('forced',0)}, stealth={counts.get('stealth',0)}; incomes: night={income.get('night_income',0)}, day={income.get('day_income',0)}")

    @visits.command(name="give")
    @commands.has_permissions(administrator=True)
    async def visits_give(self, ctx: commands.Context, member: Optional[commands.MemberConverter], kind: str, amount: int) -> None:
        if member is None:
            raise commands.MissingRequiredArgument('member')
        if kind not in ("night", "day", "forced", "stealth"):
            await __import__("mystery").mystery_send(ctx, "Invalid kind — must be one of: night, day, forced, stealth")
            return
        self.add_visits(ctx.guild.id, member.id, kind, amount)
        await __import__("mystery").mystery_send(ctx, f"✅ Given {amount} {kind} visits to {member.display_name}.")

    @visits.command(name="set-income")
    @commands.has_permissions(administrator=True)
    async def visits_set_income(self, ctx: commands.Context, member: Optional[commands.MemberConverter], night_income: int, day_income: int) -> None:
        if member is None:
            raise commands.MissingRequiredArgument('member')
        self.set_income(ctx.guild.id, member.id, night_income, day_income)
        await __import__("mystery").mystery_send(ctx, f"✅ Set incomes for {member.display_name}: night={night_income}, day={day_income}")

    @visits.command(name="reset-night")
    @commands.has_permissions(administrator=True)
    async def visits_reset_night(self, ctx: commands.Context) -> None:
        self.reset_night(ctx.guild.id)
        await __import__("mystery").mystery_send(ctx, "✅ Night visits reset to configured incomes for this guild.")

    @visits.command(name="reset-day")
    @commands.has_permissions(administrator=True)
    async def visits_reset_day(self, ctx: commands.Context) -> None:
        self.reset_day(ctx.guild.id)
        await __import__("mystery").mystery_send(ctx, "✅ Day visits reset to configured incomes for this guild.")

    @visits.command(name="set-phase")
    @commands.has_permissions(administrator=True)
    async def visits_set_phase(self, ctx: commands.Context, phase: str) -> None:
        try:
            self.set_phase(ctx.guild.id, phase)
            await __import__("mystery").mystery_send(ctx, f"✅ Phase set to {phase} for this guild.")
        except ValueError as e:
            await __import__("mystery").mystery_send(ctx, str(e))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(VisitCountCog(bot))
