import discord
from discord.ext import commands
import os # For loading cogs

# Assuming DatabaseManager will be initialized in main.py and passed,
# so direct import might not be needed here if setup_db is called from main.py
# from .database import DatabaseManager 

class AxisBot(commands.Bot):
    def __init__(self, command_prefix, intents, config=None):
        super().__init__(command_prefix=command_prefix, intents=intents)
        self.db_manager = None  # To be initialized by setup_db
        self.config = config    # To be loaded from config.py in main.py
        self.loaded_cogs = {}

    async def setup_db(self, mongo_uri):
        """Initializes the database manager."""
        # This import is here to avoid circular dependency if DatabaseManager needs the bot instance
        from .database import DatabaseManager 
        self.db_manager = DatabaseManager(MONGO_URI=mongo_uri)
        print("Database Manager initialized.")

    async def load_all_cogs(self):
        """Loads all cogs from the ./cogs directory."""
        cogs_directory = "./cogs" 
        if not os.path.exists(cogs_directory):
            os.makedirs(cogs_directory) # Create cogs directory if it doesn't exist
            print(f"Created '{cogs_directory}' directory as it did not exist.")
            return # No cogs to load yet

        for filename in os.listdir(cogs_directory):
            if filename.endswith(".py") and not filename.startswith("__"):
                cog_name = filename[:-3]
                try:
                    await self.load_extension(f"cogs.{cog_name}")
                    self.loaded_cogs[cog_name] = True
                    print(f"Successfully loaded cog: {cog_name}")
                except commands.ExtensionNotFound:
                    print(f"Cog not found: {cog_name}")
                except commands.ExtensionAlreadyLoaded:
                    print(f"Cog already loaded: {cog_name}")
                except commands.NoEntryPointError:
                    print(f"Cog {cog_name} has no setup function.")
                except commands.ExtensionFailed as e:
                    print(f"Failed to load cog {cog_name}: {e}")
                    # Optionally, store the exception: self.loaded_cogs[cog_name] = e

    async def setup_hook(self):
        # Setup database
        if self.config and hasattr(self.config, 'MONGO_URI'):
            await self.setup_db(self.config.MONGO_URI) # setup_db was defined in step 1
            print("Database manager initialized via setup_hook.")
        else:
            print("MONGO_URI not found in config. Database not initialized.")
            # Decide if this is critical and should halt the bot

        # Load core events cog
        try:
            await self.load_extension("core.events")
            print("Loaded core.events cog.")
        except Exception as e:
            print(f"Failed to load core.events cog: {e}")

        # Load all other cogs
        await self.load_all_cogs() # load_all_cogs was defined in step 1
        print("Finished loading application cogs.")

        # Optional: Sync application commands here if needed, or rely on auto-sync
        # For widespread changes, a manual sync by the owner might be safer initially.
        # Example:
        # if self.owner_ids: # Assuming owner_ids is set from config
        #    await self.tree.sync()
        #    print("Synced application commands.")
        # else:
        #    print("Owner ID not set, skipping global command sync. Commands will sync per guild or on first use.")

    # on_ready is now handled by core.events.CoreEvents
    # async def on_ready(self):
    #     # This on_ready is a basic one. Cogs might have their own.
    #     # The CoreEvents cog will also have an on_ready.
    #     print(f"{self.user} is ready and online!")

    # Example of how config might be used if it's passed during init
    def get_prefix(self, message):
        # This is a basic prefix getter. 
        # You might want to allow per-guild prefixes stored in the database.
        if self.config and hasattr(self.config, 'PREFIX'):
            return self.config.PREFIX
        return "!" # Default prefix if not in config or PREFIX attribute is missing

# Example of intents (can be refined in main.py)
# def get_intents():
#     intents = discord.Intents.default()
#     intents.members = True
#     intents.message_content = True
#     return intents
