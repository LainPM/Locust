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
    from systems.starboard import StarboardSystem
    from systems.moderation import ModerationSystem
    
    # Create system instances
    leveling_system = LevelingSystem(bot)
    starboard_system = StarboardSystem(bot)
    moderation_system = ModerationSystem(bot)
    
    # Register systems with the bot
    bot.register_system("LevelingSystem", leveling_system)
    bot.register_system("StarboardSystem", starboard_system)
    bot.register_system("ModerationSystem", moderation_system)
    
    # Initialize all systems in priority order (moderation first)
    await moderation_system.initialize()
    await leveling_system.initialize()
    await starboard_system.initialize()

async def load_commands():
    """Load all command files"""
    # Will load all command modules from the commands/ directory
    # For now, we'll just load specific commands
    await bot.load_extension("commands.leveling.rank")
    await bot.load_extension("commands.starboard.setup")
    await bot.load_extension("commands.moderation.setup")

async def cleanup_systems():
    """Clean up all systems properly before shutdown"""
    print("Cleaning up systems...")
    
    # Clean up starboard system
    starboard_system = await bot.get_system("StarboardSystem")
    if starboard_system:
        await starboard_system.cleanup()

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

@bot.event
async def on_disconnect():
    """Called when the bot disconnects from Discord"""
    # Perform cleanup
    try:
        await cleanup_systems()
    except Exception as e:
        print(f"Error during cleanup: {e}")

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
