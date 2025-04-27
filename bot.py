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
            application_id=os.getenv("APPLICATION_ID"),
        )
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        # For rapid testing, sync to a guild:
        # await self.tree.sync(guild=discord.Object(id=GUILD_ID))
        await self.tree.sync()  # Global sync :contentReference[oaicite:3]{index=3}

bot = MyBot()

@bot.tree.command(name="ping", description="Replies with Pong!")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message("Pong!")

@bot.tree.command(
    name="echo",
    description="Echoes your message back to you"
)
@app_commands.describe(text="The text to echo")
async def echo(interaction: discord.Interaction, text: str):
    await interaction.response.send_message(text)

bot.run(os.getenv("DISCORD_TOKEN"))
