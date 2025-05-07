# commands/basic/ping.py
import discord
from discord import app_commands
from discord.ext import commands

class PingCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @app_commands.command(name="ping", description="Shows the bot's latency!")
    async def ping(self, interaction: discord.Interaction):
        # Get the basic system
        basic_system = await self.bot.get_system("BasicSystem")
        if not basic_system:
            latency = round(self.bot.latency * 1000)
        else:
            latency = await basic_system.get_latency()
        
        # Create embed
        embed = discord.Embed(
            description=f"**Latency:** `{latency}ms`",
            color=discord.Color.from_rgb(255, 105, 180)  # Pink color
        )
        
        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(PingCommand(bot))
