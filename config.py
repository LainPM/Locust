# config.py
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Bot configuration
PREFIX = os.getenv("COMMAND_PREFIX", "!")
TOKEN = os.getenv("DISCORD_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Bot settings
OWNERS = [int(id.strip()) for id in os.getenv("OWNER_IDS", "").split(",") if id.strip()]
DEFAULT_STATUS = os.getenv("BOT_STATUS", "over everything.")

# Feature toggles
ENABLE_AI = os.getenv("ENABLE_AI", "true").lower() == "true"
ENABLE_MUSIC = os.getenv("ENABLE_MUSIC", "true").lower() == "true"

# Check required config
def validate_config():
    """Validate that required config variables are set"""
    missing = []
    
    if not TOKEN:
        missing.append("DISCORD_TOKEN")
    if not MONGO_URI:
        missing.append("MONGO_URI")
    
    return missing
