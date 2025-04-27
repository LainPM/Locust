import discord
from discord.ext import commands
from discord import app_commands

class Example(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="ping", description="Ping the bot.")
    async def ping(self, interaction: discord.Interaction):
        await interaction.response.send_message("🏓 Pong! ERWERRERER")

async def setup(bot):
    await bot.add_cog(Example(bot))
