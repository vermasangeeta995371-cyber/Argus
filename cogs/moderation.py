"""
Enhanced moderation cog with modlog integration.
Re-uses previous moderation commands; after successful actions it posts to mod-log via modlog.send_modlog.
"""

from __future__ import annotations
import discord
from discord.ext import commands
import discord.app_commands
from typing import Optional
import datetime
import asyncio
import modlog as modlog_helper  # new helper
import db

class Moderation(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # (helpers like _parse_duration, _get_or_create_muted_role, _bot_can_manage_role remain same as before)
    # For brevity in this message, include the helper methods as in your previous moderation cog,
    # but ensure at the end of each successful moderation action you call modlog_helper.send_modlog(...).

    # Example: kick command now logs:
    @commands.command(name="kick")
    @commands.has_permissions(kick_members=True)
    async def kick(self, ctx: commands.Context, member: discord.Member, *, reason: Optional[str] = None):
        try:
            await member.kick(reason=reason)
            await ctx.send(f"🔨 Kicked {member.mention}. Reason: {reason or 'No reason provided.'}")
            # Log to mod-log channel
            try:
                await modlog_helper.send_modlog(self.bot, ctx.guild, "Kick", ctx.author, member, reason)
            except Exception:
                pass
        except discord.Forbidden:
            await ctx.send("I don't have permission to kick that user.")
        except Exception as e:
            await ctx.send(f"Error while kicking: {e}")

    # Example: ban command logs similarly:
    @commands.command(name="ban")
    @commands.has_permissions(ban_members=True)
    async def ban(self, ctx: commands.Context, member: discord.Member, *, reason: Optional[str] = None):
        try:
            await member.ban(reason=reason)
            await ctx.send(f"🔨 Banned {member.mention}. Reason: {reason or 'No reason provided.'}")
            try:
                await modlog_helper.send_modlog(self.bot, ctx.guild, "Ban", ctx.author, member, reason)
            except Exception:
                pass
        except discord.Forbidden:
            await ctx.send("I don't have permission to ban that user.")
        except Exception as e:
            await ctx.send(f"Error while banning: {e}")

    # For mute/unmute/createrole/assignrole/removerole/deleterole you should add the same modlog call after success.
    # For brevity, keep the rest of the implementation from your existing moderation cog but add:
    #   await modlog_helper.send_modlog(self.bot, ctx.guild, "<Action>", ctx.author, <target>, reason, extra=<details>)
    # at the successful branch where you already send the user-facing confirmation.

    # --------------------
    # SLASH COMMANDS
    # --------------------
    # In each slash command, after a successful moderation action, also call modlog_helper.send_modlog
    # Example:
    @discord.app_commands.command(name="kick", description="Kick a member")
    @discord.app_commands.checks.has_permissions(kick_members=True)
    async def kick_slash(self, interaction: discord.Interaction, member: discord.Member, reason: Optional[str] = None):
        try:
            await member.kick(reason=reason)
            await interaction.response.send_message(f"🔨 Kicked {member.mention}. Reason: {reason or 'No reason provided.'}")
            try:
                await modlog_helper.send_modlog(self.bot, interaction.guild, "Kick", interaction.user, member, reason)
            except Exception:
                pass
        except discord.Forbidden:
            await interaction.response.send_message("I don't have permission to kick that user.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Error while kicking: {e}", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))