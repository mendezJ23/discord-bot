import discord
from discord.ext import commands
import json
import os
import logging
from typing import Optional, Dict, Any
from datetime import datetime

import config

logger = logging.getLogger("discord_bot")

ECONOMY_FILE = "economy.json"

class EconomyCog(commands.Cog):
    """Economy system with money, balance, and shop."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.economy_data = self._load_economy()
        # ensure default whisper template exists (guild_id 0)
        # ensure default global shop items exist (guild_id 0)
        shop = self.economy_data.setdefault("shop", {})
        added = False
        for item in getattr(config, "DEFAULT_SHOP_ITEMS", []):
            key = self._get_shop_key(0, item["name"]) if hasattr(self, '_get_shop_key') else f"0_{item['name'].lower()}"
            # If missing, create. If present, ensure price/description/name match the configured default.
            existing = shop.get(key)
            if not existing:
                shop[key] = {
                    "guild_id": 0,
                    "name": item["name"],
                    "price": item.get("price", None),
                    "description": item.get("description", ""),
                    "created_by": "system",
                    "created_at": datetime.utcnow().isoformat(),
                }
                added = True
            else:
                # normalize keys/names: update price and description to match config defaults
                updated = False
                cfg_price = item.get("price", None)
                cfg_desc = item.get("description", "")
                cfg_name = item.get("name")
                if existing.get("price") != cfg_price:
                    existing["price"] = cfg_price
                    updated = True
                if existing.get("description") != cfg_desc:
                    existing["description"] = cfg_desc
                    updated = True
                if existing.get("name") != cfg_name:
                    existing["name"] = cfg_name
                    updated = True
                if updated:
                    shop[key] = existing
                    added = True
        if added:
            self._save_economy()

    def _get_table_key(self, guild_id: int, item_name: str) -> str:
        """Generate a unique key for a table item."""
        return f"{guild_id}_{item_name.lower()}"

    def ensure_default_table_items_for_guild(self, guild_id: int) -> None:
        """Ensure DEFAULT_TABLE_ITEMS from config are present for a given guild.

        This will create guild-specific table items (not global) when a setup runs.
        """
        table = self.economy_data.setdefault("table", {})
        added = False
        for item in getattr(config, "DEFAULT_TABLE_ITEMS", []):
            key = self._get_table_key(guild_id, item["name"]) if hasattr(self, '_get_table_key') else f"{guild_id}_{item['name'].lower()}"
            existing = table.get(key)
            if not existing:
                table[key] = {
                    "guild_id": guild_id,
                    "name": item["name"],
                    "price": item.get("price", None),
                    "description": item.get("description", ""),
                    "per_customer": item.get("per_customer", None),
                    "stock": item.get("stock", None),
                    "created_by": "system",
                    "created_at": datetime.utcnow().isoformat(),
                }
                added = True
            else:
                # update mutable fields
                updated = False
                for k in ("price", "description", "per_customer", "stock", "name"):
                    if existing.get(k) != item.get(k):
                        existing[k] = item.get(k)
                        updated = True
                if updated:
                    table[key] = existing
                    added = True
        if added:
            self._save_economy()

    def _is_overseer(self, member: discord.Member) -> bool:
        try:
            if member.guild_permissions.administrator:
                return True
            for r in member.roles:
                if r.name == "Overseer":
                    return True
        except Exception:
            pass
        return False

    def _load_economy(self) -> Dict[str, Any]:
        """Load economy data from JSON file."""
        if os.path.exists(ECONOMY_FILE):
            try:
                with open(ECONOMY_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load economy data: {e}")
        return {"balances": {}, "shop": {}, "inventories": {}}

    def _save_economy(self) -> None:
        """Save economy data to JSON file."""
        try:
            with open(ECONOMY_FILE, "w", encoding="utf-8") as f:
                json.dump(self.economy_data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save economy data: {e}")

    def _get_member_key(self, guild_id: int, member_id: int) -> str:
        """Generate a unique key for a member's balance."""
        return f"{guild_id}_{member_id}"

    def _get_shop_key(self, guild_id: int, item_name: str) -> str:
        """Generate a unique key for a shop item."""
        return f"{guild_id}_{item_name.lower()}"

    # ==================== BALANCE COMMANDS ====================

    @commands.command(name="bal", usage="[@member]")
    async def balance(self, ctx: commands.Context, member: discord.Member = None) -> None:
        """Check your balance or another member's balance."""
        if member is None:
            member = ctx.author

        key = self._get_member_key(ctx.guild.id, member.id)
        balance = self.economy_data["balances"].get(key, 0)

        embed = discord.Embed(
            title=f"Balance for {member.name}",
            description=f"💰 **{balance:,}** coins",
            color=discord.Color.gold()
        )
        await ctx.send(embed=embed)

    @commands.command(name="lb")
    async def leaderboard(self, ctx: commands.Context, top: int = 10) -> None:
        """Show top balances. Overseer-only (requires role 'Overseer')."""
        # permission check: prefer role 'Overseer' but fall back to administrator
        has_perm = False
        try:
            if ctx.author.guild_permissions.administrator:
                has_perm = True
            else:
                for r in ctx.author.roles:
                    if r.name == "Overseer":
                        has_perm = True
                        break
        except Exception:
            has_perm = False

        if not has_perm:
            await __import__("mystery").mystery_send(ctx, "❌ You must be an Overseer or Administrator to use this command.")
            return
        bal = self.economy_data.get("balances", {})
        items = []
        for key, amount in bal.items():
            try:
                gid, uid = key.split("_")
                if int(gid) != ctx.guild.id:
                    continue
                member = ctx.guild.get_member(int(uid))
                name = member.display_name if member else uid
                items.append((name, amount))
            except Exception:
                continue
        items.sort(key=lambda x: x[1], reverse=True)
        if not items:
            await __import__("mystery").mystery_send(ctx, "No balances yet.")
            return
        lines = [f"{idx+1}. **{name}** — {amt:,}" for idx, (name, amt) in enumerate(items[:top])]
        embed = discord.Embed(title=f"🏆 Top {min(top, len(items))} Balances", description="\n".join(lines), color=discord.Color.gold())
        await ctx.send(embed=embed)

    # ==================== ADMIN MONEY COMMANDS ====================

    @commands.group(name="money", invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    async def money(self, ctx: commands.Context) -> None:
        """Admin commands for managing player money."""
        await __import__("mystery").mystery_send(ctx, "Usage: `.money give <member> <amount>`, `.money remove <member> <amount>`")

    @money.command(name="give")
    @commands.has_permissions(administrator=True)
    async def money_give(self, ctx: commands.Context, member: discord.Member = None, amount: int = None) -> None:
        """Give money to a member."""
        if not member:
            raise commands.MissingRequiredArgument('member')
        if amount is None or amount <= 0:
            raise commands.MissingRequiredArgument('amount')

        key = self._get_member_key(ctx.guild.id, member.id)
        current = self.economy_data["balances"].get(key, 0)
        new_balance = current + amount

        self.economy_data["balances"][key] = new_balance
        self._save_economy()

        embed = discord.Embed(
            title="💰 Money Given",
            description=f"Gave **{amount:,}** coins to {member.mention}",
            color=discord.Color.green()
        )
        embed.add_field(name="New Balance", value=f"{new_balance:,}", inline=False)
        await ctx.send(embed=embed)

    @money.command(name="remove")
    @commands.has_permissions(administrator=True)
    async def money_remove(self, ctx: commands.Context, member: discord.Member = None, amount: int = None) -> None:
        """Remove money from a member."""
        if not member:
            raise commands.MissingRequiredArgument('member')
        if amount is None or amount <= 0:
            raise commands.MissingRequiredArgument('amount')

        key = self._get_member_key(ctx.guild.id, member.id)
        current = self.economy_data["balances"].get(key, 0)
        new_balance = max(0, current - amount)

        self.economy_data["balances"][key] = new_balance
        self._save_economy()

        embed = discord.Embed(
            title="💸 Money Removed",
            description=f"Removed **{amount:,}** coins from {member.mention}",
            color=discord.Color.red()
        )
        embed.add_field(name="New Balance", value=f"{new_balance:,}", inline=False)
        await ctx.send(embed=embed)

    # ==================== SHOP COMMANDS ====================

    @commands.group(name="shop", invoke_without_command=True)
    async def shop(self, ctx: commands.Context) -> None:
        """View the shop or manage shop items."""
        # Show shop items
        # include guild-specific items and global defaults (guild_id == 0)
        guild_shop = {k: v for k, v in self.economy_data["shop"].items() if v.get("guild_id") in (ctx.guild.id, 0)}

        if not guild_shop:
            await __import__("mystery").mystery_send(ctx, "🏪 The shop is empty.")
            return

        embed = discord.Embed(
            title=f"🏪 {ctx.guild.name} Shop",
            color=discord.Color.blurple()
        )

        for key, item in list(guild_shop.items())[:10]:  # Limit to 10
            price = item.get("price")
            price_display = "∞" if price is None else f"{price:,}"
            embed.add_field(
                name=f"{item['name']} - **{price_display}** coins",
                value=f"{item['description']}",
                inline=False
            )

        if len(guild_shop) > 10:
            embed.set_footer(text=f"Showing 10 of {len(guild_shop)} items")

        await ctx.send(embed=embed)

    # ==================== TABLE COMMANDS (utensils channel only) ====================

    def _find_utensils_channel_for_guild(self, guild: discord.Guild) -> Optional[discord.TextChannel]:
        for ch in guild.text_channels:
            try:
                if "utensils" in ch.name.lower():
                    return ch
            except Exception:
                continue
        return None

    def _user_has_utensils_access(self, member: discord.Member) -> bool:
        if not member or not member.guild:
            return False
        guild = member.guild
        ch = self._find_utensils_channel_for_guild(guild)
        if not ch:
            return False
        try:
            return ch.permissions_for(member).view_channel
        except Exception:
            return False

    @commands.group(name="table", invoke_without_command=True)
    async def table(self, ctx: commands.Context) -> None:
        """View the utensils table (access requires view permission to the utensils channel)."""
        if not self._user_has_utensils_access(ctx.author):
            await __import__("mystery").mystery_send(ctx, "❌ You cannot access the table.")
            return

        # include guild-specific items and global defaults (guild_id == 0)
        guild_table = {k: v for k, v in self.economy_data.get("table", {}).items() if v.get("guild_id") in (ctx.guild.id, 0)}

        if not guild_table:
            await __import__("mystery").mystery_send(ctx, "🍽️ The table is empty.")
            return

        embed = discord.Embed(
            title=f"🍽️ {ctx.guild.name} Table",
            color=discord.Color.dark_teal()
        )

        for key, item in list(guild_table.items())[:10]:
            price = item.get("price")
            price_display = "∞" if price is None else f"{price:,}"
            stock = item.get("stock")
            stock_display = "∞" if stock is None else str(stock)
            per_cust = item.get("per_customer")
            per_cust_display = "∞" if per_cust is None else str(per_cust)
            embed.add_field(
                name=f"{item['name']} - **{price_display}** coins",
                value=f"{item.get('description','')}\nStock: {stock_display} | Per-customer: {per_cust_display}",
                inline=False
            )

        if len(guild_table) > 10:
            embed.set_footer(text=f"Showing 10 of {len(guild_table)} items")

        await ctx.send(embed=embed)

    @table.command(name="buy")
    async def table_buy(self, ctx: commands.Context, *, item_name: str) -> None:
        """Buy an item from the utensils table. Requires utensils access."""
        if not ctx.guild:
            return
        if not self._user_has_utensils_access(ctx.author):
            await __import__("mystery").mystery_send(ctx, "❌ You cannot access the table (no access to the utensils channel).")
            return
        if not item_name:
            await __import__("mystery").mystery_send(ctx, "Usage: .table buy <item_name>")
            return

        key = self._get_table_key(ctx.guild.id, item_name)
        item = self.economy_data.get("table", {}).get(key)
        if not item:
            key0 = self._get_table_key(0, item_name)
            item = self.economy_data.get("table", {}).get(key0)
            if not item:
                await __import__("mystery").mystery_send(ctx, f"❌ Item `{item_name}` not found on the table.")
                return

        price = item.get("price")
        if price is None:
            await __import__("mystery").mystery_send(ctx, "❌ This item is not for sale.")
            return

        buyer_key = self._get_member_key(ctx.guild.id, ctx.author.id)
        balance = self.economy_data.get("balances", {}).get(buyer_key, 0)

        if price > 0 and balance < price:
            await __import__("mystery").mystery_send(ctx, "❌ You don't have enough coins to buy that item.")
            return

        # per-customer limit
        per_cust = item.get("per_customer")
        inv = self.economy_data.setdefault("inventories", {})
        user_inv = inv.setdefault(buyer_key, {})
        owned = user_inv.get(item["name"], 0)
        if per_cust is not None and owned >= per_cust:
            await __import__("mystery").mystery_send(ctx, "❌ You have already bought the maximum allowed number of this item.")
            return

        # stock limit
        stock = item.get("stock")
        if stock is not None and stock <= 0:
            await __import__("mystery").mystery_send(ctx, "❌ This item is out of stock.")
            return

        # perform transaction
        if price > 0:
            self.economy_data.setdefault("balances", {})[buyer_key] = balance - price

        # decrement stock if applicable
        if stock is not None:
            # find key in the dict (prefer guild-specific key)
            tbl = self.economy_data.setdefault("table", {})
            # attempt guild key first
            real_key = key if key in tbl else self._get_table_key(0, item["name"])
            tbl[real_key]["stock"] = tbl[real_key].get("stock", 0) - 1 if tbl[real_key].get("stock") is not None else None
            if tbl[real_key].get("stock") is not None and tbl[real_key]["stock"] <= 0:
                tbl[real_key]["stock"] = 0

        # add to inventory
        user_inv[item["name"]] = user_inv.get(item["name"], 0) + 1
        self.economy_data.setdefault("inventories", {})[buyer_key] = user_inv
        self._save_economy()

        await __import__("mystery").mystery_send(ctx, f"✅ You bought **{item['name']}**.")

    @table.command(name="sell")
    async def table_sell(self, ctx: commands.Context, *, item_name: str) -> None:
        """Sell an item from your inventory back to the table (half price)."""
        if not ctx.guild:
            return
        if not self._user_has_utensils_access(ctx.author):
            await __import__("mystery").mystery_send(ctx, "❌ You cannot access the table (no access to the utensils channel).")
            return
        if not item_name:
            await __import__("mystery").mystery_send(ctx, "Usage: .table sell <item_name>")
            return

        buyer_key = self._get_member_key(ctx.guild.id, ctx.author.id)
        inv = self.economy_data.setdefault("inventories", {})
        user_inv = inv.setdefault(buyer_key, {})
        cur = user_inv.get(item_name, 0)
        if cur <= 0:
            await __import__("mystery").mystery_send(ctx, f"❌ You don't have any {item_name} to sell.")
            return

        # find table item for price
        key = self._get_table_key(ctx.guild.id, item_name)
        item = self.economy_data.get("table", {}).get(key)
        if not item:
            key0 = self._get_table_key(0, item_name)
            item = self.economy_data.get("table", {}).get(key0)
        if not item or item.get("price") is None:
            await __import__("mystery").mystery_send(ctx, "❌ This item cannot be sold here.")
            return

        sell_price = max(0, int(item.get("price") // 2))

        # remove one from inventory
        user_inv[item_name] = cur - 1
        if user_inv[item_name] <= 0:
            user_inv.pop(item_name, None)
        self.economy_data.setdefault("inventories", {})[buyer_key] = user_inv

        # credit buyer
        bal = self.economy_data.setdefault("balances", {}).get(buyer_key, 0)
        self.economy_data.setdefault("balances", {})[buyer_key] = bal + sell_price
        self._save_economy()

        await __import__("mystery").mystery_send(ctx, f"✅ You sold 1 x {item_name} for {sell_price:,} coins.")

    @shop.command(name="create")
    @commands.has_permissions(administrator=True)
    async def shop_create(self, ctx: commands.Context, item_name: str = None, price: int = None, *, description: str = None) -> None:
        """Create a new shop item."""
        if not item_name:
            raise commands.MissingRequiredArgument('item_name')
        if price is None:
            raise commands.MissingRequiredArgument('price')
        if not description:
            raise commands.MissingRequiredArgument('description')
        if price < 0:
            raise commands.BadArgument("Price cannot be negative.")

        key = self._get_shop_key(ctx.guild.id, item_name)

        if key in self.economy_data["shop"]:
            await __import__("mystery").mystery_send(ctx, f"❌ Item `{item_name}` already exists.")
            return

        self.economy_data["shop"][key] = {
            "guild_id": ctx.guild.id,
            "name": item_name,
            "price": price,
            "description": description,
            "created_by": str(ctx.author),
            "created_at": datetime.utcnow().isoformat()
        }
        self._save_economy()

        embed = discord.Embed(
            title="✅ Shop Item Created",
            description=f"**{item_name}** - {price:,} coins\n{description}",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)

    @shop.command(name="delete")
    @commands.has_permissions(administrator=True)
    async def shop_delete(self, ctx: commands.Context, item_name: str = None) -> None:
        """Delete a shop item."""
        if not item_name:
            raise commands.MissingRequiredArgument('item_name')

        key = self._get_shop_key(ctx.guild.id, item_name)
        key0 = self._get_shop_key(0, item_name)

        # allow deleting global default item if guild-specific not present
        if key in self.economy_data["shop"]:
            use_key = key
        elif key0 in self.economy_data["shop"]:
            use_key = key0
        else:
            await __import__("mystery").mystery_send(ctx, f"❌ Item `{item_name}` not found.")
            return

        item = self.economy_data["shop"][use_key]
        del self.economy_data["shop"][use_key]
        self._save_economy()

        embed = discord.Embed(
            title="🗑 Shop Item Deleted",
            description=f"**{item['name']}** has been removed from the shop.",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)

    @shop.command(name="update")
    @commands.has_permissions(administrator=True)
    async def shop_update(self, ctx: commands.Context, item_name: str = None, price: int = None, *, description: str = None) -> None:
        """Update a shop item's price or description."""
        if not item_name:
            raise commands.MissingRequiredArgument('item_name')

        key = self._get_shop_key(ctx.guild.id, item_name)
        key0 = self._get_shop_key(0, item_name)

        if key in self.economy_data["shop"]:
            use_key = key
        elif key0 in self.economy_data["shop"]:
            use_key = key0
        else:
            await __import__("mystery").mystery_send(ctx, f"❌ Item `{item_name}` not found.")
            return

        item = self.economy_data["shop"][use_key]
        if price is not None:
            if price < 0:
                raise commands.BadArgument("Price cannot be negative.")
            item["price"] = price

        if description is not None:
            item["description"] = description

        self._save_economy()

        embed = discord.Embed(
            title="✏️ Shop Item Updated",
            description=f"**{item['name']}** has been updated.",
            color=discord.Color.blue()
        )
        price_val = item.get("price")
        price_display = "∞" if price_val is None else f"{price_val:,}"
        embed.add_field(name="Price", value=f"{price_display} coins", inline=False)
        embed.add_field(name="Description", value=item['description'], inline=False)
        await ctx.send(embed=embed)

    @shop.command(name="list")
    @commands.has_permissions(administrator=True)
    async def shop_list(self, ctx: commands.Context) -> None:
        """List all shop items (admin view)."""
        # include guild-specific items and global defaults (guild_id == 0)
        guild_shop = {k: v for k, v in self.economy_data["shop"].items() if v.get("guild_id") in (ctx.guild.id, 0)}

        if not guild_shop:
            await __import__("mystery").mystery_send(ctx, "🏪 The shop is empty.")
            return

        embed = discord.Embed(
            title=f"🏪 Shop Inventory ({ctx.guild.name})",
            color=discord.Color.blurple()
        )

        for key, item in list(guild_shop.items())[:10]:
            price = item.get("price")
            price_display = "∞" if price is None else f"{price:,}"
            embed.add_field(
                name=f"{item['name']}",
                value=f"Price: **{price_display}** coins\n{item['description'][:100]}",
                inline=False
            )

        if len(guild_shop) > 10:
            embed.set_footer(text=f"Showing 10 of {len(guild_shop)} items")

        await ctx.send(embed=embed)

    @commands.group(name="item", invoke_without_command=True)
    async def item(self, ctx: commands.Context) -> None:
        await __import__("mystery").mystery_send(ctx, "Usage: .item give <member> <item_name> [amount] | .item remove <member> <item_name> [amount]")

    @item.command(name="give")
    async def item_give(self, ctx: commands.Context, member: discord.Member = None, item_name: str = None, amount: int = 1) -> None:
        """Give an item to a player's inventory. Overseer-only."""
        if not ctx.guild:
            return
        if not self._is_overseer(ctx.author):
            await __import__("mystery").mystery_send(ctx, "❌ Only Overseers or Administrators can use this command.")
            return
        if member is None or not item_name:
            raise commands.MissingRequiredArgument('member or item_name')
        if amount is None or amount <= 0:
            await __import__("mystery").mystery_send(ctx, "❌ Amount must be positive.")
            return
        key = self._get_member_key(ctx.guild.id, member.id)
        inv = self.economy_data.setdefault("inventories", {})
        user_inv = inv.setdefault(key, {})
        user_inv[item_name] = user_inv.get(item_name, 0) + int(amount)
        self.economy_data.setdefault("inventories", {})[key] = user_inv
        self._save_economy()
        await __import__("mystery").mystery_send(ctx, f"✅ Gave {amount} x {item_name} to {member.display_name}.")

    @item.command(name="remove")
    async def item_remove(self, ctx: commands.Context, member: discord.Member = None, item_name: str = None, amount: int = 1) -> None:
        """Remove an item from a player's inventory. Overseer-only."""
        if not ctx.guild:
            return
        if not self._is_overseer(ctx.author):
            await __import__("mystery").mystery_send(ctx, "❌ Only Overseers or Administrators can use this command.")
            return
        if member is None or not item_name:
            raise commands.MissingRequiredArgument('member or item_name')
        if amount is None or amount <= 0:
            await __import__("mystery").mystery_send(ctx, "❌ Amount must be positive.")
            return
        key = self._get_member_key(ctx.guild.id, member.id)
        inv = self.economy_data.setdefault("inventories", {})
        user_inv = inv.setdefault(key, {})
        cur = user_inv.get(item_name, 0)
        if cur <= 0:
            await __import__("mystery").mystery_send(ctx, f"❌ {member.display_name} has no {item_name}.")
            return
        remove_amt = min(cur, int(amount))
        user_inv[item_name] = cur - remove_amt
        if user_inv[item_name] <= 0:
            user_inv.pop(item_name, None)
        self.economy_data.setdefault("inventories", {})[key] = user_inv
        self._save_economy()
        await __import__("mystery").mystery_send(ctx, f"✅ Removed {remove_amt} x {item_name} from {member.display_name}.")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(EconomyCog(bot))
    # register module-level convenience commands that interact with the cog
    try:
        bot.add_command(inventory)
        bot.add_command(buy_item)
        bot.add_command(use_whisper)
    except Exception:
        pass


@commands.command(name="inv")
async def inventory(ctx: commands.Context) -> None:
    """Show your inventory."""
    cog = ctx.bot.get_cog("EconomyCog")
    if not cog:
        await __import__("mystery").mystery_send(ctx, "Economy not available.")
        return
    key = cog._get_member_key(ctx.guild.id, ctx.author.id)
    inv = cog.economy_data.get("inventories", {}).get(key, {})
    if not inv:
        await __import__("mystery").mystery_send(ctx, "🧺 Your inventory is empty.")
        return
    lines = []
    for item_name, count in inv.items():
        lines.append(f"{item_name} x{count}")
    await __import__("mystery").mystery_send(ctx, "\n".join(lines))


@commands.command(name="buy")
async def buy_item(ctx: commands.Context, *, item_name: str) -> None:
    """Buy an item from the shop and add to your inventory."""
    cog = ctx.bot.get_cog("EconomyCog")
    if not cog:
        await __import__("mystery").mystery_send(ctx, "Economy not available.")
        return
    if not item_name:
        await __import__("mystery").mystery_send(ctx, "Usage: .buy <item_name>")
        return
    key = cog._get_shop_key(ctx.guild.id, item_name)
    item = cog.economy_data.get("shop", {}).get(key)
    if not item:
        key0 = cog._get_shop_key(0, item_name)
        item = cog.economy_data.get("shop", {}).get(key0)
        if not item:
            await __import__("mystery").mystery_send(ctx, f"❌ Item `{item_name}` not found in the shop.")
            return
    price = item.get("price")
    if price is None:
        await __import__("mystery").mystery_send(ctx, "❌ This item is not for sale.")
        return
    buyer_key = cog._get_member_key(ctx.guild.id, ctx.author.id)
    balance = cog.economy_data.get("balances", {}).get(buyer_key, 0)
    if price > 0 and balance < price:
        await __import__("mystery").mystery_send(ctx, "❌ You don't have enough coins to buy that item.")
        return
    if price > 0:
        cog.economy_data.setdefault("balances", {})[buyer_key] = balance - price
    inv = cog.economy_data.setdefault("inventories", {})
    user_inv = inv.setdefault(buyer_key, {})
    user_inv[item['name']] = user_inv.get(item['name'], 0) + 1
    cog._save_economy()
    await __import__("mystery").mystery_send(ctx, f"✅ You bought **{item['name']}**.")


@commands.command(name="whisper")
async def use_whisper(ctx: commands.Context, member: discord.Member = None, *, message: str = None) -> None:
    """Use a whisper to send a 7-word message to another player's role channel. Usage: .whisper @player your seven word message"""
    cog = ctx.bot.get_cog("EconomyCog")
    if not cog:
        await __import__("mystery").mystery_send(ctx, "Economy not available.")
        return
    if not member or not message:
        await __import__("mystery").mystery_send(ctx, "Usage: .whisper @player <7-word message>")
        return
    words = [w for w in message.split() if w.strip()]
    if len(words) > 7:
        await __import__("mystery").mystery_send(ctx, "❌ Message must be 7 words or fewer.")
        return
    buyer_key = cog._get_member_key(ctx.guild.id, ctx.author.id)
    inv = cog.economy_data.get("inventories", {}).get(buyer_key, {})
    if not inv or inv.get("whisper", 0) <= 0:
        await __import__("mystery").mystery_send(ctx, "❌ You don't have a whisper in your inventory. Use `.buy whisper` to acquire one.")
        return
    # locate target's role channel
    roles_category = discord.utils.get(ctx.guild.categories, name="ROLES")
    target_channel = None
    if roles_category:
        for ch in roles_category.text_channels:
            try:
                if ch.permissions_for(member).view_channel:
                    target_channel = ch
                    break
            except Exception:
                continue
    if not target_channel:
        await __import__("mystery").mystery_send(ctx, "❌ Could not locate the target's role channel.")
        return
    # consume whisper
    inv['whisper'] = inv.get('whisper', 0) - 1
    if inv['whisper'] <= 0:
        inv.pop('whisper', None)
    cog.economy_data.setdefault("inventories", {})[buyer_key] = inv
    cog._save_economy()
    try:
        await target_channel.send(f"🔒 A whisper for {member.display_name}: {' '.join(words)}")
        await __import__("mystery").mystery_send(ctx, f"✅ Whisper sent to {member.display_name}'s role channel.")
        # Log the whisper to whisper-logs channel if present
        try:
            log_ch = None
            for ch in ctx.guild.text_channels:
                if "whisper-logs" in ch.name.lower() or ch.name.lower() == "whisper-logs":
                    log_ch = ch
                    break
            if log_ch:
                await log_ch.send(f"[WHISPER] From: {ctx.author} To: {member} — {' '.join(words)}")
        except Exception:
            pass
    except Exception as e:
        logger.error(f"Failed to send whisper: {e}")
        await __import__("mystery").mystery_send(ctx, "❌ Failed to deliver whisper.")
