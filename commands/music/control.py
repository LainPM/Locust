import discord
from discord import app_commands
from discord.ext import commands
import datetime
from typing import Optional, Literal

class MusicControlCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @app_commands.command(
        name="stop",
        description="Stop playback and clear the queue"
    )
    @app_commands.guild_only()
    async def stop(
        self,
        interaction: discord.Interaction
    ):
        """Stop playback and clear the queue"""
        await interaction.response.defer()
        
        # Get the music system
        music_system = await self.bot.get_system("MusicSystem")
        if not music_system:
            return await interaction.followup.send("Music system is not available.")
        
        guild_id = interaction.guild.id
        voice_client = discord.utils.get(self.bot.voice_clients, guild=interaction.guild)
        
        if not voice_client or not voice_client.is_connected():
            return await interaction.followup.send("I'm not connected to a voice channel.")
        
        # Clear the queue
        await music_system.queue.clear_queue(guild_id)
        
        # Stop playback
        if voice_client.is_playing():
            voice_client.stop()
        
        # Clear now playing
        if guild_id in music_system.player.now_playing:
            del music_system.player.now_playing[guild_id]
        
        await interaction.followup.send("Stopped playback and cleared the queue.")
    
    @app_commands.command(
        name="leave",
        description="Leave the voice channel and stop playing music"
    )
    @app_commands.guild_only()
    async def leave(
        self,
        interaction: discord.Interaction
    ):
        """Leave the voice channel"""
        await interaction.response.defer()
        
        # Get the music system
        music_system = await self.bot.get_system("MusicSystem")
        if not music_system:
            return await interaction.followup.send("Music system is not available.")
        
        guild_id = interaction.guild.id
        
        # Leave the voice channel
        success = await music_system.player.leave_voice_channel(guild_id)
        
        if success:
            await interaction.followup.send("Left the voice channel.")
        else:
            await interaction.followup.send("I'm not in a voice channel.")
    
    @app_commands.command(
        name="shuffle",
        description="Shuffle the music queue"
    )
    @app_commands.guild_only()
    async def shuffle(
        self,
        interaction: discord.Interaction
    ):
        """Shuffle the music queue"""
        await interaction.response.defer()
        
        # Get the music system
        music_system = await self.bot.get_system("MusicSystem")
        if not music_system:
            return await interaction.followup.send("Music system is not available.")
        
        guild_id = interaction.guild.id
        
        # Shuffle the queue
        success = await music_system.queue.shuffle_queue(guild_id)
        
        if success:
            await interaction.followup.send("Shuffled the music queue.")
        else:
            await interaction.followup.send("The queue is empty.")
    
    @app_commands.command(
        name="nowplaying",
        description="Show information about the currently playing song"
    )
    @app_commands.guild_only()
    async def now_playing(
        self,
        interaction: discord.Interaction
    ):
        """Show information about the currently playing song"""
        await interaction.response.defer()
        
        # Get the music system
        music_system = await self.bot.get_system("MusicSystem")
        if not music_system:
            return await interaction.followup.send("Music system is not available.")
        
        guild_id = interaction.guild.id
        
        # Check if something is playing
        if guild_id not in music_system.player.now_playing:
            return await interaction.followup.send("Nothing is playing right now.")
        
        # Get now playing info
        now_playing = music_system.player.now_playing[guild_id]
        
        # Create embed
        embed = discord.Embed(
            title="Now Playing",
            description=f"[{now_playing['title']}]({now_playing['webpage_url']})",
            color=discord.Color.green()
        )
        
        embed.add_field(name="Duration", value=now_playing['duration'], inline=True)
        
        if now_playing.get('requester'):
            embed.add_field(name="Requested By", value=now_playing['requester'], inline=True)
        
        if now_playing.get('uploader'):
            embed.add_field(name="Uploader", value=now_playing['uploader'], inline=True)
        
        if now_playing.get('thumbnail'):
            embed.set_thumbnail(url=now_playing['thumbnail'])
        
        await interaction.followup.send(embed=embed)
    
    @app_commands.command(
        name="volume",
        description="Adjust the volume of the music player"
    )
    @app_commands.describe(volume="Volume level (0-100)")
    @app_commands.guild_only()
    async def volume(
        self,
        interaction: discord.Interaction,
        volume: int
    ):
        """Adjust the volume of the music player"""
        await interaction.response.defer()
        
        # Get the music system
        music_system = await self.bot.get_system("MusicSystem")
        if not music_system:
            return await interaction.followup.send("Music system is not available.")
        
        # Validate volume level
        if volume < 0 or volume > 100:
            return await interaction.followup.send("Volume must be between 0 and 100.")
        
        guild_id = interaction.guild.id
        voice_client = discord.utils.get(self.bot.voice_clients, guild=interaction.guild)
        
        if not voice_client or not voice_client.is_connected():
            return await interaction.followup.send("I'm not connected to a voice channel.")
        
        # FFmpeg volume is between 0.0 and 1.0, convert from percentage
        normalized_volume = volume / 100.0
        
        # This only works if the source supports volume adjustment
        # For real implementation, you'd need to handle recreating the audio source
        if hasattr(voice_client, "source") and hasattr(voice_client.source, "volume"):
            voice_client.source.volume = normalized_volume
            await interaction.followup.send(f"Volume set to {volume}%")
        else:
            await interaction.followup.send("Volume adjustment is not supported for the current audio source.")

async def setup(bot):
    await bot.add_cog(MusicControlCommand(bot))
