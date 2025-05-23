from botMain.dependencies import (
    commands,
    intents,
    MONGO_URI,
    motor,
    datetime,
    os,
)

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
        
    @property
    def currently_syncing(self):
        """Check if sync is in progress, with timeout protection"""
        if self.sync_start_time is None:
            return False
        
        # Check if sync has been running too long (timeout)
        elapsed = (datetime.datetime.now() - self.sync_start_time).total_seconds()
        if elapsed > self.sync_timeout:
            print(f"⚠️ Sync operation timed out after {elapsed:.1f} seconds")
            self.sync_start_time = None  # Auto-reset
            return False
            
        return True
        
    def start_sync(self):
        """Mark sync as started with timestamp"""
        self.sync_start_time = datetime.datetime.now()
        
    def end_sync(self):
        """Mark sync as complete"""
        self.sync_start_time = None
        
    async def setup_hook(self):
        # Auto-load all cogs from the cogs directory
        print("Loading cogs...")
        for filename in os.listdir('./cogs'):
            if filename.endswith('.py'):
                try:
                    cog_name = f"cogs.{filename[:-3]}"
                    await self.load_extension(cog_name)
                    print(f"Loaded extension {cog_name}")
                except Exception as e:
                    print(f"Failed to load extension {filename}: {e}")
                    
        print("Cogs loaded successfully.")
        print("⚠️ IMPORTANT: Command syncing is COMPLETELY DISABLED to prevent rate limits.")
        print("⚠️ Use !sync_status to check which commands need syncing.")