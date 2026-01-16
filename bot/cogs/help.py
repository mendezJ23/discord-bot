import discord
from discord.ext import commands

class HelpCog(commands.Cog):
    """Custom help command with detailed usage information."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        # Store the default help command to restore later if needed
        self._original_help_command = bot.help_command
        # Remove the default help command
        bot.help_command = None

    def cog_unload(self) -> None:
        """Restore the default help command when this cog is unloaded."""
        self.bot.help_command = self._original_help_command

    @commands.command(name="help")
    async def help_command(self, ctx: commands.Context, command_name: str = None) -> None:
        """Shows help for all commands or a specific command with usage."""
        # Map cog names to friendly categories (available to both branches)
        cog_map = {
            "ServerSetup": "Administration",
            "admin": "Administration",
            "Admin": "Administration",
            "RoleChannels": "Role Channels",
            "RoleChannelsCog": "Role Channels",
            "Houses": "Houses",
            "HouseAdmin": "Houses",
            "Economy": "Economy",
            "Voting": "Voting",
            "VotingCog": "Voting",
            "Moderation": "Moderation",
            "Help": "Utility",
            "ActionQueue": "Action Queue",
            "ActionQueueCog": "Action Queue",
            "SimpleLog": "Logging",
            "RoleBasedAccess": "Roles & Access",
            "RoleBasedAccessCog": "Roles & Access",
            "Switch": "Utility",
            "Stats": "Stats",
            None: "General"
        }

        # Per-command overrides for usage and short description
        # key: command name -> (usage, short description)
        command_overrides = {
            # examples provided by user
            "actions": ("", ".actions — View or manage the action queue."),
            "admin_actions": ("", ".admin_actions — Administrator action queue overview."),
            "use": ("[A1|1] {description}", ".use A1 some details — Use ability A1 (or `1`) with an optional description; reply to a message and run `.use` to use its content."),
            "addmanor": ("{manor name or number}", ".addmanor {number or name} — Create a new manor channel to extend manors."),
            "addrole": ("{rolechannel name}", ".addrole {name} — Create a new role channel to extend role channels."),

            # role_channels commands
            "rc": ("", ".rc — Assign Alive players to existing role channels."),
            "rcrefresh": ("", ".rcrefresh — Refresh role channel permissions for Alive players."),
            "setupmanors": ("", ".setupmanors — Deprecated; use `.manor setup` instead."),
            "delmanor": ("{manor}", ".delmanor {manor} — Delete a manor channel by name or mention."),
            "delrole": ("{rolechannel}", ".delrole {name} — Delete a role channel by name."),
            "public": ("[channel]",".public [channel] — Make a channel visible to everyone (view-only)."),
            "private": ("[channel]",".private [channel] — Make a channel hidden from @everyone."),
            "add": ("#channel @member",".add #channel @member — Give a member access to a channel."),
            "remove": ("#channel @member",".remove #channel @member — Remove a member's access to a channel."),
            "disappear": ("[channel] [@member]",".disappear — Move a channel to THE SHADOW REALM and restrict access."),
            "world": ("[@member]",".world [@member] — Grant a player access to all channels in THE SHADOW REALM."),

            # other common commands
            "roll": ("[args]",".roll [args] — Roll dice or pick randomly from options or roles."),
            "log": ("{start_id} {end_id}", ".log {start_message_id} {end_message_id} — Export message range to a text file."),
            "sync_roles": ("",".sync_roles — Sync channel permissions for all members based on roles (admin)."),
            "switch": ("",".switch — Swap player and sponsor roles and reassign the role channel (admin)."),
            "v": ("",".v — Show all votes across voting sessions."),
            "p": ("",".p — List players with the Alive role."),
            "d": ("",".d — List players with the Dead role."),
            "session": ("<action> [name]",".session <action> [name] — Manage voting sessions (create/open/close/list/reset)."),
        }
        if command_name:
            # Get a single command
            cmd = self.bot.get_command(command_name)
            if not cmd:
                return await __import__("mystery").mystery_send(ctx, f"❌ Command `{command_name}` not found.")
            
            # If it's a group, show all subcommands
            if isinstance(cmd, commands.Group):
                embed = discord.Embed(
                    title=f"{ctx.prefix}{cmd.name}",
                    description=cmd.help or "No description provided.",
                    color=discord.Color.blue()
                )
                for subcmd in cmd.commands:
                    if not subcmd.hidden:
                        override = command_overrides.get(subcmd.name)
                        if override:
                            usage, desc = override
                        else:
                            # Prefer the command signature when available, fall back to usage
                            usage = getattr(subcmd, "signature", None) or getattr(subcmd, "usage", "") or ""
                            desc = (subcmd.help or "No description").splitlines()[0]
                        embed.add_field(name=f"{ctx.prefix}{cmd.name} {subcmd.name} {usage}".strip(), value=desc, inline=False)
                return await ctx.send(embed=embed)
            
            # Regular command
            override = command_overrides.get(cmd.name)
            if override:
                usage, desc = override
            else:
                desc = cmd.help or "No description provided."
                usage = getattr(cmd, "signature", None) or getattr(cmd, "usage", "") or ""
            await __import__("mystery").mystery_send(ctx, f"**{ctx.prefix}{cmd.name} {usage}**\n{desc}")
        else:
            # Show commands organized by cog/category for clarity
            embed = discord.Embed(
                title="Bot Commands",
                description="Use `.help <command>` for detailed info on a command.",
                color=discord.Color.blue()
            )

            # (using maps defined above)

            # Group commands by category
            categories: dict[str, list[str]] = {}
            for cmd in sorted(self.bot.commands, key=lambda c: c.name):
                if cmd.hidden:
                    continue
                # use the cog name to categorize; remove trailing 'Cog' when present
                raw_cog = cmd.cog_name
                mapped = cog_map.get(raw_cog)
                if mapped:
                    cat_name = mapped
                else:
                    if raw_cog and raw_cog.endswith("Cog"):
                        cat_name = raw_cog[:-3]
                    else:
                        cat_name = raw_cog or "General"
                override = command_overrides.get(cmd.name)
                if override:
                    usage, desc = override
                else:
                    # Prefer signature if available for clearer argument display
                    usage = getattr(cmd, "signature", None) or getattr(cmd, "usage", "") or ""
                    desc = (cmd.help or "No description").splitlines()[0]
                # Show aliases if any (except the canonical name)
                alias_part = ""
                try:
                    aliases = getattr(cmd, "aliases", []) or []
                    if aliases:
                        alias_part = " — aliases: " + ", ".join(aliases)
                except Exception:
                    alias_part = ""

                # If this is a fallback registration like 'aq_mute', note the original
                fallback_note = ""
                try:
                    if cmd.name.startswith("aq_"):
                        original = cmd.name[len("aq_"):]
                        fallback_note = f" — fallback for `{ctx.prefix}{original}`"
                except Exception:
                    fallback_note = ""

                line = f"`{ctx.prefix}{cmd.name} {usage}` — {desc}{alias_part}{fallback_note}".strip()
                categories.setdefault(cat_name, []).append(line)

            # Build embeds while keeping within Discord limits (6000 total chars, max 25 fields)
            def _truncate_value(v: str) -> str:
                if len(v) > 1024:
                    return v[:1000] + "\n..."
                return v

            embeds: list[discord.Embed] = []
            current = discord.Embed(title="Bot Commands", description="Use `.help <command>` for detailed info on a command.", color=discord.Color.blue())
            current_chars = len(current.title or "") + len(current.description or "")
            current_fields = 0

            for cat, lines in categories.items():
                value = _truncate_value("\n".join(lines))
                field_chars = len(cat) + len(value)

                # If adding this field would exceed embed size limits or field count, start new embed
                if current_fields >= 25 or (current_chars + field_chars) > 5900:
                    embeds.append(current)
                    current = discord.Embed(title="Bot Commands (cont.)", description="Use `.help <command>` for detailed info on a command.", color=discord.Color.blue())
                    current_chars = len(current.title or "") + len(current.description or "")
                    current_fields = 0

                current.add_field(name=cat, value=value, inline=False)
                current_chars += field_chars
                current_fields += 1

            embeds.append(current)

            # Send all embeds sequentially
            for emb in embeds:
                await ctx.send(embed=emb)

# ------------------------
# Loader
# ------------------------
async def setup(bot):
    await bot.add_cog(HelpCog(bot))
