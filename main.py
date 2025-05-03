# main.py
import os
import discord
import asyncio
from core.bot import AxisBot
from core.events import EventDispatcher
from dotenv import load_dotenv
from utils.command_loader import CommandLoader

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
    from systems.marketplace import MarketplaceSystem
    from systems.tickets import TicketSystem
    from systems.fun import FunSystem
    from systems.ai import AISystem
    from systems.utility import UtilitySystem
    
    # Create system instances
    leveling_system = LevelingSystem(bot)
    starboard_system = StarboardSystem(bot)
    moderation_system = ModerationSystem(bot)
    marketplace_system = MarketplaceSystem(bot)
    ticket_system = TicketSystem(bot)
    fun_system = FunSystem(bot)
    ai_system = AISystem(bot)
    utility_system = UtilitySystem(bot)
    
    # Register systems with the bot
    bot.register_system("LevelingSystem", leveling_system)
    bot.register_system("StarboardSystem", starboard_system)
    bot.register_system("ModerationSystem", moderation_system)
    bot.register_system("MarketplaceSystem", marketplace_system)
    bot.register_system("TicketSystem", ticket_system)
    bot.register_system("FunSystem", fun_system)
    bot.register_system("AISystem", ai_system)
    bot.register_system("UtilitySystem", utility_system)
    
    # Initialize all systems in priority order
    # Moderation first as it's critical
    await moderation_system.initialize()
    # Then core systems
    await ai_system.initialize()
    await leveling_system.initialize()
    await starboard_system.initialize()
    # Then secondary systems
    await marketplace_system.initialize()
    await ticket_system.initialize()
    await utility_system.initialize()
    await fun_system.initialize()

async def load_commands():
    """Load all command files"""
    # Use the CommandLoader utility to load all commands
    await CommandLoader.load_all_commands(bot)

async def cleanup_systems():
    """Clean up all systems properly before shutdown"""
    print("Cleaning up systems...")
    
    # Get all registered systems
    for system_name, system in bot.systems.items():
        if hasattr(system, 'cleanup'):
            try:
                await system.cleanup()
                print(f"Cleaned up {system_name}")
            except Exception as e:
                print(f"Error cleaning up {system_name}: {e}")

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
