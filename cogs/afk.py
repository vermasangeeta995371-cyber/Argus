"""
AFK cog: set AFK with c?afk [reason], auto-clear AFK on message,
and notify mentioners that the user is AFK.
"""

from __future__ import annotations
import discord
from discord.ext import commands
import datetime
import db  # local DB helper

class AFK(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="afk")
    async def afk(self, ctx: commands.Context, *, reason: str = "Away"):
        """c?afk [reason] — set yourself AFK"""
        if ctx.guild is None:
            await ctx.send("AFK works only in guilds.")
            return
        await db.set_afk(ctx.guild.id, ctx.author.id, reason)
        await ctx.send(f"Okay {ctx.author.mention}, I set your AFK: {reason}")

    @commands.command(name="back")
    async def back(self, ctx: commands.Context):
        """c?back — remove your AFK manually"""
        if ctx.guild is None:
            await ctx.send("This command works only in servers.")
            return
        removed = await db.remove_afk(ctx.guild.id, ctx.author.id)
        if removed:
            await ctx.send(f"Welcome back {ctx.author.mention}! I removed your AFK.")
        else:
            await ctx.send("You were not AFK.")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Ignore bot messages
        if message.author.bot:
            return

        # If author was AFK, remove and notify
        if message.guild:
            afk = await db.get_afk(message.guild.id, message.author.id)
            if afk:
                await db.remove_afk(message.guild.id, message.author.id)
                since = afk.get("since")
                try:
                    since_dt = datetime.datetime.fromisoformat(since)
                    delta = datetime.datetime.utcnow() - since_dt
                    # human readable
                    minutes = int(delta.total_seconds() // 60)
                    hours = minutes // 60
                    if hours > 0:
                        human = f"{hours}h{minutes%60}m"
                    else:
                        human = f"{minutes}m"
                except Exception:
                    human = "a while"
                try:
                    await message.channel.send(f"Welcome back {message.author.mention}! I removed your AFK (you were AFK for {human}).")
                except Exception:
                    pass

            # If message mentions users, notify about any AFK users mentioned
            if message.mentions:
                notified = []
                for user in message.mentions:
                    if user.bot:
                        continue
                    afk = await db.get_afk(message.guild.id, user.id)
                    if afk:
                        if user.id in notified:
                            continue
                        notified.append(user.id)
                        reason = afk.get("reason") or "AFK"
                        since = afk.get("since")
                        try:
                            since_dt = datetime.datetime.fromisoformat(since)
                            since_str = since_dt.strftime("%Y-%m-%d %H:%M UTC")
                        except Exception:
                            since_str = since
                        try:
                            await message.channel.send(f"{user.mention} is AFK: {reason} (since {since_str})")
                        except Exception:
                            pass

        # Make sure other commands still run
        await self.bot.process_commands(message)


async def setup(bot: commands.Bot):
    await bot.add_cog(AFK(bot))