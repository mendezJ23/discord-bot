import discord
from discord.ext import commands
import json
import os
import logging
from typing import Dict, List

logger = logging.getLogger("discord_bot")

VOTING_FILE = "voting.json"

class StatsCog(commands.Cog):
    """Commands to check game stats: votes, alive players, dead players."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    def _load_voting(self) -> Dict:
        """Load voting data from JSON file."""
        if os.path.exists(VOTING_FILE):
            try:
                with open(VOTING_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load voting data: {e}")
        return {"sessions": {}, "votes": {}}

    @commands.command(name="v")
    async def check_votes(self, ctx: commands.Context) -> None:
        """Check all votes across all voting sessions."""
        guild = ctx.guild
        voting_data = self._load_voting()

        # Get all votes for this guild
        guild_votes = [v for v in voting_data["votes"].values() if v["guild_id"] == guild.id]

        if not guild_votes:
            await __import__("mystery").mystery_send(ctx, "📊 No votes yet.")
            return

        # Group votes by session
        votes_by_session: Dict[str, Dict[str, int]] = {}

        for vote in guild_votes:
            session_name = vote["session_name"]
            target_name = vote["target_name"]

            if session_name not in votes_by_session:
                votes_by_session[session_name] = {}

            votes_by_session[session_name][target_name] = votes_by_session[session_name].get(target_name, 0) + 1

        # Create embed with all sessions
        embed = discord.Embed(
            title="📊 All Votes",
            color=discord.Color.gold()
        )

        for session_name in sorted(votes_by_session.keys()):
            vote_tally = votes_by_session[session_name]
            sorted_votes = sorted(vote_tally.items(), key=lambda x: x[1], reverse=True)

            vote_text = "\n".join([f"{idx}. {target} - **{count}**" for idx, (target, count) in enumerate(sorted_votes, 1)])
            embed.add_field(name=f"#{session_name}", value=vote_text, inline=False)

        await ctx.send(embed=embed)

    @commands.command(name="p")
    async def check_alive(self, ctx: commands.Context) -> None:
        """Check all players with the Alive role."""
        guild = ctx.guild
        alive_role = discord.utils.get(guild.roles, name="Alive")

        if not alive_role:
            await __import__("mystery").mystery_send(ctx, "❌ 'Alive' role not found")
            return

        alive_members = sorted([m for m in guild.members if alive_role in m.roles and not m.bot], key=lambda m: m.display_name)

        if not alive_members:
            await __import__("mystery").mystery_send(ctx, "👥 No alive players.")
            return

        embed = discord.Embed(
            title=f"👥 Alive Players ({len(alive_members)})",
            color=discord.Color.green()
        )

        # Create a paginated list and include sponsor when available
        lines: List[str] = []
        role_cog = self.bot.get_cog("RoleChannelsCog")
        for m in alive_members:
            sponsors = []
            try:
                if role_cog and hasattr(role_cog, "find_sponsor_for_member"):
                    sponsors = await role_cog.find_sponsor_for_member(guild, m) or []
            except Exception:
                sponsors = []

            if sponsors:
                sponsor_names = ", ".join([s.display_name for s in sponsors])
                lines.append(f"- {m.display_name}\n  - Sponsor: {sponsor_names}")
            else:
                lines.append(f"- {m.display_name}")

        embed.description = "\n".join(lines)

        await ctx.send(embed=embed)

    @commands.command(name="d")
    async def check_dead(self, ctx: commands.Context) -> None:
        """Check all players with the Dead role."""
        guild = ctx.guild
        dead_role = discord.utils.get(guild.roles, name="Dead")

        if not dead_role:
            await __import__("mystery").mystery_send(ctx, "❌ 'Dead' role not found")
            return

        dead_members = sorted([m for m in guild.members if dead_role in m.roles and not m.bot], key=lambda m: m.display_name)

        if not dead_members:
            await __import__("mystery").mystery_send(ctx, "💀 No dead players.")
            return

        embed = discord.Embed(
            title=f"💀 Dead Players ({len(dead_members)})",
            color=discord.Color.dark_red()
        )

        # Create a paginated list
        members_text = "\n".join([f"• {m.display_name}" for m in dead_members])
        embed.description = members_text

        await ctx.send(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(StatsCog(bot))
