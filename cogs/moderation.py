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


class _ConfirmView(discord.ui.View):
    def __init__(self, author_id: int, confirm_callback, timeout: int = 60):
        super().__init__(timeout=timeout)
        self.author_id = author_id
        self.confirm_callback = confirm_callback

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This confirmation isn't for you.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        try:
            await self.confirm_callback(interaction)
        finally:
            self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="Action cancelled.", embed=None, view=None)
        self.stop()

    async def _send_confirmation_ctx(self, ctx: commands.Context, title: str, description: str, fields: list[tuple[str, str]] | None = None):
        embed = discord.Embed(title=title, description=description, color=discord.Color.green(), timestamp=datetime.datetime.utcnow())
        if fields:
            for name, val in fields:
                embed.add_field(name=name, value=val, inline=False)
        await ctx.send(embed=embed)

    async def _send_confirmation_interaction(self, interaction: discord.Interaction, title: str, description: str, fields: list[tuple[str, str]] | None = None):
        embed = discord.Embed(title=title, description=description, color=discord.Color.green(), timestamp=datetime.datetime.utcnow())
        if fields:
            for name, val in fields:
                embed.add_field(name=name, value=val, inline=False)
        await interaction.response.send_message(embed=embed)

    async def _get_or_create_muted_role(self, guild: discord.Guild) -> discord.Role | None:
        """Get or create a 'Muted' role and attempt to apply text channel overwrites."""
        role = discord.utils.get(guild.roles, name="Muted")
        if role:
            return role
        try:
            perms = discord.Permissions(send_messages=False, speak=False)
            role = await guild.create_role(name="Muted", permissions=perms, reason="Muted role created by bot")
            # Try to set channel overwrites for text channels
            for ch in guild.text_channels:
                try:
                    await ch.set_permissions(role, send_messages=False, add_reactions=False)
                except Exception:
                    pass
            return role
        except Exception:
            return None

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
        async def _do_ban(interaction: discord.Interaction):
            try:
                await member.ban(reason=reason)
                await interaction.followup.send(f"🔨 Banned {member.mention}. Reason: {reason or 'No reason provided.'}")
                try:
                    await modlog_helper.send_modlog(self.bot, ctx.guild, "Ban", ctx.author, member, reason)
                except Exception:
                    pass
            except discord.Forbidden:
                await interaction.followup.send("I don't have permission to ban that user.")
            except Exception as e:
                await interaction.followup.send(f"Error while banning: {e}")

        view = _ConfirmView(ctx.author.id, _do_ban)
        await ctx.send(f"Are you sure you want to ban {member.mention}?", view=view)

    @discord.app_commands.command(name="ban", description="Ban a member")
    @discord.app_commands.checks.has_permissions(ban_members=True)
    async def ban_slash(self, interaction: discord.Interaction, member: discord.Member, *, reason: Optional[str] = None):
        async def _do_ban(interaction2: discord.Interaction):
            try:
                await member.ban(reason=reason)
                await interaction2.followup.send(f"🔨 Banned {member.mention}. Reason: {reason or 'No reason provided.'}")
                try:
                    await modlog_helper.send_modlog(self.bot, interaction.guild, "Ban", interaction.user, member, reason)
                except Exception:
                    pass
            except discord.Forbidden:
                await interaction2.followup.send("I don't have permission to ban that user.")
            except Exception as e:
                await interaction2.followup.send(f"Error while banning: {e}")

        await interaction.response.send_message(f"Confirm ban of {member.mention}", ephemeral=True, view=_ConfirmView(interaction.user.id, _do_ban))

    # --------------------
    # Role management
    # --------------------
    @commands.command(name="createrole")
    @commands.has_permissions(manage_roles=True)
    async def createrole(self, ctx: commands.Context, *, name: str):
        if ctx.guild is None:
            await ctx.send("This command works in servers only.")
            return
        try:
            role = await ctx.guild.create_role(name=name)
            await self._send_confirmation_ctx(ctx, "Role Created", f"Created role {role.mention}", [("Role ID", str(role.id))])
            try:
                await modlog_helper.send_modlog(self.bot, ctx.guild, "Create Role", ctx.author, str(role.name), extra=f"Role ID: {role.id}")
            except Exception:
                pass
        except Exception as e:
            await ctx.send(f"Error creating role: {e}")

    @discord.app_commands.command(name="createrole", description="Create a role")
    @discord.app_commands.checks.has_permissions(manage_roles=True)
    async def createrole_slash(self, interaction: discord.Interaction, name: str):
        try:
            role = await interaction.guild.create_role(name=name)
            await self._send_confirmation_interaction(interaction, "Role Created", f"Created role {role.mention}", [("Role ID", str(role.id))])
            try:
                await modlog_helper.send_modlog(self.bot, interaction.guild, "Create Role", interaction.user, str(role.name), extra=f"Role ID: {role.id}")
            except Exception:
                pass
        except Exception as e:
            await interaction.response.send_message(f"Error creating role: {e}", ephemeral=True)

    @commands.command(name="deleterole")
    @commands.has_permissions(manage_roles=True)
    async def deleterole(self, ctx: commands.Context, role: discord.Role):
        if ctx.guild is None:
            await ctx.send("This command works in servers only.")
            return
        # ask for confirmation via view
        async def _do_delete(interaction: discord.Interaction):
            try:
                name = role.name
                rid = role.id
                await role.delete()
                await interaction.followup.send(f"Deleted role {name}.")
                try:
                    await modlog_helper.send_modlog(self.bot, ctx.guild, "Delete Role", ctx.author, name, extra=f"Role ID: {rid}")
                except Exception:
                    pass
            except Exception as e:
                await interaction.followup.send(f"Error deleting role: {e}")

        view = _ConfirmView(ctx.author.id, _do_delete)
        await ctx.send(f"Are you sure you want to delete the role {role.mention}?", view=view)

    @discord.app_commands.command(name="deleterole", description="Delete a role")
    @discord.app_commands.checks.has_permissions(manage_roles=True)
    async def deleterole_slash(self, interaction: discord.Interaction, role: discord.Role):
        async def _do_delete(interaction2: discord.Interaction):
            try:
                name = role.name
                rid = role.id
                await role.delete()
                await interaction2.followup.send(f"Deleted role {name}.")
                try:
                    await modlog_helper.send_modlog(self.bot, interaction.guild, "Delete Role", interaction.user, name, extra=f"Role ID: {rid}")
                except Exception:
                    pass
            except Exception as e:
                await interaction2.followup.send(f"Error deleting role: {e}")

        await interaction.response.send_message(f"Confirm deletion of role {role.mention}", ephemeral=True, view=_ConfirmView(interaction.user.id, _do_delete))

    @commands.command(name="assignrole")
    @commands.has_permissions(manage_roles=True)
    async def assignrole(self, ctx: commands.Context, member: discord.Member, role: discord.Role):
        try:
            await member.add_roles(role)
            await self._send_confirmation_ctx(ctx, "Role Assigned", f"Assigned {role.mention} to {member.mention}", [("Role ID", str(role.id))])
            try:
                await modlog_helper.send_modlog(self.bot, ctx.guild, "Assign Role", ctx.author, member, extra=f"Role: {role.name} — {role.id}")
            except Exception:
                pass
        except Exception as e:
            await ctx.send(f"Error assigning role: {e}")

    @commands.command(name="removerole")
    @commands.has_permissions(manage_roles=True)
    async def removerole(self, ctx: commands.Context, member: discord.Member, role: discord.Role):
        try:
            await member.remove_roles(role)
            await self._send_confirmation_ctx(ctx, "Role Removed", f"Removed {role.mention} from {member.mention}", [("Role ID", str(role.id))])
            try:
                await modlog_helper.send_modlog(self.bot, ctx.guild, "Remove Role", ctx.author, member, extra=f"Role: {role.name} — {role.id}")
            except Exception:
                pass
        except Exception as e:
            await ctx.send(f"Error removing role: {e}")

    @discord.app_commands.command(name="assignrole", description="Assign a role to a member")
    @discord.app_commands.checks.has_permissions(manage_roles=True)
    async def assignrole_slash(self, interaction: discord.Interaction, member: discord.Member, role: discord.Role):
        try:
            await member.add_roles(role)
            await self._send_confirmation_interaction(interaction, "Role Assigned", f"Assigned {role.mention} to {member.mention}", [("Role ID", str(role.id))])
            try:
                await modlog_helper.send_modlog(self.bot, interaction.guild, "Assign Role", interaction.user, member, extra=f"Role: {role.name} — {role.id}")
            except Exception:
                pass
        except Exception as e:
            await interaction.response.send_message(f"Error assigning role: {e}", ephemeral=True)

    @discord.app_commands.command(name="removerole", description="Remove a role from a member")
    @discord.app_commands.checks.has_permissions(manage_roles=True)
    async def removerole_slash(self, interaction: discord.Interaction, member: discord.Member, role: discord.Role):
        try:
            await member.remove_roles(role)
            await self._send_confirmation_interaction(interaction, "Role Removed", f"Removed {role.mention} from {member.mention}", [("Role ID", str(role.id))])
            try:
                await modlog_helper.send_modlog(self.bot, interaction.guild, "Remove Role", interaction.user, member, extra=f"Role: {role.name} — {role.id}")
            except Exception:
                pass
        except Exception as e:
            await interaction.response.send_message(f"Error removing role: {e}", ephemeral=True)

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

    # --------------------
    # Mute / Unmute
    # --------------------
    @commands.command(name="mute")
    @commands.has_permissions(manage_roles=True)
    async def mute(self, ctx: commands.Context, member: discord.Member, *, reason: Optional[str] = None):
        if ctx.guild is None:
            await ctx.send("This command works in servers only.")
            return
        role = await self._get_or_create_muted_role(ctx.guild)
        if role is None:
            await ctx.send("Failed to get or create Muted role.")
            return
        try:
            await member.add_roles(role, reason=reason)
            await self._send_confirmation_ctx(ctx, "Member Muted", f"Muted {member.mention}", [("Reason", reason or "—"), ("Role", f"{role.name} — {role.id}")])
            try:
                await modlog_helper.send_modlog(self.bot, ctx.guild, "Mute", ctx.author, member, reason, extra=f"Role: {role.name} — {role.id}")
            except Exception:
                pass
        except Exception as e:
            await ctx.send(f"Error muting member: {e}")

    @commands.command(name="unmute")
    @commands.has_permissions(manage_roles=True)
    async def unmute(self, ctx: commands.Context, member: discord.Member, *, reason: Optional[str] = None):
        if ctx.guild is None:
            await ctx.send("This command works in servers only.")
            return
        role = discord.utils.get(ctx.guild.roles, name="Muted")
        if role is None:
            await ctx.send("Muted role not found.")
            return
        try:
            await member.remove_roles(role, reason=reason)
            await self._send_confirmation_ctx(ctx, "Member Unmuted", f"Unmuted {member.mention}", [("Reason", reason or "—")])
            try:
                await modlog_helper.send_modlog(self.bot, ctx.guild, "Unmute", ctx.author, member, reason, extra=f"Role: {role.name} — {role.id}")
            except Exception:
                pass
        except Exception as e:
            await ctx.send(f"Error unmuting member: {e}")

    @discord.app_commands.command(name="mute", description="Mute a member")
    @discord.app_commands.checks.has_permissions(manage_roles=True)
    async def mute_slash(self, interaction: discord.Interaction, member: discord.Member, reason: Optional[str] = None):
        role = await self._get_or_create_muted_role(interaction.guild)
        if role is None:
            await interaction.response.send_message("Failed to get or create Muted role.", ephemeral=True)
            return
        try:
            await member.add_roles(role, reason=reason)
            await self._send_confirmation_interaction(interaction, "Member Muted", f"Muted {member.mention}", [("Reason", reason or "—"), ("Role", f"{role.name} — {role.id}")])
            try:
                await modlog_helper.send_modlog(self.bot, interaction.guild, "Mute", interaction.user, member, reason, extra=f"Role: {role.name} — {role.id}")
            except Exception:
                pass
        except Exception as e:
            await interaction.response.send_message(f"Error muting member: {e}", ephemeral=True)

    @discord.app_commands.command(name="unmute", description="Unmute a member")
    @discord.app_commands.checks.has_permissions(manage_roles=True)
    async def unmute_slash(self, interaction: discord.Interaction, member: discord.Member, reason: Optional[str] = None):
        role = discord.utils.get(interaction.guild.roles, name="Muted")
        if role is None:
            await interaction.response.send_message("Muted role not found.", ephemeral=True)
            return
        try:
            await member.remove_roles(role, reason=reason)
            await self._send_confirmation_interaction(interaction, "Member Unmuted", f"Unmuted {member.mention}", [("Reason", reason or "—")])
            try:
                await modlog_helper.send_modlog(self.bot, interaction.guild, "Unmute", interaction.user, member, reason, extra=f"Role: {role.name} — {role.id}")
            except Exception:
                pass
        except Exception as e:
            await interaction.response.send_message(f"Error unmuting member: {e}", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))