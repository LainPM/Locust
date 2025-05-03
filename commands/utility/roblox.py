# commands/utility/roblox.py
import discord
from discord import app_commands
from discord.ext import commands

class RobloxCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @app_commands.command(
        name="roblox",
        description="Look up a Roblox user by username or ID"
    )
    @app_commands.describe(username="Roblox username or user ID")
    async def roblox_lookup(
        self,
        interaction: discord.Interaction,
        username: str
    ):
        """Look up a Roblox user by username or ID"""
        await interaction.response.defer()
        
        # Get the utility system
        utility_system = await self.bot.get_system("UtilitySystem")
        if not utility_system:
            return await interaction.followup.send("Utility system is not available.")
        
        # Look up the user
        result, files = await utility_system.roblox.lookup_user(username)
        
        if not result:
            await interaction.followup.send(f"Could not find Roblox user with username/ID '{username}'.")
            return
        
        # Send the response
        await interaction.followup.send(embed=result, files=files)

    @app_commands.command(
        name="robloxgroup",
        description="Look up a Roblox group by ID"
    )
    @app_commands.describe(group_id="Roblox group ID")
    async def roblox_group_lookup(
        self,
        interaction: discord.Interaction,
        group_id: str
    ):
        """Look up a Roblox group by ID"""
        await interaction.response.defer()
        
        # Get the utility system
        utility_system = await self.bot.get_system("UtilitySystem")
        if not utility_system:
            return await interaction.followup.send("Utility system is not available.")
        
        # Look up the group
        result, file = await utility_system.roblox.lookup_group(group_id)
        
        if not result:
            await interaction.followup.send(f"Could not find Roblox group with ID '{group_id}'.")
            return
        
        # Send the response
        if file:
            await interaction.followup.send(embed=result, file=file)
        else:
            await interaction.followup.send(embed=result)

async def setup(bot):
    await bot.add_cog(RobloxCommand(bot))
