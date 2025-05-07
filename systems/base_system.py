# systems/base_system.py
import abc
import logging
import asyncio
import inspect
from typing import Dict, List, Any, Optional, Callable, Coroutine, Union, TypeVar, Generic

T = TypeVar('T')

class System(abc.ABC):
    """
    Base class for all bot systems.
    
    A system is a self-contained module that provides specific functionality.
    Each system can register event handlers, command handlers, and background tasks.
    Systems can also access the database, interact with other systems, and maintain their own state.
    """
    
    def __init__(self, bot):
        """Initialize the system with a reference to the bot"""
        self.bot = bot
        self.name = self.__class__.__name__
        self.logger = logging.getLogger(f'axis_bot.systems.{self.name.lower()}')
        self.db = None
        self.storage = None
        self.processor = None
        self.renderer = None
        self.initialized = False
        self.settings_cache = {}
        self.background_tasks = {}
    
    async def initialize(self) -> bool:
        """
        Initialize the system components.
        This method should be overridden by subclasses.
        
        Returns:
            bool: True if initialization was successful, False otherwise
        """
        try:
            self.logger.info(f"Initializing {self.name}...")
            
            # Initialize database if bot has a db_manager
            if hasattr(self.bot, 'db_manager'):
                self.db = self.bot.db_manager
            
            # Register event handlers
            self._register_event_handlers()
            
            # Mark as initialized
            self.initialized = True
            
            self.logger.info(f"{self.name} initialized successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Error initializing {self.name}: {str(e)}", exc_info=True)
            return False
    
    def _register_event_handlers(self):
        """Register all event handlers in this system"""
        # Find all methods that start with 'on_' and register them as event handlers
        for name, method in inspect.getmembers(self, predicate=inspect.ismethod):
            if name.startswith('on_'):
                # Check if method has a priority set
                priority = getattr(method, 'priority', None)
                
                if hasattr(self.bot, 'register_event_handler'):
                    self.bot.register_event_handler(name, method, priority)
    
    async def cleanup(self):
        """
        Clean up system resources before shutdown.
        This method should be overridden by subclasses to release resources.
        """
        try:
            self.logger.info(f"Cleaning up {self.name}...")
            
            # Cancel any background tasks
            for task_name, task in list(self.background_tasks.items()):
                if not task.done():
                    task.cancel()
                    self.logger.info(f"Cancelled background task: {task_name}")
            
            self.logger.info(f"{self.name} cleaned up successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Error cleaning up {self.name}: {str(e)}", exc_info=True)
            return False
    
    async def get_settings(self, guild_id: int) -> Dict[str, Any]:
        """
        Get settings for this system in a specific guild.
        If settings are not in cache, load from database.
        
        Args:
            guild_id: The Discord guild ID
            
        Returns:
            Dict[str, Any]: The settings for this guild
        """
        # Check cache first
        if guild_id in self.settings_cache:
            return self.settings_cache[guild_id]
        
        # Load from database
        settings = await self._load_settings(guild_id)
        
        # Cache settings
        self.settings_cache[guild_id] = settings
        
        return settings
    
    async def _load_settings(self, guild_id: int) -> Dict[str, Any]:
        """
        Load settings from database. Override this in subclasses.
        
        Args:
            guild_id: The Discord guild ID
            
        Returns:
            Dict[str, Any]: Default settings if not found
        """
        # Subclasses should override this to load from their settings collection
        return {}
    
    async def update_settings(self, guild_id: int, settings: Dict[str, Any]) -> bool:
        """
        Update settings for this system in a specific guild.
        
        Args:
            guild_id: The Discord guild ID
            settings: The new settings
            
        Returns:
            bool: True if update was successful
        """
        try:
            # Update database
            success = await self._save_settings(guild_id, settings)
            
            # Update cache if successful
            if success:
                self.settings_cache[guild_id] = settings
            
            return success
            
        except Exception as e:
            self.logger.error(f"Error updating settings for guild {guild_id}: {str(e)}", exc_info=True)
            return False
    
    async def _save_settings(self, guild_id: int, settings: Dict[str, Any]) -> bool:
        """
        Save settings to database. Override this in subclasses.
        
        Args:
            guild_id: The Discord guild ID
            settings: The settings to save
            
        Returns:
            bool: True if save was successful
        """
        # Subclasses should override this to save to their settings collection
        return False
    
    async def start_background_task(self, name: str, coro: Callable[..., Coroutine], *args, **kwargs) -> bool:
        """
        Start a background task for this system.
        
        Args:
            name: Name of the task
            coro: Coroutine function to run
            *args, **kwargs: Arguments to pass to the coroutine
            
        Returns:
            bool: True if task was started successfully
        """
        # Check if task already exists
        if name in self.background_tasks and not self.background_tasks[name].done():
            self.logger.warning(f"Task {name} is already running")
            return False
        
        # Create task wrapper for error handling
        async def task_wrapper():
            try:
                await coro(*args, **kwargs)
            except asyncio.CancelledError:
                self.logger.info(f"Task {name} was cancelled")
            except Exception as e:
                self.logger.error(f"Error in background task {name}: {str(e)}", exc_info=True)
        
        # Start the task
        self.background_tasks[name] = asyncio.create_task(task_wrapper())
        self.logger.info(f"Started background task: {name}")
        
        return True
    
    async def stop_background_task(self, name: str) -> bool:
        """
        Stop a background task.
        
        Args:
            name: Name of the task to stop
            
        Returns:
            bool: True if task was stopped
        """
        if name in self.background_tasks and not self.background_tasks[name].done():
            self.background_tasks[name].cancel()
            self.logger.info(f"Cancelled background task: {name}")
            return True
        
        return False
    
    def get_priority(self, event_name: str) -> int:
        """
        Get the priority level for an event handler.
        Higher values mean the handler will be called earlier.
        
        Args:
            event_name: Name of the event
            
        Returns:
            int: Priority level (default: 50)
        """
        # Default priorities
        priorities = {
            "on_message": 50,
            "on_reaction_add": 50,
            "on_member_join": 60,
            "on_guild_join": 70,
            "on_ready": 80,
            "on_error": 90
        }
        
        return priorities.get(event_name, 50)
    
    def priority(self, level: int):
        """
        Decorator to set priority level for an event handler.
        
        Args:
            level: Priority level (higher means called earlier)
            
        Returns:
            Callable: Decorator function
        """
        def decorator(func):
            func.priority = level
            return func
        return decorator
    
    async def get_system(self, name: str) -> Optional['System']:
        """
        Get another system by name.
        
        Args:
            name: Name of the system to get
            
        Returns:
            Optional[System]: The requested system or None if not found
        """
        return await self.bot.get_system(name)
    
    def component_id(self, base_id: str, guild_id: Optional[int] = None, user_id: Optional[int] = None) -> str:
        """
        Generate a component ID with system prefix.
        Useful for creating unique IDs for buttons, select menus, etc.
        
        Args:
            base_id: The base component ID
            guild_id: Optional guild ID to include
            user_id: Optional user ID to include
            
        Returns:
            str: Formatted component ID
        """
        system_prefix = self.name.lower()
        
        if guild_id and user_id:
            return f"{system_prefix}:{base_id}:{guild_id}:{user_id}"
        elif guild_id:
            return f"{system_prefix}:{base_id}:{guild_id}"
        elif user_id:
            return f"{system_prefix}:{base_id}::{user_id}"
        else:
            return f"{system_prefix}:{base_id}"
    
    def parse_component_id(self, component_id: str) -> Dict[str, Any]:
        """
        Parse a component ID created with component_id().
        
        Args:
            component_id: The component ID to parse
            
        Returns:
            Dict[str, Any]: Parsed parts
        """
        parts = component_id.split(':')
        
        if len(parts) == 2:
            return {
                "system": parts[0],
                "id": parts[1],
                "guild_id": None,
                "user_id": None
            }
        elif len(parts) == 3:
            return {
                "system": parts[0],
                "id": parts[1],
                "guild_id": int(parts[2]) if parts[2] else None,
                "user_id": None
            }
        elif len(parts) == 4:
            return {
                "system": parts[0],
                "id": parts[1],
                "guild_id": int(parts[2]) if parts[2] else None,
                "user_id": int(parts[3]) if parts[3] else None
            }
        else:
            return {
                "system": self.name.lower(),
                "id": component_id,
                "guild_id": None,
                "user_id": None
            }
    
    # System Component Classes
    
    class Storage:
        """Base storage class for system data persistence"""
        
        def __init__(self, system):
            self.system = system
            self.bot = system.bot
            self.db = system.db
            self.logger = system.logger
        
        async def initialize(self) -> bool:
            """Initialize storage (create collections, indexes, etc.)"""
            return True
    
    class Processor:
        """Base processor class for system business logic"""
        
        def __init__(self, system):
            self.system = system
            self.bot = system.bot
            self.logger = system.logger
        
        async def initialize(self) -> bool:
            """Initialize processor"""
            return True
    
    class Renderer:
        """Base renderer class for system UI components"""
        
        def __init__(self, system):
            self.system = system
            self.bot = system.bot
            self.logger = system.logger
        
        async def initialize(self) -> bool:
            """Initialize renderer"""
            return True
        
        def create_embed(self, title: str, description: str = None, color = None) -> discord.Embed:
            """Create a standardized embed for this system"""
            if color is None:
                color = discord.Color.blue()
                
            embed = discord.Embed(
                title=title,
                description=description,
                color=color
            )
            
            return embed
