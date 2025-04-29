import os
import discord
import asyncio
from discord.ext import commands
from dotenv import load_dotenv
import motor.motor_asyncio

load_dotenv()
intents = discord.Intents.default()
intents.message_content = True  # Required to read message content

# MongoDB setup
MONGO_URI = os.getenv("MONGO_URI")

class MyBot(commands.Bot):
    def __init__(self):
        # Fix: Set a valid command prefix
        super().__init__(command_prefix="!", intents=intents)
        # Initialize MongoDB connection
        self.mongo_client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URI)
        self.db = self.mongo_client["discord_bot"]
        self.warnings_collection = self.db["warnings"]
        
    async def setup_hook(self):
        # Auto-load all cogs from the cogs directory
        print("Loading cogs...")
        for filename in os.listdir('./cogs'):
            if filename.endswith('.py'):
                try:
                    cog_name = f"cogs.{filename[:-3]}"  # Remove .py extension
                    await self.load_extension(cog_name)
                    print(f"Loaded extension {cog_name}")
                except Exception as e:
                    print(f"Failed to load extension {filename}: {e}")
                    
        print("Cogs loaded successfully.")

    # Override to disable text command processing but still allow on_message events
    async def process_commands(self, message):
        # Skip processing text commands completely
        return

bot = MyBot()

@bot.event
async def on_ready():
    print(f"Bot is ready. Logged in as {bot.user}")
    
    # Sync commands with Discord
    print("Syncing slash commands...")
    try:
        # For global commands (available in all servers where the bot is)
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s) globally")
        
    except Exception as e:
        print(f"Failed to sync commands: {e}")

# Add message listener to respond to "hi"
#@bot.event
#async def on_message(message):
    # Ignore messages from the bot itself to prevent potential loops
#    if message.author == bot.user:
        return
    
    # Check if message content is "hi" (case insensitive)
#    if message.content.lower() in ["hi", "hello", "hey"]:
#        await message.channel.send(f"Hi {message.author.mention}! How can I help you today?")
    
    # Don't call process_commands since we've disabled it

if __name__ == "__main__":
    bot.run(os.getenv("DISCORD_TOKEN").strip())
