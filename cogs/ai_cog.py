import discord
from discord.ext import commands
import os
import aiohttp
import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set

class AICog(commands.Cog):
    """AI capabilities for Axis Discord bot using Gemini API"""
    
    def __init__(self, bot):
        self.bot = bot
        
        # Use the bot's existing MongoDB connection
        self.db = None
        self.conversations = None
        
        # Set up MongoDB collections if bot has MongoDB
        if hasattr(bot, 'mongo_client') and bot.mongo_client is not None:
            try:
                self.db = bot.db
                # Create a conversations collection in the existing database
                self.conversations = self.db.conversations
                # Create active_conversations collection
                self.active_conversations_col = self.db.active_conversations
                print("AI Cog: Successfully connected to MongoDB")
            except Exception as e:
                print(f"AI Cog: Error connecting to MongoDB: {e}")
                self.db = None
        
        # In-memory storage fallback
        self.memory_storage = {}
        
        # Keep track of active conversations (user_id-channel_id)
        # This stores users who are in an active conversation with the bot
        self.active_conversations = set()
        
        # Conversation timeout (in minutes)
        self.conversation_timeout = 10
        
        # Track when each conversation was last active
        self.last_activity = {}
        
        # Maximum tokens before warning about context window
        self.max_tokens_warning = 6000
        
        # Maximum tokens before auto-ending conversation
        self.max_tokens_limit = 8000
        
        # Approximate token count per message
        self.avg_tokens_per_message = 100
        
        # Special token to indicate conversation ending
        self.end_conversation_token = "[END_CONVERSATION]"
        
        # API Key for Gemini
        self.gemini_api_key = os.getenv('GEMINI_API_KEY')
        
        # Gemini API model - using a valid model name
        # Current valid models include gemini-1.0-pro, gemini-1.0-pro-001, gemini-2.0-flash, etc.
        self.model_name = "gemini-1.0-pro"  # Fallback to most widely available model
        
        # Try to use newer models if available
        try:
            model_preference = ["gemini-2.0-flash", "gemini-1.5-flash-001", "gemini-1.0-pro"]
            for model in model_preference:
                if self.test_model(model):
                    self.model_name = model
                    print(f"AI Cog: Using {model} for Gemini API")
                    break
        except Exception as e:
            print(f"AI Cog: Error testing models, using fallback model {self.model_name}: {e}")
        
        # Gemini API endpoint
        self.api_endpoint = f"https://generativelanguage.googleapis.com/v1/models/{self.model_name}:generateContent?key={self.gemini_api_key}"
        
        # Maximum number of messages to keep in history
        self.max_history_messages = 10
        
        # Maximum number of messages to analyze in reply context
        self.max_reply_context_messages = 10
        
        # Start background task to clean up inactive conversations
        self.bg_task = bot.loop.create_task(self.cleanup_inactive_conversations())
        
        # Load active conversations from database
        bot.loop.create_task(self.load_active_conversations())

    def test_model(self, model_name):
        """Test if a model is available (Note: This is a placeholder - in a real implementation,
        you would make an async call to test if the model exists)"""
        # In a real implementation, you would make a synchronous request to check model availability
        # For now, we'll assume it exists
        return True
    
    async def load_active_conversations(self):
        """Load active conversations from database"""
        if self.db is None:
            return
            
        try:
            cursor = self.active_conversations_col.find({})
            async for doc in cursor:
                convo_id = f"{doc['user_id']}-{doc['channel_id']}"
                self.active_conversations.add(convo_id)
                self.last_activity[convo_id] = doc.get('last_activity', datetime.utcnow())
            print(f"AI Cog: Loaded {len(self.active_conversations)} active conversations from database")
        except Exception as e:
            print(f"AI Cog: Error loading active conversations: {e}")

    async def save_conversation(self, user_id: int, channel_id: int, messages: List[Dict]):
        """Save conversation to storage (MongoDB or memory)"""
        if self.conversations is not None:
            try:
                await self.conversations.update_one(
                    {"user_id": user_id, "channel_id": channel_id},
                    {"$set": {"messages": messages, "updated_at": datetime.utcnow()}},
                    upsert=True
                )
                return
            except Exception as e:
                print(f"AI Cog: Error saving to MongoDB: {e}")
        
        # Use in-memory storage as fallback
        self.memory_storage[f"{user_id}-{channel_id}"] = messages

    async def get_conversation(self, user_id: int, channel_id: int) -> List[Dict]:
        """Retrieve conversation history from storage (MongoDB or memory)"""
        if self.conversations is not None:
            try:
                convo = await self.conversations.find_one({"user_id": user_id, "channel_id": channel_id})
                if convo and "messages" in convo:
                    return convo["messages"]
            except Exception as e:
                print(f"AI Cog: Error retrieving from MongoDB: {e}")
        
        # Use in-memory storage as fallback
        return self.memory_storage.get(f"{user_id}-{channel_id}", [])

    def trim_conversation(self, messages: List[Dict]) -> List[Dict]:
        """Trim conversation to fit within limits"""
        # Always keep system instruction (first message)
        if len(messages) <= 1:
            return messages
            
        # Keep system message and the most recent messages up to max_history_messages
        system_message = messages[0]
        recent_messages = messages[-(self.max_history_messages-1):] if len(messages) > self.max_history_messages else messages[1:]
        
        return [system_message] + recent_messages
    
    async def mark_conversation_active(self, user_id: int, channel_id: int):
        """Mark a conversation as active"""
        convo_id = f"{user_id}-{channel_id}"
        self.active_conversations.add(convo_id)
        self.last_activity[convo_id] = datetime.utcnow()
        
        # Store in database if available
        if self.db is not None:
            try:
                await self.active_conversations_col.update_one(
                    {"user_id": user_id, "channel_id": channel_id},
                    {"$set": {"last_activity": datetime.utcnow()}},
                    upsert=True
                )
            except Exception as e:
                print(f"AI Cog: Error storing active conversation: {e}")
    
    async def mark_conversation_inactive(self, user_id: int, channel_id: int):
        """Mark a conversation as inactive"""
        convo_id = f"{user_id}-{channel_id}"
        if convo_id in self.active_conversations:
            self.active_conversations.remove(convo_id)
            
        if convo_id in self.last_activity:
            del self.last_activity[convo_id]
        
        # Remove from database if available
        if self.db is not None:
            try:
                await self.active_conversations_col.delete_one(
                    {"user_id": user_id, "channel_id": channel_id}
                )
            except Exception as e:
                print(f"AI Cog: Error removing active conversation: {e}")
    
    def is_conversation_active(self, user_id: int, channel_id: int) -> bool:
        """Check if a conversation is active"""
        convo_id = f"{user_id}-{channel_id}"
        return convo_id in self.active_conversations
    
    def estimate_token_count(self, messages: List[Dict]) -> int:
        """Estimate the token count in a conversation"""
        # A more accurate implementation would use tiktoken or a similar library
        # For now we'll use a simple approximation
        total_chars = sum(len(message["content"]) for message in messages)
        # Roughly 4 characters per token for English text
        return total_chars // 4
    
    async def cleanup_inactive_conversations(self):
        """Background task to clean up inactive conversations"""
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            try:
                now = datetime.utcnow()
                to_remove = []
                
                # Find inactive conversations
                for convo_id, last_time in self.last_activity.items():
                    if now - last_time > timedelta(minutes=self.conversation_timeout):
                        to_remove.append(convo_id)
                
                # Remove inactive conversations
                for convo_id in to_remove:
                    if convo_id in self.active_conversations:
                        self.active_conversations.remove(convo_id)
                        
                    if convo_id in self.last_activity:
                        del self.last_activity[convo_id]
                        
                    # Get user_id and channel_id from convo_id
                    user_id, channel_id = map(int, convo_id.split('-'))
                    
                    # Remove from database
                    if self.db is not None:
                        try:
                            await self.active_conversations_col.delete_one(
                                {"user_id": user_id, "channel_id": channel_id}
                            )
                        except Exception as e:
                            print(f"AI Cog: Error removing inactive conversation: {e}")
                
                if to_remove:
                    print(f"AI Cog: Cleaned up {len(to_remove)} inactive conversations")
                
                # Run every minute
                await asyncio.sleep(60)
            except Exception as e:
                print(f"AI Cog: Error in cleanup task: {e}")
                await asyncio.sleep(60)

    async def query_gemini_simple(self, messages: List[Dict]) -> str:
        """Simplified Gemini API query for intent detection"""
        gemini_messages = []
        
        for message in messages:
            role = message["role"]
            content = message["content"]
            
            # Map Discord bot roles to Gemini roles
            if role == "system":
                gemini_role = "user"  
                content = f"Instructions: {content}"
            elif role == "user":
                gemini_role = "user"
            elif role == "assistant":
                gemini_role = "model"
            else:
                continue  
                
            gemini_messages.append({
                "role": gemini_role,
                "parts": [{"text": content}]
            })
        
        # Prepare request payload with lower temperature for more deterministic YES/NO response
        payload = {
            "contents": gemini_messages,
            "generationConfig": {
                "temperature": 0.1,
                "maxOutputTokens": 10,
                "topP": 0.95,
                "topK": 40
            }
        }
        
        # Make API request
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.api_endpoint,
                    json=payload,
                    headers={"Content-Type": "application/json"}
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        response_text = result.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                        return response_text
                    else:
                        return "ERROR"
        except Exception as e:
            print(f"AI Cog: Error in simple query: {e}")
            return "ERROR"

    async def detect_end_intent(self, message_text: str) -> bool:
        """Detect if a message indicates intent to end conversation"""
        # This function directly asks the AI if the message indicates an intent to end the conversation
        prompt = [{
            "role": "user", 
            "content": f'Does this message indicate the user wants to end a conversation? Reply with only "YES" or "NO": "{message_text}"'
        }]
        
        response = await self.query_gemini_simple(prompt)
        return "YES" in response.strip().upper()
    
    async def detect_explanation_intent(self, message_text: str) -> bool:
        """Detect if a message indicates the user wants an explanation of something"""
        # This function asks the AI if the message indicates an intent to explain something
        prompt = [{
            "role": "user", 
            "content": f'Does this message indicate the user wants me to explain or analyze something? They might be saying things like "explain this", "what do you think about this", "can you analyze this", etc. Reply with only "YES" or "NO": "{message_text}"'
        }]
        
        response = await self.query_gemini_simple(prompt)
        return "YES" in response.strip().upper()

    async def get_conversation_context(self, channel, referenced_message, context_size=5) -> List[Dict]:
        """Get the conversation context around a referenced message
        
        Args:
            channel: The Discord channel
            referenced_message: The message being replied to
            context_size: Number of messages to get before and after the referenced message
            
        Returns:
            List of message dictionaries with author, content, and timestamp
        """
        context_messages = []
        
        try:
            # Get messages before the referenced message
            before_messages = []
            async for msg in channel.history(limit=context_size, before=referenced_message):
                if not msg.content.startswith("Hey Axis") and not msg.author.bot:
                    before_messages.append({
                        "author": msg.author.display_name,
                        "content": msg.content,
                        "timestamp": msg.created_at.isoformat(),
                        "referenced": False
                    })
            
            # Add the referenced message
            context_messages.append({
                "author": referenced_message.author.display_name,
                "content": referenced_message.content,
                "timestamp": referenced_message.created_at.isoformat(),
                "referenced": True
            })
            
            # Get messages after the referenced message
            after_messages = []
            async for msg in channel.history(limit=context_size, after=referenced_message):
                if not msg.content.startswith("Hey Axis") and not msg.author.bot:
                    after_messages.append({
                        "author": msg.author.display_name,
                        "content": msg.content,
                        "timestamp": msg.created_at.isoformat(),
                        "referenced": False
                    })
            
            # Combine all messages in chronological order
            # Before messages are in reverse order, so reverse them
            context_messages = list(reversed(before_messages)) + context_messages + after_messages
            
            return context_messages
        except Exception as e:
            print(f"AI Cog: Error fetching conversation context: {e}")
            # Return at least the referenced message if we can
            if referenced_message:
                return [{
                    "author": referenced_message.author.display_name,
                    "content": referenced_message.content,
                    "timestamp": referenced_message.created_at.isoformat(),
                    "referenced": True
                }]
            return []

    async def query_gemini(self, messages: List[Dict]) -> str:
        """Query Gemini API"""
        # Format messages for Gemini API
        gemini_messages = []
        
        for message in messages:
            role = message["role"]
            content = message["content"]
            
            # Map Discord bot roles to Gemini roles
            if role == "system":
                gemini_role = "user"  # Gemini doesn't have a system role, use as first user message
                content = f"Instructions for AI assistant: {content}"
            elif role == "user":
                gemini_role = "user"
            elif role == "assistant":
                gemini_role = "model"
            else:
                continue  # Skip unknown roles
                
            gemini_messages.append({
                "role": gemini_role,
                "parts": [{"text": content}]
            })
        
        # Prepare request payload
        payload = {
            "contents": gemini_messages,
            "generationConfig": {
                "temperature": 0.7,
                "maxOutputTokens": 1024,
                "topP": 0.95,
                "topK": 40
            }
        }
        
        # Make API request
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.api_endpoint,
                    json=payload,
                    headers={"Content-Type": "application/json"}
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        
                        # Extract response text from the result
                        try:
                            response_text = result.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                            if not response_text:
                                return "I couldn't generate a response. Please try again."
                            return response_text
                        except (KeyError, IndexError):
                            return "Error parsing the response from Gemini."
                    else:
                        error_text = await response.text()
                        try:
                            error_json = json.loads(error_text)
                            error_message = error_json.get("error", {}).get("message", "Unknown error")
                            return f"Error: {error_message}"
                        except:
                            return f"Error: Status code {response.status}"
        except Exception as e:
            return f"Error connecting to Gemini API: {str(e)}"

    @commands.Cog.listener()
    async def on_message(self, message):
        """Listen for messages and handle conversations"""
        if message.author.bot:
            return
        
        content = message.content.strip()
        user_id = message.author.id
        channel_id = message.channel.id
        
        # Check if this is an active conversation
        is_active = self.is_conversation_active(user_id, channel_id)
        
        # Check if this is a reply to another message
        is_reply = message.reference is not None
        replied_to_msg = None
        
        # Get the message being replied to if this is a reply
        if is_reply:
            try:
                # Fetch the message being replied to
                replied_to_msg = await message.channel.fetch_message(message.reference.message_id)
                
                # Skip if replying to a bot (except our own bot)
                if replied_to_msg.author.bot and not (replied_to_msg.author.id == self.bot.user.id):
                    is_reply = False
            except Exception as e:
                print(f"AI Cog: Error fetching replied message: {e}")
                is_reply = False
                # Continue processing as a normal message
        
        # Check if this is a potential reply analysis request
        if is_reply and content.lower().startswith("hey axis"):
            # Extract the query (remove "Hey Axis" prefix)
            query = content[9:].strip()
            
            # Always check for explanation intent
            try:
                # If query is empty or clearly asking for explanation, skip intent detection
                explicit_explanation_keywords = ["explain", "analyze", "what is", "what's", "what does", "what do", "what are"]
                is_explicit_explanation = any(keyword in query.lower() for keyword in explicit_explanation_keywords) if query else True
                
                # If not explicitly asking for explanation, check intent
                should_explain = is_explicit_explanation or await self.detect_explanation_intent(query)
                
                if should_explain:
                    # This is a reply and the user wants the AI to explain something
                    async with message.channel.typing():
                        # Process the conversation with context from the replied message and its surroundings
                        await self.process_reply_explanation(message, replied_to_msg, query)
                        return
            except Exception as e:
                print(f"AI Cog: Error in reply explanation detection: {e}")
                # Continue with normal processing if explanation detection fails
        
        # Original conversation logic
        if content.lower().startswith("hey axis") or is_active:
            # If user is in an active conversation, first check if they're trying to end it
            # Only do this if the message doesn't start with "Hey Axis" (which would be a new query)
            if is_active and not content.lower().startswith("hey axis"):
                # Use AI to detect if this is an intent to end the conversation
                try:
                    should_end = await self.detect_end_intent(content)
                    if should_end:
                        await self.mark_conversation_inactive(user_id, channel_id)
                        await message.reply("Conversation ended. Feel free to start a new one anytime with 'Hey Axis'!")
                        return
                except Exception as e:
                    print(f"AI Cog: Error detecting end intent: {e}")
                    # Continue with normal processing if intent detection fails
                
            # If message starts with "Hey Axis", remove that part to get the query
            if content.lower().startswith("hey axis"):
                query = content[9:].strip()
                
                # If no query after "Hey Axis", just greet
                if not query:
                    await message.reply("Hey there!")
                    await self.mark_conversation_active(user_id, channel_id)
                    return
            else:
                # Use the entire message as query
                query = content
            
            # Continue only if there's an actual query
            if query:
                async with message.channel.typing():
                    try:
                        # Mark the conversation as active
                        await self.mark_conversation_active(user_id, channel_id)
                        
                        # Process the query
                        await self.process_ai_query(message, query)
                    except Exception as e:
                        print(f"AI Cog: Error processing AI query: {e}")
                        await message.reply(f"Sorry, I encountered an error: {str(e)}")

    async def process_reply_explanation(self, message, replied_to_msg, query_text):
        """Process a request to explain someone's messages in a reply context"""
        user_id = message.author.id
        channel_id = message.channel.id
        
        # Get conversation history or create a new one
        conversation = await self.get_conversation(user_id, channel_id)
        
        # If no conversation yet, add system message
        if not conversation:
            conversation = [{
                "role": "system",
                "content": f"You are Axis, a helpful AI assistant for Discord. Be concise, friendly, and helpful. The user can chat with you in conversation mode, and they don't need to prefix messages with 'Hey Axis' during an active conversation. When analyzing Discord conversations, be confident and insightful. IMPORTANTLY, you should recognize when a user wants to end the conversation, even if they express it casually (e.g., 'that's all I needed', 'thanks for your help', 'I'll talk to you later', etc.). If you detect the user wants to end the conversation, respond appropriately and include {self.end_conversation_token} at the end of your message (which will be automatically removed before the user sees it)."
            }]
        
        # Get the conversation context around the replied message
        context_messages = await self.get_conversation_context(
            message.channel,
            replied_to_msg,
            context_size=5  # Get 5 messages before and after
        )
        
        # Format the conversation context for the AI
        formatted_context = ""
        for i, ctx_msg in enumerate(context_messages):
            prefix = "➤ " if ctx_msg.get("referenced", False) else ""
            formatted_context += f"{prefix}**{ctx_msg['author']}**: {ctx_msg['content']}\n\n"
        
        # Determine the query - either use what comes after "Hey Axis" or use a default intent
        if query_text.strip():
            intent = query_text.strip()
        else:
            intent = "explain this conversation and what they're talking about"
        
        # Create a prompt that includes the context from the conversation
        replied_to_username = replied_to_msg.author.display_name
        prompt = (
            f"I'm in a Discord conversation and I've replied to a message from '{replied_to_username}' "
            f"asking you to {intent}. Here's the conversation context (the message I replied to is marked with ➤):\n\n"
            f"{formatted_context}\n\n"
            f"Please analyze this conversation with confidence and clarity. Focus particularly on the message "
            f"I replied to, but use the surrounding context to give a more accurate and insightful analysis."
        )
        
        # Add the analysis request to the conversation
        conversation.append({
            "role": "user",
            "content": prompt
        })
        
        # Estimate token count and check for warnings
        estimated_tokens = self.estimate_token_count(conversation)
        
        # If approaching token limit, warn user and continue
        if estimated_tokens > self.max_tokens_warning and estimated_tokens <= self.max_tokens_limit:
            await message.reply("⚠️ Our conversation is getting quite long. Consider ending it soon to restart with a fresh context.")
        
        # If exceeding token limit, auto-end conversation
        if estimated_tokens > self.max_tokens_limit:
            await message.reply("Our conversation has reached the context limit. I'll need to end this chat session. Feel free to start a new one with 'Hey Axis'!")
            await self.mark_conversation_inactive(user_id, channel_id)
            await self.clear_conversation(None, user_id, channel_id)
            return
        
        # Trim conversation to fit context window
        trimmed_conversation = self.trim_conversation(conversation)
        
        # Generate response
        response_text = await self.query_gemini(trimmed_conversation)
        
        # Add assistant response to conversation
        conversation.append({
            "role": "assistant",
            "content": response_text
        })
        
        # Save updated conversation
        await self.save_conversation(user_id, channel_id, conversation)
        
        # Mark as active conversation
        await self.mark_conversation_active(user_id, channel_id)
        
        # Send response to user, splitting if necessary
        if len(response_text) > 2000:
            chunks = [response_text[i:i+1990] for i in range(0, len(response_text), 1990)]
            for i, chunk in enumerate(chunks):
                if i == 0:
                    await message.reply(chunk)
                else:
                    await message.channel.send(chunk)
        else:
            await message.reply(response_text)

    async def process_ai_query(self, message, query):
        """Process an AI query and respond"""
        user_id = message.author.id
        channel_id = message.channel.id
        
        # Get conversation history
        conversation = await self.get_conversation(user_id, channel_id)
        
        # If no conversation yet, add system message with smart ending detection instructions
        if not conversation:
            conversation = [{
                "role": "system",
                "content": f"You are Axis, a helpful AI assistant for Discord. Be concise, friendly, and helpful. The user can chat with you in conversation mode, and they don't need to prefix messages with 'Hey Axis' during an active conversation. IMPORTANTLY, you should recognize when a user wants to end the conversation, even if they express it casually (e.g., 'that's all I needed', 'thanks for your help', 'I'll talk to you later', etc.). If you detect the user wants to end the conversation, respond appropriately and include {self.end_conversation_token} at the end of your message (which will be automatically removed before the user sees it)."
            }]
        
        # Add user message
        conversation.append({
            "role": "user",
            "content": query
        })
        
        # Estimate token count and check for warnings
        estimated_tokens = self.estimate_token_count(conversation)
        
        # If approaching token limit, warn user and continue
        if estimated_tokens > self.max_tokens_warning and estimated_tokens <= self.max_tokens_limit:
            await message.reply("⚠️ Our conversation is getting quite long. Consider ending it soon to restart with a fresh context.")
        
        # If exceeding token limit, auto-end conversation
        if estimated_tokens > self.max_tokens_limit:
            await message.reply("Our conversation has reached the context limit. I'll need to end this chat session. Feel free to start a new one with 'Hey Axis'!")
            await self.mark_conversation_inactive(user_id, channel_id)
            await self.clear_conversation(None, user_id, channel_id)
            return
        
        # Trim conversation to fit context window
        trimmed_conversation = self.trim_conversation(conversation)
        
        # Generate response
        response_text = await self.query_gemini(trimmed_conversation)
        
        # Check if AI has indicated to end the conversation with the special token
        if self.end_conversation_token in response_text:
            # Remove the token before showing the response to the user
            clean_response = response_text.replace(self.end_conversation_token, "").strip()
            
            # Add the cleaned response to conversation history
            conversation.append({
                "role": "assistant",
                "content": clean_response
            })
            
            # Save updated conversation
            await self.save_conversation(user_id, channel_id, conversation)
            
            # Send response to user
            if len(clean_response) > 2000:
                chunks = [clean_response[i:i+1990] for i in range(0, len(clean_response), 1990)]
                for i, chunk in enumerate(chunks):
                    if i == 0:
                        await message.reply(chunk)
                    else:
                        await message.channel.send(chunk)
            else:
                await message.reply(clean_response)
            
            # End the conversation since AI indicated it should end
            await self.mark_conversation_inactive(user_id, channel_id)
            return
        
        # Normal response handling if not ending conversation
        # Add assistant response to conversation
        conversation.append({
            "role": "assistant",
            "content": response_text
        })
        
        # Save updated conversation
        await self.save_conversation(user_id, channel_id, conversation)
        
        # Send response to user
        # Split message if it's too long for Discord
        if len(response_text) > 2000:
            chunks = [response_text[i:i+1990] for i in range(0, len(response_text), 1990)]
            for i, chunk in enumerate(chunks):
                if i == 0:
                    await message.reply(chunk)
                else:
                    await message.channel.send(chunk)
        else:
            await message.reply(response_text)

    @commands.command(name="ai-clear")
    async def clear_conversation_command(self, ctx):
        """Clear your conversation history in this channel"""
        user_id = ctx.author.id
        channel_id = ctx.channel.id
        
        await self.clear_conversation(ctx, user_id, channel_id)
    
    async def clear_conversation(self, ctx, user_id, channel_id):
        """Clear conversation helper method"""
        if self.conversations is not None:
            try:
                await self.conversations.delete_one({"user_id": user_id, "channel_id": channel_id})
            except Exception as e:
                print(f"AI Cog: Error clearing conversation in MongoDB: {e}")
                
                # Remove from memory storage if we've switched to memory
                if f"{user_id}-{channel_id}" in self.memory_storage:
                    del self.memory_storage[f"{user_id}-{channel_id}"]
        else:
            # Remove from memory storage
            if f"{user_id}-{channel_id}" in self.memory_storage:
                del self.memory_storage[f"{user_id}-{channel_id}"]
        
        # Send confirmation message if this was called from a command
        if ctx:
            await ctx.send("Your conversation history in this channel has been cleared.")

    @commands.command(name="ai-model")
    async def show_model(self, ctx):
        """Show which Gemini model is being used"""
        await ctx.send(f"Currently using Gemini model: `{self.model_name}`")
    
    @commands.command(name="ai-status")
    async def show_status(self, ctx):
        """Show status of active conversations"""
        user_id = ctx.author.id
        channel_id = ctx.channel.id
        
        is_active = self.is_conversation_active(user_id, channel_id)
        
        if is_active:
            # Get conversation history
            conversation = await self.get_conversation(user_id, channel_id)
            estimated_tokens = self.estimate_token_count(conversation)
            
            await ctx.send(f"You are in an active conversation with Axis.\n"
                          f"Messages in history: {len(conversation) - 1}\n"
                          f"Estimated tokens: {estimated_tokens}/{self.max_tokens_limit}\n"
                          f"The conversation will automatically end after {self.conversation_timeout} minutes of inactivity.")
        else:
            await ctx.send("You are not in an active conversation with Axis. Start one by saying 'Hey Axis'!")

async def setup(bot):
    await bot.add_cog(AICog(bot))
