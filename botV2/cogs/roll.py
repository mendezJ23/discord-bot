import random
import re
import discord
from discord.ext import commands
from typing import Optional


class RollCog(commands.Cog):
	"""Random roll/pick utilities.

	Commands:
	- .roll -> random 1-6
	- .roll <number> -> random 1-number
	- .roll a, b, c -> random choice from comma-separated items
	- .roll <role name> -> random non-bot member with that role
	"""

	def __init__(self, bot: commands.Bot) -> None:
		self.bot = bot

	@commands.command(name="roll")
	async def roll(self, ctx: commands.Context, *, arg: Optional[str] = None) -> None:
		"""Roll dice or pick a random item/member based on the argument."""
		# No argument: standard 1-6 roll
		if not arg:
			result = random.randint(1, 6)
			await __import__("mystery").mystery_send(ctx, f"🎲 You rolled {result}.")
			return

		s = arg.strip()

		# Range like 9-18 -> roll between those inclusive
		if re.fullmatch(r"\d+\s*-\s*\d+", s):
			m = re.match(r"^(\d+)\s*-\s*(\d+)$", s)
			a, b = int(m.group(1)), int(m.group(2))
			low, high = (a, b) if a <= b else (b, a)
			if low < 1 or high < 1:
				await __import__("mystery").mystery_send(ctx, "❌ Numbers must be at least 1.")
				return
			result = random.randint(low, high)
			await __import__("mystery").mystery_send(ctx, f"🎲 You rolled {result} ({low}-{high}).")
			return

		# If it's a plain integer -> roll 1..N
		if re.fullmatch(r"\d+", s):
			maxv = int(s)
			if maxv < 1:
				await __import__("mystery").mystery_send(ctx, "❌ Number must be at least 1.")
				return
			result = random.randint(1, maxv)
			await __import__("mystery").mystery_send(ctx, f"🎲 You rolled {result} (1-{maxv}).")
			return

		# Comma-separated list -> pick one
		if "," in s:
			items = [part.strip() for part in s.split(",") if part.strip()]
			if not items:
				await __import__("mystery").mystery_send(ctx, "❌ No valid options provided.")
				return
			choice = random.choice(items)
			await __import__("mystery").mystery_send(ctx, f"🎲 I choose: {choice}")
			return

		# Try to resolve a role (mention or name, case-insensitive)
		role = None
		if ctx.guild:
			m = re.match(r"^<@&(\d+)>$", s)
			if m:
				role = ctx.guild.get_role(int(m.group(1)))
			if role is None:
				for r in ctx.guild.roles:
					if r.name.lower() == s.lower():
						role = r
						break

		if role:
			members = [m for m in ctx.guild.members if role in m.roles and not m.bot]
			if not members:
				await __import__("mystery").mystery_send(ctx, f"❌ No non-bot members have the role {role.name}.")
				return
			member = random.choice(members)
			await __import__("mystery").mystery_send(ctx, f"🎲 {member.mention} (from role {role.name})")
			return

		# Fallback: treat the whole argument as a single choice
		await __import__("mystery").mystery_send(ctx, f"🎲 I choose: {s}")

	@commands.command(name="mario")
	async def mario(self, ctx: commands.Context, member: Optional[discord.Member] = None) -> None:
		"""Add a player to the 🎂│mario-party channel."""
		if not ctx.guild:
			return
		# find channel by name substring
		ch = None
		for c in ctx.guild.text_channels:
			try:
				if "mario-party" in c.name.lower():
					ch = c
					break
			except Exception:
				continue
		if not ch:
			await __import__("mystery").mystery_send(ctx, "❌ Could not find the 🎂│mario-party channel")
			return

		target = member or ctx.author
		try:
			await ch.set_permissions(target, view_channel=True, send_messages=True, reason=f"Added to mario-party by {ctx.author}")
			await __import__("mystery").mystery_send(ctx, f"✅ {target.mention} can now access {ch.mention}")
		except Exception as e:
			await __import__("mystery").mystery_send(ctx, f"❌ Could not add member to mario-party: {e}")

	@commands.command(name="mariomove")
	async def mariomove(self, ctx: commands.Context, member: Optional[discord.Member] = None) -> None:
		"""Output a random number from 1-20 for the given player (or the caller) — bolded."""
		n = random.randint(1, 20)
		target = member or ctx.author
		try:
			await __import__("mystery").mystery_send(ctx, f"{target.mention} rolled **{n}**")
		except Exception:
			await __import__("mystery").mystery_send(ctx, f"**{n}**")


# ------------------------
# Loader
# ------------------------
async def setup(bot: commands.Bot) -> None:
	await bot.add_cog(RollCog(bot))

