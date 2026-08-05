from __future__ import annotations
import discord
from discord.ext import commands
import discord.app_commands
from typing import Optional
import datetime
import asyncio

import db  # local db helper

class Utility(commands.Cog):
    """Utility commands: user/server info, avatar, clear, warn system, say, poll."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # --------------------
    # PREFIX COMMANDS
    # --------------------
    @commands.command(name="userinfo")
    async def userinfo(self, ctx: commands.Context, member: Optional[discord.Member] = None):
        """!userinfo [member]"""
        member = member or ctx.author
        embed = discord.Embed(title=f"User Info — {member}", color=discord.Color.blurple(), timestamp=datetime.datetime.utcnow())
        embed.set_thumbnail(url=member.display_avatar.url if member.display_avatar else None)
        embed.add_field(name="ID", value=member.id, inline=True)
        embed.add_field(name="Bot?", value=member.bot, inline=True)
        embed.add_field(name="Top role", value=member.top_role.mention if member.top_role else "None", inline=True)
        embed.add_field(name="Created", value=member.created_at.strftime("%Y-%m-%d %H:%M UTC"), inline=True)
        if isinstance(member, discord.Member):
            embed.add_field(name="Joined", value=member.joined_at.strftime("%Y-%m-%d %H:%M UTC") if member.joined_at else "Unknown", inline=True)
        await ctx.send(embed=embed)

    @commands.command(name="serverinfo")
    async def serverinfo(self, ctx: commands.Context):
        """!serverinfo"""
        guild = ctx.guild
        if guild is None:
            await ctx.send("This command only works in a server.")
            return
        embed = discord.Embed(title=f"Server Info — {guild.name}", color=discord.Color.green(), timestamp=datetime.datetime.utcnow())
        embed.set_thumbnail(url=guild.icon.url if guild.icon else None)
        embed.add_field(name="ID", value=guild.id, inline=True)
        embed.add_field(name="Owner", value=str(guild.owner) if guild.owner else "Unknown", inline=True)
        embed.add_field(name="Members", value=guild.member_count, inline=True)
        embed.add_field(name="Created", value=guild.created_at.strftime("%Y-%m-%d %H:%M UTC"), inline=True)
        await ctx.send(embed=embed)

    @commands.command(name="avatar")
    async def avatar(self, ctx: commands.Context, member: Optional[discord.Member] = None):
        """!avatar [member]"""
        member = member or ctx.author
        if member.display_avatar:
            await ctx.send(member.display_avatar.url)
        else:
            await ctx.send("No avatar found.")

    @commands.command(name="clear", aliases=["purge"])
    @commands.has_permissions(manage_messages=True)
    async def clear(self, ctx: commands.Context, amount: int = 10):
        """!clear <amount> — requires Manage Messages"""
        if amount <= 0:
            await ctx.send("Amount must be positive.")
            return
        deleted = await ctx.channel.purge(limit=amount + 1)  # +1 to remove command message
        await ctx.send(f"Deleted {len(deleted)-1} messages.", delete_after=5)

    @commands.command(name="say")
    @commands.has_permissions(manage_messages=True)
    async def say(self, ctx: commands.Context, *, message: str):
        """!say <message> — bot repeats message"""
        await ctx.message.delete()
        await ctx.send(message)

    @commands.command(name="poll")
    async def poll(self, ctx: commands.Context, question: str, *options: str):
        """!poll "Question" "Option1" "Option2" ... (max 10 options)
        If no options provided, does a yes/no poll.
        """
        if not options:
            msg = await ctx.send(f"Poll: **{question}**\nReact with ✅ or ❌")
            await msg.add_reaction("✅")
            await msg.add_reaction("❌")
            return
        if len(options) > 10:
            await ctx.send("Max 10 options.")
            return
        emojis = ["1️⃣","2️⃣","3️⃣","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣","🔟"]
        description = "\n".join(f"{emojis[i]} {opt}" for i, opt in enumerate(options))
        embed = discord.Embed(title=question, description=description, color=discord.Color.gold())
        msg = await ctx.send(embed=embed)
        for i in range(len(options)):
            await msg.add_reaction(emojis[i])

    # --------------------
    # Warn system (prefix)
    # --------------------
    @commands.command(name="warn")
    @commands.has_permissions(kick_members=True)
    async def warn(self, ctx: commands.Context, member: discord.Member, *, reason: Optional[str] = "No reason provided"):
        """!warn @user [reason] — persists a warning"""
        wid = await db.add_warn(ctx.guild.id, member.id, ctx.author.id, reason)
        await ctx.send(f"Warned {member.mention}. Warn ID: {wid}")

    @commands.command(name="warns")
    async def warns(self, ctx: commands.Context, member: Optional[discord.Member] = None):
        """!warns [member] — list warnings"""
        member = member or ctx.author
        rows = await db.get_warns(ctx.guild.id, member.id)
        if not rows:
            await ctx.send(f"No warnings for {member.mention}.")
            return
        lines = []
        for r in rows:
            mod = ctx.guild.get_member(r["moderator_id"])
            mod_name = mod.display_name if mod else str(r["moderator_id"])
            created = r["created_at"]
            lines.append(f"ID {r['id']} — by {mod_name} — {created}\nReason: {r['reason'] or 'No reason'}")
        # Send in multiple messages if long
        chunk_size = 1900
        out = f"Warnings for {member.mention}:\n\n" + "\n\n".join(lines)
        if len(out) <= chunk_size:
            await ctx.send(out)
        else:
            for i in range(0, len(out), chunk_size):
                await ctx.send(out[i:i+chunk_size])

    @commands.command(name="unwarn")
    @commands.has_permissions(kick_members=True)
    async def unwarn(self, ctx: commands.Context, warn_id: int):
        """!unwarn <warn_id> — removes a single warn by ID"""
        count = await db.remove_warn(ctx.guild.id, warn_id)
        if count:
            await ctx.send(f"Removed warn ID {warn_id}.")
        else:
            await ctx.send(f"No warn with ID {warn_id} found.")

    # --------------------
    # SLASH COMMANDS
    # --------------------
    @discord.app_commands.command(name="userinfo", description="Show user info")
    async def userinfo_slash(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        member = member or interaction.user
        embed = discord.Embed(title=f"User Info — {member}", color=discord.Color.blurple(), timestamp=datetime.datetime.utcnow())
        embed.set_thumbnail(url=member.display_avatar.url if member.display_avatar else None)
        embed.add_field(name="ID", value=member.id, inline=True)
        embed.add_field(name="Bot?", value=member.bot, inline=True)
        embed.add_field(name="Top role", value=member.top_role.mention if member.top_role else "None", inline=True)
        embed.add_field(name="Created", value=member.created_at.strftime("%Y-%m-%d %H:%M UTC"), inline=True)
        if isinstance(member, discord.Member):
            embed.add_field(name="Joined", value=member.joined_at.strftime("%Y-%m-%d %H:%M UTC") if member.joined_at else "Unknown", inline=True)
        await interaction.response.send_message(embed=embed)

    @discord.app_commands.command(name="serverinfo", description="Show server info")
    async def serverinfo_slash(self, interaction: discord.Interaction):
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("This command only works in a server.", ephemeral=True)
            return
        embed = discord.Embed(title=f"Server Info — {guild.name}", color=discord.Color.green(), timestamp=datetime.datetime.utcnow())
        embed.set_thumbnail(url=guild.icon.url if guild.icon else None)
        embed.add_field(name="ID", value=guild.id, inline=True)
        embed.add_field(name="Owner", value=str(guild.owner) if guild.owner else "Unknown", inline=True)
        embed.add_field(name="Members", value=guild.member_count, inline=True)
        embed.add_field(name="Created", value=guild.created_at.strftime("%Y-%m-%d %H:%M UTC"), inline=True)
        await interaction.response.send_message(embed=embed)

    @discord.app_commands.command(name="avatar", description="Show a user's avatar")
    async def avatar_slash(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        member = member or interaction.user
        if member.display_avatar:
            await interaction.response.send_message(member.display_avatar.url)
        else:
            await interaction.response.send_message("No avatar found.", ephemeral=True)

    @discord.app_commands.command(name="clear", description="Clear messages (requires Manage Messages)")
    @discord.app_commands.checks.has_permissions(manage_messages=True)
    async def clear_slash(self, interaction: discord.Interaction, amount: int = 10):
        await interaction.response.defer(thinking=True, ephemeral=False)
        if amount <= 0:
            await interaction.followup.send("Amount must be positive.", ephemeral=True)
            return
        deleted = await interaction.channel.purge(limit=amount)
        await interaction.followup.send(f"Deleted {len(deleted)} messages.", ephemeral=True)

    @discord.app_commands.command(name="warn", description="Warn a user (records to DB)")
    @discord.app_commands.checks.has_permissions(kick_members=True)
    async def warn_slash(self, interaction: discord.Interaction, member: discord.Member, reason: Optional[str] = "No reason provided"):
        wid = await db.add_warn(interaction.guild.id, member.id, interaction.user.id, reason)
        await interaction.response.send_message(f"Warned {member.mention}. Warn ID: {wid}")

    @discord.app_commands.command(name="warns", description="List warnings for a user")
    async def warns_slash(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        member = member or interaction.user
        rows = await db.get_warns(interaction.guild.id, member.id)
        if not rows:
            await interaction.response.send_message(f"No warnings for {member.mention}.", ephemeral=True)
            return
        lines = []
        for r in rows:
            mod = interaction.guild.get_member(r["moderator_id"])
            mod_name = mod.display_name if mod else str(r["moderator_id"])
            created = r["created_at"]
            lines.append(f"ID {r['id']} — by {mod_name} — {created}\nReason: {r['reason'] or 'No reason'}")
        out = f"Warnings for {member.mention}:\n\n" + "\n\n".join(lines)
        # If long, send ephemeral then full as followup
        if len(out) > 1900:
            await interaction.response.send_message("Too long to show in one message — sending privately.", ephemeral=True)
            for i in range(0, len(out), 1900):
                await interaction.user.send(out[i:i+1900])
        else:
            await interaction.response.send_message(out, ephemeral=True)

    @discord.app_commands.command(name="unwarn", description="Remove a warning by ID")
    @discord.app_commands.checks.has_permissions(kick_members=True)
    async def unwarn_slash(self, interaction: discord.Interaction, warn_id: int):
        count = await db.remove_warn(interaction.guild.id, warn_id)
        if count:
            await interaction.response.send_message(f"Removed warn ID {warn_id}.")
        else:
            await interaction.response.send_message(f"No warn with ID {warn_id} found.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Utility(bot))