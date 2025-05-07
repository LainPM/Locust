import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional
import re

class PlayCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @app_commands.command(
        name="play",
        description="Play a song in your voice channel"
    )
    @app_commands.describe(query="URL or search query for a song to play")
    @app_commands.guild_only()
    async def play(
        self,
        interaction: discord.Interaction,
        query: str
    ):
        """Play a song in your voice channel"""
        await interaction.response.defer()
        
        # Get the music system
        music_system = await self.bot.get_system("MusicSystem")
        if not music_system:
            return await interaction.followup.send("Music system is not available.")
        
        # Try to join the voice channel
        voice_client = await music_system.player.join_voice_channel(interaction)
        if not voice_client:
            return
        
        # Check if the query is a URL
        is_url = re.match(r'https?://(?:www\.)?.+', query) is not None
        
        if not is_url:
            # If it's not a URL, search YouTube for the query
            query = f"ytsearch:{query}"
        
        # Extract song info
        song_info = await music_system.player._get_song_info(query)
        
        if not song_info:
            return await interaction.followup.send("Could not find any audio for this query.")
        
        # Add requester info
        song_info['requester'] = interaction.user.display_name
        
        guild_id = interaction.guild.id
        
        # Check if something is already playing
        if guild_id in music_system.player.now_playing:
            # Add to queue
            position = await music_system.queue.add_to_queue(guild_id, song_info)
            
            # Create embed
            embed = discord.Embed(
                title="Added to Queue",
                description=f"[{song_info['title']}]({song_info['webpage_url']})",
                color=discord.Color.blue()
            )
            
            embed.add_field(name="Position", value=str(position), inline=True)
            embed.add_field(name="Duration", value=song_info['duration'], inline=True)
            embed.add_field(name="Requested By", value=song_info['requester'], inline=True)
            
            if song_info['thumbnail']:
                embed.set_thumbnail(url=song_info['thumbnail'])
            
            await interaction.followup.send(embed=embed)
        else:
            # Play directly
            success = await music_system.player.play_song(guild_id, song_info['url'], interaction)
            
            if success:
                # Add requester info
                music_system.player.now_playing[guild_id]['requester'] = song_info['requester']
                
                # Create embed
                embed = discord.Embed(
                    title="Now Playing",
                    description=f"[{song_info['title']}]({song_info['webpage_url']})",
                    color=discord.Color.green()
                )
                
                embed.add_field(name="Duration", value=song_info['duration'], inline=True)
                embed.add_field(name="Requested By", value=song_info['requester'], inline=True)
                
                if song_info['thumbnail']:
                    embed.set_thumbnail(url=song_info['thumbnail'])
                
                await interaction.followup.send(embed=embed)
    
    @app_commands.command(
        name="playnext",
        description="Add a song to the front of the queue"
    )
    @app_commands.describe(query="URL or search query for a song to play next")
    @app_commands.guild_only()
    async def play_next(
        self,
        interaction: discord.Interaction,
        query: str
    ):
        """Add a song to the front of the queue"""
        await interaction.response.defer()
        
        # Get the music system
        music_system = await self.bot.get_system("MusicSystem")
        if not music_system:
            return await interaction.followup.send("Music system is not available.")
        
        # Check if the bot is in a voice channel
        voice_client = discord.utils.get(self.bot.voice_clients, guild=interaction.guild)
        if not voice_client:
            return await interaction.followup.send("I'm not in a voice channel. Use /play first.")
            
        # Check if the query is a URL
        is_url = re.match(r'https?://(?:www\.)?.+', query) is not None
        
        if not is_url:
            # If it's not a URL, search YouTube for the query
            query = f"ytsearch:{query}"
        
        # Extract song info
        song_info = await music_system.player._get_song_info(query)
        
        if not song_info:
            return await interaction.followup.send("Could not find any audio for this query.")
        
        # Add requester info
        song_info['requester'] = interaction.user.display_name
        
        guild_id = interaction.guild.id
        
        # Add to front of queue
        if guild_id not in music_system.queue.queues:
            music_system.queue.queues[guild_id] = []
        
        music_system.queue.queues[guild_id].insert(0, song_info)
        
        # Create embed
        embed = discord.Embed(
            title="Added to Play Next",
            description=f"[{song_info['title']}]({song_info['webpage_url']})",
            color=discord.Color.blue()
        )
        
        embed.add_field(name="Position", value="Next in queue", inline=True)
        embed.add_field(name="Duration", value=song_info['duration'], inline=True)
        embed.add_field(name="Requested By", value=song_info['requester'], inline=True)
        
        if song_info['thumbnail']:
            embed.set_thumbnail(url=song_info['thumbnail'])
        
        await interaction.followup.send(embed=embed)

async def setup(bot):
    await bot.add_cog(PlayCommand(bot))
