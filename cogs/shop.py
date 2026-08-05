# cogs/shop.py
from __future__ import annotations
import discord
from discord.ext import commands
import discord.app_commands
from typing import Optional, List
import db
import math
import datetime
import modlog as modlog_helper

CURRENCY = "Coins"
ITEMS_PER_PAGE = 5
LISTINGS_PER_PAGE = 5


class PageView(discord.ui.View):
    def __init__(self, pages: List[discord.Embed], author_id: int, timeout: int = 120):
        super().__init__(timeout=timeout)
        self.pages = pages
        self.index = 0
        self.author_id = author_id

    async def send_initial(self, ctx_or_interaction):
        target = ctx_or_interaction
        if isinstance(target, discord.Interaction):
            await target.response.send_message(embed=self.pages[0], view=self, ephemeral=False)
            return await target.original_response()
        else:
            return await target.send(embed=self.pages[0], view=self)

    async def update_message(self, interaction: discord.Interaction):
        await interaction.response.edit_message(embed=self.pages[self.index], view=self)

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary)
    async def previous(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This paginator isn't for you.", ephemeral=True)
            return
        self.index = (self.index - 1) % len(self.pages)
        await self.update_message(interaction)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This paginator isn't for you.", ephemeral=True)
            return
        self.index = (self.index + 1) % len(self.pages)
        await self.update_message(interaction)


class Shop(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ---------- shop list (paginated) ----------
    @commands.group(name="shop", invoke_without_command=True)
    async def shop(self, ctx: commands.Context):
        await ctx.send("Usage: c?shop list | c?shop buy <item-id-or-name> [quantity]")

    @shop.command(name="list")
    async def shop_list(self, ctx: commands.Context):
        guild = ctx.guild
        if guild is None:
            await ctx.send("This only works in servers.")
            return
        items = await db.get_items(guild.id)
        if not items:
            await ctx.send("No items in the shop.")
            return
        embeds = []
        for i in range(0, len(items), ITEMS_PER_PAGE):
            chunk = items[i : i + ITEMS_PER_PAGE]
            embed = discord.Embed(title=f"{guild.name} — Shop", color=discord.Color.blurple(), timestamp=datetime.datetime.utcnow())
            for it in chunk:
                name = f"ID {it['id']}: {it['name']}"
                desc = it.get("description") or ""
                category = f"Category: {it.get('category')}" if it.get("category") else "Category: —"
                typ = it.get("type")
                cooldown = it.get("cooldown_seconds", 0)
                effect = f"{it.get('effect_type')}:{it.get('effect_value')}" if it.get("effect_type") else "—"
                role_part = f" (role id {it.get('role_id')})" if it.get("role_id") else ""
                embed.add_field(
                    name=name,
                    value=f"{desc}\nPrice: {it['price']:,} {CURRENCY}\nType: {typ}{role_part}\n{category}\nCooldown: {cooldown}s\nEffect: {effect}",
                    inline=False,
                )
            embed.set_footer(text=f"Page {i//ITEMS_PER_PAGE + 1}/{math.ceil(len(items)/ITEMS_PER_PAGE)}")
            embeds.append(embed)
        view = PageView(embeds, ctx.author.id)
        await view.send_initial(ctx)

    # ---------- buy ----------
    @shop.command(name="buy")
    async def shop_buy(self, ctx: commands.Context, item: str, quantity: int = 1):
        guild = ctx.guild
        if guild is None:
            await ctx.send("This only works in servers.")
            return

        # resolve item: try numeric id first, otherwise name
        item_obj = None
        item_id = None
        if item.isdigit():
            item_id = int(item)
            item_obj = await db.get_item(guild.id, item_id)
        else:
            item_obj = await db.get_item_by_name(guild.id, item)
            if item_obj:
                item_id = item_obj["id"]

        if not item_obj:
            await ctx.send("Item not found (by id or name).")
            return

        success, msg, item_info = await db.buy_item(guild.id, ctx.author.id, item_id, quantity)
        if not success:
            await ctx.send(f"❌ {msg}")
            return

        total = item_info["price"] * int(quantity)

        # If item is role-type, attempt to assign role now (common UX). If assignment fails, refund & remove inventory.
        if item_info.get("type") == "role" and item_info.get("role_id"):
            role = guild.get_role(int(item_info["role_id"]))
            if role is None:
                # refund + remove inventory quantity purchased
                await db.add_balance(guild.id, ctx.author.id, item_info["price"] * int(quantity))
                await db.remove_inventory_item(guild.id, ctx.author.id, item_id, int(quantity))
                await ctx.send("❌ Role for this item not found (refunded). Please contact an admin.")
                # log refund
                try:
                    await modlog_helper.send_modlog(self.bot, guild, "Refund", ctx.author, item_info["name"], reason="Role not found", extra=f"Refunded {total:,} {CURRENCY}")
                except Exception:
                    pass
                return

            # managed roles cannot be assigned
            if role.managed:
                await db.add_balance(guild.id, ctx.author.id, item_info["price"] * int(quantity))
                await db.remove_inventory_item(guild.id, ctx.author.id, item_id, int(quantity))
                await ctx.send("❌ That role is managed by an integration and cannot be assigned (refunded).")
                try:
                    await modlog_helper.send_modlog(self.bot, guild, "Refund", ctx.author, item_info["name"], reason="Role is managed", extra=f"Refunded {total:,} {CURRENCY}")
                except Exception:
                    pass
                return

            me = guild.me or guild.get_member(self.bot.user.id)
            if not me.guild_permissions.manage_roles:
                await db.add_balance(guild.id, ctx.author.id, item_info["price"] * int(quantity))
                await db.remove_inventory_item(guild.id, ctx.author.id, item_id, int(quantity))
                await ctx.send("❌ I don't have Manage Roles permission to assign the purchased role (refunded).")
                try:
                    await modlog_helper.send_modlog(self.bot, guild, "Refund", ctx.author, item_info["name"], reason="Missing Manage Roles", extra=f"Refunded {total:,} {CURRENCY}")
                except Exception:
                    pass
                return

            if role.position >= me.top_role.position:
                await db.add_balance(guild.id, ctx.author.id, item_info["price"] * int(quantity))
                await db.remove_inventory_item(guild.id, ctx.author.id, item_id, int(quantity))
                await ctx.send("❌ I cannot assign that role because it is higher than my top role (refunded).")
                try:
                    await modlog_helper.send_modlog(self.bot, guild, "Refund", ctx.author, item_info["name"], reason="Role higher than bot", extra=f"Refunded {total:,} {CURRENCY}")
                except Exception:
                    pass
                return

            try:
                await ctx.author.add_roles(role, reason="Purchased from shop")
                await ctx.send(f"✅ Purchased and assigned role {role.mention}.")
                try:
                    await modlog_helper.send_modlog(self.bot, guild, "Role Purchase", ctx.author, item_info["name"], reason=None, extra=f"Qty: {quantity} • Total: {total:,} {CURRENCY}")
                except Exception:
                    pass
                return
            except Exception as e:
                await db.add_balance(guild.id, ctx.author.id, item_info["price"] * int(quantity))
                await db.remove_inventory_item(guild.id, ctx.author.id, item_id, int(quantity))
                await ctx.send(f"❌ Failed to assign role (refunded): {e}")
                try:
                    await modlog_helper.send_modlog(self.bot, guild, "Refund", ctx.author, item_info["name"], reason=f"Assign failed: {e}", extra=f"Refunded {total:,} {CURRENCY}")
                except Exception:
                    pass
                return

        # Non-role or role items that were not auto-assigned
        try:
            await modlog_helper.send_modlog(self.bot, guild, "Purchase", ctx.author, item_info["name"], reason=None, extra=f"Qty: {quantity} • Total: {total:,} {CURRENCY}")
        except Exception:
            pass

        await ctx.send(f"✅ Purchased {quantity}x **{item_info['name']}** for {total:,} {CURRENCY}.")

    # -----------------
    # Admin: add/remove items
    # -----------------
    @shop.command(name="add")
    @commands.has_permissions(manage_guild=True)
    async def shop_add(self, ctx: commands.Context, name: str, price: int, *, description: Optional[str] = None):
        """c?shop add <name> <price> [description] — add a consumable item to the shop (admin)"""
        guild = ctx.guild
        if guild is None:
            await ctx.send("Server-only.")
            return
        try:
            item_id = await db.create_item(guild.id, name=name, price=price, description=description or "", type_="consumable")
            embed = discord.Embed(title="Shop Item Added", description=f"Added **{name}** (ID {item_id}) to the shop.", color=discord.Color.green(), timestamp=datetime.datetime.utcnow())
            embed.add_field(name="Price", value=f"{price:,} {CURRENCY}", inline=True)
            if description:
                embed.add_field(name="Description", value=description, inline=False)
            await ctx.send(embed=embed)
            try:
                await modlog_helper.send_modlog(self.bot, guild, "Shop Item Created", ctx.author, name, reason=None, extra=f"ID {item_id} • Price {price:,} {CURRENCY}")
            except Exception:
                pass
        except Exception as e:
            await ctx.send(f"Error creating item: {e}")

    @shop.command(name="remove")
    @commands.has_permissions(manage_guild=True)
    async def shop_remove(self, ctx: commands.Context, identifier: str):
        """c?shop remove <id|name> — remove an item from the shop (admin)"""
        guild = ctx.guild
        if guild is None:
            await ctx.send("Server-only.")
            return
        try:
            item = None
            if identifier.isdigit():
                item = await db.get_item(guild.id, int(identifier))
            else:
                item = await db.get_item_by_name(guild.id, identifier)
            if not item:
                await ctx.send("Item not found.")
                return
            removed = await db.delete_item(guild.id, item["id"]) if isinstance(item, dict) else await db.delete_item(guild.id, item.id)
            # db.delete_item returns rowcount
            await ctx.send(f"Removed item {item['name'] if isinstance(item, dict) else str(item)} (ID {item['id'] if isinstance(item, dict) else item.id}).")
            try:
                await modlog_helper.send_modlog(self.bot, guild, "Shop Item Removed", ctx.author, item['name'] if isinstance(item, dict) else str(item), reason=None, extra=f"ID {item['id'] if isinstance(item, dict) else item.id}")
            except Exception:
                pass
        except Exception as e:
            await ctx.send(f"Error removing item: {e}")

    # Slash admin commands (typed, safer)
    @discord.app_commands.command(name="shop_add", description="Add an item to the shop (admin)")
    @discord.app_commands.checks.has_permissions(manage_guild=True)
    async def shop_add_slash(self, interaction: discord.Interaction, name: str, price: int, description: Optional[str] = None, type_: Optional[str] = "consumable", role_id: Optional[int] = None, category: Optional[str] = None, cooldown_seconds: Optional[int] = 0, effect_type: Optional[str] = None, effect_value: Optional[str] = None):
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("This command works in servers only.", ephemeral=True)
            return
        try:
            item_id = await db.create_item(
                guild.id,
                name=name,
                price=price,
                type_=type_ or "consumable",
                description=description,
                role_id=role_id,
                category=category,
                cooldown_seconds=int(cooldown_seconds or 0),
                effect_type=effect_type,
                effect_value=effect_value,
            )
            embed = discord.Embed(title="Shop Item Added", description=f"Added **{name}** (ID {item_id}) to the shop.", color=discord.Color.green(), timestamp=datetime.datetime.utcnow())
            embed.add_field(name="Price", value=f"{price:,} {CURRENCY}", inline=True)
            if description:
                embed.add_field(name="Description", value=description, inline=False)
            await interaction.response.send_message(embed=embed)
            try:
                await modlog_helper.send_modlog(self.bot, guild, "Shop Item Created", interaction.user, name, reason=None, extra=f"ID {item_id} • Price {price:,} {CURRENCY}")
            except Exception:
                pass
        except Exception as e:
            await interaction.response.send_message(f"Error creating item: {e}", ephemeral=True)

    @discord.app_commands.command(name="shop_remove", description="Remove an item from the shop by id (admin)")
    @discord.app_commands.checks.has_permissions(manage_guild=True)
    async def shop_remove_slash(self, interaction: discord.Interaction, item_id: int):
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("This command works in servers only.", ephemeral=True)
            return
        try:
            item = await db.get_item(guild.id, item_id)
            if not item:
                await interaction.response.send_message("Item not found.", ephemeral=True)
                return
            rows = await db.delete_item(guild.id, item_id)
            await interaction.response.send_message(embed=discord.Embed(title="Shop Item Removed", description=f"Removed **{item['name']}** (ID {item_id})", color=discord.Color.orange(), timestamp=datetime.datetime.utcnow()))
            try:
                await modlog_helper.send_modlog(self.bot, guild, "Shop Item Removed", interaction.user, item['name'], reason=None, extra=f"ID {item_id}")
            except Exception:
                pass
        except Exception as e:
            await interaction.response.send_message(f"Error removing item: {e}", ephemeral=True)

    # inventory command
    @commands.command(name="inventory", aliases=["inv"])
    async def inventory(self, ctx: commands.Context):
        guild = ctx.guild
        if guild is None:
            await ctx.send("This only works in servers.")
            return
        rows = await db.get_inventory(guild.id, ctx.author.id)
        if not rows:
            await ctx.send("Your inventory is empty.")
            return
        lines = []
        for r in rows:
            lines.append(f"Item ID {r['item_id']}: **{r['name']}** x{r['quantity']} — {r['type']}\n{r['description'] or ''}")
        out = "\n\n".join(lines)
        if len(out) <= 1900:
            await ctx.send(out)
        else:
            for i in range(0, len(out), 1900):
                await ctx.send(out[i:i+1900])

    # use item
    @commands.command(name="use")
    async def use_item(self, ctx: commands.Context, item_id: int):
        """c?use <item_id> — use one quantity of a consumable item or apply a role-type item"""
        guild = ctx.guild
        if guild is None:
            await ctx.send("This only works in servers.")
            return
        inv = await db.get_inventory(guild.id, ctx.author.id)
        found = None
        for it in inv:
            if it["item_id"] == item_id:
                found = it
                break
        if not found:
            await ctx.send("You don't have that item.")
            return

        if found["type"] == "consumable":
            ok = await db.remove_inventory_item(guild.id, ctx.author.id, item_id, 1)
            if ok:
                eff_type = found.get("effect_type")
                eff_val = found.get("effect_value")
                if eff_type == "coins" and eff_val:
                    try:
                        amount = int(eff_val)
                        await db.add_balance(guild.id, ctx.author.id, amount)
                        await ctx.send(f"✅ You used {found['name']} and received {amount:,} {CURRENCY}.")
                        try:
                            await modlog_helper.send_modlog(self.bot, guild, "Item Use", ctx.author, found['name'], reason=None, extra=f"Received {amount:,} {CURRENCY}")
                        except Exception:
                            pass
                    except Exception:
                        await ctx.send(f"✅ You used {found['name']}.")
                else:
                    await ctx.send(f"✅ You used {found['name']}.")
                # update last_used via DB helper
                await db.set_inventory_last_used(guild.id, ctx.author.id, item_id)
            else:
                await ctx.send("Failed to consume the item (insufficient quantity).")
            return

        elif found["type"] == "role":
            role_id = found.get("role_id")
            if not role_id:
                await ctx.send("This role item is broken (no role configured). Contact admin.")
                return
            role = guild.get_role(int(role_id))
            if role is None:
                await ctx.send("Target role not found. Contact admin.")
                return
            me = guild.me or guild.get_member(self.bot.user.id)
            if not me.guild_permissions.manage_roles:
                await ctx.send("I lack Manage Roles permission to assign the role.")
                return
            if role.managed:
                await ctx.send("I cannot assign managed roles.")
                return
            if role.position >= me.top_role.position:
                await ctx.send("I cannot assign that role because it is higher than my top role.")
                return
            try:
                await ctx.author.add_roles(role, reason="Used role item from shop")
                await ctx.send(f"✅ Assigned role {role.mention} to you.")
                try:
                    await modlog_helper.send_modlog(self.bot, guild, "Role Use", ctx.author, role.name, reason="Used role item", extra=None)
                except Exception:
                    pass
            except Exception as e:
                await ctx.send(f"❌ Failed to assign role: {e}")
            return

        elif found["type"] == "permanent":
            await ctx.send(f"✅ {found['name']} is a permanent item and stays in your inventory.")
            return

        else:
            await ctx.send("Unknown item type.")

    # -----------------
    # Admin (slash preferred) - create/delete/give items (omitted here — keep existing behavior)
    # -----------------

    # ---------- marketplace (sell by name or id) ----------
    @commands.group(name="market", invoke_without_command=True)
    async def market(self, ctx: commands.Context):
        await ctx.send("Usage: c?market sell <item-id-or-name> <quantity> <price> | c?market list | c?market buy <listing_id> <quantity> | c?market cancel <listing_id>")

    @market.command(name="sell")
    async def market_sell(self, ctx: commands.Context, item: str, quantity: int, price_per_item: int):
        guild = ctx.guild
        if guild is None:
            await ctx.send("Server-only.")
            return

        # resolve item
        if item.isdigit():
            item_id = int(item)
            it = await db.get_item(guild.id, item_id)
        else:
            it = await db.get_item_by_name(guild.id, item)
            item_id = it["id"] if it else None

        if not it:
            await ctx.send("Item not found (by id or name).")
            return

        success, msg, lid = await db.create_listing(guild.id, ctx.author.id, item_id, quantity, price_per_item)
        if not success:
            await ctx.send(f"❌ {msg}")
            return

        # mod-log
        try:
            await modlog_helper.send_modlog(self.bot, guild, "Listing Created", ctx.author, it["name"], reason=None, extra=f"Listing ID {lid} • Qty {quantity} • Price each {price_per_item:,} {CURRENCY}")
        except Exception:
            pass

        await ctx.send(f"✅ Listing created: ID {lid} — {quantity}x **{it['name']}** @ {price_per_item:,} {CURRENCY} each")

    @market.command(name="list")
    async def market_list(self, ctx: commands.Context):
        guild = ctx.guild
        if guild is None:
            await ctx.send("Server-only.")
            return
        listings = await db.get_listings(guild.id, True)
        if not listings:
            await ctx.send("No active marketplace listings.")
            return
        embeds = []
        for i in range(0, len(listings), LISTINGS_PER_PAGE):
            chunk = listings[i : i + LISTINGS_PER_PAGE]
            embed = discord.Embed(title=f"{guild.name} — Marketplace", color=discord.Color.gold(), timestamp=datetime.datetime.utcnow())
            for l in chunk:
                item = await db.get_item(guild.id, l["item_id"])
                item_name = item["name"] if item else f"Item {l['item_id']}"
                seller = guild.get_member(l["seller_id"])
                seller_name = seller.display_name if seller else str(l["seller_id"])
                embed.add_field(
                    name=f"Listing {l['id']} — {item_name} x{l['quantity']}",
                    value=f"Seller: {seller_name}\nPrice each: {l['price_per_item']:,} {CURRENCY}\nCreated: {l['created_at']}",
                    inline=False,
                )
            embed.set_footer(text=f"Page {i//LISTINGS_PER_PAGE + 1}/{math.ceil(len(listings)/LISTINGS_PER_PAGE)}")
            embeds.append(embed)
        view = PageView(embeds, ctx.author.id)
        await view.send_initial(ctx)

    @market.command(name="buy")
    async def market_buy(self, ctx: commands.Context, listing_id: int, quantity: int = 1):
        guild = ctx.guild
        if guild is None:
            await ctx.send("Server-only.")
            return
        listing = await db.get_listing(guild.id, listing_id)
        if not listing:
            await ctx.send("Listing not found.")
            return
        item = await db.get_item(guild.id, listing["item_id"])
        success, msg = await db.buy_listing(guild.id, ctx.author.id, listing_id, quantity)
        if not success:
            await ctx.send(f"❌ {msg}")
            return

        total = listing["price_per_item"] * int(quantity)
        seller_member = guild.get_member(listing["seller_id"])
        seller_display = seller_member.mention if seller_member else str(listing["seller_id"])

        # mod-log
        try:
            await modlog_helper.send_modlog(
                self.bot,
                guild,
                "Market Purchase",
                ctx.author,
                item["name"] if item else f"Item {listing['item_id']}",
                reason=None,
                extra=f"Listing {listing_id} • Qty {quantity} • Total {total:,} {CURRENCY} • Seller: {seller_display}",
            )
        except Exception:
            pass

        await ctx.send(f"✅ Purchase complete: Bought {quantity}x **{item['name'] if item else listing['item_id']}** for {total:,} {CURRENCY}.")

    @market.command(name="cancel")
    async def market_cancel(self, ctx: commands.Context, listing_id: int):
        guild = ctx.guild
        if guild is None:
            await ctx.send("Server-only.")
            return
        listing = await db.get_listing(guild.id, listing_id)
        if not listing:
            await ctx.send("Listing not found.")
            return
        success, msg = await db.cancel_listing(guild.id, ctx.author.id, listing_id)
        if not success:
            await ctx.send(f"❌ {msg}")
            return

        item = await db.get_item(guild.id, listing["item_id"])
        try:
            await modlog_helper.send_modlog(self.bot, guild, "Listing Cancelled", ctx.author, item["name"] if item else f"Item {listing['item_id']}", reason=None, extra=f"Listing {listing_id} • Qty {listing['quantity']}")
        except Exception:
            pass

        await ctx.send("✅ Listing cancelled and items returned.")


async def setup(bot: commands.Bot):
    await bot.add_cog(Shop(bot))