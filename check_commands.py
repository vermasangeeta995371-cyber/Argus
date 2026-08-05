import sys
import os
import asyncio
os.chdir(r'C:\Users\milan\OneDrive\Desktop\Full Stack\Argus')
sys.path.insert(0, os.getcwd())
import bot
async def m():
    await bot.load_cogs()
    names = sorted(c.name for c in bot.bot.commands)
    print(names)
    print('daily' in names, 'help' in names)
    print(list(bot.bot.extensions.keys()))
asyncio.run(m())
