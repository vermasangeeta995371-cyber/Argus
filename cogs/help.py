from __future__ import annotations
import discord
from discord.ext import commands
import discord.app_commands
from typing import List, Optional, Dict, Any
import math
import datetime
import db  # uses the get_guild_locale helper added earlier

# Small localization map: extend as needed
_LOCALE_TEXT = {
    "en": {
        "help_title": "{} Help — {}",
        "footer_general": "{} • Page {}/{}",
        "no_commands": "No commands found for this category.",
        "command_not_found": "Command not found: {}",
        "usage_prefix": "Prefix: `c?{name} {signature}`",
        "usage_slash": "Slash: `/{name}` (use options shown in client)",
        "aliases": "Aliases: {}",
        "cooldown": "Cooldown: {}",
        "permissions": "Permissions: {}",
        "examples": "Examples: {}",
        "short_mode_notice": "(short mode)",
        "help_query_title": "Help — {}",
        "help_query_field_desc": "Description",
        "help_query_field_usage": "Usage",
        "help_query_field_more": "More",
        "jump_prompt": "Enter a page number (e.g. 3) or category name (e.g. Economy).",
        "jump_invalid": "Invalid page or category: {}",
        "jump_success": "Jumped to page {}/{}.",
    },
    "es": {
        "help_title": "{} Ayuda — {}",
        "footer_general": "{} • Página {}/{}",
        "no_commands": "No se encontraron comandos para esta categoría.",
        "command_not_found": "Comando no encontrado: {}",
        "usage_prefix": "Prefijo: `c?{name} {signature}`",
        "usage_slash": "Slash: `/{name}` (use las opciones mostradas en el cliente)",
        "aliases": "Aliases: {}",
        "cooldown": "Enfriamiento: {}",
        "permissions": "Permisos: {}",
        "examples": "Ejemplos: {}",
        "short_mode_notice": "(modo corto)",
        "help_query_title": "Ayuda — {}",
        "help_query_field_desc": "Descripción",
        "help_query_field_usage": "Uso",
        "help_query_field_more": "Más",
        "jump_prompt": "Ingrese un número de página (ej. 3) o el nombre de la categoría (ej. Economía).",
        "jump_invalid": "Página o categoría inválida: {}",
        "jump_success": "Saltado a la página {}/{}.",
    },
}


class JumpModal(discord.ui.Modal):
    """Modal to accept a page number or category name to jump to."""

    page_or_category = discord.ui.TextInput(
        label="Page number or Category",
        placeholder="e.g. 3  OR  Economy",
        required=True,
        max_length=100,
    )

    def __init__(self, view: "PageView", locale_text: Dict[str, str]):
        super().__init__(title="Jump to page")
        self.parent_view = view
        self.locale_text = locale_text

    async def on_submit(self, interaction: discord.Interaction):
        query = self.page_or_category.value.strip()
        pages = self.parent_view.pages
        total = len(pages)
        target_index: Optional[int] = None

        # Try numeric page (1-based)
        if query.isdigit():
            n = int(query)
            if 1 <= n <= total:
                target_index = n - 1
            else:
                await interaction.response.send_message(self.locale_text["jump_invalid"].format(query), ephemeral=True)
                return
        else:
            # Try to match category name in page titles (case-insensitive)
            q = query.lower()
            for i, embed in enumerate(pages):
                title = (embed.title or "").lower()
                # strip emoji and "help —" parts: just check substring
                if q in title:
                    target_index = i
                    break
            if target_index is None:
                await interaction.response.send_message(self.locale_text["jump_invalid"].format(query), ephemeral=True)
                return

        # Set view index and edit the message
        self.parent_view.index = target_index
        try:
            # update stored message (view.message should be set)
            await self.parent_view.message.edit(embed=self.parent_view.pages[self.parent_view.index], view=self.parent_view)
        except Exception:
            # fallback: try editing original response
            try:
                await interaction.response.edit_message(embed=self.parent_view.pages[self.parent_view.index], view=self.parent_view)
            except Exception:
                pass

        await interaction.response.send_message(self.locale_text["jump_success"].format(self.parent_view.index + 1, total), ephemeral=True)


