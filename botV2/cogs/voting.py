import discord
from discord.ext import commands
import asyncio
import json
import os
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime

logger = logging.getLogger("discord_bot")

VOTING_FILE = "voting.json"

class VotingCog(commands.Cog):
    """Automatic voting system - tracks member pings in voting channels."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.voting_data = self._load_voting()
        self._ensure_default_sessions()

    async def create_voting_channel(self, guild: discord.Guild, desired_name: str, existing_session_ch: Optional[discord.TextChannel] = None) -> tuple[Optional[discord.TextChannel], bool]:
        """Create or return an existing voting channel using existing session prefix/category.

        Returns (channel, created_flag).
        """
        create_name = desired_name
        create_category = None
        if existing_session_ch:
            try:
                lower = existing_session_ch.name.lower()
                idx = lower.find('vote-session')
                prefix = existing_session_ch.name[:idx] if idx > 0 else ''
                create_name = f"{prefix}{desired_name}"
                create_category = existing_session_ch.category
            except Exception:
                create_name = desired_name

        voting_channel = discord.utils.get(guild.text_channels, name=create_name)
        created_channel = False
        if not voting_channel:
            try:
                if create_category:
                    voting_channel = await guild.create_text_channel(create_name, category=create_category)
                else:
                    voting_channel = await guild.create_text_channel(create_name)
                created_channel = True
                await asyncio.sleep(0.5)
            except Exception as e:
                logger.warning(f"Could not create voting channel {create_name}: {e}")
                return None, False
        return voting_channel, created_channel

    def _load_voting(self) -> Dict[str, Any]:
        """Load voting data from JSON file."""
        if os.path.exists(VOTING_FILE):
            try:
                with open(VOTING_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load voting data: {e}")
        return {"sessions": {}, "votes": {}, "vote_count_message_id": None}

    def _save_voting(self) -> None:
        """Save voting data to JSON file."""
        try:
            with open(VOTING_FILE, "w", encoding="utf-8") as f:
                json.dump(self.voting_data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save voting data: {e}")

    def _ensure_default_sessions(self) -> None:
        """Ensure default voting sessions exist."""
        # Get all guilds
        for guild in self.bot.guilds:
            guild_key = f"{guild.id}_vote-session-1"
            leader_key = f"{guild.id}_leader-election-1"
            
            # Create vote-session-1 if it doesn't exist
            if guild_key not in self.voting_data["sessions"]:
                self.voting_data["sessions"][guild_key] = {
                    "guild_id": guild.id,
                    "name": "vote-session-1",
                    "active": True,
                    "created_at": datetime.utcnow().isoformat()
                }
            
            # Create leader-election-1 if it doesn't exist
            if leader_key not in self.voting_data["sessions"]:
                self.voting_data["sessions"][leader_key] = {
                    "guild_id": guild.id,
                    "name": "leader-election-1",
                    "active": True,
                    "created_at": datetime.utcnow().isoformat()
                }
        
        self._save_voting()

    def clear_sessions_for_guild(self, guild_id: int) -> None:
        """Remove all sessions and votes for a given guild."""
        # Remove sessions
        keys_to_remove = [k for k, s in list(self.voting_data.get("sessions", {}).items()) if s.get("guild_id") == guild_id]
        for k in keys_to_remove:
            self.voting_data["sessions"].pop(k, None)

        # Remove votes
        vote_keys = [k for k, v in list(self.voting_data.get("votes", {}).items()) if v.get("guild_id") == guild_id]
        for k in vote_keys:
            self.voting_data["votes"].pop(k, None)

        # Remove saved vote_count_message_id for the guild
        if "vote_count_message_id" in self.voting_data and str(guild_id) in self.voting_data["vote_count_message_id"]:
            self.voting_data["vote_count_message_id"].pop(str(guild_id), None)

        self._save_voting()

    def _get_session_key(self, guild_id: int, session_name: str) -> str:
        """Generate a unique key for a voting session."""
        return f"{guild_id}_{session_name.lower()}"

    def _get_vote_key(self, guild_id: int, session_name: str, voter_id: int) -> str:
        """Generate a unique key for a vote."""
        return f"{guild_id}_{session_name.lower()}_{voter_id}"

    def _is_voting_channel(self, channel: discord.TextChannel, guild_id: int) -> Optional[str]:
        """Check if a channel is a voting channel and return the session name if it is."""
        for session_key, session in self.voting_data["sessions"].items():
            if session["guild_id"] == guild_id:
                # Check if channel name matches a voting session
                # match either exact or contains (handles emoji prefixes like '🗳│vote-session-1')
                # use case-insensitive matching on names
                ch_name = channel.name.lower()
                sess_name = session["name"].lower()
                if ch_name == sess_name or sess_name in ch_name:
                    return session["name"]
        return None

    def _find_vote_count_channel(self, guild: discord.Guild) -> Optional[discord.TextChannel]:
        """Find the vote-count channel by token in the channel name (handles emoji prefixes)."""
        for ch in guild.text_channels:
            try:
                if "vote-count" in ch.name.lower():
                    return ch
            except Exception:
                continue
        return None

    def ensure_default_sessions_for_guild(self, guild: discord.Guild) -> None:
        """Ensure default voting sessions exist for a specific guild.

        This is intended to be called after setup clears sessions so the
        canonical `vote-session-1` and `leader-election-1` entries are recreated.
        """
        guild_key = f"{guild.id}_vote-session-1"
        leader_key = f"{guild.id}_leader-election-1"

        # Create vote-session-1 if it doesn't exist
        if guild_key not in self.voting_data.get("sessions", {}):
            # try to detect a channel for it
            channel_obj = None
            for ch in guild.text_channels:
                try:
                    if "vote-session-1" in ch.name.lower():
                        channel_obj = ch
                        break
                except Exception:
                    continue

            self.voting_data.setdefault("sessions", {})[guild_key] = {
                "guild_id": guild.id,
                "name": "vote-session-1",
                "active": True,
                "created_at": datetime.utcnow().isoformat(),
                "channel_id": channel_obj.id if channel_obj else None,
                "created_channel": False if channel_obj else False,
            }

        # Create leader-election-1 if it doesn't exist
        if leader_key not in self.voting_data.get("sessions", {}):
            self.voting_data.setdefault("sessions", {})[leader_key] = {
                "guild_id": guild.id,
                "name": "leader-election-1",
                "active": True,
                "created_at": datetime.utcnow().isoformat()
            }

        self._save_voting()

    async def _initialize_vote_count_message(self, guild: discord.Guild, vote_count_ch: discord.TextChannel) -> None:
        """Initialize the vote-count message during setup."""
        embed = discord.Embed(
            title="📊 Voting Results",
            color=discord.Color.gold()
        )
        embed.description = "Voting sessions will appear here as they are created."
        embed.set_footer(text=f"Last updated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")
        
        msg = await vote_count_ch.send(embed=embed)
        
        if "vote_count_message_id" not in self.voting_data:
            self.voting_data["vote_count_message_id"] = {}
        self.voting_data["vote_count_message_id"][str(guild.id)] = str(msg.id)
        self._save_voting()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Track votes when members are pinged in voting channels."""
        # Ignore bot messages
        if message.author.bot:
            return

        guild = message.guild
        if not guild:
            return

        # Check if this is a voting channel
        session_name = self._is_voting_channel(message.channel, guild.id)
        if not session_name:
            return

        session_key = self._get_session_key(guild.id, session_name)
        session = self.voting_data["sessions"].get(session_key)

        if not session or not session.get("active", True):
            return

        # Check if message contains member mentions
        if not message.mentions:
            return

        # Only count the first mention as the vote target
        target_member = message.mentions[0]

        if target_member.bot:
            return

        voter_id = message.author.id
        vote_key = self._get_vote_key(guild.id, session_name, voter_id)

        # Remove previous vote if it exists
        if vote_key in self.voting_data["votes"]:
            del self.voting_data["votes"][vote_key]

        # Record the new vote
        self.voting_data["votes"][vote_key] = {
            "guild_id": guild.id,
            "session_name": session_name,
            "voter_id": voter_id,
            "voter_name": str(message.author),
            "target_id": target_member.id,
            "target_name": str(target_member),
            "message_id": message.id,
            "timestamp": datetime.utcnow().isoformat()
        }
        self._save_voting()

        # Acknowledge the vote
        try:
            await message.add_reaction("✅")
        except Exception:
            pass

        # Update vote-count channel for this specific session
        try:
            vote_count_ch = self._find_vote_count_channel(guild)
            if vote_count_ch:
                await self._update_vote_count_message(guild, vote_count_ch)
        except Exception as e:
            logger.warning(f"Could not update vote-count channel: {e}")

    async def _update_session_vote_display(self, guild: discord.Guild, vote_count_ch: discord.TextChannel, session_name: str) -> None:
        """Update the main vote count message with all sessions."""
        guild_sessions = [s for s in self.voting_data["sessions"].values() if s["guild_id"] == guild.id]

        if not guild_sessions:
            return

        embed = discord.Embed(
            title="📊 Voting Results",
            color=discord.Color.gold()
        )

        # Create a section for each session
        for session in sorted(guild_sessions, key=lambda s: s["name"]):
            session_name = session["name"]
            
            # Aggregate votes by target for this session
            vote_tally: Dict[str, int] = {}

            for vote_key, vote_data in self.voting_data["votes"].items():
                if vote_data["guild_id"] == guild.id and str(vote_data.get("session_name", "")).lower() == str(session_name).lower():
                    target_name = vote_data["target_name"]
                    vote_tally[target_name] = vote_tally.get(target_name, 0) + 1

            if vote_tally:
                sorted_votes = sorted(vote_tally.items(), key=lambda x: x[1], reverse=True)
                vote_text = "\n".join([f"{idx}. {target} - **{count}**" for idx, (target, count) in enumerate(sorted_votes, 1)])
            else:
                vote_text = "No votes yet"

            embed.add_field(name=f"#{session_name}", value=vote_text, inline=False)

        embed.set_footer(text=f"Last updated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")
        return embed

    async def _update_vote_count_message(self, guild: discord.Guild, vote_count_ch: discord.TextChannel) -> None:
        """Update the single vote-count message with all sessions."""
        embed = await self._update_session_vote_display(guild, vote_count_ch, "")
        if not embed:
            embed = discord.Embed(title="📊 Voting Results", description="No sessions or votes yet.", color=discord.Color.gold())

        # Get or create the message ID
        if "vote_count_message_id" not in self.voting_data:
            self.voting_data["vote_count_message_id"] = {}
        
        message_id = self.voting_data["vote_count_message_id"].get(str(guild.id))

        try:
            if message_id:
                # Try to update existing message
                try:
                    msg = await vote_count_ch.fetch_message(int(message_id))
                    await msg.edit(embed=embed)
                except (discord.NotFound, discord.HTTPException):
                    # Message was deleted, create a new one
                    msg = await vote_count_ch.send(embed=embed)
                    self.voting_data["vote_count_message_id"][str(guild.id)] = str(msg.id)
                    self._save_voting()
            else:
                # Create new message
                msg = await vote_count_ch.send(embed=embed)
                self.voting_data["vote_count_message_id"][str(guild.id)] = str(msg.id)
                self._save_voting()
        except Exception as e:
            logger.warning(f"Could not update vote-count message: {e}")

    async def _update_vote_count_channel(self, guild: discord.Guild, vote_count_ch: discord.TextChannel) -> None:
        """Update the vote-count channel with current vote tallies for all sessions."""
        await self._update_vote_count_message(guild, vote_count_ch)

    @commands.command(name="session")
    @commands.has_permissions(administrator=True)
    async def session(self, ctx: commands.Context, action: str = None, session_name: str = None) -> None:
        """Manage voting sessions.
        
        Usage:
        - .session create <name>     - Create a new voting session (must have corresponding channel)
        - .session close <name>      - Close a voting session
        - .session open <name>       - Reopen a closed voting session
        - .session list              - List all sessions
        - .session reset <name>      - Clear all votes from a session
        """
        if not action:
            await __import__("mystery").mystery_send(ctx, "Usage: `.session create <name>`, `.session close <name>`, `.session open <name>`, `.session list`, `.session reset <name>`")
            return

        guild = ctx.guild

        if action.lower() == "create":
            # Try to detect an existing vote-session channel to copy category and emoji prefix
            existing_session_ch = None
            for ch in guild.text_channels:
                try:
                    if "vote-session" in ch.name.lower():
                        existing_session_ch = ch
                        break
                except Exception:
                    continue

            # If no session_name provided, auto-generate next vote-session-N
            desired_name = None
            if session_name:
                desired_name = session_name.lower()

            # If not provided, pick next vote-session-N
            if not desired_name:
                # find highest existing vote-session-N in guild channels or existing sessions
                highest = 0
                for ch in guild.text_channels:
                    m = __import__('re').search(r"vote-session-(\d+)", ch.name.lower())
                    if m:
                        try:
                            highest = max(highest, int(m.group(1)))
                        except Exception:
                            continue
                for s in self.voting_data.get("sessions", {}).values():
                    if s.get("guild_id") == guild.id:
                        m = __import__('re').search(r"vote-session-(\d+)", s.get("name", ""))
                        if m:
                            try:
                                highest = max(highest, int(m.group(1)))
                            except Exception:
                                continue
                desired_name = f"vote-session-{highest+1}"

            # normalize name (canonical name without prefix)
            desired_name = desired_name.lower()

            # Prepare creation name and category based on existing session channel
            create_name = desired_name
            create_category = None
            if existing_session_ch:
                try:
                    lower = existing_session_ch.name.lower()
                    idx = lower.find('vote-session')
                    prefix = existing_session_ch.name[:idx] if idx > 0 else ''
                    create_name = f"{prefix}{desired_name}"
                    create_category = existing_session_ch.category
                except Exception:
                    create_name = desired_name

            # Create channel if missing (use helper so other cogs can reuse)
            voting_channel, created_channel = await self.create_voting_channel(guild, desired_name, existing_session_ch)
            if not voting_channel:
                await __import__("mystery").mystery_send(ctx, f"❌ Could not create or find channel for `{desired_name}`.")
                return

            session_key = self._get_session_key(guild.id, desired_name)

            if session_key in self.voting_data["sessions"]:
                await __import__("mystery").mystery_send(ctx, f"❌ Session `{desired_name}` already exists.")
                return

            self.voting_data["sessions"][session_key] = {
                "guild_id": guild.id,
                "name": desired_name,
                "active": True,
                "created_by": str(ctx.author),
                "created_at": datetime.utcnow().isoformat(),
                "channel_id": voting_channel.id,
                "created_channel": created_channel
            }
            self._save_voting()

            await __import__("mystery").mystery_send(ctx, f"✅ Voting session `{desired_name}` created. Votes from #{voting_channel.name} will be tracked.")

            # Update the vote-count message
            try:
                vote_count_ch = self._find_vote_count_channel(guild)
                if vote_count_ch:
                    await self._update_vote_count_message(guild, vote_count_ch)
            except Exception as e:
                logger.warning(f"Could not update vote-count: {e}")

        elif action.lower() == "close":
            if not session_name:
                await __import__("mystery").mystery_send(ctx, "Usage: `.session close <session_name>`")
                return

            session_key = self._get_session_key(guild.id, session_name)

            if session_key not in self.voting_data["sessions"]:
                await __import__("mystery").mystery_send(ctx, f"❌ Session `{session_name}` does not exist.")
                return

            self.voting_data["sessions"][session_key]["active"] = False
            self._save_voting()

            await __import__("mystery").mystery_send(ctx, f"✅ Voting session `{session_name}` closed. No more votes will be accepted.")

        elif action.lower() == "open":
            if not session_name:
                await __import__("mystery").mystery_send(ctx, "Usage: `.session open <session_name>`")
                return

            session_key = self._get_session_key(guild.id, session_name)

            if session_key not in self.voting_data["sessions"]:
                await __import__("mystery").mystery_send(ctx, f"❌ Session `{session_name}` does not exist.")
                return

            self.voting_data["sessions"][session_key]["active"] = True
            self._save_voting()

            await __import__("mystery").mystery_send(ctx, f"✅ Voting session `{session_name}` reopened. Votes are now being accepted.")

        elif action.lower() == "reset":
            if not session_name:
                await __import__("mystery").mystery_send(ctx, "Usage: `.session reset <session_name>`")
                return

            session_key = self._get_session_key(guild.id, session_name)

            if session_key not in self.voting_data["sessions"]:
                await __import__("mystery").mystery_send(ctx, f"❌ Session `{session_name}` does not exist.")
                return

            # Remove all votes for this session
            keys_to_remove = [k for k in self.voting_data["votes"].keys() 
                            if self.voting_data["votes"][k]["guild_id"] == guild.id 
                            and self.voting_data["votes"][k]["session_name"] == session_name.lower()]
            for k in keys_to_remove:
                del self.voting_data["votes"][k]

            self._save_voting()

            await __import__("mystery").mystery_send(ctx, f"✅ All votes in `{session_name}` have been cleared.")

            # Update the vote-count message
            try:
                vote_count_ch = self._find_vote_count_channel(guild)
                if vote_count_ch:
                    await self._update_vote_count_message(guild, vote_count_ch)
            except Exception as e:
                logger.warning(f"Could not update vote-count: {e}")

        elif action.lower() == "delete":
            if not session_name:
                await __import__("mystery").mystery_send(ctx, "Usage: `.session delete <session_name>`")
                return

            session_key = self._get_session_key(guild.id, session_name)

            if session_key not in self.voting_data["sessions"]:
                await __import__("mystery").mystery_send(ctx, f"❌ Session `{session_name}` does not exist.")
                return

            # remove votes for this session
            keys_to_remove = [k for k, v in list(self.voting_data["votes"].items())
                              if v["guild_id"] == guild.id and v["session_name"] == session_name.lower()]
            for k in keys_to_remove:
                del self.voting_data["votes"][k]

            # optionally delete channel if created by bot
            sess = self.voting_data["sessions"].pop(session_key)
            try:
                if sess.get("created_channel") and sess.get("channel_id"):
                    ch = discord.utils.get(guild.text_channels, id=sess.get("channel_id"))
                    if ch:
                        await ch.delete(reason=f"Deleted by .session delete {ctx.author}")
            except Exception:
                pass

            self._save_voting()
            await __import__("mystery").mystery_send(ctx, f"✅ Voting session `{session_name}` deleted along with its votes.")

            # Update the vote-count message
            try:
                vote_count_ch = self._find_vote_count_channel(guild)
                if vote_count_ch:
                    await self._update_vote_count_message(guild, vote_count_ch)
            except Exception as e:
                logger.warning(f"Could not update vote-count: {e}")

        elif action.lower() == "list":
            guild_sessions = [s for s in self.voting_data["sessions"].values() if s["guild_id"] == guild.id]

            if not guild_sessions:
                await __import__("mystery").mystery_send(ctx, "📋 No voting sessions created yet.")
                return

            embed = discord.Embed(
                title="📋 Voting Sessions",
                color=discord.Color.blue()
            )

            for session in guild_sessions:
                status = "🟢 Active" if session.get("active", True) else "🔴 Closed"
                # Count votes in this session
                vote_count = len([v for v in self.voting_data["votes"].values() 
                                if v["guild_id"] == guild.id and v["session_name"] == session["name"]])
                embed.add_field(
                    name=f"#{session['name']} - {status}",
                    value=f"Votes: {vote_count}",
                    inline=False
                )

            await ctx.send(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(VotingCog(bot))

