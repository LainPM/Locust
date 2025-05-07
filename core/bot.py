# core/bot.py
import discord
from discord.ext import commands
import asyncio
import datetime
import motor.motor_asyncio
import os
import logging
import traceback
from typing import Dict, List, Optional, Any, Callable, Coroutine, Union

class AxisBot(commands.Bot):
    """Main bot class with enhanced functionality"""
    
    def __init__(self, command_prefix="!", **options):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        
        super().__init__(command_prefix=command_prefix, intents=intents, **options)
        
        # Setup logger
        self.logger = logging.getLogger('axis_bot.core')
        
        # Event dispatch system
        self.event_handlers = {}
        
        # Database connections
        self.db = None
        self.mongo_client = None
        self.db_manager = None
        
        # Systems registry
        self.systems = {}
        
        # Background tasks
        self.background_tasks = {}
        
        # Bot stats
        self.stats = {
            "commands_used": 0,
            "events_processed": 0,
            "start_time": datetime.datetime.now(),
            "errors": 0
        }
    
    async def setup_hook(self):
    """Called when the bot is starting up"""
    try:
        # Set up MongoDB
        mongo_uri = os.getenv("MONGO_URI")
        if mongo_uri:
            self.mongo_client = motor.motor_asyncio.AsyncIOMotorClient(mongo_uri)
            self.db = self.mongo_client["discord_bot"]
            self.logger.info("Database connection established")
        else:
            self.logger.warning("No MONGO_URI provided, database features will be unavailable")
        
        # Initialize event handlers dictionary
        event_names = [
            'on_message', 
            'on_message_delete', 
            'on_message_edit',
            'on_reaction_add', 
            'on_reaction_remove',
            'on_member_join', 
            'on_member_remove',
            'on_guild_join', 
            'on_guild_remove',
            'on_guild_update',
            'on_ready',
            'on_disconnect',
            'on_error',
            'on_voice_state_update',
            'on_interaction'
        ]
        
        for event_name in event_names:
            self.event_handlers[event_name] = []
        
        # Add additional custom events
        custom_events = [
            "on_system_error",
            "on_database_error",
            "on_command_completion"
        ]
        
        for event_name in custom_events:
            if event_name not in self.event_handlers:
                self.event_handlers[event_name] = []
        
        self.logger.info("Bot setup complete")
    except Exception as e:
        self.logger.error(f"Error in setup_hook: {e}", exc_info=True)
        raise
    
    async def load_commands(self):
        """Load all command modules"""
        # This will be implemented by the CommandLoader utility
        pass
    
    async def initialize_systems(self):
        """Initialize all bot systems"""
        # This will be implemented in main.py
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
        
        self.logger.debug(f"Registered event handler for {event_name} from {handler.__module__}")
    
    def register_system(self, name: str, system: Any):
        """Register a system with the bot"""
        self.systems[name] = system
        self.logger.info(f"Registered system: {name}")
    
    async def get_system(self, name: str) -> Any:
        """Get a registered system by name"""
        system = self.systems.get(name)
        if not system:
            self.logger.warning(f"System '{name}' not found")
        return system
    
    async def process_events(self, event_name: str, *args, **kwargs):
        """Process all handlers for an event"""
        if event_name not in self.event_handlers:
            return []
            
        handlers = self.event_handlers.get(event_name, [])
        self.stats["events_processed"] += 1
        
        results = []
        for handler_info in handlers:
            handler = handler_info["handler"]
            handler_system = handler_info["system"]
            
            try:
                result = await handler(*args, **kwargs)
                results.append(result)
                
                # Allow handlers to cancel event propagation
                if result is False:
                    self.logger.debug(f"Event {event_name} propagation stopped by {handler_system}")
                    break
            except Exception as e:
                self.stats["errors"] += 1
                self.logger.error(f"Error in {event_name} handler from {handler_system}: {e}", exc_info=True)
                
                # Emit system error event
                await self.process_events("on_system_error", handler_system, event_name, e, args, kwargs)
        
        return results
    
    async def start_background_task(self, name: str, coro: Callable, *args, **kwargs):
        """Start a background task with proper tracking and error handling"""
        if name in self.background_tasks and not self.background_tasks[name].done():
            self.logger.warning(f"Task {name} is already running")
            return False
        
        async def task_wrapper():
            try:
                await coro(*args, **kwargs)
            except asyncio.CancelledError:
                self.logger.info(f"Task {name} was cancelled")
            except Exception as e:
                self.stats["errors"] += 1
                self.logger.error(f"Error in background task {name}: {e}", exc_info=True)
                
                # Emit system error event
                module_name = coro.__module__
                await self.process_events("on_system_error", module_name, f"task_{name}", e, args, kwargs)
        
        self.background_tasks[name] = self.loop.create_task(task_wrapper())
        self.logger.info(f"Started background task: {name}")
        return True
    
    async def stop_background_task(self, name: str):
        """Stop a background task"""
        if name in self.background_tasks and not self.background_tasks[name].done():
            self.background_tasks[name].cancel()
            self.logger.info(f"Cancelled background task: {name}")
            return True
        return False
    
    async def stop_all_background_tasks(self):
        """Stop all background tasks"""
        for name, task in list(self.background_tasks.items()):
            if not task.done():
                task.cancel()
                self.logger.info(f"Cancelled background task: {name}")
    
    async def get_bot_stats(self):
        """Get statistics about the bot"""
        uptime = datetime.datetime.now() - self.stats["start_time"]
        
        stats = {
            **self.stats,
            "uptime_seconds": uptime.total_seconds(),
            "uptime_str": str(uptime).split('.')[0],  # Remove microseconds
            "system_count": len(self.systems),
            "event_handlers": {name: len(handlers) for name, handlers in self.event_handlers.items() if handlers},
            "background_tasks": {name: not task.done() for name, task in self.background_tasks.items()},
            "latency_ms": round(self.latency * 1000)
        }
        
        return stats
    
    async def on_command_completion(self, ctx):
        """Tracks command usage statistics"""
        self.stats["commands_used"] += 1
        
        command_name = ctx.command.qualified_name
        self.logger.info(f"Command '{command_name}' used by {ctx.author} ({ctx.author.id}) in guild {ctx.guild.id if ctx.guild else 'DM'}")
        
        # Allow systems to react to command completion
        await self.process_events("on_command_completion", ctx)
    
    async def on_error(self, event_method, *args, **kwargs):
        """Global error handler for bot events"""
        self.stats["errors"] += 1
        
        error = traceback.format_exc()
        self.logger.error(f"Error in {event_method}: {error}")
        
        # Let systems handle the error if they want
        await self.process_events("on_system_error", "bot", event_method, error, args, kwargs)
    
    async def close(self):
        """Clean up resources when bot is shutting down"""
        self.logger.info("Bot is shutting down...")
        
        # Stop all background tasks
        await self.stop_all_background_tasks()
        
        # Close database connection
        if self.mongo_client:
            self.mongo_client.close()
            self.logger.info("Closed database connection")
        
        # Call parent close method
        await super().close()
