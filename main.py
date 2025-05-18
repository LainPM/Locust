from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
import discord
from discord.app_commands import AppCommand
import os
import asyncio
import motor.motor_asyncio
import datetime
import traceback
from discord import AppInfo
from typing import Optional, Dict, Any
import aiohttp

# Load environment variables
load_dotenv()

# Set up intents
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

# MongoDB setup
MONGO_URI = os.getenv("MONGO_URI")

# Discord API base URL
DISCORD_API_URL = "https://discord.com/api/v10"

# Override discord.py's CommandTree.sync method to prevent automatic syncing
original_sync = app_commands.CommandTree.sync

async def disabled_sync(*args, **kwargs):
    print("⚠️ SYNC ATTEMPT BLOCKED: Command sync was attempted but is disabled")
    print(f"Called with args: {args}, kwargs: {kwargs}")
    print("Use !sync_status and manual sync commands instead")
    return []

# Apply the monkey patch
app_commands.CommandTree.sync = disabled_sync

class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)
        
        # Initialize MongoDB connection
        self.mongo_client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URI)
        self.db = self.mongo_client["discord_bot"]
        self.warnings_collection = self.db["warnings"]
        
        # Currently syncing flag with timestamp
        self.sync_start_time = None
        self.sync_timeout = 600  # 10 minutes max for a sync operation
        
        # Cache for registered commands
        self.registered_commands = []
        self.last_command_fetch = None
        self._app: Optional[AppInfo] = None
        self._session: Optional[aiohttp.ClientSession] = None
        
    async def setup_hook(self):
        self._session = aiohttp.ClientSession()
        # Rest of setup_hook implementation...
        
    async def close(self):
        if self._session:
            await self._session.close()
        await super().close()
        
    async def get_app(self) -> AppInfo:
        """Get or fetch application info"""
        if not self._app:
            self._app = await self.application_info()
        return self._app
        
    async def _make_request(self, method: str, endpoint: str, json: Optional[Dict[str, Any]] = None) -> Any:
        """Helper method to make Discord API requests"""
        if not self._session:
            self._session = aiohttp.ClientSession()
            
        headers = {
            "Authorization": f"Bot {self.http.token}",
            "Content-Type": "application/json"
        }
        
        url = f"https://discord.com/api/v10{endpoint}"
        
        async with self._session.request(method, url, headers=headers, json=json) as resp:
            if resp.status == 429:  # Rate limited
                data = await resp.json()
                retry_after = data.get('retry_after', 0)
                print(f"Rate limited, retry after: {retry_after} seconds")
                raise discord.HTTPException(resp, data)
                
            resp.raise_for_status()
            return await resp.json()
        
    async def _sync_request(self, command_data, guild_id=None):
        """Internal method to make the actual sync request"""
        try:
            app = await self.get_app()
            if not app:
                raise AttributeError("Failed to get application info")
                
            try:
                endpoint = f"/applications/{app.id}/commands"
                if guild_id:
                    endpoint = f"/applications/{app.id}/guilds/{guild_id}/commands"
                    
                result = await self._make_request("POST", endpoint, json=command_data)
                return True, result
            except discord.HTTPException as e:
                print(f"HTTP error during sync: {e}")
                return False, e

        except Exception as e:
            print(f"Sync request error: {e}")
            return False, e
            
    async def get_registered_commands(self, force_refresh=False):
        """Get all commands currently registered with Discord"""
        now = datetime.datetime.now()
        
        # Use cached result if available and recent
        try:
            if (not force_refresh and 
                self.last_command_fetch is not None and 
                isinstance(self.last_command_fetch, datetime.datetime) and
                (now - self.last_command_fetch).total_seconds() < 300):
                return self.registered_commands
        except (TypeError, AttributeError):
            pass
        
        try:
            app = await self.get_app()
            if not app:
                raise AttributeError("Failed to get application info")
                
            try:
                endpoint = f"/applications/{app.id}/commands"
                commands = await self._make_request("GET", endpoint)
                
                # Update cache
                self.registered_commands = commands
                self.last_command_fetch = now
                
                return commands
            except discord.HTTPException as e:
                print(f"HTTP error fetching registered commands: {e}")
                return self.registered_commands if self.registered_commands else []

        except Exception as e:
            print(f"Unexpected error fetching registered commands: {e}")
            print(traceback.format_exc())
            return self.registered_commands if self.registered_commands else []
            
    def get_command_json(self, command):
        """Extract JSON data from a command"""
        data = {
            "name": command.name,
            "description": command.description or "No description provided"
        }
        
        # Add options/parameters if present
        options = []
        for param in getattr(command, 'parameters', []):
            option = {
                "name": param.name,
                "description": param.description or "No description provided",
                "required": getattr(param, 'required', False),
                "type": 3  # Default to string type
            }
            
            # Add choices if any
            if hasattr(param, 'choices') and param.choices:
                option["choices"] = [
                    {"name": str(choice.name), "value": str(choice.value)}
                    for choice in param.choices
                ]
            
            options.append(option)
        
        if options:
            data["options"] = options
        
        return data
    
    def is_command_synced(self, command, registered_commands):
        """Check if a command is already properly synced with Discord"""
        command_data = self.get_command_json(command)
        
        for reg_cmd in registered_commands:
            if isinstance(reg_cmd, dict):
                reg_name = reg_cmd.get("name")
            else:
                reg_name = getattr(reg_cmd, "name", None)
                
            if reg_name == command_data["name"]:
                return True
        return False

# Create bot instance
bot = MyBot()

@bot.command()
@commands.is_owner()
async def sync_status(ctx):
    """Check the current sync status and list commands that need syncing"""
    status_message = await ctx.send("Fetching command status...")
