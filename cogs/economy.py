"""
Economy cog: balance, pay, daily, weekly, work, crime, leaderboard, gamble, and admin setbalance.
"""

from __future__ import annotations
import aiosqlite
import datetime
import discord
from discord.ext import commands
import discord.app_commands
from typing import Optional
import random
import db

CURRENCY = "Coins"
DAILY_AMOUNT = 100
WEEKLY_AMOUNT = 700
WEEKLY_COOLDOWN_HOURS = 24 * 7
WORK_MIN = 50
WORK_MAX = 150
WORK_COOLDOWN_HOURS = 1
CRIME_SUCCESS_CHANCE = 0.45
CRIME_MIN_REWARD = 100
CRIME_MAX_REWARD = 500
CRIME_MIN_FINE = 50
CRIME_MAX_FINE = 300
CRIME_COOLDOWN_HOURS = 2
GAMBLE_MULTIPLIER_WIN = 2


class Economy(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _get_economy_row(self, guild_id: int, user_id: int):
        await db._ensure_economy_row(guild_id, user_id)
        async with aiosqlite.connect(db.DB_PATH) as conn:
            cur = await conn.execute(
                "SELECT balance, last_daily, last_weekly, last_work, last_crime FROM economy WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id),
            )
            row = await cur.fetchone()
            return row

    async def _update_economy_row(self, guild_id: int, user_id: int, **fields):
        if not fields:
            return
        cols = ", ".join(f"{k} = ?" for k in fields.keys())
        values = list(fields.values()) + [guild_id, user_id]
        async with aiosqlite.connect(db.DB_PATH) as conn:
            await conn.execute(f"UPDATE economy SET {cols} WHERE guild_id = ? AND user_id = ?", values)
            await conn.commit()

    @commands.command(name="balance", aliases=["bal"])
    async def balance(self, ctx: commands.Context, member: Optional[discord.Member] = None):
        guild = ctx.guild
        if guild is None:
            await ctx.send("This command works in servers only.")
            return
        member = member or ctx.author
        bal = await db.get_balance(guild.id, member.id)
        await ctx.send(f"{member.mention} has {bal:,} {CURRENCY}.")

    @commands.command(name="pay")
    async def pay(self, ctx: commands.Context, member: discord.Member, amount: int):
        guild = ctx.guild
        if guild is None:
            await ctx.send("This command works in servers only.")
            return
        if member.bot:
            await ctx.send("You cannot pay a bot.")
            return
        if amount <= 0:
            await ctx.send("Amount must be positive.")
            return
        if member.id == ctx.author.id:
            await ctx.send("You cannot pay yourself.")
            return
        balance = await db.get_balance(guild.id, ctx.author.id)
        if balance < amount:
            await ctx.send(f"You only have {balance:,} {CURRENCY}.")
            return
        transferred = await db.transfer_balance(guild.id, ctx.author.id, member.id, amount)
        if not transferred:
            await ctx.send("Failed to transfer funds.")
            return
        await ctx.send(f"{ctx.author.mention} paid {member.mention} {amount:,} {CURRENCY}.")

    @commands.command(name="daily")
    async def daily(self, ctx: commands.Context):
        guild = ctx.guild
        if guild is None:
            await ctx.send("This command works in servers only.")
            return
        row = await self._get_economy_row(guild.id, ctx.author.id)
        last_daily = row[1]
        now = datetime.datetime.utcnow()
        if last_daily:
            try:
                last = datetime.datetime.fromisoformat(last_daily)
                elapsed = (now - last).total_seconds()
            except Exception:
                elapsed = 24 * 60 * 60 + 1
        else:
            elapsed = 24 * 60 * 60 + 1
        if elapsed < 24 * 60 * 60:
            remaining = int(24 * 60 * 60 - elapsed)
            hours = remaining // 3600
            minutes = (remaining % 3600) // 60
            await ctx.send(f"Daily reward already claimed. Try again in {hours}h {minutes}m.")
            return
        await db.add_balance(guild.id, ctx.author.id, DAILY_AMOUNT)
        await self._update_economy_row(guild.id, ctx.author.id, last_daily=now.isoformat())
        await ctx.send(f"You received your daily {DAILY_AMOUNT:,} {CURRENCY}!")

    @commands.command(name="weekly")
    async def weekly(self, ctx: commands.Context):
        guild = ctx.guild
        if guild is None:
            await ctx.send("This command works in servers only.")
            return
        row = await self._get_economy_row(guild.id, ctx.author.id)
        last_weekly = row[2]
        now = datetime.datetime.utcnow()
        if last_weekly:
            try:
                last = datetime.datetime.fromisoformat(last_weekly)
                elapsed = (now - last).total_seconds()
            except Exception:
                elapsed = 7 * 24 * 60 * 60 + 1
        else:
            elapsed = 7 * 24 * 60 * 60 + 1
        if elapsed < WEEKLY_COOLDOWN_HOURS * 3600:
            remaining = int(WEEKLY_COOLDOWN_HOURS * 3600 - elapsed)
            days = remaining // 86400
            hours = (remaining % 86400) // 3600
            await ctx.send(f"Weekly reward already claimed. Try again in {days}d {hours}h.")
            return
        await db.add_balance(guild.id, ctx.author.id, WEEKLY_AMOUNT)
        await self._update_economy_row(guild.id, ctx.author.id, last_weekly=now.isoformat())
        await ctx.send(f"You received your weekly {WEEKLY_AMOUNT:,} {CURRENCY}!")

    @commands.command(name="work")
    async def work(self, ctx: commands.Context):
        guild = ctx.guild
        if guild is None:
            await ctx.send("This command works in servers only.")
            return
        row = await self._get_economy_row(guild.id, ctx.author.id)
        last_work = row[3]
        now = datetime.datetime.utcnow()
        if last_work:
            try:
                last = datetime.datetime.fromisoformat(last_work)
                elapsed = (now - last).total_seconds()
            except Exception:
                elapsed = WORK_COOLDOWN_HOURS * 3600 + 1
        else:
            elapsed = WORK_COOLDOWN_HOURS * 3600 + 1
        if elapsed < WORK_COOLDOWN_HOURS * 3600:
            remaining = int(WORK_COOLDOWN_HOURS * 3600 - elapsed)
            minutes = remaining // 60
            await ctx.send(f"You need to wait {minutes}m before working again.")
            return
        amount = random.randint(WORK_MIN, WORK_MAX)
        await db.add_balance(guild.id, ctx.author.id, amount)
        await self._update_economy_row(guild.id, ctx.author.id, last_work=now.isoformat())
        await ctx.send(f"You worked and earned {amount:,} {CURRENCY}.")

    @commands.command(name="crime")
    async def crime(self, ctx: commands.Context):
        guild = ctx.guild
        if guild is None:
            await ctx.send("This command works in servers only.")
            return
        row = await self._get_economy_row(guild.id, ctx.author.id)
        last_crime = row[4]
        now = datetime.datetime.utcnow()
        if last_crime:
            try:
                last = datetime.datetime.fromisoformat(last_crime)
                elapsed = (now - last).total_seconds()
            except Exception:
                elapsed = CRIME_COOLDOWN_HOURS * 3600 + 1
        else:
            elapsed = CRIME_COOLDOWN_HOURS * 3600 + 1
        if elapsed < CRIME_COOLDOWN_HOURS * 3600:
            remaining = int(CRIME_COOLDOWN_HOURS * 3600 - elapsed)
            minutes = remaining // 60
            await ctx.send(f"You need to wait {minutes}m before attempting crime again.")
            return
        success = random.random() < CRIME_SUCCESS_CHANCE
        if success:
            amount = random.randint(CRIME_MIN_REWARD, CRIME_MAX_REWARD)
            await db.add_balance(guild.id, ctx.author.id, amount)
            result = f"Crime successful! You gained {amount:,} {CURRENCY}."
        else:
            amount = random.randint(CRIME_MIN_FINE, CRIME_MAX_FINE)
            balance = await db.get_balance(guild.id, ctx.author.id)
            new_balance = max(balance - amount, 0)
            await db.set_balance(guild.id, ctx.author.id, new_balance)
            result = f"Crime failed! You were fined {amount:,} {CURRENCY}."
        await self._update_economy_row(guild.id, ctx.author.id, last_crime=now.isoformat())
        await ctx.send(result)

    @commands.command(name="leaderboard", aliases=["lb"])
    async def leaderboard(self, ctx: commands.Context, limit: int = 10):
        guild = ctx.guild
        if guild is None:
            await ctx.send("This command works in servers only.")
            return
        limit = max(1, min(limit, 20))
        leaderboard = await db.get_leaderboard(guild.id, limit)
        if not leaderboard:
            await ctx.send("No economy data yet.")
            return
        lines = []
        for rank, row in enumerate(leaderboard, start=1):
            member = guild.get_member(row["user_id"])
            display = member.display_name if member else f"<@{row['user_id']}>"
            lines.append(f"{rank}. {display} — {row['balance']:,} {CURRENCY}")
        await ctx.send("\n".join(lines))

    @commands.command(name="gamble")
    async def gamble(self, ctx: commands.Context, amount: int):
        guild = ctx.guild
        if guild is None:
            await ctx.send("This command works in servers only.")
            return
        if amount <= 0:
            await ctx.send("Amount must be positive.")
            return
        balance = await db.get_balance(guild.id, ctx.author.id)
        if balance < amount:
            await ctx.send(f"You only have {balance:,} {CURRENCY}.")
            return
        win = random.random() < 0.5
        if win:
            await db.add_balance(guild.id, ctx.author.id, amount)
            await ctx.send(f"You won {amount:,} {CURRENCY}!")
        else:
            await db.add_balance(guild.id, ctx.author.id, -amount)
            await ctx.send(f"You lost {amount:,} {CURRENCY}.")

    # --------------------
    # ADMIN: setbalance
    # --------------------
    @commands.command(name="setbalance")
    @commands.has_permissions(manage_guild=True)
    async def setbalance(self, ctx: commands.Context, member: discord.Member, amount: int):
        """c?setbalance @member amount — admin only"""
        if amount < 0:
            await ctx.send("Amount cannot be negative.")
            return
        guild = ctx.guild
        await db.set_balance(guild.id, member.id, amount)
        await ctx.send(f"Set {member.mention}'s balance to {amount:,} {CURRENCY}.")

    @discord.app_commands.command(name="setbalance", description="Set a user's balance (admin)")
    @discord.app_commands.checks.has_permissions(manage_guild=True)
    async def setbalance_slash(self, interaction: discord.Interaction, member: discord.Member, amount: int):
        await interaction.response.defer(ephemeral=True, thinking=True)
        if amount < 0:
            await interaction.followup.send("Amount cannot be negative.", ephemeral=True)
            return
        guild = interaction.guild
        await db.set_balance(guild.id, member.id, amount)
        await interaction.followup.send(f"Set {member.mention}'s balance to {amount:,} {CURRENCY}.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Economy(bot))