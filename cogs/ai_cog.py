import discord
from discord.ext import commands
import os
import aiohttp
import asyncio
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
from datetime import datetime
import json
from typing import Dict, List, Optional

class AICog(commands.Cog):
    """AI capabilities for Axis Discord bot using Gemini Flash"""
    
    def __init__(self, bot):
        self.bot = bot
        
        # MongoDB connection with fallback
        self.use_mongodb = True
        try:
            mongodb_uri = os.getenv('MONGODB_URI', 'mongodb://localhost:27017/axisbot')
            self.mongo_client = MongoClient(mongodb_uri, serverSelectionTimeoutMS=5000)
            # Test the connection
            self.mongo_client.admin.command('ping')
            self.db = self.mongo_client['axis_bot_db']
            self.conversations = self.db['conversations']
            print("MongoDB connection successful")
        except (ConnectionFailure, ServerSelectionTimeoutError) as e:
            print(f"MongoDB connection failed: {e}. Using in-memory storage instead.")
            self.use_mongodb = False
            # Fallback to in-memory storage
            self.memory_storage = {}
        
        # API Key for Gemini
        self.gemini_api_key = os.getenv('GEMINI_API_KEY')
        
        # Gemini Flash API endpoint
        self.api_endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash:generateContent?key={self.gemini_api_key}"
        
        # Maximum context size (tokens) for Gemini Flash
        self.max_context_size = 8192  # Adjust based on actual model specs
        
        # Maximum number of messages to keep in history
        self.max_history_messages = 10

    async def save_conversation(self, user_id: int, channel_id: int, messages: List[Dict]):
        """Save conversation to storage (MongoDB or memory)"""
        if self.use_mongodb:
            try:
                await asyncio.to_thread(
                    self.conversations.update_one,
                    {"user_id": user_id, "channel_id": channel_id},
                    {"$set": {"messages": messages, "updated_at": datetime.utcnow()}},
                    upsert=True
                )
            except Exception as e:
                print(f"Error saving to MongoDB: {e}. Using memory storage.")
                self.use_mongodb = False
                self.memory_storage[f"{user_id}-{channel_id}"] = messages
        else:
            # Use in-memory storage
            self.memory_storage[f"{user_id}-{channel_id}"] = messages

    async def get_conversation(self, user_id: int, channel_id: int) -> List[Dict]:
        """Retrieve conversation history from storage (MongoDB or memory)"""
        if self.use_mongodb:
            try:
                convo = await asyncio.to_thread(
                    self.conversations.find_one,
                    {"user_id": user_id, "channel_id": channel_id}
                )
                if convo and "messages" in convo:
                    return convo["messages"]
            except Exception as e:
                print(f"Error retrieving from MongoDB: {e}. Using memory storage.")
                self.use_mongodb = False
                return self.memory_storage.get(f"{user_id}-{channel_id}", [])
        else:
            # Use in-memory storage
            return self.memory_storage.get(f"{user_id}-{channel_id}", [])
        
        return []

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
        """Query Gemini Flash API"""
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
                    print(f"Error processing AI query: {e}")
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
                "content": "You are Axis, a helpful AI assistant for Discord powered by Gemini Flash. Be concise, friendly, and helpful."
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
        
        if self.use_mongodb:
            try:
                await asyncio.to_thread(
                    self.conversations.delete_one,
                    {"user_id": user_id, "channel_id": channel_id}
                )
            except Exception as e:
                print(f"Error clearing conversation in MongoDB: {e}")
                self.use_mongodb = False
                
                # Remove from memory storage if we've switched to memory
                if f"{user_id}-{channel_id}" in self.memory_storage:
                    del self.memory_storage[f"{user_id}-{channel_id}"]
        else:
            # Remove from memory storage
            if f"{user_id}-{channel_id}" in self.memory_storage:
                del self.memory_storage[f"{user_id}-{channel_id}"]
                
        await ctx.send("Your conversation history in this channel has been cleared.")

async def setup(bot):
    await bot.add_cog(AICog(bot))
