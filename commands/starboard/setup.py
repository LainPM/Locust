# commands/starboard/setup.py
import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional, List

class StarboardSetupCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @app_commands.command(
        name="setup_starboard",
        description="Set up or update the starboard system"
    )
    @app_commands.describe(
        channels="Channels to monitor for starred messages (#channel1 #channel2)",
        star_emoji="The emoji to use for starring (default: ⭐)",
        attachments_only="Only allow posts with attachments",
        auto_threads="Automatically create threads for posts",
        featured_channel="Channel to send starred posts to",
        threshold="Number of stars needed to feature a post (default: 3)"
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    async def setup_starboard(
        self,
        interaction: discord.Interaction,
        channels: str,
        star_emoji: Optional[str] = "⭐",
        attachments_only: Optional[bool] = False,
        auto_threads: Optional[bool] = False,
        featured_channel: Optional[discord.TextChannel] = None,
        threshold: Optional[int] = 3
    ):
        """Set up the starboard system"""
        await interaction.response.defer(ephemeral=True)
        
        # Check for admin permissions
        if not interaction.user.guild_permissions.administrator:
            return await interaction.followup.send("You need administrator permissions to set up the starboard.", ephemeral=True)
        
        # Get the starboard system
        starboard_system = await self.bot.get_system("StarboardSystem")
        if not starboard_system:
            return await interaction.followup.send("Starboard system is not available.", ephemeral=True)
        
        # Parse the channels input
        showcase_channel_ids = []
        showcase_channels_mentions = []
        
        # Split the input by spaces and process each part
        parts = channels.split()
        for part in parts:
            # Check if it's a channel mention
            if part.startswith("<#") and part.endswith(">"):
                try:
                    channel_id = int(part[2:-1])
                    channel = interaction.guild.get_channel(channel_id)
                    if channel and isinstance(channel, discord.TextChannel):
                        showcase_channel_ids.append(channel_id)
                        showcase_channels_mentions.append(channel.mention)
                except ValueError:
                    continue
        
        if not showcase_channel_ids:
            return await interaction.followup.send("Please provide at least one valid channel using #channel format.", ephemeral=True)
        
        # Validate the emoji
        if len(star_emoji.strip()) == 0:
            return await interaction.followup.send("Please provide a valid emoji for starring posts.", ephemeral=True)
        
        # Additional validation for thresholds
        if threshold is not None and threshold < 1:
            threshold = 1
        
        # Save settings to database
        guild_id = interaction.guild.id
        
        settings = {
            "guild_id": guild_id,
            "enabled": True,
            "showcase_channels": showcase_channel_ids,
            "star_emoji": star_emoji.strip(),
            "attachments_only": attachments_only,
            "auto_threads": auto_threads,
            "bot_react": True,  # Default to true for auto-reactions
            "updated_at": datetime.datetime.now().isoformat()
        }
        
        # Add featured channel and threshold if provided
        if featured_channel:
            settings["featured_channel_id"] = featured_channel.id
            settings["threshold"] = threshold or 3
        
        # Update settings
        await starboard_system.storage.update_settings(guild_id, settings)
        
        # Reload settings cache
        starboard_system.settings_cache[guild_id] = await starboard_system.storage.get_settings(guild_id)
        
        # Create confirmation message
        embed = discord.Embed(
            title="Starboard Setup Complete",
            description="The starboard system has been configured successfully.",
            color=discord.Color.gold(),
            timestamp=datetime.datetime.now()
        )
        
        embed.add_field(name="Showcase Channels", value="\n".join(showcase_channels_mentions), inline=False)
        embed.add_field(name="Star Emoji", value=star_emoji.strip(), inline=True)
        embed.add_field(name="Attachments Only", value="Yes" if attachments_only else "No", inline=True)
        embed.add_field(name="Auto Threads", value="Yes" if auto_threads else "No", inline=True)
        
        if featured_channel:
            embed.add_field(name="Featured Channel", value=featured_channel.mention, inline=True)
            embed.add_field(name="Star Threshold", value=str(threshold or 3), inline=True)
        else:
            embed.add_field(name="Featured Posts", value="Disabled (no featured channel set)", inline=False)
        
        await interaction.followup.send(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(StarboardSetupCommand(bot))
