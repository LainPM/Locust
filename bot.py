import os
import sys
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

# ─── Validate Env Vars ───────────────────────────────────────────────
TOKEN = os.getenv("DISCORD_TOKEN", "").strip()
APP_ID = os.getenv("APPLICATION_ID")
GUILD_ID = os.getenv("GUILD_ID")

if not TOKEN:
    print("❌ DISCORD_TOKEN is missing. Exiting.")
    sys.exit(1)
if not APP_ID or not GUILD_ID:
    print("❌ APPLICATION_ID or GUILD_ID missing. Exiting.")
    sys.exit(1)

# ─── Intents ─────────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True  # required for prefix commands & content access :contentReference[oaicite:4]{index=4}

# ─── Bot Definition ───────────────────────────────────────────────────
class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix="!",                    # still required but unused by slash :contentReference[oaicite:5]{index=5}
            intents=intents,
            application_id=int(APP_ID),
            tree_cls=app_commands.CommandTree     # ensure only one CommandTree is created :contentReference[oaicite:6]{index=6}
        )
        self.GUILD_ID = int(GUILD_ID)

    async def setup_hook(self):
        # 1) Clear all existing slash commands in this guild
        await self.tree.clear_commands(guild=discord.Object(id=self.GUILD_ID))  # un-register stale commands :contentReference[oaicite:7]{index=7}
        # 2) Sync only the commands defined in code
        await self.tree.sync(guild=discord.Object(id=self.GUILD_ID))            # register fresh commands :contentReference[oaicite:8]{index=8}
        # 3) Load your cogs (each cog’s setup() can also register commands)
        await self.load_extension("cogs.example")                                # load existing commands :contentReference[oaicite:9]{index=9}
        print(f"✅ Cleared & synced slash commands, then loaded cogs for guild {self.GUILD_ID}")

# ─── Instantiate & Run ─────────────────────────────────────────────────
bot = MyBot()

@bot.event
async def on_ready():
    print(f"Bot ready: {bot.user} (ID: {bot.user.id})")

# ─── One-Off Prefix Command to Clear & Re-Sync (if needed) ─────────────
@bot.command(name="clear_commands", help="Clear & re-sync slash commands in this guild")
@commands.is_owner()
async def clear_commands(ctx):
    await bot.tree.clear_commands(guild=discord.Object(id=ctx.guild.id))        # :contentReference[oaicite:10]{index=10}
    await bot.tree.sync(guild=discord.Object(id=ctx.guild.id))                  # :contentReference[oaicite:11]{index=11}
    await ctx.send("✅ Commands cleared and re-synced.")

# ─── Example Slash Commands ───────────────────────────────────────────────
@bot.tree.command(name="ping", description="Replies with Pong!")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message("🏓 Pong!")

@bot.tree.command(name="echo", description="Echoes your message")
@app_commands.describe(text="Text to echo back")
async def echo(interaction: discord.Interaction, text: str):
    await interaction.response.send_message(text)

# ─── Finally: Run ────────────────────────────────────────────────────────
bot.run(TOKEN)
