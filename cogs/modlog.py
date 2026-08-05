"""
Cog for configuring the mod-log channel and testing it:
- c?modlog set #channel
- c?modlog clear
- c?modlog show
- c?modlog test [message]
Slash equivalents available including /modlog_test.
"""

from __future__ import annotations
import discord
from discord.ext import commands
import discord.app_commands
import db
import datetime
from typing import Optional

class ModLog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.group(name="modlog", invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def modlog(self, ctx: commands.Context):
        await ctx.send("Usage: c?modlog set #channel | c?modlog clear | c?modlog show | c?modlog test [message]")

    @modlog.command(name="set")
    @commands.has_permissions(manage_guild=True)
    async def modlog_set(self, ctx: commands.Context, channel: discord.TextChannel):
        await db.set_modlog_channel(ctx.guild.id, channel.id)
        await ctx.send(f"Mod-log channel set to {channel.mention}.")

    @modlog.command(name="clear")
    @commands.has_permissions(manage_guild=True)
    async def modlog_clear(self, ctx: commands.Context):
        await db.clear_modlog_channel(ctx.guild.id)
        await ctx.send("Cleared mod-log channel.")

    @modlog.command(name="show")
    @commands.has_permissions(manage_guild=True)
    async def modlog_show(self, ctx: commands.Context):
        ch = await db.get_modlog_channel(ctx.guild.id)
        if ch:
            channel = self.bot.get_channel(int(ch))
            await ctx.send(f"Mod-log channel: {channel.mention if channel else str(ch)}")
        else:
            await ctx.send("No mod-log channel configured.")

    @modlog.command(name="test")
    @commands.has_permissions(manage_guild=True)
    async def modlog_test(self, ctx: commands.Context, *, message: Optional[str] = "This is a mod-log test message."):
        """c?modlog test [message] — send a safe test embed to the configured mod-log channel"""
        guild = ctx.guild
        if guild is None:
            await ctx.send("This command must be used in a server.")
            return

        ch_id = await db.get_modlog_channel(guild.id)
        if not ch_id:
            await ctx.send("No mod-log channel configured. Set one with `c?modlog set #channel`.")
            return

        channel = self.bot.get_channel(int(ch_id))
        if channel is None:
            await ctx.send("Configured mod-log channel not found (it may have been deleted or I lack access).")
            return

        # Build test embed (non-destructive)
        moderator = ctx.author
        target = ctx.author  # safe: use the invoker as the target for the test embed
        mod_name = moderator.display_name
        mod_id = moderator.id
        mod_avatar = None
        try:
            mod_avatar = moderator.display_avatar.url
        except Exception:
            mod_avatar = None
        tgt_name = target.display_name
        tgt_id = target.id
        tgt_avatar = None
        try:
            tgt_avatar = target.display_avatar.url
        except Exception:
            tgt_avatar = None

        embed = discord.Embed(title="Mod-log — Test", color=discord.Color.blue(), timestamp=datetime.datetime.utcnow())
        # Author uses moderator name + id, with avatar
        author_name = f"{mod_name} — {mod_id}"
        if mod_avatar:
            embed.set_author(name=author_name, icon_url=mod_avatar)
        else:
            embed.set_author(name=author_name)

        # Target field + thumbnail
        target_display = f"{tgt_name} — {tgt_id}"
        embed.add_field(name="Target", value=target_display, inline=True)
        if tgt_avatar:
            embed.set_thumbnail(url=tgt_avatar)

        embed.add_field(name="Action", value="Test", inline=True)
        embed.add_field(name="Reason / Message", value=message, inline=False)
        embed.set_footer(text=f"{guild.name} • Test")

        # Send to configured mod-log channel
        try:
            await channel.send(embed=embed)
            await ctx.send(f"Test embed sent to {channel.mention}.")
        except discord.Forbidden:
            await ctx.send("I don't have permission to send messages to the configured mod-log channel.")
        except Exception as e:
            await ctx.send(f"Failed to send test embed: {e}")

    # SLASH COMMANDS
    @discord.app_commands.command(name="modlog_set", description="Set mod-log channel")
    @discord.app_commands.checks.has_permissions(manage_guild=True)
    async def modlog_set_slash(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await db.set_modlog_channel(interaction.guild.id, channel.id)
        await interaction.response.send_message(f"Mod-log channel set to {channel.mention}", ephemeral=True)

    @discord.app_commands.command(name="modlog_clear", description="Clear mod-log channel")
    @discord.app_commands.checks.has_permissions(manage_guild=True)
    async def modlog_clear_slash(self, interaction: discord.Interaction):
        await db.clear_modlog_channel(interaction.guild.id)
        await interaction.response.send_message("Cleared mod-log channel.", ephemeral=True)

    @discord.app_commands.command(name="modlog_show", description="Show mod-log channel")
    @discord.app_commands.checks.has_permissions(manage_guild=True)
    async def modlog_show_slash(self, interaction: discord.Interaction):
        ch = await db.get_modlog_channel(interaction.guild.id)
        if ch:
            channel = self.bot.get_channel(int(ch))
            await interaction.response.send_message(f"Mod-log channel: {channel.mention if channel else str(ch)}", ephemeral=True)
        else:
            await interaction.response.send_message("No mod-log channel configured.", ephemeral=True)

    @discord.app_commands.command(name="modlog_test", description="Send a test mod-log embed to the configured channel")
    @discord.app_commands.checks.has_permissions(manage_guild=True)
    async def modlog_test_slash(self, interaction: discord.Interaction, message: Optional[str] = "This is a mod-log test message."):
        await interaction.response.defer(ephemeral=True, thinking=True)
        guild = interaction.guild
        if guild is None:
            await interaction.followup.send("This command must be used in a server.", ephemeral=True)
            return

        ch_id = await db.get_modlog_channel(guild.id)
        if not ch_id:
            await interaction.followup.send("No mod-log channel configured. Set one with `c?modlog set #channel`.", ephemeral=True)
            return

        channel = self.bot.get_channel(int(ch_id))
        if channel is None:
            await interaction.followup.send("Configured mod-log channel not found (it may have been deleted or I lack access).", ephemeral=True)
            return

        moderator = interaction.user
        target = interaction.user
        mod_name = moderator.display_name if hasattr(moderator, "display_name") else str(moderator)
        mod_id = getattr(moderator, "id", "")
        mod_avatar = None
        try:
            mod_avatar = moderator.display_avatar.url
        except Exception:
            mod_avatar = None
        tgt_name = getattr(target, "display_name", str(target))
        tgt_id = getattr(target, "id", "")

        embed = discord.Embed(title="Mod-log — Test", color=discord.Color.blue(), timestamp=datetime.datetime.utcnow())
        author_name = f"{mod_name} — {mod_id}"
        if mod_avatar:
            embed.set_author(name=author_name, icon_url=mod_avatar)
        else:
            embed.set_author(name=author_name)

        target_display = f"{tgt_name} — {tgt_id}"
        embed.add_field(name="Target", value=target_display, inline=True)
        embed.add_field(name="Action", value="Test", inline=True)
        embed.add_field(name="Reason / Message", value=message, inline=False)
        embed.set_footer(text=f"{guild.name} • Test")

        try:
            await channel.send(embed=embed)
            await interaction.followup.send(f"Test embed sent to {channel.mention}.", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send("I don't have permission to send messages to the configured mod-log channel.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"Failed to send test embed: {e}", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(ModLog(bot))