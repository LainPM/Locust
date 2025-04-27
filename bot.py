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
        await self.load_extension("cogs.example")
        print("Cogs loaded and slash commands synced.")

bot = MyBot()

# ─── One-Off Clear Command ───────────────────────────────────────────
@bot.command(name="clear_commands", help="Clears & re-syncs slash commands in this guild")
@commands.is_owner()
async def clear_commands(ctx):
    # Clear all existing guild commands…
    await bot.tree.clear_commands(guild=discord.Object(id=ctx.guild.id))  # :contentReference[oaicite:0]{index=0}
    # …then re-sync your current definitions
    await bot.tree.sync(guild=discord.Object(id=ctx.guild.id))           # :contentReference[oaicite:1]{index=1}
    await ctx.send("✅ Commands cleared and re-synced.")

@bot.event
async def on_ready():
    print(f"Bot is ready. Logged in as {bot.user}")

bot.run(os.getenv("DISCORD_TOKEN").strip())
