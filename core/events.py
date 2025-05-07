# core/events.py
import discord
import inspect
import asyncio
import logging
from typing import Dict, List, Callable, Any, Optional, Union

class EventDispatcher:
    """Manages event registration and dispatching for all systems"""
    
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger('axis_bot.events')
        self.registered_events = {}
        self.event_stats = {}
        
        # Default event priorities
        self.DEFAULT_PRIORITIES = {
            "on_message": 50,
            "on_member_join": 50,
            "on_member_remove": 50,
            "on_guild_join": 80,  # Higher priority for important server events
            "on_guild_remove": 80,
            "on_ready": 100,      # Highest priority for initialization
            "on_disconnect": 100,
            "on_error": 100
        }
    
    async def setup(self):
        """Set up the event dispatcher and register core event listeners"""
        # Override the bot's dispatch method to use our custom event system
        original_dispatch = self.bot.dispatch
        
        # Replace the dispatch method with our custom one
        async def custom_dispatch(event_name, *args, **kwargs):
            # First, run the original dispatch to maintain compatibility
            original_dispatch(event_name, *args, **kwargs)
            
            # Then run our custom event processing
            await self.process_event(event_name, *args, **kwargs)
        
        self.bot.dispatch = custom_dispatch
        
        # Reset event stats
        self.event_stats = {
            "total_events": 0,
            "events_by_type": {},
            "handler_executions": 0,
            "handler_errors": 0
        }
        
        self.logger.info("Event dispatcher set up successfully")
        return True
    
    def get_priority(self, event_name: str, default: int = 0) -> int:
        """Get the default priority for an event type"""
        return self.DEFAULT_PRIORITIES.get(event_name, default)
    
    def register_event(self, event_name: str, handler: Callable, system_name: str, priority: Optional[int] = None):
        """Register an event handler"""
        # Initialize the event type if it doesn't exist
        if event_name not in self.registered_events:
            self.registered_events[event_name] = []
            self.event_stats["events_by_type"][event_name] = 0
        
        # Use default priority if none specified
        if priority is None:
            priority = self.get_priority(event_name)
        
        # Add the handler with metadata
        self.registered_events[event_name].append({
            "handler": handler,
            "system": system_name,
            "priority": priority,
            "calls": 0,
            "errors": 0,
            "last_call": None,
            "async": asyncio.iscoroutinefunction(handler)
        })
        
        # Sort handlers by priority (highest first)
        self.registered_events[event_name].sort(key=lambda x: x["priority"], reverse=True)
        
        self.logger.debug(f"Registered {event_name} handler from {system_name} with priority {priority}")
    
    def register_system_events(self, system, system_name: str):
        """Register all event handlers from a system"""
        # Find all methods in the system that start with 'on_'
        for name, method in inspect.getmembers(system, predicate=inspect.ismethod):
            if name.startswith('on_'):
                # Get priority from method attribute if available
                priority = getattr(method, 'priority', None)
                self.register_event(name, method, system_name, priority)
                
        self.logger.info(f"Registered events for system: {system_name}")
    
    async def process_event(self, event_name: str, *args, **kwargs):
        """Process an event through all registered handlers"""
        # Skip if no handlers for this event
        if event_name not in self.registered_events:
            return []
        
        # Update stats
        self.event_stats["total_events"] += 1
        self.event_stats["events_by_type"][event_name] = self.event_stats["events_by_type"].get(event_name, 0) + 1
        
        handlers = self.registered_events[event_name]
        results = []
        
        for handler_info in handlers:
            handler = handler_info["handler"]
            system_name = handler_info["system"]
            is_async = handler_info["async"]
            
            try:
                # Update handler stats
                handler_info["calls"] += 1
                handler_info["last_call"] = asyncio.get_event_loop().time()
                self.event_stats["handler_executions"] += 1
                
                # Execute handler (async or non-async)
                if is_async:
                    result = await handler(*args, **kwargs)
                else:
                    result = handler(*args, **kwargs)
                    
                results.append(result)
                
                # Stop propagation if handler returns False
                if result is False:
                    self.logger.debug(f"Event {event_name} propagation stopped by {system_name}")
                    break
                    
            except Exception as e:
                handler_info["errors"] += 1
                self.event_stats["handler_errors"] += 1
                self.logger.error(f"Error in {event_name} handler from {system_name}: {str(e)}", exc_info=True)
                
                # Emit system error event (avoiding infinite recursion)
                if event_name != "on_system_error" and hasattr(self.bot, "process_events"):
                    try:
                        await self.bot.process_events("on_system_error", system_name, event_name, e, args, kwargs)
                    except Exception as e2:
                        self.logger.error(f"Error emitting system_error event: {str(e2)}")
        
        return results
    
    def get_event_stats(self):
        """Get statistics about event processing"""
        # Calculate additional stats
        event_counts = []
        handler_counts = {}
        
        for event_name, handlers in self.registered_events.items():
            handler_counts[event_name] = len(handlers)
            event_counts.append({
                "event": event_name,
                "handlers": len(handlers),
                "calls": self.event_stats["events_by_type"].get(event_name, 0)
            })
        
        # Sort by most frequently called
        event_counts.sort(key=lambda x: x["calls"], reverse=True)
        
        return {
            **self.event_stats,
            "registered_events": len(self.registered_events),
            "registered_handlers": sum(handler_counts.values()),
            "event_details": event_counts[:10],  # Top 10 events
            "success_rate": 1 - (self.event_stats["handler_errors"] / max(1, self.event_stats["handler_executions"]))
        }
    
    def event_priority(self, priority: int):
        """Decorator to set event handler priority"""
        def decorator(func):
            func.priority = priority
            return func
        return decorator
    
    async def cleanup(self):
        """Clean up resources used by the event dispatcher"""
        # Reset registered events
        self.registered_events = {}
        
        # Save final stats
        self.logger.info(f"Event dispatcher cleaned up. Processed {self.event_stats['total_events']} events.")
