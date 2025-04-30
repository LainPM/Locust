import discord
from discord.ext import commands
import os
import aiohttp
import asyncio
import json
from datetime import datetime
from typing import Dict, List, Optional

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
                print("AI Cog: Successfully connected to MongoDB")
            except Exception as e:
                print(f"AI Cog: Error connecting to MongoDB: {e}")
                self.db = None
        
        # In-memory storage fallback
        self.memory_storage = {}
        
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

    def test_model(self, model_name):
        """Test if a model is available (Note: This is a placeholder - in a real implementation,
        you would make an async call to test if the model exists)"""
        # In a real implementation, you would make a synchronous request to check model availability
        # For now, we'll assume it exists
        return True

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
        """Listen for 'Hey Axis' messages"""
        if message.author.bot:
            return
        
        content = message.content.strip().lower()
        
        # Check if message starts with "Hey Axis"
        if content.startswith("hey axis"):
            # Remove the trigger phrase and get the actual query
            query = message.content[9:].strip()
            
            if not query:
                await message.channel.send("Hey there! How can I help you today?")
                return
            
            async with message.channel.typing():
                try:
                    await self.process_ai_query(message, query)
                except Exception as e:
                    print(f"AI Cog: Error processing AI query: {e}")
                    await message.channel.send(f"Sorry, I encountered an error: {str(e)}")

    async def process_ai_query(self, message, query):
        """Process an AI query and respond"""
        user_id = message.author.id
        channel_id = message.channel.id
        
        # Get conversation history
        conversation = await self.get_conversation(user_id, channel_id)
        
        # If no conversation yet, add system message
        if not conversation:
            conversation = [{
                "role": "system",
                "content": "You are Axis, a helpful AI assistant for Discord. Be concise, friendly, and helpful."
            }]
        
        # Add user message
        conversation.append({
            "role": "user",
            "content": query
        })
        
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
    async def clear_conversation(self, ctx):
        """Clear your conversation history in this channel"""
        user_id = ctx.author.id
        channel_id = ctx.channel.id
        
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
                
        await ctx.send("Your conversation history in this channel has been cleared.")

    @commands.command(name="ai-model")
    async def show_model(self, ctx):
        """Show which Gemini model is being used"""
        await ctx.send(f"Currently using Gemini model: `{self.model_name}`")

async def setup(bot):
    await bot.add_cog(AICog(bot))
