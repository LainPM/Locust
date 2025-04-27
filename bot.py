import os
import sys
import discord
from discord import app_commands
from discord.ext import commands

# QUICK CHECK: fail fast if token isn’t set
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    print("❌ DISCORD_TOKEN env var is missing or empty. Exiting.")
    sys.exit(1)

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
        print(f"✅ Synced slash commands to guild {self.GUILD_ID}")

bot = MyBot()

@bot.tree.command(name="ping", description="Replies with Pong!")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message("Pong!")

bot.run(TOKEN)
