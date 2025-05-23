# main.py
import os
import sys
# main.py
import os
import sys
import asyncio
import logging
from datetime import datetime
import discord
from dotenv import load_dotenv
import config # Import the config module
from core.bot import AxisBot
from core.database import DatabaseManager # Retained for type hinting or direct use if needed

# Create necessary directories
os.makedirs('logs', exist_ok=True)
# Ensure cogs directory exists - AxisBot.load_all_cogs() also does this
os.makedirs('cogs', exist_ok=True) 

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

# Initialize the bot
intents = discord.Intents.default()
intents.members = True  # Enable member intent
intents.message_content = True # Enable message content intent
bot = AxisBot(command_prefix=config.PREFIX, intents=intents, config=config)
# The config object is now passed during AxisBot initialization, 
# so bot.config = config is handled in AxisBot's __init__ if you set it there.
# If not, uncomment the line below:
# bot.config = config


def create_directories():
    """Create necessary directories if they don't exist."""
    # logs and cogs are created above, adding 'data' as it was in the original
    directories = ['data'] 
    for directory in directories:
        if not os.path.exists(directory):
            os.makedirs(directory)
            logger.info(f"Created directory: {directory}")

def check_environment_from_config():
    """Validate required environment variables using config.py"""
    logger.info("Checking environment variables from config...")
    missing = config.validate_config() # This function is in config.py
    if missing:
        logger.critical(f"Missing or invalid configuration for: {', '.join(missing)}")
        logger.critical("Please check your .env file and config.py settings.")
        return False
    logger.info("Environment configuration validated successfully.")
    return True

# Global error handler for application commands
@bot.event
async def on_application_command_error(interaction: discord.Interaction, error: Exception):
    """Global handler for slash command errors."""
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
        logger.error(f"Unhandled command error in '{interaction.command.name if interaction.command else 'unknown command'}': {error}", exc_info=True)
        if interaction.response.is_done():
            await interaction.followup.send("An unexpected error occurred. Please try again later.", ephemeral=True)
        else:
            await interaction.response.send_message("An unexpected error occurred. Please try again later.", ephemeral=True)

async def main_async():
    """Asynchronous main function to start the bot."""
    try:
        logger.info("Starting bot...")
        # The bot.setup_hook() will be called automatically by bot.start()
        # This includes DB initialization and cog loading.
        await bot.start(config.TOKEN.strip())
    except discord.LoginFailure:
        logger.critical("Error: Invalid Discord token. Check your .env or config.py.")
        sys.exit(1)
    except Exception as e:
        logger.critical(f"Critical error starting bot: {e}", exc_info=True)
        sys.exit(1)
    finally:
        if not bot.is_closed(): # Ensure cleanup only if bot didn't close properly
            await bot.close() # Gracefully close the bot and run cleanup
        logger.info("Bot has shut down.")

if __name__ == "__main__":
    create_directories() # Create 'data' directory if needed
    
    if not check_environment_from_config(): # Validate config
        sys.exit(1)
    
    asyncio.run(main_async())
