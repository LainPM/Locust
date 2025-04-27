import os
import sys
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

# ─── Environment Variables ───────────────────────────────────────────
TOKEN = os.getenv("DISCORD_TOKEN", "").strip()
APP_ID = os.getenv("APPLICATION_ID")
GUILD_ID = os.getenv("GUILD_ID")

if not TOKEN or not APP_ID or not GUILD_ID:
    print("❌ One of DISCORD_TOKEN, APPLICATION_ID or GUILD_ID is missing.")
    sys.exit(1)

# ─── Intents ─────────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True

# ─── Bot Definition ───────────────────────────────────────────────────
class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix="!",
            intents=intents,
            application_id=int(APP_ID),
            tree_cls=app_commands.CommandTree
        )
        self.GUILD = discord.Object(id=int(GUILD_ID))

    async def setup_hook(self):
        # 1) Load your cogs so their @app_commands get registered in tree
        await self.load_extension("cogs.ping")        

        # 2) Clear any existing slash commands in this guild
        await self.tree.clear_commands(guild=self.GUILD)

        # 3) Sync everything (your code + cogs) as slash commands
        await self.tree.sync(guild=self.GUILD)

        print(f"✅ Loaded cogs, cleared old commands, and synced to guild {GUILD_ID}")

bot = MyBot()

# ─── Ready Event ──────────────────────────────────────────────────────
@bot.event
async def on_ready():
    print(f"Bot ready: {bot.user} (ID: {bot.user.id})")

# ─── One‐Off Prefix Command ───────────────────────────────────────────
@bot.command(name="clear_commands", help="Clear & re-sync slash commands")
@commands.is_owner()
async def clear_commands(ctx):
    await bot.tree.clear_commands(guild=bot.GUILD)
    await bot.tree.sync(guild=bot.GUILD)
    await ctx.send("✅ Commands cleared and re-synced.")

# ─── Example Inline Slash Command ────────────────────────────────────
@bot.tree.command(name="echo", description="Echo a message")
@app_commands.describe(text="Text to echo back")
async def echo(interaction: discord.Interaction, text: str):
    await interaction.response.send_message(text)

# ─── Run ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    bot.run(TOKEN)
