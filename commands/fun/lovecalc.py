# commands/fun/lovecalc.py
import discord
from discord import app_commands
from discord.ext import commands

class LoveCalcCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @app_commands.command(
        name="lovecalc",
        description="Calculate the love compatibility between two users"
    )
    async def love_calculator(
        self,
        interaction: discord.Interaction,
        user1: discord.User,
        user2: discord.User
    ):
        """Calculate love compatibility between two users"""
        await interaction.response.defer()
        
        # Get the fun system
        fun_system = await self.bot.get_system("FunSystem")
        if not fun_system:
            return await interaction.followup.send("Fun system is not available.")
        
        # Calculate compatibility and create card
        result, file = await fun_system.lovecalc.calculate(user1, user2)
        
        # Create embed and send response
        embed = discord.Embed(
            title="❤️ Love Calculator ❤️",
            description=result,
            color=discord.Color.from_rgb(255, 105, 180)  # Pink
        )
        
        if file:
            embed.set_image(url="attachment://lovecalc.png")
            await interaction.followup.send(embed=embed, file=file)
        else:
            await interaction.followup.send(embed=embed)

async def setup(bot):
    await bot.add_cog(LoveCalcCommand(bot))
