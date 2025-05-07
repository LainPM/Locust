# commands/leveling/rank.py
import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional

class RankCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @app_commands.command(
        name="rank",
        description="Show your current rank and level"
    )
    async def rank(
        self, 
        interaction: discord.Interaction, 
        user: Optional[discord.User] = None
    ):
        """Show your current rank and level"""
        await interaction.response.defer()
        
        # Get the leveling system
        leveling_system = await self.bot.get_system("LevelingSystem")
        if not leveling_system:
            await interaction.followup.send("Leveling system is not available.")
            return
        
        # Get target user (default to command user)
        target_user = user or interaction.user
        
        # Get settings
        settings = await leveling_system.get_settings(interaction.guild.id)
        if not settings.get("enabled", False):
            await interaction.followup.send("The leveling system is disabled in this server.")
            return
        
        # Get user data
        user_data = await leveling_system.storage.get_user_data(target_user.id, interaction.guild.id)
        
        # Get user rank
        rank = await leveling_system.storage.get_user_rank(target_user.id, interaction.guild.id)
        
        try:
            # Create rank card
            rank_card = await leveling_system.renderer.create_rank_card(
                target_user, user_data, rank, interaction.guild
            )
            
            await interaction.followup.send(file=rank_card)
        except Exception as e:
            # Fallback to text response if image creation fails
            print(f"Error generating rank card: {e}")
            
            level = user_data["level"]
            xp = user_data["xp"]
            current_xp = leveling_system.storage.calculate_xp_for_level(level)
            next_level_xp = leveling_system.storage.calculate_xp_for_level(level + 1)
            
            # Calculate progress to next level
            total_needed = next_level_xp - current_xp
            current_progress = xp - current_xp
            progress_percent = (current_progress / total_needed) * 100 if total_needed > 0 else 100
            
            embed = discord.Embed(
                title=f"{target_user.display_name}'s Rank",
                description=f"**Rank:** #{rank}\n"
                            f"**Level:** {level}\n"
                            f"**XP:** {xp} ({current_progress}/{total_needed})\n"
                            f"**Progress:** {int(progress_percent)}%\n"
                            f"**Messages:** {user_data.get('messages', 0)}",
                color=discord.Color.blue()
            )
            
            embed.set_thumbnail(url=target_user.display_avatar.url)
            embed.set_footer(text=f"Requested by {interaction.user.display_name}", 
                            icon_url=interaction.user.display_avatar.url)
            
            await interaction.followup.send(embed=embed)

async def setup(bot):
    await bot.add_cog(RankCommand(bot))
