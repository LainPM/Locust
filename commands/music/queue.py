import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional

class QueueCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @app_commands.command(
        name="queue",
        description="Show the current music queue"
    )
    @app_commands.describe(page="Page number to view")
    @app_commands.guild_only()
    async def queue(
        self,
        interaction: discord.Interaction,
        page: Optional[int] = 1
    ):
        """Show the current music queue"""
        await interaction.response.defer()
        
        # Get the music system
        music_system = await self.bot.get_system("MusicSystem")
        if not music_system:
            return await interaction.followup.send("Music system is not available.")
        
        guild_id = interaction.guild.id
        
        # Get the queue
        queue = await music_system.queue.get_queue(guild_id)
        
        if not queue and guild_id not in music_system.player.now_playing:
            return await interaction.followup.send("The queue is empty and nothing is playing.")
        
        # Calculate pages
        items_per_page = 10
        total_pages = max(1, (len(queue) + items_per_page - 1) // items_per_page)
        
        # Validate page number
        if page < 1 or page > total_pages:
            page = 1
        
        # Create embed
        embed = discord.Embed(title="Music Queue", color=discord.Color.blue())
        
        # Add now playing
        if guild_id in music_system.player.now_playing:
            now_playing = music_system.player.now_playing[guild_id]
            embed.add_field(
                name="Now Playing",
                value=f"[{now_playing['title']}]({now_playing['webpage_url']}) | {now_playing['duration']} | Requested by {now_playing['requester']}",
                inline=False
            )
        
        # Add queue items for current page
        start_idx = (page - 1) * items_per_page
        end_idx = min(start_idx + items_per_page, len(queue))
        
        if queue:
            queue_list = []
            for i in range(start_idx, end_idx):
                song = queue[i]
                queue_list.append(f"`{i+1}.` [{song['title']}]({song['webpage_url']}) | {song['duration']} | Requested by {song['requester']}")
            
            embed.add_field(
                name="Queue",
                value="\n".join(queue_list) if queue_list else "No songs in queue",
                inline=False
            )
        
        # Add page info
        embed.set_footer(text=f"Page {page}/{total_pages} | {len(queue)} songs in queue")
        
        await interaction.followup.send(embed=embed)
    
    @app_commands.command(
        name="skip",
        description="Skip the current song"
    )
    @app_commands.guild_only()
    async def skip(
        self,
        interaction: discord.Interaction
    ):
        """Skip the current song"""
        await interaction.response.defer()
        
        # Get the music system
        music_system = await self.bot.get_system("MusicSystem")
        if not music_system:
            return await interaction.followup.send("Music system is not available.")
        
        guild_id = interaction.guild.id
        voice_client = discord.utils.get(self.bot.voice_clients, guild=interaction.guild)
        
        if not voice_client or not voice_client.is_connected():
            return await interaction.followup.send("I'm not connected to a voice channel.")
        
        if not voice_client.is_playing():
            return await interaction.followup.send("Nothing is playing right now.")
        
        # Get the current song title before stopping
        now_playing = None
        if guild_id in music_system.player.now_playing:
            now_playing = music_system.player.now_playing[guild_id]['title']
        
        # Stop the current playback (will automatically play next song)
        voice_client.stop()
        
        # Send confirmation
        if now_playing:
            await interaction.followup.send(f"Skipped: {now_playing}")
        else:
            await interaction.followup.send("Skipped the current song.")
    
    @app_commands.command(
        name="remove",
        description="Remove a song from the queue"
    )
    @app_commands.describe(position="Position of the song to remove")
    @app_commands.guild_only()
    async def remove(
        self,
        interaction: discord.Interaction,
        position: int
    ):
        """Remove a song from the queue"""
        await interaction.response.defer()
        
        # Get the music system
        music_system = await self.bot.get_system("MusicSystem")
        if not music_system:
            return await interaction.followup.send("Music system is not available.")
        
        guild_id = interaction.guild.id
        
        # Check if position is valid
        queue = await music_system.queue.get_queue(guild_id)
        if not queue:
            return await interaction.followup.send("The queue is empty.")
        
        # Position is 1-indexed for users, but 0-indexed in the code
        position -= 1
        
        if position < 0 or position >= len(queue):
            return await interaction.followup.send(f"Invalid position. The queue has {len(queue)} songs.")
        
        # Remove the song
        removed_song = await music_system.queue.remove_from_queue(guild_id, position)
        
        if removed_song:
            await interaction.followup.send(f"Removed: {removed_song['title']}")
        else:
            await interaction.followup.send("Failed to remove the song.")

async def setup(bot):
    await bot.add_cog(QueueCommand(bot))
