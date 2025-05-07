# main.py
import os
import sys
import inspect
import importlib
import pkgutil
import discord
import asyncio
import logging
from datetime import datetime
from core.bot import AxisBot
from core.events import EventDispatcher
from core.database import DatabaseManager
from dotenv import load_dotenv
from utils.command_loader import CommandLoader
from systems.base_system import System
from systems.music import MusicSystem

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f"logs/bot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('axis_bot')

# Load environment variables
load_dotenv()

# Initialize the bot with our custom class
bot = AxisBot(command_prefix=os.getenv("COMMAND_PREFIX", "!"))

# System initialization priority
# Higher priority systems are initialized first
SYSTEM_PRIORITIES = {
    "BasicSystem": 100,
    "ModerationSystem": 90,
    "AISystem": 80,
    "LevelingSystem": 70,
    "StarboardSystem": 60,
    "MarketplaceSystem": 50,
    "TicketSystem": 40,
    "UtilitySystem": 30,
    "FunSystem": 20,
    "MusicSystem": 10,
}

# Critical systems that must be initialized for the bot to function
CRITICAL_SYSTEMS = ["BasicSystem", "ModerationSystem"]

async def discover_systems():
    """Dynamically discover all available system modules"""
    import systems
    
    discovered_systems = []
    system_modules = {}
    
    # Find all subpackages in the systems package
    for _, name, ispkg in pkgutil.iter_modules(systems.__path__, systems.__name__ + '.'):
        if ispkg and name != 'systems.base_system':
            try:
                # Import the module
                module = importlib.import_module(name)
                system_modules[name] = module
                
                # Find the system class in the module
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if (inspect.isclass(attr) and 
                        issubclass(attr, System) and 
                        attr is not System):
                        
                        system_name = attr.__name__
                        
                        # Get priority or use default
                        priority = SYSTEM_PRIORITIES.get(system_name, 0)
                        critical = system_name in CRITICAL_SYSTEMS
                        
                        discovered_systems.append({
                            "name": system_name,
                            "class": attr,
                            "module": module,
                            "priority": priority,
                            "critical": critical
                        })
                        
                        logger.info(f"Discovered system: {system_name}")
                        break
            except Exception as e:
                logger.error(f"Error discovering system {name}: {e}")
    
    # Sort systems by priority (highest first)
    discovered_systems.sort(key=lambda s: s["priority"], reverse=True)
    
    return discovered_systems

async def load_systems():
    """Load and initialize all systems"""
    # Discover all available systems
    systems_info = await discover_systems()
    
    # Create and register system instances
    for system_info in systems_info:
        system_name = system_info["name"]
        system_class = system_info["class"]
        
        try:
            # Create instance
            system_instance = system_class(bot)
            
            # Register with bot
            bot.register_system(system_name, system_instance)
            # Add to the info dictionary for initialization
            system_info["instance"] = system_instance
            
            logger.info(f"Registered system: {system_name}")
        except Exception as e:
            logger.error(f"Error creating system {system_name}: {e}", exc_info=True)
            system_info["instance"] = None
            
            if system_info["critical"]:
                logger.critical(f"Failed to create critical system {system_name}. Shutting down.")
                return False
    
    # Initialize all systems
    for system_info in systems_info:
        system_name = system_info["name"]
        system_instance = system_info.get("instance")
        
        if system_instance is None:
            continue
            
        try:
            logger.info(f"Initializing {system_name}...")
            await system_instance.initialize()
            logger.info(f"✅ {system_name} initialized successfully")
        except Exception as e:
            logger.error(f"❌ Error initializing {system_name}: {e}", exc_info=True)
            if system_info["critical"]:
                logger.critical(f"Critical system {system_name} failed to initialize. Shutting down.")
                return False
    
    return True

async def load_commands():
    """Load all command files"""
    try:
        # Use the CommandLoader utility to load all commands
        loaded, errors = await CommandLoader.load_all_commands(bot)
        logger.info(f"Loaded {loaded} commands with {errors} errors")
        return True
    except Exception as e:
        logger.error(f"Failed to load commands: {e}", exc_info=True)
        return False

