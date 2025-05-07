import discord
import asyncio
import yt_dlp as youtube_dl
import re
from typing import Optional, Dict, Any

# YouTube DL options
ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',  # Bind to ipv4
}

ffmpeg_options = {
    'options': '-vn',
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
}

ytdl = youtube_dl.YoutubeDL(ytdl_format_options)

class MusicPlayer:
    """Component for playing music in voice channels"""
    
    def __init__(self, system):
        self.system = system
        self.bot = system.bot
        
        # Currently playing info by guild
        self.now_playing = {}  # Guild ID -> song info
    
    async def join_voice_channel(self, ctx: discord.Interaction) -> Optional[discord.VoiceClient]:
        """Join a voice channel"""
        # Check if the user is in a voice channel
        if not ctx.user.voice:
            await ctx.followup.send("You need to be in a voice channel to use this command.")
            return None
        
        voice_channel = ctx.user.voice.channel
        guild_id = ctx.guild.id
        
        # Check if already connected to a voice channel
        voice_client = discord.utils.get(self.bot.voice_clients, guild=ctx.guild)
        
        if voice_client:
            if voice_client.channel.id == voice_channel.id:
                # Already in the right channel
                return voice_client
            else:
                # Move to the new channel
                await voice_client.move_to(voice_channel)
                return voice_client
        else:
            # Connect to the voice channel
            voice_client = await voice_channel.connect()
            self.system.voice_clients[guild_id] = voice_client
            return voice_client
    
    async def leave_voice_channel(self, guild_id: int) -> bool:
        """Leave a voice channel"""
        voice_client = discord.utils.get(self.bot.voice_clients, guild=self.bot.get_guild(guild_id))
        
        if voice_client:
            await voice_client.disconnect()
            
            if guild_id in self.system.voice_clients:
                del self.system.voice_clients[guild_id]
                
            # Clear the queue
            await self.system.queue.clear_queue(guild_id)
            
            # Clear now playing
            if guild_id in self.now_playing:
                del self.now_playing[guild_id]
                
            return True
        
        return False
    
    async def play_song(self, guild_id: int, song_url: str, ctx: discord.Interaction = None) -> bool:
        """Play a song in the voice channel"""
        voice_client = discord.utils.get(self.bot.voice_clients, guild=self.bot.get_guild(guild_id))
        
        if not voice_client:
            if ctx:
                await ctx.followup.send("I'm not connected to a voice channel.")
            return False
        
        # Get song info
        try:
            # Try to extract song info
            song_info = await self._get_song_info(song_url)
            
            if not song_info:
                if ctx:
                    await ctx.followup.send("Could not find any audio for this URL.")
                return False
            
            # Store now playing info
            self.now_playing[guild_id] = song_info
            
            # Create audio source
            audio_source = discord.FFmpegPCMAudio(song_info['url'], **ffmpeg_options)
            
            # Play the song
            voice_client.play(
                audio_source, 
                after=lambda e: asyncio.run_coroutine_threadsafe(
                    self._song_finished(guild_id, e), 
                    self.bot.loop
                )
            )
            
            return True
            
        except Exception as e:
            print(f"Error playing song: {e}")
            if ctx:
                await ctx.followup.send(f"Error playing the song: {str(e)}")
            return False
    
    async def _get_song_info(self, url: str) -> Dict[str, Any]:
        """Get song information from URL"""
        loop = asyncio.get_event_loop()
        
        try:
            # Run youtube-dl in a separate thread to avoid blocking
            data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=False))
            
            if 'entries' in data:
                # Take first item from a playlist
                data = data['entries'][0]
            
            # Format the song info
            return {
                'title': data['title'],
                'url': data['url'],
                'thumbnail': data.get('thumbnail'),
                'duration': self._format_duration(data.get('duration', 0)),
                'webpage_url': data.get('webpage_url', url),
                'requester': None,  # Will be set when a user requests a song
                'uploader': data.get('uploader', 'Unknown')
            }
            
        except Exception as e:
            print(f"Error extracting song info: {e}")
            return None
    
    async def _song_finished(self, guild_id: int, error=None):
        """Called when a song finishes playing"""
        if error:
            print(f"Error in playback: {error}")
        
        # Remove from now playing
        if guild_id in self.now_playing:
            del self.now_playing[guild_id]
        
        # Play next song in queue
        next_song = await self.system.queue.get_next_song(guild_id)
        
        if next_song:
            await self.play_song(guild_id, next_song['url'])
    
    def _format_duration(self, duration: int) -> str:
        """Format duration in seconds to MM:SS or HH:MM:SS"""
        if not duration:
            return "Unknown"
            
        minutes, seconds = divmod(duration, 60)
        hours, minutes = divmod(minutes, 60)
        
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        else:
            return f"{minutes:02d}:{seconds:02d}"
