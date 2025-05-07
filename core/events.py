# core/events.py
import discord
from discord.ext import commands
from typing import Dict, List, Any

class EventDispatcher:
    """Central event dispatcher for bot systems"""
    
    def __init__(self, bot):
        self.bot = bot
        self.has_setup = False
    
    async def setup(self):
        """Set up event listeners"""
        if self.has_setup:
            return
        
        # Register built-in event methods
        self.bot.add_listener(self.on_message)
        self.bot.add_listener(self.on_member_join)
        self.bot.add_listener(self.on_member_remove)
        self.bot.add_listener(self.on_reaction_add)
        self.bot.add_listener(self.on_reaction_remove)
        
        self.has_setup = True
    
    async def on_message(self, message: discord.Message):
        """Central message handler - dispatches to all registered handlers"""
        if message.author.bot:  # Skip bot messages
            return
        
        # Let all registered handlers process this event
        await self.bot.process_events("on_message", message)
    
    async def on_member_join(self, member: discord.Member):
        """Central member join handler"""
        await self.bot.process_events("on_member_join", member)
    
    async def on_member_remove(self, member: discord.Member):
        """Central member remove handler"""
        await self.bot.process_events("on_member_remove", member)
    
    async def on_reaction_add(self, reaction: discord.Reaction, user: discord.User):
        """Central reaction add handler"""
        if user.bot:  # Skip bot reactions
            return
        
        await self.bot.process_events("on_reaction_add", reaction, user)
    
    async def on_reaction_remove(self, reaction: discord.Reaction, user: discord.User):
        """Central reaction remove handler"""
        if user.bot:  # Skip bot reactions
            return
        
        await self.bot.process_events("on_reaction_remove", reaction, user)