class PageView(discord.ui.View):
    def __init__(self, pages: List[discord.Embed], author_id: int, timeout: int = 180):
        super().__init__(timeout=timeout)
        self.pages = pages
        self.index = 0
        self.author_id = author_id
        self.message: Optional[discord.Message] = None  # will be set after sending

    async def send_initial(self, ctx_or_interaction):
        # Send the first page and store the message object for later editing
        if isinstance(ctx_or_interaction, discord.Interaction):
            await ctx_or_interaction.response.send_message(embed=self.pages[0], view=self, ephemeral=True)
            self.message = await ctx_or_interaction.original_response()
            return self.message
        else:
            self.message = await ctx_or_interaction.send(embed=self.pages[0], view=self)
            return self.message

    async def update_message(self, interaction: discord.Interaction):
        # Re-edit stored message; if not set try to edit via interaction
        if self.message:
            await self.message.edit(embed=self.pages[self.index], view=self)
            await interaction.response.defer()
        else:
            await interaction.response.edit_message(embed=self.pages[self.index], view=self)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This help session isn't for you. Run help to open your own.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="◀ Previous", style=discord.ButtonStyle.secondary, custom_id="help_prev")
    async def previous(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.index = (self.index - 1) % len(self.pages)
        await self.update_message(interaction)

    @discord.ui.button(label="Jump", style=discord.ButtonStyle.primary, custom_id="help_jump")
    async def jump(self, interaction: discord.Interaction, button: discord.ui.Button):
        # open modal to accept page number or category
        # fetch locale text for the guild (best-effort)
        guild = interaction.guild
        locale = "en"
        try:
            if guild:
                locale = await db.get_guild_locale(guild.id)
        except Exception:
            locale = "en"
        locale_text = _LOCALE_TEXT.get(locale, _LOCALE_TEXT["en"])
        modal = JumpModal(self, locale_text)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.secondary, custom_id="help_next")
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.index = (self.index + 1) % len(self.pages)
        await self.update_message(interaction)


