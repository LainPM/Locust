# core/bot.py
import discord
from discord.ext import commands
import asyncio
import datetime
import motor.motor_asyncio
import os
from typing import Dict, List, Optional, Any, Callable

class AxisBot(commands.Bot):
    """Main bot class with enhanced functionality"""
    
    def __init__(self, command_prefix="!", **options):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        
        super().__init__(command_prefix=command_prefix, intents=intents, **options)
        
        # Event dispatch system
        self.event_handlers = {
            "on_message": [],
            "on_member_join": [],
            "on_member_remove": [],
            "on_reaction_add": [],
            "on_reaction_remove": []
        }
        
        # Database connections
        self.db = None
        self.mongo_client = None
        
        # Systems registry
        self.systems = {}
        
    async def setup_hook(self):
        """Called when the bot is starting up"""
        # Set up MongoDB
        mongo_uri = os.getenv("MONGO_URI")
        if mongo_uri:
            self.mongo_client = motor.motor_asyncio.AsyncIOMotorClient(mongo_uri)
            self.db = self.mongo_client["discord_bot"]
            print("Database connection established")
        
        # Load all commands
        await self.load_commands()
        
        # Initialize all systems
        await self.initialize_systems()
        
        print("Bot setup complete")
    
    async def load_commands(self):
        """Load all command modules"""
        # This will be implemented to load commands from the commands/ directory
        pass
    
    async def initialize_systems(self):
        """Initialize all bot systems"""
        # This will be implemented to initialize systems from the systems/ directory
        pass
    
    def register_event_handler(self, event_name: str, handler: Callable, priority: int = 0):
        """Register an event handler with optional priority"""
        if event_name not in self.event_handlers:
            self.event_handlers[event_name] = []
        
        self.event_handlers[event_name].append({
            "handler": handler,
            "priority": priority,
            "system": handler.__module__
        })
        
        # Sort handlers by priority (highest first)
        self.event_handlers[event_name].sort(key=lambda x: x["priority"], reverse=True)
        
        print(f"Registered event handler for {event_name} from {handler.__module__}")
    
    def register_system(self, name: str, system: Any):
        """Register a system with the bot"""
        self.systems[name] = system
        print(f"Registered system: {name}")
    
    async def get_system(self, name: str) -> Any:
        """Get a registered system by name"""
        return self.systems.get(name)
    
    async def process_events(self, event_name: str, *args, **kwargs):
        """Process all handlers for an event"""
        handlers = self.event_handlers.get(event_name, [])
        
        results = []
        for handler_info in handlers:
            handler = handler_info["handler"]
            try:
                result = await handler(*args, **kwargs)
                results.append(result)
                
                # Allow handlers to cancel event propagation
                if result is False:
                    break
            except Exception as e:
                print(f"Error in {event_name} handler from {handler_info['system']}: {e}")
        
        return results
