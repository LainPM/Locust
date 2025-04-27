import os
import sys
import logging
import discord
from discord import app_commands
from discord.ext import commands

# ─── Logging Configuration ─────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
    ]
)

# ─── Bot Setup ──────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True

class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix="!",               # unused but required
            intents=intents,
            application_id=int(os.getenv("APPLICATION_ID")),
            tree_cls=app_commands.CommandTree
        )
        self.GUILD_ID = int(os.getenv("GUILD_ID"))

    async def setup_hook(self):
        # 1. Clear old commands for the guild
        await self.tree.clear_commands(guild=discord.Object(id=self.GUILD_ID))
        # 2. Sync current code’s slash commands
        await self.tree.sync(guild=discord.Object(id=self.GUILD_ID))
        print(f"✅ Cleared old commands and synced to guild {self.GUILD_ID}")

bot = MyBot()

# ─── Event: Bot Ready ────────────────────────────────────────────────
@bot.event
async def on_ready():
    print(f"Bot is ready. Logged in as {bot.user} (ID: {bot.user.id})")

# ─── Global Slash‐Command Error Handler ──────────────────────────────
@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    logging.getLogger('discord.app_commands').exception(
        f"Error in slash command {interaction.command.name}: {error}"
    )
    await interaction.response.send_message("❌ Something went wrong.", ephemeral=True)

# ─── Example Slash Commands ─────────────────────────────────────────
@bot.tree.command(name="ping", description="Replies with Pong!")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message("🏓 Pong!")

@bot.tree.command(name="echo", description="Echoes your message back")
@app_commands.describe(text="Text to echo back")
async def echo(interaction: discord.Interaction, text: str):
    await interaction.response.send_message(text)

# ─── Run the Bot ────────────────────────────────────────────────────
if __name__ == "__main__":
    token = os.getenv("DISCORD_TOKEN", "").strip()
    if not token:
        print("❌ DISCORD_TOKEN env var is missing or empty. Exiting.")
        sys.exit(1)
    bot.run(token)
