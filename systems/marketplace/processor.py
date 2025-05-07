# systems/marketplace/processor.py
import discord
import asyncio
import datetime
import io
from typing import Dict, List, Any

class MarketplaceProcessor:
    """Processor component for the Marketplace system"""
    
    def __init__(self, system):
        self.system = system
        self.bot = system.bot
    
    async def process_message(self, message: discord.Message) -> bool:
        """Process messages in marketplace channels"""
        # Skip bot messages and DMs
        if message.author.bot or not message.guild:
            return True
        
        # Get settings
        guild_id = message.guild.id
        settings = await self.system.get_settings(guild_id)
        
        # Check if this is a marketplace channel
        marketplace_channels = [
            settings.get("hiring_channel_id"),
            settings.get("forhire_channel_id"),
            settings.get("selling_channel_id")
        ]
        
        if message.channel.id not in marketplace_channels:
            return True
        
        # Check if user has moderator role
        mod_role_ids = settings.get("approval_mod_roles", [])
        has_mod_role = False
        
        for role in message.author.roles:
            if role.id in mod_role_ids:
                has_mod_role = True
                break
        
        # If not a moderator, delete the message and send a DM
        if not has_mod_role:
            try:
                await message.delete()
                
                # Get channel type
                channel_type = None
                if message.channel.id == settings.get("hiring_channel_id"):
                    channel_type = "Hiring"
                elif message.channel.id == settings.get("forhire_channel_id"):
                    channel_type = "For-Hire"
                elif message.channel.id == settings.get("selling_channel_id"):
                    channel_type = "Selling"
                
                # Send DM to the user
                try:
                    embed = discord.Embed(
                        title="Message Removed",
                        description="Your message in the marketplace channel was automatically removed.",
                        color=discord.Color.orange()
                    )
                    
                    embed.add_field(
                        name="Why was my message removed?",
                        value=f"The {channel_type} channel is only for approved marketplace posts. To create a post, use the `/post` command and select the appropriate type.",
                        inline=False
                    )
                    
                    await message.author.send(embed=embed)
                except:
                    # Unable to DM the user, just continue
                    pass
            except:
                # Unable to delete the message, just continue
                pass
            
            return False
        
        return True
    
    async def check_scheduled_deletions(self, guild_id: int):
        """Background task to check for channels that need to be deleted"""
        await self.bot.wait_until_ready()
        
        while not self.bot.is_closed():
            try:
                # Get channels scheduled for deletion
                scheduled = await self.system.storage.get_scheduled_deletions()
                
                for deletion in scheduled:
                    channel_id = deletion["channel_id"]
                    scheduled_guild_id = deletion["guild_id"]
                    
                    # Only process deletions for this guild
                    if scheduled_guild_id != guild_id:
                        continue
                    
                    guild = self.bot.get_guild(guild_id)
                    if guild:
                        channel = guild.get_channel(channel_id)
                        if channel:
                            try:
                                await channel.delete(reason="Marketplace post processed")
                                print(f"Deleted channel {channel_id} from guild {guild_id}")
                            except discord.Forbidden:
                                print(f"Could not delete channel {channel_id}: Missing permissions")
                            except discord.NotFound:
                                # Channel already deleted
                                print(f"Channel {channel_id} already deleted")
                            except Exception as e:
                                print(f"Error deleting channel {channel_id}: {str(e)}")
                    
                    # Remove from scheduled deletions
                    await self.system.storage.remove_scheduled_deletion(channel_id)
                
                # Check every 30 seconds
                await asyncio.sleep(30)
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Error in marketplace deletion task: {e}")
                await asyncio.sleep(30)
