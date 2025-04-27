import os
import sys
import logging
import discord
from discord import app_commands
from discord.ext import commands

# ─── Logging Configuration ─────────────────────────────────────────
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("bot.log", encoding="utf-8")
    ]
)                                                        # :contentReference[oaicite:8]{index=8}

# ─── Global Exception Hook ─────────────────────────────────────────
def handle_unhandled_exception(exc_type, exc_value, exc_tb):
    if issubclass(exc_type, KeyboardInterrupt):
        return sys.__excepthook__(exc_type, exc_value, exc_tb)
    logging.getLogger('bot').critical("Uncaught exception", exc_info=(exc_type, exc_value, exc_tb))

sys.excepthook = handle_unhandled_exception             # :contentReference[oaicite:9]{index=9}

# ─── Intents & Bot Setup ──────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True

class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix="!",
            intents=intents,
            application_id=int(os.getenv("APPLICATION_ID")),
            tree_cls=app_commands.CommandTree
        )
        self.GUILD_ID = int(os.getenv("GUILD_ID"))

    async def setup_hook(self):
        await self.tree.sync(guild=discord.Object(id=self.GUILD_ID))
        logging.getLogger('bot').info(f"Synced slash commands to guild {self.GUILD_ID}")

bot = MyBot()

# ─── Global Event Error ───────────────────────────────────────────
@bot.event
async def on_error(event_method, *args, **kwargs):
    logging.getLogger('discord').exception(f"Unhandled exception in {event_method}")  # :contentReference[oaicite:10]{index=10}

# ─── Slash‐Command Error ───────────────────────────────────────────
@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    logging.getLogger('discord.app_commands').exception(
        f"Error in slash command {interaction.command.name}"
    )                                                      # :contentReference[oaicite:11]{index=11}
    await interaction.response.send_message("❌ Something went wrong.", ephemeral=True)

# ─── Prefix/Hybrid Command Error ───────────────────────────────────
@bot.event
async def on_command_error(ctx, error):
    logger = logging.getLogger('discord.command')
    if hasattr(error, 'original'):
        logger.exception(f"Error in command {ctx.command}")   # :contentReference[oaicite:12]{index=12}
    else:
        logger.error(f"Error in command {ctx.command}: {error}")
    await ctx.send("❌ Command failed. Check logs.")

# ─── Example Slash Command ────────────────────────────────────────
@bot.tree.command(name="ping", description="Check responsiveness")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message("Pong!")

# ─── Run ─────────────────────────────────────────────────────────
bot.run(os.getenv("DISCORD_TOKEN"))
