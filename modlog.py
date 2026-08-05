"""
Helper to send moderation embeds to the configured mod-log channel.
Includes moderator and target avatars and numeric IDs in the embed.
"""

from __future__ import annotations
import discord
import datetime
import db


async def send_modlog(bot: discord.Client | discord.AutoShardedClient | discord.ext.commands.Bot,
                      guild: discord.Guild,
                      action: str,
                      moderator: discord.abc.User | str,
                      target: discord.abc.User | str | None = None,
                      reason: str | None = None,
                      extra: str | None = None):
    """
    Send a mod log embed to configured channel for guild.
    - bot: the bot instance
    - guild: guild object
    - action: e.g. "Kick", "Ban", "Warn"
    - moderator: user who performed action (Member/User or string)
    - target: the target user (Member/User or string)
    - reason: optional reason text
    - extra: optional extra text (e.g., duration, role changed)
    """
    chan_id = await db.get_modlog_channel(guild.id)
    if not chan_id:
        return
    channel = bot.get_channel(int(chan_id))
    if channel is None:
        return

    # Prepare moderator display values
    if hasattr(moderator, "display_name"):
        mod_name = moderator.display_name
    else:
        mod_name = str(moderator)

    mod_id = getattr(moderator, "id", None)
    mod_avatar = None
    if hasattr(moderator, "display_avatar"):
        try:
            mod_avatar = moderator.display_avatar.url
        except Exception:
            mod_avatar = None

    # Prepare target display values
    if target is not None and hasattr(target, "display_name"):
        tgt_name = target.display_name
    else:
        tgt_name = str(target) if target is not None else "—"

    tgt_id = getattr(target, "id", None)
    tgt_avatar = None
    if target is not None and hasattr(target, "display_avatar"):
        try:
            tgt_avatar = target.display_avatar.url
        except Exception:
            tgt_avatar = None

    embed = discord.Embed(title=f"Moderation — {action}",
                          color=discord.Color.dark_red(),
                          timestamp=datetime.datetime.utcnow())

    # Use moderator as embed author with avatar if available
    author_name = f"{mod_name}"
    if mod_id is not None:
        author_name += f" — {mod_id}"
    if mod_avatar:
        embed.set_author(name=author_name, icon_url=mod_avatar)
    else:
        embed.set_author(name=author_name)

    # Add target info as a field and set thumbnail to target avatar if available
    if target is not None:
        target_display = f"{tgt_name}"
        if tgt_id is not None:
            target_display += f" — {tgt_id}"
        embed.add_field(name="Target", value=target_display, inline=True)
        if tgt_avatar:
            embed.set_thumbnail(url=tgt_avatar)
    else:
        embed.add_field(name="Target", value="—", inline=True)

    # Add reason and extra if present
    if reason:
        embed.add_field(name="Reason", value=reason, inline=False)
    if extra:
        embed.add_field(name="Details", value=extra, inline=False)

    # Footer with guild and action time
    embed.set_footer(text=f"{guild.name} • {action}")

    try:
        await channel.send(embed=embed)
    except Exception:
        # Best-effort: do not raise so moderation actions are not blocked by logging failures
        return