class Help(commands.Cog):
    """Auto-generated help: per-cog pages, command lookup, short/compact mode, and jump-to-page."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _build_pages_auto(self, guild: discord.Guild, short_mode: bool = False) -> List[discord.Embed]:
        """
        Auto-generate one embed per loaded cog. Each embed lists that cog's prefix commands and app (slash) commands.
        short_mode: produce compact lines instead of detailed fields.
        """
        locale = await db.get_guild_locale(guild.id) if guild else "en"
        texts = _LOCALE_TEXT.get(locale, _LOCALE_TEXT["en"])

        now = datetime.datetime.datetime.utcnow()
        pages: List[discord.Embed] = []

        # Collect slash commands per cog
        slash_commands_by_cog: Dict[str, List[discord.app_commands.AppCommand]] = {}
        for appcmd in self.bot.tree.walk_commands():
            cogname = getattr(appcmd, "cog_name", "Global") or "Global"
            slash_commands_by_cog.setdefault(cogname, []).append(appcmd)

        # Collect prefix commands per cog
        prefix_by_cog: Dict[str, List[commands.Command]] = {}
        for cmd in sorted(self.bot.commands, key=lambda c: (c.cog_name or "NoCog", c.name)):
            cogname = cmd.cog_name or "NoCog"
            prefix_by_cog.setdefault(cogname, []).append(cmd)

        # Combine cogs
        all_cogs = sorted(set(list(prefix_by_cog.keys()) + list(slash_commands_by_cog.keys())))

        # Visual mapping for default icons/colors
        mapping = {
            "NoCog": ("🔧", discord.Color.green(), "Miscellaneous"),
            "Utility": ("🛠️", discord.Color.green(), "Utility"),
            "Moderation": ("🔨", discord.Color.red(), "Moderation"),
            "Economy": ("💰", discord.Color.gold(), "Economy"),
            "Shop": ("🏪", discord.Color.purple(), "Shop"),
            "Market": ("🧾", discord.Color.dark_teal(), "Marketplace"),
            "MiniGames": ("🎰", discord.Color.dark_orange(), "MiniGames"),
            "AFK": ("🛌", discord.Color.teal(), "AFK"),
            "Help": ("📘", discord.Color.blurple(), "Help"),
            "Global": ("🌐", discord.Color.greyple(), "Global Commands"),
        }

        for idx, cogname in enumerate(all_cogs, start=1):
            # pick visual style
            emoji, color, footer = mapping.get(cogname, ("📘", discord.Color.blurple(), cogname))
            title = texts["help_title"].format(emoji, cogname)
            embed = discord.Embed(title=title, color=color, timestamp=now)

            embed.set_footer(text=texts["footer_general"].format(footer, idx, len(all_cogs)))

            prefix_cmds = prefix_by_cog.get(cogname, [])
            slash_cmds = slash_commands_by_cog.get(cogname, [])

            if not prefix_cmds and not slash_cmds:
                embed.add_field(name="\u200b", value=texts["no_commands"], inline=False)
                pages.append(embed)
                continue

            if short_mode:
                lines: List[str] = []
                for c in prefix_cmds:
                    aliases = f" (aliases: {', '.join(c.aliases)})" if getattr(c, "aliases", []) else ""
                    sig = getattr(c, "signature", "")
                    short_desc = (c.short_doc or c.help or "").split("\n")[0]
                    lines.append(f"c?{c.name} {sig}{aliases} — {short_desc}")
                for ac in slash_cmds:
                    lines.append(f"/{ac.name} — {ac.description or ''}")
                embed.add_field(name="Commands", value="\n".join(lines)[:1024] or texts["no_commands"], inline=False)
            else:
                for c in prefix_cmds:
                    sig = getattr(c, "signature", "")
                    desc = c.help or c.short_doc or ""
                    aliases = ", ".join(c.aliases) if getattr(c, "aliases", None) else ""
                    val = f"{texts['usage_prefix'].format(name=c.name, signature=sig)}\n{desc}"
                    if aliases:
                        val += f"\n{texts['aliases'].format(aliases)}"
                    embed.add_field(name=f"c?{c.name}", value=val[:1024], inline=False)
                for ac in slash_cmds:
                    desc = ac.description or ""
                    embed.add_field(name=f"/{ac.name}", value=desc[:1024], inline=False)

            pages.append(embed)

        return pages

    async def _find_command(self, query: str) -> Optional[Dict[str, Any]]:
        """
        Search prefix and slash commands by name or alias (case-insensitive).
        Returns a dict with info or None.
        """
        q = query.lower()
        # Search prefix commands
        for cmd in self.bot.commands:
            if cmd.name.lower() == q or q in [a.lower() for a in getattr(cmd, "aliases", [])]:
                return {"type": "prefix", "command": cmd}
        # Search slash commands
        for ac in self.bot.tree.walk_commands():
            if getattr(ac, "name", "").lower() == q:
                return {"type": "slash", "command": ac}
        return None

    def _format_command_detail(self, found: Dict[str, Any], locale_text: Dict[str, str]) -> discord.Embed:
        now = datetime.datetime.datetime.utcnow()
        typ = found["type"]
        cmd = found["command"]
        if typ == "prefix":
            name = cmd.name
            sig = getattr(cmd, "signature", "")
            desc = cmd.help or cmd.short_doc or "No description."
            aliases = ", ".join(cmd.aliases) if getattr(cmd, "aliases", None) else "—"
            embed = discord.Embed(title=locale_text["help_query_title"].format(name), color=discord.Color.blue(), timestamp=now)
            embed.add_field(name=locale_text["help_query_field_desc"], value=desc or "—", inline=False)
            embed.add_field(name=locale_text["help_query_field_usage"], value=locale_text["usage_prefix"].format(name=name, signature=sig), inline=False)
            embed.add_field(name=locale_text["help_query_field_more"], value=f"{locale_text['aliases'].format(aliases)}", inline=False)
            return embed
        else:
            name = getattr(cmd, "name", "")
            desc = getattr(cmd, "description", "") or "No description."
            embed = discord.Embed(title=locale_text["help_query_title"].format(name), color=discord.Color.blue(), timestamp=now)
            embed.add_field(name=locale_text["help_query_field_desc"], value=desc or "—", inline=False)
            embed.add_field(name=locale_text["help_query_field_usage"], value=locale_text["usage_slash"].format(name=name), inline=False)
            # show options if available
            opts = []
            try:
                for p in getattr(cmd, "parameters", []):
                    opts.append(f"{p.name}: {getattr(p, 'description', '')}")
            except Exception:
                pass
            if opts:
                embed.add_field(name="Options", value="\n".join(opts), inline=False)
            return embed

    # Prefix: c?help [query] or c?help short
    @commands.command(name="help")
    async def help_command(self, ctx: commands.Context, *, query: Optional[str] = None):
        """c?help [command_or_category] — show help. Use 'short' to view compact mode."""
        guild = ctx.guild
        if guild is None:
            await ctx.send("Help works in servers.")
            return

        locale = await db.get_guild_locale(guild.id)
        texts = _LOCALE_TEXT.get(locale, _LOCALE_TEXT["en"])

        # Short/compact mode
        short_mode = False
        if query and query.strip().lower() == "short":
            short_mode = True
            query = None

        if query:
            # Quick lookup
            found = await self._find_command(query.strip())
            if not found:
                await ctx.send(texts["command_not_found"].format(query))
                return
            embed = self._format_command_detail(found, texts)
            await ctx.send(embed=embed)
            return

        pages = await self._build_pages_auto(guild, short_mode=short_mode)
        view = PageView(pages, ctx.author.id)
        await view.send_initial(ctx)

    # Jump helper: prefix command that opens help starting at a target page or category
    @commands.command(name="help_goto", aliases=["help_goto", "helpgoto", "helpgoto"])
    async def help_goto(self, ctx: commands.Context, *, query: str):
        """c?help goto <page|category> — open help starting at a page number or category name."""
        guild = ctx.guild
        if guild is None:
            await ctx.send("This command works in servers.")
            return

        pages = await self._build_pages_auto(guild, short_mode=False)
        # try numeric page
        q = query.strip()
        target_index: Optional[int] = None
        if q.isdigit():
            n = int(q)
            if 1 <= n <= len(pages):
                target_index = n - 1
        else:
            qlow = q.lower()
            for i, embed in enumerate(pages):
                title = (embed.title or "").lower()
                if qlow in title:
                    target_index = i
                    break

        if target_index is None:
            locale = await db.get_guild_locale(guild.id)
            texts = _LOCALE_TEXT.get(locale, _LOCALE_TEXT["en"])
            await ctx.send(texts["jump_invalid"].format(query))
            return

        view = PageView(pages, ctx.author.id)
        view.index = target_index
        await view.send_initial(ctx)
        # immediately edit to desired page (send_initial sends page 0 by default)
        if view.message:
            await view.message.edit(embed=view.pages[view.index], view=view)

    # Slash: /help (for query) already exists; add a slash "jump" command
    @discord.app_commands.command(name="help_jump", description="Open help at a page or category (jump).")
    @discord.app_commands.describe(page="Page number to open", category="Category name to open")
    async def help_jump(self, interaction: discord.Interaction, page: Optional[int] = None, category: Optional[str] = None):
        """
        Slash helper to open full help starting at a specified page number or category.
        Usage: /help_jump page:3  OR  /help_jump category:Economy
        """
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        if guild is None:
            await interaction.followup.send("This command works in servers only.", ephemeral=True)
            return

        pages = await self._build_pages_auto(guild, short_mode=False)
        target_index: Optional[int] = None
        if page is not None:
            if 1 <= page <= len(pages):
                target_index = page - 1
        elif category:
            qlow = category.strip().lower()
            for i, embed in enumerate(pages):
                title = (embed.title or "").lower()
                if qlow in title:
                    target_index = i
                    break

        if target_index is None:
            locale = await db.get_guild_locale(guild.id)
            texts = _LOCALE_TEXT.get(locale, _LOCALE_TEXT["en"])
            await interaction.followup.send(texts["jump_invalid"].format(page or category), ephemeral=True)
            return

        view = PageView(pages, interaction.user.id)
        # send the first page and store the message
        await view.send_initial(interaction)
        # set to target and edit
        view.index = target_index
        if view.message:
            await view.message.edit(embed=view.pages[view.index], view=view)

    # Admin: set locale for guild
    @commands.group(name="helplang", invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def helplang(self, ctx: commands.Context):
        await ctx.send("Usage: c?helplang set <locale> | c?helplang show")

    @helplang.command(name="set")
    @commands.has_permissions(manage_guild=True)
    async def helplang_set(self, ctx: commands.Context, locale: str):
        """c?helplang set en|es — set guild help locale (admin)"""
        locale = locale.lower()
        if locale not in _LOCALE_TEXT:
            await ctx.send("Unsupported locale. Supported: " + ", ".join(_LOCALE_TEXT.keys()))
            return
        await db.set_guild_locale(ctx.guild.id, locale)
        await ctx.send(f"Set help locale to {locale}.")

    @helplang.command(name="show")
    @commands.has_permissions(manage_guild=True)
    async def helplang_show(self, ctx: commands.Context):
        locale = await db.get_guild_locale(ctx.guild.id)
        await ctx.send(f"Guild help locale: {locale}")


async def setup(bot: commands.Bot):
    await bot.add_cog(Help(bot))