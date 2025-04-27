import os
import discord
from discord import app_commands
from discord.ext import commands

intents = discord.Intents.default()
intents.message_content = True

class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix="!",
            intents=intents,
            application_id=int(os.getenv("APPLICATION_ID")),
            tree_cls=app_commands.CommandTree      # ← Use default tree_cls
        )
        self.GUILD_ID = int(os.getenv("GUILD_ID"))

    async def setup_hook(self):
        # sync only to your guild for instant slash updates
        await self.tree.sync(guild=discord.Object(id=self.GUILD_ID))
        print(f"Slash commands synced to guild {self.GUILD_ID}")

bot = MyBot()

@bot.tree.command(name="ping", description="Replies with Pong!")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message("Pong!")

bot.run(os.getenv("DISCORD_TOKEN"))
