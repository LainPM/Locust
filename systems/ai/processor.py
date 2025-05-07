# systems/ai/processor.py
import discord
import asyncio
import datetime
from typing import Dict, List, Any, Tuple, Optional

class AIProcessor:
    """Processor for AI chat functionality"""
    
    def __init__(self, system):
        self.system = system
        self.bot = system.bot
        
        # Constants
        self.conversation_timeout = 30  # Minutes
        self.max_history_length = 10
        self.max_tokens = 8000
        
        # Cleanup task
        self.cleanup_task = None
    
    async def process_message(self, message) -> bool:
        """Process messages for AI chat"""
        # Skip bot messages and DMs
        if message.author.bot or not message.guild:
            return True
        
        # Check if message starts with "Hey Axis" (case insensitive)
        content = message.content.lower()
        if content.startswith("hey axis"):
            # Handle AI chat
            await self._handle_ai_chat(message)
            return False  # Stop further processing
        
        # Check if user is in an active conversation
        user_id = message.author.id
        channel_id = message.channel.id
        
        if self._is_in_conversation(user_id, channel_id):
            # Update conversation
            await self._update_conversation(message)
            return False  # Stop further processing
        
        return True
    
    async def _handle_ai_chat(self, message):
        """Handle initial AI chat request"""
        user_id = message.author.id
        channel_id = message.channel.id
        
        # Create or update conversation
        if not self._is_in_conversation(user_id, channel_id):
            # Start new conversation
            await self._start_conversation(message)
        else:
            # Update existing conversation
            await self._update_conversation(message)
    
    async def _start_conversation(self, message):
        """Start a new conversation"""
        user_id = message.author.id
        channel_id = message.channel.id
        
        # Add to active conversations
        self.system.active_conversations.add(f"{user_id}-{channel_id}")
        
        # Set timeout
        expiry = datetime.datetime.now() + datetime.timedelta(minutes=self.conversation_timeout)
        self.system.conversation_timeouts[f"{user_id}-{channel_id}"] = expiry
        
        # Initialize user messages
        if user_id not in self.system.user_messages:
            self.system.user_messages[user_id] = {}
        
        self.system.user_messages[user_id][channel_id] = [{
            "role": "user",
            "content": message.content,
            "timestamp": datetime.datetime.now()
        }]
        
        # Reply with simple response for now
        await message.channel.send(f"Hello {message.author.display_name}! How can I help you today?")
    
    async def _update_conversation(self, message):
        """Update an existing conversation"""
        user_id = message.author.id
        channel_id = message.channel.id
        
        # Update timeout
        expiry = datetime.datetime.now() + datetime.timedelta(minutes=self.conversation_timeout)
        self.system.conversation_timeouts[f"{user_id}-{channel_id}"] = expiry
        
        # Add message to history
        if user_id in self.system.user_messages and channel_id in self.system.user_messages[user_id]:
            self.system.user_messages[user_id][channel_id].append({
                "role": "user",
                "content": message.content,
                "timestamp": datetime.datetime.now()
            })
            
            # Limit history length
            if len(self.system.user_messages[user_id][channel_id]) > self.max_history_length:
                self.system.user_messages[user_id][channel_id] = self.system.user_messages[user_id][channel_id][-self.max_history_length:]
        
        # Simple response for now
        await message.channel.send(f"I'm a simple AI. You said: {message.content}")
    
    def _is_in_conversation(self, user_id: int, channel_id: int) -> bool:
        """Check if user is in an active conversation in this channel"""
        return f"{user_id}-{channel_id}" in self.system.active_conversations
    
    async def get_status(self, user_id: int, channel_id: int) -> Tuple[bool, int, int, int]:
        """Get conversation status for a user"""
        is_active = self._is_in_conversation(user_id, channel_id)
        
        message_count = 0
        token_count = 0
        
        if user_id in self.system.user_messages and channel_id in self.system.user_messages[user_id]:
            message_count = len(self.system.user_messages[user_id][channel_id])
            
            # Estimate token count (very roughly ~4 chars per token)
            total_chars = sum(len(msg["content"]) for msg in self.system.user_messages[user_id][channel_id])
            token_count = total_chars // 4
        
        return is_active, message_count, token_count, self.max_tokens
    
    async def cleanup_old_data(self):
        """Background task to clean up expired conversations"""
        self.cleanup_task = asyncio.current_task()
        
        while True:
            try:
                now = datetime.datetime.now()
                
                # Check timeouts
                expired = []
                for conv_id, expiry in self.system.conversation_timeouts.items():
                    if now > expiry:
                        expired.append(conv_id)
                
                # Clean up expired conversations
                for conv_id in expired:
                    self.system.active_conversations.discard(conv_id)
                    self.system.conversation_timeouts.pop(conv_id, None)
                    
                    # Parse user_id and channel_id
                    parts = conv_id.split('-')
                    if len(parts) == 2:
                        user_id, channel_id = int(parts[0]), int(parts[1])
                        
                        # Clean up messages
                        if user_id in self.system.user_messages:
                            self.system.user_messages[user_id].pop(channel_id, None)
                            
                            # If no more conversations, clean up user data
                            if not self.system.user_messages[user_id]:
                                self.system.user_messages.pop(user_id, None)
                
                # Sleep for 1 minute
                await asyncio.sleep(60)
                
            except asyncio.CancelledError:
                # Task was cancelled, exit gracefully
                break
            except Exception as e:
                print(f"Error in AI cleanup task: {e}")
                await asyncio.sleep(60)  # Sleep and try again
