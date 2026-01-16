import logging
import discord
import asyncio
from discord.ext import commands
from typing import List, Optional
import time
import re
from config import RULES_TEXT
from discord import PermissionOverwrite

from config import SERVER_STRUCTURE, TOP_LEVEL_CHANNELS, ROLE_PERMISSIONS, DEFAULT_ROLES

logger = logging.getLogger("discord_bot")

THROTTLE = 1
SETUP_COOLDOWN = 150  # seconds between allowed setup runs per guild




class ServerSetupCog(commands.Cog):
    """Cog to create a server skeleton and apply role-based overwrites."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        # track running setups to prevent concurrent runs per guild
        self._setup_running: set[int] = set()

    # Public helpers to create canonical channels that can be called from other cogs
    async def create_vote_count_channel(self, guild: discord.Guild, canonical_vote: Optional[str], vote_cat: Optional[str]) -> Optional[discord.TextChannel]:
        if not canonical_vote:
            return None
        vote_count_ch = discord.utils.get(guild.text_channels, name=canonical_vote)
        if vote_count_ch:
            return vote_count_ch
        try:
            cat_obj = discord.utils.get(guild.categories, name=vote_cat) if vote_cat else None
            vote_count_ch = await guild.create_text_channel(canonical_vote, category=cat_obj)
            await asyncio.sleep(THROTTLE)
            return vote_count_ch
        except Exception as e:
            logger.warning(f"Could not create canonical vote-count channel {canonical_vote}: {e}")
            return None

    async def create_rules_channel(self, guild: discord.Guild, canonical_rules: Optional[str], rules_cat: Optional[str]) -> Optional[discord.TextChannel]:
        if not canonical_rules:
            return None
        rules_ch = discord.utils.get(guild.text_channels, name=canonical_rules)
        if rules_ch:
            return rules_ch
        try:
            cat_obj = discord.utils.get(guild.categories, name=rules_cat) if rules_cat else None
            rules_ch = await guild.create_text_channel(canonical_rules, category=cat_obj)
            await asyncio.sleep(THROTTLE)
            # send canonical rules text split into reasonably sized messages
            try:
                points = re.split(r"\n(?=\d+\.)", RULES_TEXT.strip())
                points = [p.strip() for p in points if p.strip()]
                if len(points) <= 9:
                    await rules_ch.send("📜 **Server Rules**\n\n" + "\n\n".join(points))
                else:
                    first = "\n\n".join(points[:9])
                    rest = "\n\n".join(points[9:])
                    await rules_ch.send("📜 **Server Rules**\n\n" + first)
                    await rules_ch.send(rest)
            except Exception as e:
                logger.warning(f"Failed to send rules message in {canonical_rules}: {e}")
            return rules_ch
        except Exception as e:
            logger.warning(f"Could not create canonical rules channel {canonical_rules}: {e}")
            return None

    async def create_map_channel(self, guild: discord.Guild, canonical_map: Optional[str], map_cat: Optional[str]) -> Optional[discord.TextChannel]:
        if not canonical_map:
            return None
        map_ch = discord.utils.get(guild.text_channels, name=canonical_map)
        if map_ch:
            return map_ch
        try:
            cat_obj = discord.utils.get(guild.categories, name=map_cat) if map_cat else None
            map_ch = await guild.create_text_channel(canonical_map, category=cat_obj)
            await asyncio.sleep(THROTTLE)
            # delegate to ManorsCog if available
            try:
                manors_cog = self.bot.get_cog("ManorsCog")
                if manors_cog and hasattr(manors_cog, "generate_map_for_channel"):
                    await manors_cog.generate_map_for_channel(guild, map_ch)
            except Exception:
                pass
            return map_ch
        except Exception as e:
            logger.warning(f"Could not create canonical map channel {canonical_map}: {e}")
            return None

    async def create_lynch_session(self, guild: discord.Guild, base_name: str = "lynch-session") -> Optional[discord.TextChannel]:
        """Create a lynch session channel `🗳│lynch-session-N` in category DAYCHAT and return it.

        If an existing channel with the canonical prefix is found, reuse category/prefix.
        """
        # determine next available number
        highest = 0
        for ch in guild.text_channels:
            try:
                m = __import__('re').search(rf"{base_name}-(\d+)", ch.name.lower())
                if m:
                    highest = max(highest, int(m.group(1)))
            except Exception:
                continue
        desired = f"{base_name}-{highest+1}"
        # preserve prefix from an existing vote/lynch channel if present
        prefix = ""
        for ch in guild.text_channels:
            try:
                if base_name in ch.name.lower():
                    lower = ch.name.lower()
                    idx = lower.find(base_name)
                    prefix = ch.name[:idx]
                    break
            except Exception:
                continue

        create_name = f"{prefix}{desired}" if prefix else desired
        # find DAYCHAT category if available
        daycat = discord.utils.get(guild.categories, name="DAYCHAT")
        existing = discord.utils.get(guild.text_channels, name=create_name)
        if existing:
            return existing
        try:
            ch = await guild.create_text_channel(create_name, category=daycat)
            await asyncio.sleep(THROTTLE)
            return ch
        except Exception as e:
            logger.warning(f"Could not create lynch session channel {create_name}: {e}")
            return None

    async def safe_send(self, guild: discord.Guild, channel: Optional[discord.abc.Messageable], message: str) -> None:
        """Try sending to preferred channels, fall back to available ones."""
        if channel:
            try:
                await channel.send(message)
                return
            except Exception:
                logger.info("Failed to send to invoking channel, falling back")

        for name in ("commands", "general"):
            ch = discord.utils.get(guild.text_channels, name=name)
            if ch:
                try:
                    await ch.send(message)
                    return
                except Exception:
                    continue

        # As a last resort try to DM the guild owner
        try:
            owner = guild.owner
            if owner:
                await owner.send(message)
        except Exception:
            logger.warning("Could not deliver setup message anywhere")

    async def clear_server(self, guild: discord.Guild, protect_channels: Optional[List[discord.abc.Snowflake]] = None):
        """Delete non-protected channels, categories, and roles. Returns lists of deleted names."""
        protect_channels = protect_channels or []
        deleted_channels = []
        deleted_categories = []
        deleted_roles = []

        # Delete channels (skip protected)
        for ch in list(guild.channels):
            try:
                if ch in protect_channels:
                    continue
                await ch.delete()
                await asyncio.sleep(THROTTLE)
                deleted_channels.append(getattr(ch, "name", str(ch)))
            except Exception as e:
                logger.warning(f"Failed to delete channel {getattr(ch,'name',ch)}: {e}")

        # Delete categories
        for cat in list(guild.categories):
            try:
                await cat.delete()
                await asyncio.sleep(THROTTLE)
                deleted_categories.append(cat.name)
            except Exception as e:
                logger.warning(f"Failed to delete category {cat.name}: {e}")

        # Delete roles (safe: don't delete @everyone or roles >= bot top role)
        for role in list(guild.roles):
            try:
                if role.is_default() or role >= guild.me.top_role:
                    continue
                await role.delete()
                await asyncio.sleep(THROTTLE)
                deleted_roles.append(role.name)
            except Exception as e:
                logger.warning(f"Failed to delete role {role.name}: {e}")

        return deleted_channels, deleted_categories, deleted_roles

    async def set_channel_permissions(self, guild: discord.Guild) -> None:
        # Simple permission applicator: applies ROLE_PERMISSIONS to categories/channels.
        categories = {c.name: c for c in guild.categories}
        channels = {c.name: c for c in guild.text_channels}

        for role_name, perms in ROLE_PERMISSIONS.items():
            # find role by name
            role = discord.utils.get(guild.roles, name=role_name)
            if not role:
                continue

            for target_name, settings in perms.items():
                if not isinstance(settings, dict):
                    settings = {"view": bool(settings)}

                target = categories.get(target_name) or channels.get(target_name)
                if not target:
                    continue

                overwrite = PermissionOverwrite()

                if "view" in settings:
                    overwrite.view_channel = bool(settings["view"])
                if "send" in settings:
                    overwrite.send_messages = bool(settings["send"])

                try:
                    await target.set_permissions(role, overwrite=overwrite)
                except Exception as e:
                    logger.warning(f"Failed to set permissions for role {role_name} on {getattr(target,'name',target)}: {e}")

                # Handle per-channel exceptions
                for chan_name, chan_settings in (settings.get("exceptions") or {}).items():
                    chan = channels.get(chan_name)
                    if not chan:
                        # try normalized match (strip emoji prefix)
                        for c_name, c_obj in channels.items():
                            if chan_name.lower() in c_name.lower():
                                chan = c_obj
                                break
                    if not chan:
                        continue

                    ex_overwrite = PermissionOverwrite()
                    if isinstance(chan_settings, dict):
                        if "view" in chan_settings:
                            ex_overwrite.view_channel = bool(chan_settings["view"])
                        if "send" in chan_settings:
                            ex_overwrite.send_messages = bool(chan_settings["send"])
                    else:
                        # boolean shorthand
                        ex_overwrite.view_channel = bool(chan_settings)
                        ex_overwrite.send_messages = bool(chan_settings)

                    try:
                        await chan.set_permissions(role, overwrite=ex_overwrite)
                    except Exception as e:
                        logger.warning(f"Failed to set exception permissions for role {role_name} on {getattr(chan,'name',chan)}: {e}")

    @commands.group(name="setup", invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    @commands.cooldown(1, SETUP_COOLDOWN, commands.BucketType.guild)
    async def setup(self, ctx: commands.Context, number: int = None) -> None:
        """Create server structure, roles, and apply permissions.
        
        Workflow:
        1. Delete all categories
        2. Create general channel if missing
        3. Delete all non-general channels
        4. Create full setup (categories, channels, roles, permissions)
        5. Delete general channel
        """
        guild = ctx.guild
        if not guild:
            await __import__("mystery").mystery_send(ctx, "❌ Command must be used in a guild")
            return

        # Prevent concurrent runs for the same guild
        if guild.id in self._setup_running:
            await __import__("mystery").mystery_send(ctx, "⚠️ Setup is already in progress for this guild")
            return

        # mark running
        self._setup_running.add(guild.id)

        try:
            # Reset notes when setup is executed
            try:
                notes_cog = self.bot.get_cog("NotesCog")
                if notes_cog and hasattr(notes_cog, "reset_all_notes"):
                    notes_cog.reset_all_notes()
                    logger.info("Reset all notes as part of setup")
            except Exception as e:
                logger.warning(f"Could not reset notes: {e}")

            guild = guild
            deleted_channels = []
            deleted_categories = []
            deleted_roles = []

            # Step 1: Delete all categories (this cascades to their channels)
            # Clear previous voting sessions to avoid stale sessions persisting
            try:
                voting_cog = self.bot.get_cog("VotingCog")
                if voting_cog and hasattr(voting_cog, "clear_sessions_for_guild"):
                    voting_cog.clear_sessions_for_guild(guild.id)
                    logger.info(f"Cleared previous voting sessions for guild {guild.id} as part of setup")
            except Exception as e:
                logger.warning(f"Could not clear voting sessions before setup: {e}")

            for cat in list(guild.categories):
                try:
                    await cat.delete()
                    deleted_categories.append(cat.name)
                except Exception as e:
                    logger.warning(f"Failed to delete category {cat.name}: {e}")

            # Step 2: Ensure a stable 'general' channel exists to receive progress messages.
            general = discord.utils.get(guild.text_channels, name="general")
            if not general:
                # Prefer renaming the invoking channel so ctx.send continues to work
                try:
                    if ctx.channel and getattr(ctx.channel, 'guild', None) == guild:
                        try:
                            await ctx.channel.edit(name="general")
                            general = ctx.channel
                            logger.info(f"Renamed invoking channel to 'general' in {guild.name}")
                        except Exception:
                            # Fall back to creating a new channel
                            general = await guild.create_text_channel("general")
                            await asyncio.sleep(THROTTLE)
                            logger.info(f"Created 'general' channel in {guild.name}")
                    else:
                        general = await guild.create_text_channel("general")
                        await asyncio.sleep(THROTTLE)
                        logger.info(f"Created 'general' channel in {guild.name}")
                except Exception as e:
                    logger.warning(f"Failed to ensure general channel: {e}")
                    general = None

            # Step 3: Delete all channels except general
            for ch in list(guild.text_channels):
                try:
                    if ch != general:
                        await ch.delete()
                        await asyncio.sleep(THROTTLE)
                        deleted_channels.append(ch.name)
                except Exception as e:
                    logger.warning(f"Failed to delete channel {getattr(ch, 'name', ch)}: {e}")

            # Step 3b: Delete all roles from DEFAULT_ROLES
            for role_data in DEFAULT_ROLES:
                role_name = role_data[0]
                try:
                    role = discord.utils.get(guild.roles, name=role_name)
                    if role and not role.is_default() and role < guild.me.top_role:
                        await role.delete()
                        deleted_roles.append(role_name)
                except Exception as e:
                    logger.warning(f"Failed to delete role {role_name}: {e}")

            created_categories = []
            created_channels = []
            skipped_categories = []
            skipped_channels = []
            created_category_objs = {}

            # Step 4: Create full setup (categories, channels, roles, permissions)
            # Create categories and channels
            for category_name, channels in SERVER_STRUCTURE.items():
                try:
                    category = discord.utils.get(guild.categories, name=category_name)
                    if not category:
                        category = await guild.create_category(category_name)
                        await asyncio.sleep(THROTTLE)
                        created_categories.append(category_name)
                    else:
                        skipped_categories.append(category_name)

                    created_category_objs[category_name] = category

                    if category_name == "MANORS" and number:
                        channels = [f"🏰│manor-{i+1}" for i in range(number)]
                    elif category_name == "ROLES" and number:
                        channels = [str(i+1) for i in range(number)]

                    for channel_name in channels:
                            try:
                                # Skip canonical special channels; created via dedicated helpers later
                                ln = channel_name.lower() if channel_name else ""
                                if any(tok in ln for tok in ("rules", "map", "vote-count")):
                                    skipped_channels.append(f"{category_name}/{channel_name} (special)")
                                    continue
                                # Check if channel exists within this specific category (not globally)
                                if discord.utils.get(category.text_channels, name=channel_name):
                                    skipped_channels.append(f"{category_name}/{channel_name}")
                                    continue
                                logger.info(f"Creating channel {channel_name} in category {category_name} for guild {guild.id}")
                                try:
                                    await guild.create_text_channel(channel_name, category=category)
                                except TypeError as e:
                                    logger.warning(f"Invalid parameters when creating channel {channel_name}: {e}")
                                    skipped_channels.append(f"{category_name}/{channel_name} (invalid params)")
                                    continue
                                await asyncio.sleep(THROTTLE)
                                created_channels.append(f"{category_name}/{channel_name}")
                            except Exception as e:
                                logger.warning(f"Failed to create channel {channel_name}: {e}")
                except Exception as e:
                    logger.warning(f"Error processing category {category_name}: {e}")

            # Top level channels
            for channel_name in TOP_LEVEL_CHANNELS:
                try:
                    if discord.utils.get(guild.channels, name=channel_name):
                        skipped_channels.append(f"(top) {channel_name}")
                        continue
                    logger.info(f"Creating top-level channel {channel_name} in guild {guild.id}")
                    try:
                        await guild.create_text_channel(channel_name)
                    except TypeError as e:
                        logger.warning(f"Invalid parameters when creating top-level channel {channel_name}: {e}")
                        skipped_channels.append(f"(top) {channel_name} (invalid params)")
                        continue
                    await asyncio.sleep(THROTTLE)
                    created_channels.append(f"(top) {channel_name}")
                except Exception as e:
                    logger.warning(f"Failed to create top-level channel {channel_name}: {e}")

            # Create roles from DEFAULT_ROLES with colors and permissions
            created_roles = []
            skipped_new_roles = []
            for role_data in DEFAULT_ROLES:
                try:
                    role_name = role_data[0]
                    hex_colour = role_data[1]
                    has_admin = role_data[2] if len(role_data) > 2 else False
                    
                    if discord.utils.get(guild.roles, name=role_name):
                        skipped_new_roles.append(role_name)
                        continue
                    
                    colour = discord.Colour(int(hex_colour, 16))
                    
                    # Create role with admin permissions if needed
                    if has_admin:
                        perms = discord.Permissions(administrator=True)
                        await guild.create_role(name=role_name, colour=colour, permissions=perms)
                        await asyncio.sleep(THROTTLE)
                    else:
                        await guild.create_role(name=role_name, colour=colour)
                        await asyncio.sleep(THROTTLE)
                    
                    created_roles.append(role_name)
                except Exception as e:
                    logger.warning(f"Failed to create role {role_name}: {e}")

            # Apply role-based permissions after all roles are created
            try:
                await self.set_channel_permissions(guild)
            except Exception as e:
                logger.error(f"Error applying channel permissions: {e}")

            

            # After all channels/roles/permissions are created and general removed,
            # initialize messaging content last so channels/permissions exist.
            # Ensure vote-count, rules and megaphone exist, then perform final actions
            try:
                def find_canonical(token: str):
                    for cat_name, channels in SERVER_STRUCTURE.items():
                        for ch_name in channels:
                            # match by token ending to handle emoji prefixes like '📊│vote-count'
                            if ch_name.endswith(token) or token in ch_name:
                                return ch_name, cat_name
                    return None, None

                # canonical vote-count
                canonical_vote, vote_cat = find_canonical("vote-count")
                # remove old plain channels
                for old in ("vote-count", "rules", "megaphone"):
                    old_ch = discord.utils.get(guild.text_channels, name=old)
                    if old_ch:
                        try:
                            await old_ch.delete(reason="Removing legacy plain channel during setup")
                            await asyncio.sleep(0.25)
                        except Exception:
                            pass

                # create canonical vote-count in its category via helper
                vote_count_ch = None
                if canonical_vote:
                    vote_count_ch = await self.create_vote_count_channel(guild, canonical_vote, vote_cat)
                    if vote_count_ch:
                        created_channels.append(f"{vote_cat}/{canonical_vote}" if vote_cat else canonical_vote)

                # canonical rules (create via helper)
                canonical_rules, rules_cat = find_canonical("rules")
                rules_ch = None
                if canonical_rules:
                    rules_ch = await self.create_rules_channel(guild, canonical_rules, rules_cat)
                    if rules_ch:
                        created_channels.append(f"{rules_cat}/{canonical_rules}" if rules_cat else canonical_rules)

                # canonical megaphone
                canonical_mega, mega_cat = find_canonical("megaphone")
                megaphone_ch = None
                if canonical_mega:
                    megaphone_ch = discord.utils.get(guild.text_channels, name=canonical_mega)
                    if not megaphone_ch:
                        try:
                            cat_obj = discord.utils.get(guild.categories, name=mega_cat) if mega_cat else None
                            megaphone_ch = await guild.create_text_channel(canonical_mega, category=cat_obj)
                            await asyncio.sleep(0.5)
                            created_channels.append(f"{mega_cat}/{canonical_mega}" if mega_cat else canonical_mega)
                        except Exception as e:
                            logger.warning(f"Could not create canonical megaphone channel {canonical_mega}: {e}")

                # canonical map
                canonical_map, map_cat = find_canonical("map")
                map_ch = None
                if canonical_map:
                    map_ch = await self.create_map_channel(guild, canonical_map, map_cat)
                    if map_ch:
                        created_channels.append(f"{map_cat}/{canonical_map}" if map_cat else canonical_map)

                # Re-apply role permissions to ensure these new channels have correct overwrites
                try:
                    await self.set_channel_permissions(guild)
                except Exception as e:
                    logger.warning(f"Could not reapply channel permissions after creating canonical channels: {e}")

                # Apply phase-specific send permissions if PhasesCog is available
                try:
                    phases_cog = self.bot.get_cog("PhasesCog")
                    if phases_cog and hasattr(phases_cog, "_get_phase_for_guild") and hasattr(phases_cog, "apply_phase_permissions"):
                        try:
                            current_phase = phases_cog._get_phase_for_guild(guild.id)
                        except Exception:
                            current_phase = "pregame"
                        try:
                            await phases_cog.apply_phase_permissions(guild, current_phase)
                            logger.info(f"Applied phase permissions ({current_phase}) for guild {guild.id}")
                        except Exception as e:
                            logger.warning(f"Could not apply phase permissions: {e}")
                except Exception:
                    pass

                # Ensure default table items are created for this guild (utensils table)
                try:
                    economy_cog = self.bot.get_cog("EconomyCog")
                    if economy_cog and hasattr(economy_cog, "ensure_default_table_items_for_guild"):
                        try:
                            economy_cog.ensure_default_table_items_for_guild(guild.id)
                            logger.info(f"Initialized default table items for guild {guild.id}")
                        except Exception as e:
                            logger.warning(f"Could not initialize default table items: {e}")
                except Exception:
                    pass

                # Initialize vote-count message via voting cog if available
                try:
                    voting_cog = self.bot.get_cog("VotingCog")
                    # ensure default sessions exist for this guild after we cleared them earlier
                    if voting_cog and hasattr(voting_cog, "ensure_default_sessions_for_guild"):
                        try:
                            voting_cog.ensure_default_sessions_for_guild(guild)
                            logger.info(f"Recreated default voting sessions for guild {guild.id}")
                        except Exception as e:
                            logger.warning(f"Could not recreate default sessions: {e}")

                    if voting_cog and vote_count_ch and hasattr(voting_cog, "_initialize_vote_count_message"):
                        await voting_cog._initialize_vote_count_message(guild, vote_count_ch)
                        logger.info(f"Initialized vote-count message in {guild.name}")
                except Exception as e:
                    logger.warning(f"Could not initialize vote-count message: {e}")

                # Send rules message to rules_ch
                if rules_ch:
                    rules_text = RULES_TEXT
                    try:
                        # delete old rule messages if any to avoid duplicates
                        try:
                            async for m in rules_ch.history(limit=20):
                                if m.author == self.bot.user:
                                    try:
                                        await m.delete()
                                    except Exception:
                                        pass
                        except Exception:
                            pass

                        # Split rules into numbered points and send 1-9 then 10+
                        points = re.split(r"\n(?=\d+\.)", rules_text.strip())
                        # ensure points are non-empty
                        points = [p.strip() for p in points if p.strip()]
                        if len(points) <= 9:
                            await rules_ch.send("📜 **Server Rules**\n\n" + "\n\n".join(points))
                        else:
                            first = "\n\n".join(points[:9])
                            rest = "\n\n".join(points[9:])
                            await rules_ch.send("📜 **Server Rules**\n\n" + first)
                            # place the remaining points (10+) in the next message
                            await rules_ch.send(rest)
                    except Exception as e:
                        logger.warning(f"Failed to send rules message: {e}")

                # Set slowmode on megaphone if present
                if megaphone_ch:
                    try:
                        await megaphone_ch.edit(slowmode_delay=21600)
                    except Exception as e:
                        logger.warning(f"Could not set megaphone slowmode: {e}")
                # expose a helper to initialize certain canonical channels
                async def _initialize_channel_by_token(token: str, target_ch: Optional[discord.TextChannel] = None):
                    tkn = token.lower()
                    # vote-count: use VotingCog to initialize the vote-count message
                    if "vote-count" in tkn or "vote_count" in tkn:
                        try:
                            voting_cog = self.bot.get_cog("VotingCog")
                            if voting_cog and hasattr(voting_cog, "_initialize_vote_count_message"):
                                ch = target_ch or discord.utils.get(guild.text_channels, name=canonical_vote)
                                if ch:
                                    await voting_cog._initialize_vote_count_message(guild, ch)
                        except Exception:
                            pass
                        return

                    # rules: send canonical rules text (split into messages with 1-9 and 10+)
                    if "rules" in tkn:
                        try:
                            ch = target_ch or rules_ch
                            if not ch:
                                return
                            # delete old bot rule messages
                            try:
                                async for m in ch.history(limit=50):
                                    if m.author == self.bot.user:
                                        try:
                                            await m.delete()
                                        except Exception:
                                            pass
                            except Exception:
                                pass

                            # split RULES_TEXT into numbered points and send 1-9 then 10+
                            parts = re.split(r"\n(?=\d+\.)", RULES_TEXT.strip())
                            parts = [p.strip() for p in parts if p.strip()]
                            if len(parts) <= 9:
                                await ch.send("📜 **Server Rules**\n\n" + "\n\n".join(parts))
                            else:
                                first = "\n\n".join(parts[:9])
                                rest = "\n\n".join(parts[9:])
                                await ch.send("📜 **Server Rules**\n\n" + first)
                                await ch.send("📜 **Server Rules (cont.)**\n\n" + rest)
                        except Exception:
                            pass
                        return

                    # map: delegate to ManorsCog if available
                    if "map" in tkn or "manor" in tkn:
                        try:
                            manors_cog = self.bot.get_cog("ManorsCog")
                            if manors_cog and hasattr(manors_cog, "generate_map_for_channel"):
                                ch = target_ch or discord.utils.get(guild.text_channels, name="map")
                                if ch:
                                    await manors_cog.generate_map_for_channel(guild, ch)
                        except Exception:
                            pass
                        return
                    # attach helper to the cog instance for reuse
                    self.initialize_canonical_channel = _initialize_channel_by_token
            except Exception as e:
                logger.warning(f"Final setup messaging step failed: {e}")

            msgs = []
            if deleted_channels:
                msgs.append(f"🗑 Deleted channels: {', '.join(deleted_channels)}")
            if deleted_categories:
                msgs.append(f"🗑 Deleted categories: {', '.join(deleted_categories)}")
            if created_categories:
                msgs.append(f"✅ Created categories: {', '.join(created_categories)}")
            if skipped_categories:
                msgs.append(f"⚠ Skipped categories: {', '.join(skipped_categories)}")
            if created_channels:
                msgs.append(f"✅ Created channels: {', '.join(created_channels)}")
            if skipped_channels:
                msgs.append(f"⚠ Skipped channels: {', '.join(skipped_channels)}")
            if created_roles:
                msgs.append(f"✅ Created roles: {', '.join(created_roles)}")
            if skipped_new_roles:
                msgs.append(f"⚠ Skipped roles: {', '.join(skipped_new_roles)}")

            # Step 5: Delete the general channel
            if general:
                try:
                    await general.delete()
                    msgs.append(f"🗑 Deleted general channel")
                    logger.info(f"Deleted 'general' channel from {guild.name}")
                except Exception as e:
                    logger.warning(f"Failed to delete general channel: {e}")
                    msgs.append(f"⚠ Could not delete general channel: {e}")

            summary = "\n".join(msgs) if msgs else "Setup completed with no changes."
            await self.safe_send(guild, ctx.channel, summary)
        except Exception as e:
            logger.exception(f"Unexpected error in setup command: {e}")
            await self.safe_send(ctx.guild, ctx.channel, f"❌ An unexpected error occurred during setup: {e}")
        finally:
            try:
                self._setup_running.discard(guild.id)
            except Exception:
                pass

    @setup.command(name="delete")
    @commands.has_permissions(administrator=True)
    async def delete(self, ctx: commands.Context) -> None:
        """Delete all server structure except general channel.
        
        Workflow:
        1. Ensure general channel exists
        2. Delete all categories (cascades to their channels)
        3. Delete all channels except general
        4. Delete all roles
        """
        guild = ctx.guild
        deleted_channels = []
        deleted_categories = []
        deleted_roles = []
        
        # Step 1: Ensure general exists
        general = discord.utils.get(guild.text_channels, name="general")
        if not general:
            try:
                general = await guild.create_text_channel("general")
                logger.info(f"Created 'general' channel in {guild.name}")
            except Exception as e:
                logger.warning(f"Failed to create general channel: {e}")
                general = None
        
        # Step 2: Delete all categories (cascades to their channels)
        for cat in list(guild.categories):
            try:
                await cat.delete()
                deleted_categories.append(cat.name)
            except Exception as e:
                logger.warning(f"Failed to delete category {cat.name}: {e}")
        
        # Step 3: Delete all channels except general
        for ch in list(guild.text_channels):
            try:
                if ch != general:
                    await ch.delete()
                    deleted_channels.append(ch.name)
            except Exception as e:
                logger.warning(f"Failed to delete channel {getattr(ch, 'name', ch)}: {e}")
        
        # Step 4: Delete roles from DEFAULT_ROLES
        for role_data in DEFAULT_ROLES:
            role_name = role_data[0]
            try:
                role = discord.utils.get(guild.roles, name=role_name)
                if role and not role.is_default() and role < guild.me.top_role:
                    await role.delete()
                    deleted_roles.append(role_name)
            except Exception as e:
                logger.warning(f"Failed to delete role {role_name}: {e}")
        
        msgs = []
        if deleted_channels:
            msgs.append(f"🗑 Deleted channels: {', '.join(deleted_channels)}")
        if deleted_categories:
            msgs.append(f"🗑 Deleted categories: {', '.join(deleted_categories)}")
        if deleted_roles:
            msgs.append(f"🗑 Deleted roles: {', '.join(deleted_roles)}")
        if general:
            msgs.append(f"✅ Remaining channel: {general.name}")
        
        summary = "\n".join(msgs) if msgs else "Cleanup complete."
        await self.safe_send(guild, ctx.channel, summary)

    @setup.command(name="clean_overwrites")
    @commands.has_permissions(administrator=True)
    async def clean_overwrites(self, ctx: commands.Context) -> None:
        """Count member-specific overwrites across channels (no destructive changes)."""
        guild = ctx.guild
        removed = 0
        await __import__("mystery").mystery_send(ctx, "⏳ Scanning for member-specific overwrites...")

        for channel in list(guild.channels):
            try:
                targets = list(channel.overwrites.keys())
            except Exception:
                targets = []

            for target in targets:
                if isinstance(target, discord.Member):
                    removed += 1

        await __import__("mystery").mystery_send(ctx, f"✅ Found {removed} member-specific overwrites (no changes made).")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ServerSetupCog(bot))
