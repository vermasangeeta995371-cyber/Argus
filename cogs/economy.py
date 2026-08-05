"""
Economy cog: balance, pay, daily, weekly, work, crime, leaderboard, gamble, and admin setbalance.
"""

from __future__ import annotations
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

    # user commands omitted here for brevity — keep your existing implementations
    # We'll only show the setbalance admin command additions and ensure balance helpers exist.

    @commands.command(name="balance", aliases=["bal"])
    async def balance(self, ctx: commands.Context, member: Optional[discord.Member] = None):
        guild = ctx.guild
        if guild is None:
            await ctx.send("This command works in servers only.")
            return
        member = member or ctx.author
        bal = await db.get_balance(guild.id, member.id)
        await ctx.send(f"{member.mention} has {bal:,} {CURRENCY}.")

    # ... other user commands (pay,daily,weekly,work,crime,leaderboard,gamble) should be present as before.
    # For brevity, ensure the previous code you had for those commands remains here unchanged.

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