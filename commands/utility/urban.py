# commands/utility/urban.py
import discord
from discord import app_commands
from discord.ext import commands

class UrbanCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @app_commands.command(
        name="urban",
        description="Look up a word or phrase on Urban Dictionary"
    )
    @app_commands.describe(term="The term to look up")
    async def urban(
        self,
        interaction: discord.Interaction,
        term: str
    ):
        """Search for a term on Urban Dictionary"""
        await interaction.response.defer()
        
        # Get the utility system
        utility_system = await self.bot.get_system("UtilitySystem")
        if not utility_system:
            return await interaction.followup.send("Utility system is not available.")
        
        # Look up the term
        result = await utility_system.urban.lookup(term)
        
        if not result:
            await interaction.followup.send(f"No definitions found for **{term}**.")
            return
        
        # The urban module will handle pagination internally
        await utility_system.urban.send_result(interaction, result)

async def setup(bot):
    await bot.add_cog(UrbanCommand(bot))
