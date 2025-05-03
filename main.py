# main.py
import os
import discord
import asyncio
from core.bot import AxisBot
from core.events import EventDispatcher
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize the bot with our custom class
bot = AxisBot(command_prefix="!")

async def load_systems():
    """Load and initialize all systems"""
    # Import systems
    from systems.leveling import LevelingSystem
    
    # Create system instances
    leveling_system = LevelingSystem(bot)
    
    # Register systems with the bot
    bot.register_system("LevelingSystem", leveling_system)
    
    # Initialize all systems
    await leveling_system.initialize()

async def load_commands():
    """Load all command files"""
    # Will load all command modules from the commands/ directory
    # For now, we'll just load the rank command directly
    await bot.load_extension("commands.leveling.rank")

@bot.event
async def on_ready():
    """Called when the bot is ready"""
    print(f"Bot is ready. Logged in as {bot.user}")
    
    # Set up the event dispatcher
    event_dispatcher = EventDispatcher(bot)
    await event_dispatcher.setup()
    
    # Load systems
    await load_systems()
    
    # Load commands
    await load_commands()
    
    # Set bot activity
    await bot.change_presence(activity=discord.Activity(
        type=discord.ActivityType.watching, 
        name="over everything."
    ))
    
    print("Bot setup complete and ready to go!")

# Run the bot
if __name__ == "__main__":
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("Error: No Discord token found in .env file")
        exit(1)
        
    try:
        bot.run(token.strip())
    except discord.LoginFailure:
        print("Error: Invalid Discord token")
    except Exception as e:
        print(f"Error starting bot: {e}")
