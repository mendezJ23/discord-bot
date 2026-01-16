import discord
from discord.ext import commands
import json
import os
import logging
from typing import Optional, Dict, Any
from datetime import datetime

logger = logging.getLogger("discord_bot")

NOTES_FILE = "notes.json"

class NotesCog(commands.Cog):
    """Cog for storing and managing notes on members and channels."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.notes = self._load_notes()

    def _load_notes(self) -> Dict[str, Dict[str, Any]]:
        """Load notes from JSON file."""
        if os.path.exists(NOTES_FILE):
            try:
                with open(NOTES_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load notes: {e}")
        return {}

    def _save_notes(self) -> None:
        """Save notes to JSON file."""
        try:
            with open(NOTES_FILE, "w", encoding="utf-8") as f:
                json.dump(self.notes, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save notes: {e}")

    def _get_note_key(self, guild_id: int, target_id: int) -> str:
        """Generate a unique key for a note."""
        return f"{guild_id}_{target_id}"

    def reset_all_notes(self) -> None:
        """Clear all notes (called on server setup)."""
        self.notes = {}
        self._save_notes()
        logger.info("All notes have been reset")

    @commands.group(name="note", invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    async def note(self, ctx: commands.Context, target = None, *, text: str = None) -> None:
        """Add a note to a member, channel, or manor number. Usage: .note <member/channel/number> <text>"""
        if not target:
            await __import__("mystery").mystery_send(
                ctx,
                "Usage: `.note <member/channel/number> <text>`, `.note remove <member/channel>`, `.note check <member/channel>`",
            )
            return

        # Try to parse as manor number if it's a string that is a digit
        if isinstance(target, str) and target.isdigit():
            manor_num = target
            manors_cat = discord.utils.get(ctx.guild.categories, name="MANORS")
            if not manors_cat:
                await __import__("mystery").mystery_send(ctx, "❌ 'MANORS' category not found")
                return

            house_channel = discord.utils.get(
                manors_cat.text_channels, name=f"🏰│manor-{manor_num}"
            )
            if not house_channel:
                house_channel = discord.utils.get(
                    manors_cat.text_channels, name=f"manor-{manor_num}"
                )

            if not house_channel:
                await __import__("mystery").mystery_send(ctx, f"❌ Manor {manor_num} not found")
                return

            target = house_channel

        if not text:
            raise commands.MissingRequiredArgument(ctx.command)

        # Add note directly without requiring 'add' subcommand
        await self.note_add(ctx, target, text=text)

    @note.command(name="add")
    @commands.has_permissions(administrator=True)
    async def note_add(self, ctx: commands.Context, target: discord.Member | discord.TextChannel = None, *, text: str = None) -> None:
        """Add a note to a member or channel."""
        if not target:
            raise commands.MissingRequiredArgument(ctx.command)
        if not text:
            raise commands.MissingRequiredArgument(ctx.command)

        key = self._get_note_key(ctx.guild.id, target.id)
        self.notes[key] = {
            "guild_id": ctx.guild.id,
            "target_id": target.id,
            "target_name": target.name if isinstance(target, discord.Member) else target.name,
            "target_type": "member" if isinstance(target, discord.Member) else "channel",
            "note": text,
            "added_by": str(ctx.author),
            "timestamp": datetime.utcnow().isoformat()
        }
        self._save_notes()
        await __import__("mystery").mystery_send(ctx, f"✅ Note added for {target.mention}: `{text}`")

    @note.command(name="remove")
    @commands.has_permissions(administrator=True)
    async def note_remove(self, ctx: commands.Context, target: discord.Member | discord.TextChannel = None) -> None:
        """Remove a note from a member or channel."""
        if not target:
            raise commands.MissingRequiredArgument(ctx.command)

        key = self._get_note_key(ctx.guild.id, target.id)
        if key not in self.notes:
            await __import__("mystery").mystery_send(ctx, f"❌ No note found for {target.mention}.")
            return

        del self.notes[key]
        self._save_notes()
        await __import__("mystery").mystery_send(ctx, f"🗑 Note removed for {target.mention}.")

    @note.command(name="check")
    @commands.has_permissions(administrator=True)
    async def note_check(self, ctx: commands.Context, target: discord.Member | discord.TextChannel = None) -> None:
        """Check notes for a member or channel (deprecated, use .notes instead)."""
        if not target:
            raise commands.MissingRequiredArgument(ctx.command)

        key = self._get_note_key(ctx.guild.id, target.id)
        if key not in self.notes:
            await __import__("mystery").mystery_send(ctx, f"📝 No notes found for {target.mention}.")
            return

        note_data = self.notes[key]
        embed = discord.Embed(
            title=f"Notes for {target.name}",
            color=discord.Color.blue(),
            description=note_data["note"]
        )
        embed.add_field(name="Added by", value=note_data["added_by"], inline=False)
        embed.add_field(name="Date", value=note_data["timestamp"], inline=False)
        await ctx.send(embed=embed)

    @commands.command(name="notes")
    @commands.has_permissions(administrator=True)
    async def notes(self, ctx: commands.Context, target = None) -> None:
        """Check notes for a member, channel, or manor number.
        
        Usage:
        - .notes @member (check member note)
        - .notes #channel (check channel note)
        - .notes 1 (check note for manor-1)
        """
        if not target:
            raise commands.MissingRequiredArgument(ctx.command)

        # Try to parse as manor number
        if isinstance(target, str) and target.isdigit():
            manor_num = target
            manors_category = discord.utils.get(ctx.guild.categories, name="MANORS")
            if not manors_category:
                await __import__("mystery").mystery_send(ctx, "❌ 'MANORS' category not found")
                return

            house_channel = discord.utils.get(manors_category.text_channels, name=f"🏰│manor-{manor_num}")
            if not house_channel:
                # Try without emoji
                house_channel = discord.utils.get(manors_category.text_channels, name=f"manor-{manor_num}")
            
            if not house_channel:
                await __import__("mystery").mystery_send(ctx, f"❌ Manor {manor_num} not found")
                return
            
            target = house_channel
        
        # Now check for notes on the target (either resolved or passed as member/channel)
        key = self._get_note_key(ctx.guild.id, target.id)
        if key not in self.notes:
            await __import__("mystery").mystery_send(ctx, f"📝 No notes found for {target.mention}.")
            return

        note_data = self.notes[key]
        embed = discord.Embed(
            title=f"Notes for {target.name}",
            color=discord.Color.blue(),
            description=note_data["note"]
        )
        embed.add_field(name="Added by", value=note_data["added_by"], inline=False)
        embed.add_field(name="Date", value=note_data["timestamp"], inline=False)
        await ctx.send(embed=embed)

    @note.command(name="list")
    @commands.has_permissions(administrator=True)
    async def note_list(self, ctx: commands.Context) -> None:
        """List all notes in the guild."""
        guild_notes = {k: v for k, v in self.notes.items() if v["guild_id"] == ctx.guild.id}
        
        if not guild_notes:
            await __import__("mystery").mystery_send(ctx, "📝 No notes in this guild.")
            return

        embed = discord.Embed(
            title=f"All Notes in {ctx.guild.name}",
            color=discord.Color.blue()
        )
        for key, note_data in list(guild_notes.items())[:10]:  # Limit to 10 for embed size
            embed.add_field(
                name=f"{note_data['target_name']} ({note_data['target_type']})",
                value=f"{note_data['note'][:100]}...",
                inline=False
            )
        
        if len(guild_notes) > 10:
            embed.set_footer(text=f"Showing 10 of {len(guild_notes)} notes")

        await ctx.send(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(NotesCog(bot))
