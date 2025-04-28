# cogs/ping.py
import discord
from discord.ext import commands
from discord import app_commands

class Ping(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="ping", description="Shows the bot's latency!")
    async def ping(self, interaction: discord.Interaction):
        latency = round(self.bot.latency * 1000)
        await interaction.response.send_message(f"🏓 Latency: {latency}ms")

async def setup(bot):
    await bot.add_cog(Ping(bot))
