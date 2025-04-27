import os
import discord
from discord.ext import commands

# 1. Configure intents
intents = discord.Intents.default()
intents.message_content = True

# 2. Create the bot with intents
bot = commands.Bot(
    command_prefix="!",
    intents=intents
)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user.name}")

@bot.command()
async def ping(ctx):
    await ctx.send("Pong!")

# 3. Run using the token from your environment
bot.run(os.getenv("DISCORD_TOKEN"))
