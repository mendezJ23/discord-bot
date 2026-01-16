import discord
from discord.ext import commands
from datetime import datetime
from typing import Optional, Dict, Union, List
import re
import config
import json
import os
import logging

logger = logging.getLogger("discord_bot")

class ActionStatus:
    """Stores information about a queued action."""
    def __init__(self, action_id: int, user_id: int, channel_id: int, message_id: int, action_type: str, description: str, timestamp: datetime):
        self.action_id = action_id
        self.user_id = user_id
        self.channel_id = channel_id
        self.message_id = message_id
        self.action_type = action_type
        self.description = description
        self.timestamp = timestamp
        self.status = "pending"  # pending, done, cancelled
        self.guild_id = None
        self.player_message_id = None  # Message in original channel
        self.admin_message_id = None   # Message in log-actions

class PlayerActionView(discord.ui.View):
    """Buttons for the user in the channel where action started - only Cancel button."""
    def __init__(self, action: ActionStatus, cog: 'ActionQueueCog', timeout: Optional[float] = None):
        super().__init__(timeout=timeout)
        self.action = action
        self.cog = cog

    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.red)
    async def cancel_action(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Cancel the action - only initiator can cancel."""
        if interaction.user.id != self.action.user_id:
            await interaction.response.send_message("❌ Only the user who initiated this action can cancel it.", ephemeral=True)
            return
        
        self.action.status = "cancelled"
        
        # Update BOTH messages: player and admin
        await self.cog.update_action_messages(self.action, interaction.guild)
        
        await interaction.response.defer()
        logger.info(f"Action {self.action.action_id} cancelled by {interaction.user}")

class AdminActionView(discord.ui.View):
    """Buttons for log-actions channel - Done, Cancel, Jump to message, Jump to channel. Anyone can click."""
    def __init__(self, action: ActionStatus, guild: discord.Guild, cog: 'ActionQueueCog', timeout: Optional[float] = None):
        super().__init__(timeout=timeout)
        self.action = action
        self.guild = guild
        self.cog = cog
        
        # Add link buttons for jumping
        self.add_item(discord.ui.Button(
            label="📍 Jump to Message",
            style=discord.ButtonStyle.link,
            url=f"https://discord.com/channels/{guild.id}/{action.channel_id}/{action.message_id}"
        ))
        self.add_item(discord.ui.Button(
            label="🔗 Jump to Channel",
            style=discord.ButtonStyle.link,
            url=f"https://discord.com/channels/{guild.id}/{action.channel_id}"
        ))

    @discord.ui.button(label="✅ Done", style=discord.ButtonStyle.green)
    async def mark_done(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Mark action as done - anyone can click."""
        if self.action.status in ("done", "cancelled"):
            await interaction.response.send_message(f"❌ This action is already {self.action.status}.", ephemeral=True)
            return
        
        self.action.status = "done"
        
        # Update BOTH messages
        await self.cog.update_action_messages(self.action, interaction.guild)
        
        await interaction.response.defer()
        logger.info(f"Action {self.action.action_id} marked as done by {interaction.user}")

    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.red)
    async def cancel_action(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Cancel action - anyone can click."""
        if self.action.status in ("done", "cancelled"):
            await interaction.response.send_message(f"❌ This action is already {self.action.status}.", ephemeral=True)
            return
        
        self.action.status = "cancelled"
        
        # Update BOTH messages
        await self.cog.update_action_messages(self.action, interaction.guild)
        
        await interaction.response.defer()
        logger.info(f"Action {self.action.action_id} cancelled by {interaction.user}")


class ActionQueueCog(commands.Cog):
    """Cog for queueing and tracking user actions when bot is mentioned in Roles, Alts, Dead RC channels."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.actions: Dict[int, ActionStatus] = {}  # action_id -> ActionStatus
        self.next_action_id = 1
        # Abilities assigned to RCs: channel_id -> {ability_key: {category, uses, owner_channel_id}}
        self.abilities: Dict[int, Dict[str, Dict]] = {}
        # Teams per RC channel_id -> team name
        self.teams: Dict[int, str] = {}
        # Pending abilities list for OS processing
        self.pending_abilities: list[Dict] = []
        # Extra votes mapping target_id -> count
        self.extra_votes: Dict[int, int] = {}
        # Blocks for suing: store member ids and channel ids
        self.blocksue_members: set[int] = set()
        self.blocksue_channels: set[int] = set()
        # Muted players (by member id)
        self.muted_players: set[int] = set()
        # Presets per channel
        self.presets: Dict[int, list[Dict]] = {}
        # Current phase tracking
        self.current_phase = "Day 1"
        # Visits per RC: channel_id -> {type -> uses}
        self.visits: Dict[int, Dict[str, str]] = {}
        # Roleblocks: (channel_id, ability_key) -> {until, boundary, forever(bool)}
        self.roleblocks: Dict[str, Dict] = {}

        # persistence
        self._data_dir = os.path.join(os.path.dirname(__file__), "..", "data")
        try:
            os.makedirs(self._data_dir, exist_ok=True)
        except Exception:
            pass
        self._state_file = os.path.normpath(os.path.join(self._data_dir, "action_queue_state.json"))
        # load state if exists
        try:
            self._load_state()
        except Exception:
            logger.info("No saved action queue state or failed to load state")

    async def update_action_messages(self, action: ActionStatus, guild: discord.Guild) -> None:
        """Update both player and admin messages with new status."""
        color_map = {
            "pending": discord.Color.yellow(),
            "done": discord.Color.green(),
            "cancelled": discord.Color.greyple()
        }
        status_map = {
            "pending": "⏳ Pending",
            "done": "✅ Done",
            "cancelled": "❌ Cancelled"
        }
        
        # Create updated embed
        embed = discord.Embed(
            title="🔔 Action Started",
            color=color_map[action.status],
            timestamp=action.timestamp
        )
        embed.add_field(name="Action ID", value=str(action.action_id), inline=True)
        embed.add_field(name="User", value=f"<@{action.user_id}>", inline=True)
        embed.add_field(name="Status", value=status_map[action.status], inline=True)
        embed.add_field(name="Channel", value=f"<#{action.channel_id}>", inline=False)
        embed.add_field(name="Time", value=action.timestamp.strftime("%Y-%m-%d %H:%M:%S UTC"), inline=False)
        embed.add_field(name="Message", value=action.description or "(empty)", inline=False)
        
        # Update player message in original channel
        if action.player_message_id:
            try:
                channel = guild.get_channel(action.channel_id)
                if channel:
                    msg = await channel.fetch_message(action.player_message_id)
                    await msg.edit(embed=embed, view=None)  # Remove buttons after action is done
            except Exception as e:
                logger.warning(f"Failed to update player message {action.player_message_id}: {e}")
        
        # Update admin message in log-actions
        if action.admin_message_id:
            try:
                log_channel = discord.utils.get(guild.text_channels, name="🌀│log-actions")
                if log_channel:
                    msg = await log_channel.fetch_message(action.admin_message_id)
                    await msg.edit(embed=embed, view=None)  # Remove buttons after action is done
            except Exception as e:
                logger.warning(f"Failed to update admin message {action.admin_message_id}: {e}")

    def is_monitored_category(self, channel: discord.TextChannel) -> bool:
        """Check if channel is in one of the monitored categories: ROLES, ALTS, DEAD RC."""
        if not channel.category:
            return False
        
        category_name = channel.category.name
        return category_name in ("ROLES", "ALTS", "DEAD RC")

    def _load_state(self) -> None:
        try:
            if not os.path.isfile(self._state_file):
                return
            with open(self._state_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            self.abilities = {int(k): v for k, v in data.get("abilities", {}).items()}
            # keys for abilities may be strings -> ensure nested keys are preserved
            self.teams = {int(k): v for k, v in data.get("teams", {}).items()}
            # pending abilities: convert timestamps
            pend = []
            for p in data.get("pending_abilities", []):
                p["timestamp"] = datetime.fromisoformat(p["timestamp"]) if p.get("timestamp") else datetime.utcnow()
                pend.append(p)
            self.pending_abilities = pend
            self.extra_votes = {int(k): int(v) for k, v in data.get("extra_votes", {}).items()}
            self.blocksue_members = set(data.get("blocksue_members", []))
            self.blocksue_channels = set(data.get("blocksue_channels", []))
            self.muted_players = set(data.get("muted_players", []))
            # presets timestamps
            presets = {}
            for k, lst in data.get("presets", {}).items():
                presets[int(k)] = [{"text": it.get("text"), "timestamp": datetime.fromisoformat(it.get("timestamp")) if it.get("timestamp") else datetime.utcnow()} for it in lst]
            self.presets = presets
            self.current_phase = data.get("current_phase", self.current_phase)
            self.visits = {int(k): v for k, v in data.get("visits", {}).items()}
            self.roleblocks = data.get("roleblocks", {}) or {}
            # next_action_id
            self.next_action_id = int(data.get("next_action_id", self.next_action_id))
        except Exception as e:
            logger.warning(f"Failed to load action queue state: {e}")

    def _save_state(self) -> None:
        try:
            payload = {
                "abilities": {str(k): v for k, v in self.abilities.items()},
                "teams": {str(k): v for k, v in self.teams.items()},
                "pending_abilities": [
                    {**{k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in p.items()}}
                    for p in self.pending_abilities
                ],
                "extra_votes": {str(k): v for k, v in self.extra_votes.items()},
                "blocksue_members": list(self.blocksue_members),
                "blocksue_channels": list(self.blocksue_channels),
                "muted_players": list(self.muted_players),
                "presets": {str(k): [{"text": it.get("text"), "timestamp": (it.get("timestamp").isoformat() if isinstance(it.get("timestamp"), datetime) else it.get("timestamp"))} for it in lst] for k, lst in self.presets.items()},
                "current_phase": self.current_phase,
                "visits": {str(k): v for k, v in self.visits.items()},
                "roleblocks": self.roleblocks,
                "next_action_id": self.next_action_id
            }
            with open(self._state_file, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"Failed to save action queue state: {e}")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Listen for bot mentions in Roles, Alts, Dead RC category channels."""
        # Ignore bot messages and messages without mentions
        if message.author.bot or not message.mentions:
            return

        # Check if bot is mentioned
        if self.bot.user not in message.mentions:
            return

        guild = message.guild
        if not guild:
            return

        # Check if message is from monitored categories
        if not self.is_monitored_category(message.channel):
            return

        # The action-queue is now triggered via the `.use` command instead of pinging the bot.
        return

    @commands.command(name="use")
    async def use(self, ctx: commands.Context, *, description: Optional[str] = None) -> None:
        """Queue an action (use instead of pinging the bot).

        Usage:
          - `.use` (reply to a message to use that message's content as the description)
          - `.use some details` (supply a description)
        """
        guild = ctx.guild
        if not guild:
            return

        # Only allow in monitored categories
        if not self.is_monitored_category(ctx.channel):
            await __import__("mystery").mystery_send(ctx, "❌ The `.use` command can only be used inside role/alt/dead RC channels.")
            return

        # If replying to a message and no explicit description provided, use replied message content
        referenced = None
        if ctx.message.reference:
            try:
                referenced = ctx.message.reference.resolved
            except Exception:
                referenced = None
        if referenced and isinstance(referenced, discord.Message) and not description:
            description_text = (referenced.content or "")[:1024]
            message_id = referenced.id
        else:
            description_text = (description or "").strip()[:1024]
            message_id = ctx.message.id

        # detect ability use pattern at start of description (e.g., A1 or 1)
        first_token = None
        rest = description or ""
        if rest:
            parts = rest.split(None, 1)
            first_token = parts[0]
            rest = parts[1] if len(parts) > 1 else ""

        ability_key = None
        if first_token:
            tok = first_token.upper()
            if tok.startswith("A") and tok[1:].isdigit():
                ability_key = tok
            elif first_token.isdigit():
                ability_key = first_token

        # If ability usage: validate and register in pending_abilities
        if ability_key:
            channel_abilities = self.abilities.get(ctx.channel.id, {})
            # allow either numeric or A-prefixed lookup (1 == A1)
            ability_def = channel_abilities.get(ability_key)
            if not ability_def:
                # try alternate form
                if ability_key.upper().startswith("A") and ability_key[1:].isdigit():
                    alt = ability_key[1:]
                elif ability_key.isdigit():
                    alt = f"A{ability_key}"
                else:
                    alt = None
                if alt:
                    ability_def = channel_abilities.get(alt.upper()) or channel_abilities.get(alt)
                    # normalize ability_key to stored variant if found
                    if ability_def:
                        ability_key = next((k for k in channel_abilities.keys() if k.upper() == alt.upper()), ability_key)
            if not ability_def:
                await __import__("mystery").mystery_send(ctx, f"❌ Ability `{ability_key}` not found for this RC.")
                return
            # create pending ability entry
            pending = {
                "channel_id": ctx.channel.id,
                "ability": ability_key,
                "category": ability_def.get("category"),
                "team": self.teams.get(ctx.channel.id),
                "timestamp": datetime.utcnow(),
                "description": rest or description or "(no description)",
                "status": "pending",
                "user_id": ctx.author.id
            }
            self.pending_abilities.append(pending)
            await __import__("mystery").mystery_send(ctx, f"✅ Registered ability `{ability_key}` for OS processing.")
            # also create an action entry for tracking
        action = ActionStatus(
            action_id=self.next_action_id,
            user_id=ctx.author.id,
            channel_id=ctx.channel.id,
            message_id=message_id,
            action_type="use_command",
            description=description_text,
            timestamp=datetime.utcnow()
        )
        action.guild_id = guild.id
        self.next_action_id += 1

        # Store action
        self.actions[action.action_id] = action

        # Build embed
        embed = discord.Embed(
            title="🔔 Action Started",
            color=discord.Color.yellow(),
            timestamp=datetime.utcnow()
        )
        embed.add_field(name="Action ID", value=str(action.action_id), inline=True)
        embed.add_field(name="User", value=f"{ctx.author.mention} ({ctx.author.id})", inline=True)
        embed.add_field(name="Status", value="⏳ Pending", inline=True)
        embed.add_field(name="Channel", value=f"{ctx.channel.mention}", inline=False)
        embed.add_field(name="Time", value=action.timestamp.strftime("%Y-%m-%d %H:%M:%S UTC"), inline=False)
        embed.add_field(name="Message", value=action.description or "(empty)", inline=False)

        # Send player view
        try:
            player_view = PlayerActionView(action, self)
            player_msg = await ctx.channel.send(embed=embed, view=player_view)
            action.player_message_id = player_msg.id
            logger.info(f"Action {action.action_id} player message sent in {ctx.channel.name}")
        except Exception as e:
            logger.error(f"Failed to send player message: {e}")

        # Send admin view in log-actions
        log_channel = discord.utils.get(guild.text_channels, name="🌀│log-actions")
        if log_channel:
            try:
                admin_view = AdminActionView(action, guild, self)
                admin_msg = await log_channel.send(embed=embed, view=admin_view)
                action.admin_message_id = admin_msg.id
                logger.info(f"Action {action.action_id} admin message sent in log-actions")
            except Exception as e:
                logger.error(f"Failed to send admin message: {e}")
        else:
            logger.warning(f"🌀│log-actions channel not found in {guild.name}")

    @commands.command(name="actions")
    async def view_actions(self, ctx: commands.Context) -> None:
        """View your pending actions."""
        user_id = ctx.author.id
        user_actions = [a for a in self.actions.values() if a.user_id == user_id]
        
        if not user_actions:
            await __import__("mystery").mystery_send(ctx, "❌ You have no actions.")
            return

        embeds = []
        for action in user_actions:
            color_map = {
                "pending": discord.Color.yellow(),
                "done": discord.Color.green(),
                "cancelled": discord.Color.greyple()
            }
            status_map = {
                "pending": "⏳ Pending",
                "done": "✅ Done",
                "cancelled": "❌ Cancelled"
            }

            embed = discord.Embed(
                title=f"Action #{action.action_id}",
                color=color_map[action.status],
                timestamp=action.timestamp
            )
            embed.add_field(name="Status", value=status_map[action.status], inline=True)
            embed.add_field(name="Channel", value=f"<#{action.channel_id}>", inline=True)
            embed.add_field(name="Time", value=action.timestamp.strftime("%Y-%m-%d %H:%M:%S UTC"), inline=False)
            embed.add_field(name="Message", value=action.description or "(empty)", inline=False)
            
            embeds.append(embed)

        # Send embeds in chunks
        for i in range(0, len(embeds), 10):
            await ctx.send(embeds=embeds[i:i+10])

    # --- New commands for abilities, teams, OS list, presets, votes, blocks, mute ---
    @commands.command(name="giveability")
    @commands.has_permissions(administrator=True)
    async def give_ability(self, ctx: commands.Context, rc: discord.TextChannel, ability_key: str, category: str, uses: str) -> None:
        """Assign an ability to an RC: .giveability #rc {ABILITY-NUMBER} {CATEGORY} {USES}"""
        # normalize ability key
        key = ability_key.upper()
        if not (key.startswith("A") and key[1:].isdigit()) and not key.isdigit():
            await __import__("mystery").mystery_send(ctx, "❌ Ability number must be numeric (1) or prefixed with A (A1).")
            return

        # normalize category (allow common aliases)
        cat_map = {
            "MANIPULATION": "Manipulation", "MANIP": "Manipulation",
            "PROTECTION": "Protection", "PROT": "Protection",
            "BLOCKING": "Blocking", "BLOCK": "Blocking",
            "CURING": "Curing", "CURE": "Curing",
            "INFORMATION": "Information", "INFO": "Information",
            "ECONOMY": "Economy", "ECO": "Economy", "ECON": "Economy",
            "TRANSPORT": "Transport", "TRANSPORTATION": "Transport",
            "COMMUNICATION": "Communication",
            "LETHAL": "Lethal",
            "OTHER": "Other"
        }
        cat = cat_map.get(category.upper(), category.title())

        # validate against canonical categories in config
        if getattr(config, "ABILITY_CATEGORIES", None) and cat not in config.ABILITY_CATEGORIES:
            await __import__("mystery").mystery_send(ctx, f"❌ Invalid category `{category}`. Allowed: {', '.join(config.ABILITY_CATEGORIES)}")
            return

        # parse uses (store as raw string)
        uses_raw = uses.lower()

        chid = rc.id
        self.abilities.setdefault(chid, {})
        # Prevent duplicate numeric identifiers regardless of A prefix (e.g., 1 and A1 conflict)
        num_part = key[1:] if key.upper().startswith("A") else key
        for existing in self.abilities[chid].keys():
            existing_num = existing[1:] if existing.upper().startswith("A") else existing
            if existing_num == num_part:
                await __import__("mystery").mystery_send(ctx, f"❌ Ability number `{num_part}` already assigned as `{existing}` for {rc.mention}.")
                return

        self.abilities[chid][key] = {"category": cat, "uses": uses_raw, "owner_channel": chid}
        await __import__("mystery").mystery_send(ctx, f"✅ Assigned ability `{key}` ({cat}, uses={uses_raw}) to {rc.mention}.")
        self._save_state()

    @commands.command(name="team")
    @commands.has_permissions(administrator=True)
    async def set_team(self, ctx: commands.Context, rc: discord.TextChannel, team_name: str) -> None:
        """Assign a team to an RC: .team #rc {team}"""
        self.teams[rc.id] = team_name.lower()
        await __import__("mystery").mystery_send(ctx, f"✅ Set team for {rc.mention} to `{team_name}`")
        self._save_state()

    @commands.command(name="osabilities")
    @commands.has_permissions(administrator=True)
    async def os_abilities(self, ctx: commands.Context) -> None:
        """Show ordered list of pending abilities for OS processing."""
        if not self.pending_abilities:
            await __import__("mystery").mystery_send(ctx, "✅ No pending abilities.")
            return

        # Priority ordering map
        priority = {
            "Manipulation": 1,
            "Blocking": 2,
            "Protection": 3,
            "Curing": 4,
            "Lethal": 5,
            "Other": 6,
            "Transport": 7
        }

        def sort_key(item):
            pr = priority.get(item.get("category"), 99)
            # team-aware ordering inside categories
            team = (item.get("team") or "?").lower()
            # Lethal categories use Sublime -> Shadow -> Dark -> Neutral
            if str(item.get("category")).lower() == "lethal":
                team_order = ["sublime", "shadow", "dark", "neutral"]
            else:
                # non-lethal ordering: Dark -> RK -> Sublime -> Neutral
                team_order = ["dark", "rk", "sublime", "neutral"]
            try:
                team_idx = team_order.index(team)
            except ValueError:
                team_idx = 99
            # tie-break by team priority then timestamp
            return (pr, team_idx, item.get("timestamp"))

        ordered = sorted(self.pending_abilities, key=sort_key)

        # Group into fields by category
        groups = {}
        for it in ordered:
            cat = it.get("category") or "Other"
            teams = it.get("team") or "?"
            rcid = it.get("channel_id")
            ability = it.get("ability")
            desc = it.get("description")
            line = f"[{teams}] <#{rcid}> `{ability}` — {desc}"
            groups.setdefault(cat, []).append(line)

        embed = discord.Embed(title="📋 OS Abilities Queue", color=discord.Color.gold())
        for cat, lines in groups.items():
            embed.add_field(name=cat, value="\n".join(lines)[:1020], inline=False)

        await ctx.send(embed=embed)
        # no state change

    @commands.command(name="extravote")
    @commands.has_permissions(administrator=True)
    async def extra_vote(self, ctx: commands.Context, target: discord.Member) -> None:
        """Give an extra vote to a player: .extravote @player"""
        self.extra_votes[target.id] = self.extra_votes.get(target.id, 0) + 1
        await __import__("mystery").mystery_send(ctx, f"✅ Added an extra vote to {target.mention} (total extra: {self.extra_votes[target.id]})")
        self._save_state()

    @commands.command(name="removeextra")
    @commands.has_permissions(administrator=True)
    async def remove_extra_vote(self, ctx: commands.Context, target: discord.Member) -> None:
        """Remove one extra vote from a player: .removeextra @player"""
        if self.extra_votes.get(target.id, 0) > 0:
            self.extra_votes[target.id] -= 1
            await __import__("mystery").mystery_send(ctx, f"✅ Removed one extra vote from {target.mention} (remaining extra: {self.extra_votes[target.id]})")
            self._save_state()
        else:
            await __import__("mystery").mystery_send(ctx, f"⚠ {target.mention} has no extra votes.")
            # no state change

    async def block_sue(self, ctx: commands.Context, target: Optional[Union[discord.Member, discord.TextChannel]] = None) -> None:
        """Block a player or RC from suing: .blocksue @player or .blocksue #rc"""
        if isinstance(target, discord.Member):
            self.blocksue_members.add(target.id)
            await __import__("mystery").mystery_send(ctx, f"✅ {target.mention} is blocked from suing.")
            self._save_state()
            return
        if isinstance(target, discord.TextChannel):
            self.blocksue_channels.add(target.id)
            await __import__("mystery").mystery_send(ctx, f"✅ {target.mention} (RC) is blocked from suing.")
            self._save_state()
            return
        await __import__("mystery").mystery_send(ctx, "❌ Usage: .blocksue @player or .blocksue #rc")

    async def unblock_sue(self, ctx: commands.Context, target: Optional[Union[discord.Member, discord.TextChannel]] = None) -> None:
        """Unblock a player or RC from suing: .unblocksue @player or .unblocksue #rc"""
        if isinstance(target, discord.Member):
            self.blocksue_members.discard(target.id)
            await __import__("mystery").mystery_send(ctx, f"✅ {target.mention} is unblocked from suing.")
            self._save_state()
            return
        if isinstance(target, discord.TextChannel):
            self.blocksue_channels.discard(target.id)
            await __import__("mystery").mystery_send(ctx, f"✅ {target.mention} (RC) is unblocked from suing.")
            self._save_state()
            return
        await __import__("mystery").mystery_send(ctx, "❌ Usage: .unblocksue @player or .unblocksue #rc")

    async def mute_player_rc(self, ctx: commands.Context, rc: discord.TextChannel) -> None:
        """Mute the player of an RC so they cannot chat in DAYCHAT: .mute #rc"""
        # find member owning the rc via overwrites
        owner = None
        for target, ow in rc.overwrites.items():
            try:
                if isinstance(target, discord.Member) and getattr(ow, 'view_channel', False):
                    owner = target
                    break
            except Exception:
                continue
        if not owner:
            await __import__("mystery").mystery_send(ctx, "❌ Could not determine RC owner to mute.")
            return
        daycat = discord.utils.get(ctx.guild.categories, name="DAYCHAT")
        if not daycat:
            await __import__("mystery").mystery_send(ctx, "❌ DAYCHAT category not found.")
            return
        for ch in daycat.text_channels:
            try:
                await ch.set_permissions(owner, send_messages=False, reason="Muted via .mute")
            except Exception:
                continue
        self.muted_players.add(owner.id)
        await __import__("mystery").mystery_send(ctx, f"✅ Muted {owner.display_name} in DAYCHAT.")
        self._save_state()

    async def unmute_player_rc(self, ctx: commands.Context, rc: discord.TextChannel) -> None:
        """Undo mute applied by .mute: .unmute #rc"""
        owner = None
        for target, ow in rc.overwrites.items():
            try:
                if isinstance(target, discord.Member) and getattr(ow, 'view_channel', False):
                    owner = target
                    break
            except Exception:
                continue
        if not owner:
            await __import__("mystery").mystery_send(ctx, "❌ Could not determine RC owner to unmute.")
            return
        daycat = discord.utils.get(ctx.guild.categories, name="DAYCHAT")
        if not daycat:
            await __import__("mystery").mystery_send(ctx, "❌ DAYCHAT category not found.")
            return
        for ch in daycat.text_channels:
            try:
                await ch.set_permissions(owner, overwrite=None, reason="Unmuted via .unmute")
            except Exception:
                continue
        self.muted_players.discard(owner.id)
        await __import__("mystery").mystery_send(ctx, f"✅ Unmuted {owner.display_name} in DAYCHAT.")
        self._save_state()

    async def show_phase(self, ctx: commands.Context) -> None:
        """Show the current phase: .phase"""
        # Prefer PhasesCog's authoritative display if present
        try:
            pc = self.bot.get_cog("PhasesCog")
            if pc and hasattr(pc, "get_display_phase"):
                display = pc.get_display_phase(ctx.guild.id)
            else:
                display = str(self.current_phase or "").strip()
        except Exception:
            display = str(self.current_phase or "").strip()

        await __import__("mystery").mystery_send(ctx, f"📍 Current phase: {display}")

    # --- Phase and OS processing helpers ---
    def _phase_epoch(self, phase_str: str) -> Optional[int]:
        """Convert phase string like 'Day 1' or 'Night 2' to an integer epoch for ordering.

        Day1 -> 0, Night1 -> 1, Day2 -> 2, Night2 -> 3, ...
        Returns None if unparsable.
        """
        if not phase_str:
            return None
        try:
            parts = phase_str.strip().split()
            if len(parts) >= 2 and parts[1].isdigit():
                typ = parts[0].lower()
                num = int(parts[1])
                base = (num - 1) * 2
                return base + (0 if typ.startswith("d") else 1)
        except Exception:
            return None
        # try short token like 'd1' or 'n2'
        m = re.match(r"^([dn])(\s*)(\d+)$", phase_str.strip().lower())
        if m:
            typ = m.group(1)
            num = int(m.group(3))
            base = (num - 1) * 2
            return base + (0 if typ == "d" else 1)
        return None

    def _until_to_epoch(self, token: str) -> Optional[int]:
        """Parse an 'until' token like 'n2', 'd3', 'Day 2' into epoch integer or None for forever/unparsable."""
        if not token:
            return None
        token = str(token).strip().lower()
        if token == "forever":
            return None
        # allow forms: n2, d3, day 2, night 1
        m = re.match(r"^([dn])(\s*)(\d+)$", token)
        if m:
            typ = m.group(1)
            num = int(m.group(3))
            base = (num - 1) * 2
            return base + (0 if typ == "d" else 1)
        m2 = re.match(r"^(day|night)\s*(\d+)$", token)
        if m2:
            typ = m2.group(1)[0]
            num = int(m2.group(2))
            base = (num - 1) * 2
            return base + (0 if typ == "d" else 1)
        return None

    async def process_phase_change(self, new_phase: str) -> None:
        """Process stored roleblocks/visit blocks and expire ones whose 'until' has passed for the new phase."""
        new_epoch = self._phase_epoch(new_phase)
        if new_epoch is None:
            logger.info(f"process_phase_change: could not parse new_phase='{new_phase}'")
            return

        removed_keys = []
        # process keyed roleblocks like 'rcid:ABILITY'
        for key in list(self.roleblocks.keys()):
            try:
                if ":" in key:
                    entry = self.roleblocks.get(key, {})
                    until = entry.get("until")
                    if until and until != "forever":
                        until_epoch = self._until_to_epoch(until)
                        if until_epoch is None:
                            continue
                        boundary = entry.get("boundary", "end")
                        if (boundary == "end" and new_epoch > until_epoch) or (boundary == "beginning" and new_epoch >= until_epoch):
                            del self.roleblocks[key]
                            removed_keys.append(key)
                else:
                    # channel-scoped blocks (stored under string channel id)
                    entry = self.roleblocks.get(key)
                    if isinstance(entry, dict) and entry.get("visit_block"):
                        vb = entry.get("visit_block")
                        until = vb.get("until")
                        if until and until != "forever":
                            until_epoch = self._until_to_epoch(until)
                            if until_epoch is None:
                                continue
                            boundary = vb.get("boundary", "end")
                            if (boundary == "end" and new_epoch > until_epoch) or (boundary == "beginning" and new_epoch >= until_epoch):
                                # remove visit_block
                                try:
                                    del self.roleblocks[key]["visit_block"]
                                    if not self.roleblocks[key]:
                                        del self.roleblocks[key]
                                    removed_keys.append(f"{key}.visit_block")
                                except Exception:
                                    continue
            except Exception:
                continue

        if removed_keys:
            self._save_state()
            logger.info(f"Cleared expired roleblocks/visitblocks: {removed_keys}")

    async def set_phase(self, new_phase: str) -> None:
        """Public API to set the current phase and process expiries."""
        self.current_phase = new_phase
        self._save_state()
        await self.process_phase_change(new_phase)

    @commands.command(name="processos")
    @commands.has_permissions(administrator=True)
    async def process_os(self, ctx: commands.Context) -> None:
        """Process pending abilities for OS: consumes visits when applicable and skips blocked entries."""
        if not self.pending_abilities:
            await __import__("mystery").mystery_send(ctx, "✅ No pending abilities to process.")
            return

        # Priority ordering map (same as os_abilities)
        priority = {
            "Manipulation": 1,
            "Blocking": 2,
            "Protection": 3,
            "Curing": 4,
            "Lethal": 5,
            "Other": 6,
            "Transport": 7
        }

        def sort_key(item):
            pr = priority.get(item.get("category"), 99)
            team = (item.get("team") or "?").lower()
            if str(item.get("category")).lower() == "lethal":
                team_order = ["sublime", "shadow", "dark", "neutral"]
            else:
                team_order = ["dark", "rk", "sublime", "neutral"]
            try:
                team_idx = team_order.index(team)
            except ValueError:
                team_idx = 99
            return (pr, team_idx, item.get("timestamp"))

        ordered = sorted(self.pending_abilities, key=sort_key)

        processed = []
        skipped = []

        for p in ordered:
            try:
                ch_id = p.get("channel_id")
                ability = p.get("ability")
                # check ability-specific roleblock
                rb_key = f"{ch_id}:{ability}"
                if rb_key in self.roleblocks:
                    skipped.append((p, "ability_blocked"))
                    continue

                # check visit block on channel
                ch_rb = self.roleblocks.get(str(ch_id), {})
                if isinstance(ch_rb, dict) and ch_rb.get("visit_block"):
                    skipped.append((p, "visit_blocked"))
                    continue

                # consume a visit if available for this RC
                if ch_id in self.visits and self.visits[ch_id]:
                    # prefer order regular, stealth, forced, both
                    for t in ("regular", "stealth", "forced", "both"):
                        if t in self.visits.get(ch_id, {}):
                            val = self.visits[ch_id][t]
                            m = re.match(r"^(\d+)", str(val))
                            if m:
                                cnt = int(m.group(1)) - 1
                                if cnt <= 0:
                                    del self.visits[ch_id][t]
                                else:
                                    newval = re.sub(r"^\d+", str(cnt), str(val), count=1)
                                    self.visits[ch_id][t] = newval
                            else:
                                # non-numeric or special token -> consume and remove
                                del self.visits[ch_id][t]
                            break

                # mark processed
                p["status"] = "processed"
                processed.append(p)
            except Exception:
                skipped.append((p, "error"))
                continue

        # remove processed entries
        self.pending_abilities = [p for p in self.pending_abilities if p.get("status") != "processed"]
        self._save_state()

        await __import__("mystery").mystery_send(ctx, f"✅ Processed {len(processed)} abilities, skipped {len(skipped)}.")

    @commands.command(name="preset")
    async def add_preset(self, ctx: commands.Context, *, preset_text: str) -> None:
        """Add a preset action for your RC: .preset <time> <action description>"""
        # If user typed `.preset list` or `.preset show`, show presets instead
        if preset_text.strip().lower() in ("list", "show"):
            return await self.list_presets(ctx)

        chid = ctx.channel.id
        self.presets.setdefault(chid, [])

        entry = {"text": preset_text, "timestamp": datetime.utcnow()}
        # If preset begins with an ability token like A1 or 1, attach ability/category metadata
        toks = preset_text.strip().split(None, 1)
        if toks:
            tok0 = toks[0]
            ak = None
            if tok0.upper().startswith("A") and tok0[1:].isdigit():
                ak = tok0.upper()
            elif tok0.isdigit():
                ak = tok0
            if ak:
                # try to resolve to stored ability key (A-prefixed or numeric)
                chmap = self.abilities.get(chid, {})
                abdef = chmap.get(ak)
                if not abdef:
                    # try alternate form
                    alt = (ak[1:] if ak.upper().startswith("A") else f"A{ak}")
                    abdef = chmap.get(alt) or chmap.get(alt.upper())
                    if abdef:
                        ak = next((k for k in chmap.keys() if k.upper() == (alt).upper()), ak)
                if abdef:
                    entry["ability"] = ak
                    entry["category"] = abdef.get("category")
                    entry["team"] = self.teams.get(chid)

        self.presets[chid].append(entry)
        await __import__("mystery").mystery_send(ctx, f"✅ Preset added for this RC: {preset_text}")
        self._save_state()

    @commands.command(name="presets", aliases=["presetlist", "preset_list", "presetlist"])
    async def list_presets(self, ctx: commands.Context) -> None:
        """List presets for this RC with pagination: .presets"""
        chid = ctx.channel.id
        lst = self.presets.get(chid, [])
        if not lst:
            await __import__("mystery").mystery_send(ctx, "✅ No presets for this RC.")
            return

        # Paginate 5 per page
        page_size = 5
        pages = [lst[i:i+page_size] for i in range(0, len(lst), page_size)]

        class PresetPager(discord.ui.View):
            def __init__(self, pages):
                super().__init__(timeout=120)
                self.pages = pages
                self.idx = 0

            async def update_message(self, interaction=None, send_msg=None):
                page = self.pages[self.idx]
                embed = discord.Embed(title=f"Presets for {ctx.channel.name} (Page {self.idx+1}/{len(self.pages)})", color=discord.Color.blurple())
                for i, it in enumerate(page, start=self.idx*page_size+1):
                    text = it.get("text") if isinstance(it, dict) else str(it)
                    cat = it.get("category") if isinstance(it, dict) else None
                    abil = it.get("ability") if isinstance(it, dict) else None
                    label = f"[{cat}] " if cat else ""
                    if abil:
                        label += f"`{abil}` "
                    embed.add_field(name=f"{i}.", value=label + text, inline=False)
                if interaction:
                    await interaction.response.edit_message(embed=embed, view=self)
                else:
                    await send_msg.edit(embed=embed, view=self)

            @discord.ui.button(label="◀ Prev", style=discord.ButtonStyle.secondary)
            async def prev(self, inter: discord.Interaction, button: discord.ui.Button):
                if self.idx > 0:
                    self.idx -= 1
                    await self.update_message(interaction=inter)
                else:
                    await inter.response.defer()

            @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.secondary)
            async def next(self, inter: discord.Interaction, button: discord.ui.Button):
                if self.idx < len(self.pages)-1:
                    self.idx += 1
                    await self.update_message(interaction=inter)
                else:
                    await inter.response.defer()

        view = PresetPager(pages)
        # send initial message
        embed = discord.Embed(title=f"Presets for {ctx.channel.name} (Page 1/{len(pages)})", color=discord.Color.blurple())
        for i, it in enumerate(pages[0], start=1):
            text = it.get("text") if isinstance(it, dict) else str(it)
            cat = it.get("category") if isinstance(it, dict) else None
            abil = it.get("ability") if isinstance(it, dict) else None
            label = f"[{cat}] " if cat else ""
            if abil:
                label += f"`{abil}` "
            embed.add_field(name=f"{i}.", value=label + text, inline=False)
        msg = await ctx.send(embed=embed, view=view)
        # pass send_msg for first render
        await view.update_message(send_msg=msg)

    @commands.command(name="presetmove")
    async def preset_move(self, ctx: commands.Context, old_index: int, new_index: int) -> None:
        """Reorder presets for this RC: .presetmove <old_index> <new_index> (1-based indexes)."""
        chid = ctx.channel.id
        lst = self.presets.get(chid, [])
        if not lst:
            await __import__("mystery").mystery_send(ctx, "❌ No presets for this RC.")
            return

        # determine channel owner (member with view overwrite)
        owner = None
        for target, ow in ctx.channel.overwrites.items():
            try:
                if isinstance(target, discord.Member) and getattr(ow, 'view_channel', False):
                    owner = target
                    break
            except Exception:
                continue

        if owner and owner.id != ctx.author.id and not ctx.author.guild_permissions.administrator:
            await __import__("mystery").mystery_send(ctx, "❌ Only the RC owner or an administrator can reorder presets.")
            return

        # convert to zero-based
        try:
            oi = int(old_index) - 1
            ni = int(new_index) - 1
        except Exception:
            await __import__("mystery").mystery_send(ctx, "❌ Indexes must be integers.")
            return

        if oi < 0 or oi >= len(lst) or ni < 0 or ni > len(lst):
            await __import__("mystery").mystery_send(ctx, "❌ Index out of range for presets.")
            return

        item = lst.pop(oi)
        lst.insert(ni, item)
        self.presets[chid] = lst
        self._save_state()
        await __import__("mystery").mystery_send(ctx, f"✅ Moved preset from position {old_index} to {new_index}.")

    @commands.command(name="ospreset")
    @commands.has_permissions(administrator=True)
    async def ospreset(self, ctx: commands.Context) -> None:
        """Admin view of all presets across RCs: .ospreset"""
        if not ctx.guild:
            await __import__("mystery").mystery_send(ctx, "❌ This command must be used in a server (not DM).")
            return

        if not self.presets:
            await __import__("mystery").mystery_send(ctx, "✅ No presets stored.")
            return

        embed = discord.Embed(title="📋 All Presets", color=discord.Color.blue())
        for chid, lst in self.presets.items():
            try:
                ch = ctx.guild.get_channel(int(chid)) if isinstance(chid, str) else ctx.guild.get_channel(chid)
                title = ch.mention if ch else str(chid)
            except Exception:
                title = str(chid)
            lines = []
            for idx, it in enumerate(lst, 1):
                if isinstance(it, dict):
                    text = it.get("text")
                    cat = it.get("category")
                    abil = it.get("ability")
                    prefix = f"[{cat}] `" + abil + "` " if abil and cat else (f"[{cat}] " if cat else "")
                    lines.append(f"{idx}. {prefix}{text}")
                else:
                    lines.append(f"{idx}. {str(it)}")
            embed.add_field(name=title, value="\n".join(lines)[:1020], inline=False)

        # send via ctx.send because mystery_send does not accept embed kw
        await ctx.send(embed=embed)

    @commands.command(name="updateability")
    @commands.has_permissions(administrator=True)
    async def update_ability(self, ctx: commands.Context, rc: discord.TextChannel, ability_key: str, new_category: str) -> None:
        """Update ability category: .update {ability number} {newcategory}"""
        chmap = self.abilities.get(rc.id, {})
        key = ability_key.upper()
        if key not in chmap:
            await __import__("mystery").mystery_send(ctx, "❌ Ability not found.")
            return
        chmap[key]["category"] = new_category
        await __import__("mystery").mystery_send(ctx, f"✅ Updated `{key}` to category `{new_category}` for {rc.mention}.")
        self._save_state()

    @commands.command(name="addability")
    @commands.has_permissions(administrator=True)
    async def add_ability_alias(self, ctx: commands.Context, rc: discord.TextChannel, ability_key: str, category: str, uses: str) -> None:
        """Add new ability (alias to giveability)."""
        await self.give_ability.callback(self, ctx, rc, ability_key, category, uses)
        # give_ability.save will call _save_state

    @commands.command(name="removeability")
    @commands.has_permissions(administrator=True)
    async def remove_ability(self, ctx: commands.Context, rc: discord.TextChannel, ability_key: str) -> None:
        """Remove ability without renumbering others: .remove {ability number}"""
        key = ability_key.upper()
        if rc.id in self.abilities and key in self.abilities[rc.id]:
            del self.abilities[rc.id][key]
            await __import__("mystery").mystery_send(ctx, f"✅ Removed ability `{key}` from {rc.mention}.")
            self._save_state()
        else:
            await __import__("mystery").mystery_send(ctx, "❌ Ability not found.")

    @commands.command(name="givevisit")
    @commands.has_permissions(administrator=True)
    async def give_visit(self, ctx: commands.Context, rc: discord.TextChannel, count: str, vtype: Optional[str] = None) -> None:
        """Give visits to an RC: .givevisit #rc {COUNT} {TYPE}

        TYPE: regular (default), stealth, forced, both
        COUNT: same format as uses (1n, 1d, 1p, 1g, 1gn, 1gd, 1now)
        """
        t = (vtype or "regular").lower()
        if t not in ("regular", "stealth", "forced", "both"):
            await __import__("mystery").mystery_send(ctx, "❌ Invalid visit type. Use: regular, stealth, forced, both")
            return
        self.visits.setdefault(rc.id, {})
        # store latest count string for type
        self.visits[rc.id][t] = count.lower()
        await __import__("mystery").mystery_send(ctx, f"✅ Gave {count} ({t}) visits to {rc.mention}.")
        self._save_state()

    @commands.command(name="removevisits")
    @commands.has_permissions(administrator=True)
    async def remove_visits(self, ctx: commands.Context, rc: discord.TextChannel, count: str, vtype: Optional[str] = None) -> None:
        """Remove visits: .removevisits #rc {COUNT} {TYPE}"""
        t = (vtype or "regular").lower()
        if rc.id not in self.visits or t not in self.visits[rc.id]:
            await __import__("mystery").mystery_send(ctx, f"⚠ No visits of type {t} found for {rc.mention}.")
            return
        # naive implementation: if counts match, delete; otherwise clear
        if self.visits[rc.id].get(t) == count.lower():
            del self.visits[rc.id][t]
            await __import__("mystery").mystery_send(ctx, f"✅ Removed visits {count} ({t}) from {rc.mention}.")
        else:
            # if different, remove the entry
            del self.visits[rc.id][t]
            await __import__("mystery").mystery_send(ctx, f"✅ Removed visits of type {t} from {rc.mention}.")
        self._save_state()

    @commands.command(name="visitblock")
    @commands.has_permissions(administrator=True)
    async def visit_block(self, ctx: commands.Context, rc: discord.TextChannel, until: str) -> None:
        """Block visits for an RC until a phase: .visitblock #rc {UNTIL-WHEN} (e.g., n2, d3, forever)"""
        # store simple block entry
        self.roleblocks.setdefault(str(rc.id), {})
        self.roleblocks[str(rc.id)]["visit_block"] = {"until": until, "set_at": datetime.utcnow().isoformat()}
        await __import__("mystery").mystery_send(ctx, f"✅ Visits for {rc.mention} blocked until {until}.")
        self._save_state()

    @commands.command(name="unvisitblock")
    @commands.has_permissions(administrator=True)
    async def unvisit_block(self, ctx: commands.Context, rc: discord.TextChannel) -> None:
        """Unblock visits for an RC: .unvisitblock #rc"""
        if str(rc.id) in self.roleblocks and "visit_block" in self.roleblocks[str(rc.id)]:
            del self.roleblocks[str(rc.id)]["visit_block"]
            await __import__("mystery").mystery_send(ctx, f"✅ Visit block removed for {rc.mention}.")
            self._save_state()
        else:
            await __import__("mystery").mystery_send(ctx, f"⚠ No visit block found for {rc.mention}.")

    @commands.command(name="block")
    @commands.has_permissions(administrator=True)
    async def block_ability(self, ctx: commands.Context, rc: discord.TextChannel, ability_key: str, until: str = None, boundary: str = "end") -> None:
        """Block a specific ability for an RC: .block #rc {ABILITY-NUMBER} {UNTIL-WHEN} {beginning/end} or 'forever'"""
        key = ability_key.upper()
        rb_key = f"{rc.id}:{key}"
        self.roleblocks[rb_key] = {"until": until or "forever", "boundary": boundary, "set_at": datetime.utcnow().isoformat()}
        await __import__("mystery").mystery_send(ctx, f"✅ Blocked ability `{key}` on {rc.mention} until `{until or 'forever'}` ({boundary}).")
        self._save_state()

    @commands.command(name="unblock")
    @commands.has_permissions(administrator=True)
    async def unblock_ability(self, ctx: commands.Context, rc: discord.TextChannel, ability_key: str) -> None:
        """Unblock a specific ability: .unblock #rc {ABILITY-NUMBER}"""
        key = ability_key.upper()
        rb_key = f"{rc.id}:{key}"
        if rb_key in self.roleblocks:
            del self.roleblocks[rb_key]
            await __import__("mystery").mystery_send(ctx, f"✅ Unblocked ability `{key}` on {rc.mention}.")
            self._save_state()
        else:
            await __import__("mystery").mystery_send(ctx, "⚠ No roleblock found.")

    @commands.command(name="admin_actions")
    @commands.has_permissions(administrator=True)
    async def admin_view_actions(self, ctx: commands.Context) -> None:
        """Admin view of all actions with their status."""
        if not self.actions:
            await __import__("mystery").mystery_send(ctx, "❌ No actions queued.")
            return

        # Send one interactive message per action so admins can click Done/Cancel.
        # This favors explicit per-action control over a single large embed.
        for action_id, action in list(self.actions.items()):
            color_map = {
                "pending": discord.Color.yellow(),
                "done": discord.Color.green(),
                "cancelled": discord.Color.greyple()
            }
            status_map = {
                "pending": "⏳ Pending",
                "done": "✅ Done",
                "cancelled": "❌ Cancelled"
            }

            embed = discord.Embed(
                title=f"Action #{action.action_id}",
                color=color_map.get(action.status, discord.Color.light_grey()),
                timestamp=action.timestamp
            )
            embed.add_field(name="Status", value=status_map.get(action.status, action.status), inline=True)
            embed.add_field(name="User", value=f"<@{action.user_id}>", inline=True)
            embed.add_field(name="Channel", value=f"<#{action.channel_id}>", inline=True)
            embed.add_field(name="Time", value=action.timestamp.strftime("%Y-%m-%d %H:%M:%S UTC"), inline=False)
            embed.add_field(name="Message", value=action.description or "(empty)", inline=False)

            try:
                admin_view = AdminActionView(action, ctx.guild, self)
                await ctx.send(embed=embed, view=admin_view)
            except Exception as e:
                # Fallback: send embed without interactive buttons
                await ctx.send(embed=embed)


async def setup(bot: commands.Bot) -> None:
    cog = ActionQueueCog(bot)
    await bot.add_cog(cog)

    # Conditionally register commands that may conflict with other cogs.
    # If a command with the desired name already exists, register an alternative name.
    def _add_conditional(name: str, func, check_perm: bool = True):
        """Register the command under a prefixed name to avoid colliding with other cogs.

        This will always register `aq_<name>` so other cogs can safely expose
        the canonical command name like `mute` or `blocksue`.

        A small wrapper is used to ensure the callback signature includes a
        `ctx` parameter (avoids errors when introspecting bound methods).
        """
        cmd_name = f"aq_{name}"
        async def _wrapper(ctx, *a, **kw):
            try:
                return await func(ctx, *a, **kw)
            except TypeError:
                # In case func doesn't accept ctx, try calling without ctx
                return await func(*a, **kw)

        try:
            bot.add_command(commands.Command(_wrapper, name=cmd_name))
            logger.info(f"Registered command: {cmd_name} (requested: {name})")
        except Exception as e:
            logger.warning(f"Could not register command {cmd_name}: {e}")

    # block/unblock sue
    _add_conditional("blocksue", cog.block_sue)
    _add_conditional("unblocksue", cog.unblock_sue)

    # mute/unmute RC owner in DAYCHAT
    _add_conditional("mute", cog.mute_player_rc)
    _add_conditional("unmute", cog.unmute_player_rc)

    # phase command
    _add_conditional("phase", cog.show_phase)

