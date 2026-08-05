import os
import asyncio
from dotenv import load_dotenv
import logging
import discord
from discord.ext import commands
from aiohttp import web

load_dotenv()
import db  # local db helper

TOKEN = os.getenv("DISCORD_TOKEN")
CLIENT_ID = os.getenv("CLIENT_ID")
GUILD_ID = os.getenv("GUILD_ID")  # optional, for guild-scoped command testing
HEALTHCHECK_PORT = int(os.getenv("PORT", os.getenv("HEALTHCHECK_PORT", "8080")))
HEALTHCHECK_HOST = os.getenv("HEALTHCHECK_HOST", "0.0.0.0")

if TOKEN is None:
    raise RuntimeError("DISCORD_TOKEN not set in environment")

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

# Accept mentions, "c?", and "C?" as prefixes (removed "!")
bot = commands.Bot(command_prefix=commands.when_mentioned_or("c?", "C?"),
                   intents=intents,
                   description="Example Python discord.py bot")

logger = logging.getLogger("discord")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter("%(asctime)s:%(levelname)s:%(name)s: %(message)s"))
logger.addHandler(handler)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    print("------")
    # Sync app commands
    try:
        if GUILD_ID:
            guild = discord.Object(id=int(GUILD_ID))
            await bot.tree.sync(guild=guild)
            print(f"Synced commands to guild {GUILD_ID}")
        else:
            await bot.tree.sync()
            print("Synced global commands")
    except Exception as e:
        print("Failed to sync commands:", e)

def load_cogs():
    cogs_dir = os.path.join(os.path.dirname(__file__), "cogs")
    for filename in os.listdir(cogs_dir):
        if filename.endswith(".py") and not filename.startswith("_"):
            ext = f"cogs.{filename[:-3]}"
            try:
                bot.load_extension(ext)
                print(f"Loaded extension: {ext}")
            except Exception as e:
                print(f"Failed to load extension {ext}: {e}")

async def healthcheck(request):
    return web.Response(text="OK", status=200)

async def start_healthcheck_server():
    app = web.Application()
    app.router.add_get("/health", healthcheck)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, HEALTHCHECK_HOST, HEALTHCHECK_PORT)
    await site.start()
    print(f"Healthcheck endpoint running on http://{HEALTHCHECK_HOST}:{HEALTHCHECK_PORT}/health")
    return runner

async def main():
    # Initialize DB
    await db.init_db()
    # Load cogs
    load_cogs()
    # Start healthcheck server
    runner = await start_healthcheck_server()
    try:
        # Start bot
        await bot.start(TOKEN)
    finally:
        await runner.cleanup()

if __name__ == "__main__":
    asyncio.run(main())