import os
import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

intents = discord.Intents.default()
intents.message_content = True

class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        # Load cogs here
        await self.load_extension("cogs.ping")
        await self.load_extension("cogs.starboard")

        print("Cogs loaded and slash commands synced.")

bot = MyBot()

@bot.event
async def on_ready():
    print(f"Bot is ready. Logged in as {bot.user}")

bot.run(os.getenv("DISCORD_TOKEN").strip())