async def cleanup_systems():
    """Clean up all systems properly before shutdown"""
    logger.info("Cleaning up systems...")
    
    # Get all registered systems
    for system_name, system in bot.systems.items():
        if hasattr(system, 'cleanup'):
            try:
                await system.cleanup()
                logger.info(f"Cleaned up {system_name}")
            except Exception as e:
                logger.error(f"Error cleaning up {system_name}: {e}", exc_info=True)

def check_environment():
    """Validate required environment variables"""
    logger.info("Checking environment variables...")
    required_vars = ['DISCORD_TOKEN', 'MONGO_URI']
    
    missing = []
    for var in required_vars:
        if not os.getenv(var):
            missing.append(var)
    
    if missing:
        logger.critical(f"Missing required environment variables: {', '.join(missing)}")
        logger.critical("Please check your .env file")
        return False
    
    return True

def create_directories():
    """Create necessary directories"""
    directories = ['logs', 'data']
    
    for directory in directories:
        if not os.path.exists(directory):
            os.makedirs(directory)
            logger.info(f"Created directory: {directory}")

@bot.event
async def on_ready():
    """Called when the bot is ready"""
    logger.info(f"Bot is ready. Logged in as {bot.user}")
    
    try:
        # Initialize database manager
        bot.db_manager = DatabaseManager(bot)
        logger.info("Database manager initialized")
        
        # Set up the event dispatcher
        event_dispatcher = EventDispatcher(bot)
        await event_dispatcher.setup()
        logger.info("Event dispatcher set up")
        
        # Load systems
        systems_loaded = await load_systems()
        if not systems_loaded:
            logger.critical("Failed to load critical systems. Shutting down.")
            await bot.close()
            return
        
        # Load commands
        commands_loaded = await load_commands()
        if not commands_loaded:
            logger.error("Failed to load commands.")
        
        # Set bot activity
        status_text = os.getenv("BOT_STATUS", "over everything.")
        await bot.change_presence(activity=discord.Activity(
            type=discord.ActivityType.watching, 
            name=status_text
        ))
        
        logger.info("Bot setup complete and ready to go!")
    except Exception as e:
        logger.critical(f"Error during bot initialization: {e}", exc_info=True)
        await bot.close()

@bot.event
async def on_disconnect():
    """Called when the bot disconnects from Discord"""
    # Perform cleanup
    try:
        logger.info("Bot disconnected. Cleaning up...")
        await cleanup_systems()
    except Exception as e:
        logger.error(f"Error during cleanup: {e}", exc_info=True)

@bot.event
async def on_application_command_error(interaction: discord.Interaction, error: Exception):
    """Handle slash command errors"""
    if isinstance(error, discord.app_commands.errors.CommandOnCooldown):
        await interaction.response.send_message(
            f"This command is on cooldown. Try again in {error.retry_after:.1f} seconds.",
            ephemeral=True
        )
    elif isinstance(error, discord.app_commands.errors.MissingPermissions):
        await interaction.response.send_message(
            f"You don't have permission to use this command: {str(error)}",
            ephemeral=True
        )
    elif isinstance(error, discord.app_commands.errors.BotMissingPermissions):
        await interaction.response.send_message(
            f"I don't have the necessary permissions to execute this command: {str(error)}",
            ephemeral=True
        )
    else:
        # Log the error
        logger.error(f"Command error in {interaction.command.name if interaction.command else 'unknown'}: {str(error)}", exc_info=True)
        
        # Notify user
        if interaction.response.is_done():
            await interaction.followup.send(
                "An error occurred while executing this command. Please try again later.",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "An error occurred while executing this command. Please try again later.",
                ephemeral=True
            )

# Run the bot
if __name__ == "__main__":
    # Create necessary directories
    create_directories()
    
    # Check environment variables
    if not check_environment():
        sys.exit(1)
    
    # Get token
    token = os.getenv("DISCORD_TOKEN")
    
    try:
        logger.info("Starting bot...")
        bot.run(token.strip())
    except discord.LoginFailure:
        logger.critical("Error: Invalid Discord token")
        sys.exit(1)
    except Exception as e:
        logger.critical(f"Error starting bot: {e}", exc_info=True)
        sys.exit(1)
    finally:
        logger.info("Bot has shut down")
