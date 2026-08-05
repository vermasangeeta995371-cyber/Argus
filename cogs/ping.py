from discord.ext import commands
import discord

class Ping(commands.Cog):
    """Simple ping/hello commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="ping")
    async def ping(self, ctx: commands.Context):
        """Prefix command: !ping"""
        await ctx.send("Pong! :ping_pong:")

    # Slash command inside a cog using app_commands
    @discord.app_commands.command(name="hello", description="Say hello")
    async def hello(self, interaction: discord.Interaction):
        await interaction.response.send_message(f"Hello, {interaction.user.mention}!")

async def setup(bot: commands.Bot):
    await bot.add_cog(Ping(bot))