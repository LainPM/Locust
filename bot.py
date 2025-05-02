import os
import discord
import asyncio
import datetime
import hashlib
import json
import random
import sys
import aiohttp
from datetime import timedelta
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
import motor.motor_asyncio

# Load environment variables
load_dotenv()

# Set up intents
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

# MongoDB setup
MONGO_URI = os.getenv("MONGO_URI")

class RateLimitHandler:
    """Custom handler for tracking and managing rate limits"""
    def __init__(self, bot):
        self.bot = bot
        self.rate_limits = {}
        self.sync_cooldown_until = None
    
    async def log_rate_limit(self, endpoint, retry_after):
        """Log rate limit occurrences for monitoring"""
        now = datetime.datetime.utcnow()
        
        # Store in memory
        if endpoint not in self.rate_limits:
            self.rate_limits[endpoint] = []
        
        self.rate_limits[endpoint].append({
            "timestamp": now,
            "retry_after": retry_after
        })
        
        # Limit to last 20 events per endpoint
        if len(self.rate_limits[endpoint]) > 20:
            self.rate_limits[endpoint] = self.rate_limits[endpoint][-20:]
        
        # Store in database for persistence
        try:
            await self.bot.db.rate_limits.insert_one({
                "endpoint": endpoint,
                "timestamp": now,
                "retry_after": retry_after
            })
        except Exception as e:
            print(f"Failed to log rate limit to database: {e}")
    
    async def should_sync_commands(self):
        """Determine if we should sync commands based on rate limit history"""
        if self.sync_cooldown_until and datetime.datetime.utcnow() < self.sync_cooldown_until:
            # Still in cooldown period
            time_left = (self.sync_cooldown_until - datetime.datetime.utcnow()).total_seconds()
            print(f"Skipping command sync due to cooldown. Try again in {time_left:.2f} seconds")
            return False
        
        # Check recent rate limits on application endpoints
        app_endpoints = [e for e in self.rate_limits.keys() if "applications" in e]
        recent_limits = []
        
        for endpoint in app_endpoints:
            recent = [r for r in self.rate_limits.get(endpoint, []) 
                      if (datetime.datetime.utcnow() - r["timestamp"]).total_seconds() < 3600]
            recent_limits.extend(recent)
        
        # If we've hit multiple rate limits in the last hour, impose a cooldown
        if len(recent_limits) >= 3:
            # Add exponential backoff with jitter
            base_cooldown = 1800  # 30 minutes
            multiplier = min(2 ** (len(recent_limits) - 3), 8)  # Cap at 8x
            jitter = random.uniform(0.8, 1.2)
            cooldown = base_cooldown * multiplier * jitter
            
            self.sync_cooldown_until = datetime.datetime.utcnow() + timedelta(seconds=cooldown)
            print(f"Too many recent rate limits. Command sync cooldown for {cooldown:.2f} seconds")
            return False
        
        return True

class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)
        
        # Custom rate limit handling
        self.rate_limit_handler = RateLimitHandler(self)
        
        # Initialize MongoDB with better connection parameters
        self.mongo_client = motor.motor_asyncio.AsyncIOMotorClient(
            MONGO_URI,
            serverSelectionTimeoutMS=5000,
            connectTimeoutMS=10000,
            retryWrites=True
        )
        self.db = self.mongo_client["discord_bot"]
        self.warnings_collection = self.db["warnings"]
        
        # Track if we've synced commands during this session
        self.has_synced_this_session = False
        
        # Configure custom HTTP session with proper headers and backoff
        # This will be applied to discord.py's internal HTTP client
        self._http_config = {
            "retry_rate_limit": True,
            "max_retries": 5
        }
        
    async def get_commands_hash(self):
        """Generate a deterministic hash of the current command structure"""
        commands = []
        for cmd in self.tree.get_commands():
            cmd_dict = {
                "name": cmd.name,
                "description": cmd.description,
                "parameters": sorted([
                    {
                        "name": param.name,
                        "description": param.description,
                        "required": param.required
                    }
                    for param in cmd.parameters
                ], key=lambda x: x["name"])
            }
            commands.append(cmd_dict)
        
        commands.sort(key=lambda x: x["name"])
        commands_str = json.dumps(commands, sort_keys=True)
        return hashlib.sha256(commands_str.encode()).hexdigest()
    
    async def setup_hook(self):
        # Ensure rate limits collection exists
        collections = await self.db.list_collection_names()
        if "rate_limits" not in collections:
            await self.db.create_collection("rate_limits")
            # Create TTL index to auto-expire old rate limit records after 7 days
            await self.db.rate_limits.create_index(
                "timestamp", 
                expireAfterSeconds=7*24*60*60
            )
        
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
        
    async def process_commands(self, message):
        if message.content.startswith(self.command_prefix):
            ctx = await self.get_context(message)
            if ctx.command is not None:
                await self.invoke(ctx)
    
    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.CommandNotFound):
            return
        elif isinstance(error, commands.MissingPermissions):
            await ctx.send("You don't have permission to use this command.")
        elif isinstance(error, commands.BotMissingPermissions):
            await ctx.send("I don't have the necessary permissions to do that.")
        elif isinstance(error, commands.CommandOnCooldown):
            # Add jitter to cooldown response
            retry_after = error.retry_after * random.uniform(0.9, 1.1)
            await ctx.send(
                f"This command is on cooldown. Try again in {retry_after:.2f} seconds."
            )
        elif isinstance(error, discord.HTTPException) and error.status == 429:
            # Handle rate limits specially
            await self.rate_limit_handler.log_rate_limit(
                f"command:{ctx.command.name}", error.retry_after
            )
            await ctx.send(
                "This action is being rate limited by Discord. Please try again later."
            )
        else:
            print(f"Command error: {error}")
            await ctx.send(f"An error occurred: {error}")
    
    async def on_app_command_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.CommandOnCooldown):
            # Add jitter to cooldown response
            retry_after = error.retry_after * random.uniform(0.9, 1.1)
            await interaction.response.send_message(
                f"This command is on cooldown. Try again in {retry_after:.2f} seconds.", 
                ephemeral=True
            )
        elif isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                "You don't have permission to use this command.", 
                ephemeral=True
            )
        elif getattr(error, "original", None) and isinstance(error.original, discord.HTTPException) and error.original.status == 429:
            # Handle rate limits specially
            await self.rate_limit_handler.log_rate_limit(
                f"app_command:{interaction.command.name}", 
                getattr(error.original, "retry_after", 60)
            )
            
            # Try to respond if interaction hasn't been responded to
            try:
                if interaction.response.is_done():
                    await interaction.followup.send(
                        "This action is being rate limited by Discord. Please try again later.", 
                        ephemeral=True
                    )
                else:
                    await interaction.response.send_message(
                        "This action is being rate limited by Discord. Please try again later.", 
                        ephemeral=True
                    )
            except:
                pass
        else:
            print(f"Slash command error: {error}")
            
            try:
                if interaction.response.is_done():
                    await interaction.followup.send("An error occurred while processing this command.", ephemeral=True)
                else:
                    await interaction.response.send_message("An error occurred while processing this command.", ephemeral=True)
            except:
                pass

# Add HTTP exception handler to hook into discord.py's HTTP client
class HTTPExceptionHandler:
    @staticmethod
    async def on_request(route, **kwargs):
        return kwargs
    
    @staticmethod
    async def on_response(response, *, route, **kwargs):
        if response.status == 429:
            retry_after = response.headers.get('Retry-After')
            if retry_after:
                retry_after = float(retry_after)
            else:
                retry_after = 60.0
                
            endpoint = f"{route.method} {route.path}"
            print(f"Rate limited: {endpoint}, retry after {retry_after}s")
            
            # Add jitter to retry time
            jitter = random.uniform(0.8, 1.2)
            retry_after = retry_after * jitter
            
            # Log the rate limit
            try:
                await bot.rate_limit_handler.log_rate_limit(endpoint, retry_after)
            except Exception as e:
                print(f"Failed to log rate limit: {e}")
                
            # Set cooldown on command sync if this is an applications endpoint
            if "applications" in route.path:
                bot.rate_limit_handler.sync_cooldown_until = (
                    datetime.datetime.utcnow() + 
                    timedelta(seconds=max(3600, retry_after * 2))
                )
                print(f"Setting sync cooldown until {bot.rate_limit_handler.sync_cooldown_until}")

# Create bot instance
bot = MyBot()

# Add HTTP exception handler
discord.http.HTTPClient.on_request = HTTPExceptionHandler.on_request
discord.http.HTTPClient.on_response = HTTPExceptionHandler.on_response

@bot.command()
@commands.is_owner()
@commands.cooldown(1, 3600, commands.BucketType.default)  # Once per hour global cooldown
async def force_sync(ctx):
    """Manually sync application commands globally, ignoring cooldown"""
    await ctx.send("Forcing global command sync... This might take a moment.")
    
    # Check recent rate limits regardless of cooldown
    can_sync = await bot.rate_limit_handler.should_sync_commands()
    if not can_sync:
        await ctx.send("Cannot sync commands due to recent rate limiting. Try again later.")
        return
        
    try:
        # First sync to a test guild if possible (much lower rate limits)
        test_guild_id = os.getenv("TEST_GUILD_ID")
        if test_guild_id:
            test_guild = discord.Object(id=int(test_guild_id))
            guild_synced = await bot.tree.sync(guild=test_guild)
            await ctx.send(f"Synced {len(guild_synced)} command(s) to test guild first")
            # Wait a bit before global sync
            await asyncio.sleep(5)
        
        # Now do global sync
        current_hash = await bot.get_commands_hash()
        synced = await bot.tree.sync()
        
        # Update hash and sync time
        await bot.db.sync_info.update_one(
            {"bot_id": str(bot.user.id)},
            {"$set": {
                "commands_hash": current_hash,
                "last_sync": datetime.datetime.utcnow(),
                "last_sync_reason": "Manual force sync"
            }},
            upsert=True
        )
        
        bot.has_synced_this_session = True
        await ctx.send(f"Synced {len(synced)} command(s) globally!")
    except discord.HTTPException as e:
        if e.status == 429:
            retry_after = e.retry_after * random.uniform(1.0, 1.5)  # Add jitter
            await bot.rate_limit_handler.log_rate_limit("force_sync", retry_after)
            await ctx.send(f"Rate limited! Please try again in {retry_after:.2f} seconds.")
        else:
            await ctx.send(f"HTTP Error: {e}")
    except Exception as e:
        await ctx.send(f"Failed to sync commands: {e}")

@bot.command()
@commands.is_owner()
async def sync_status(ctx):
    """Check the current sync status"""
    sync_info = await bot.db.sync_info.find_one({"bot_id": str(bot.user.id)})
    
    if not sync_info:
        await ctx.send("No sync information found. The bot has not synced commands yet.")
        return
    
    current_time = datetime.datetime.utcnow()
    last_sync = sync_info.get("last_sync", "Never")
    
    if last_sync != "Never":
        time_since = current_time - last_sync
        days = time_since.days
        hours = time_since.seconds // 3600
        minutes = (time_since.seconds % 3600) // 60
        time_since_str = f"{days} days, {hours} hours, {minutes} minutes ago"
    else:
        time_since_str = "Never"
    
    embed = discord.Embed(
        title="Command Sync Status",
        color=discord.Color.blue()
    )
    
    embed.add_field(name="Last Sync", value=time_since_str, inline=False)
    embed.add_field(name="Last Sync Reason", value=sync_info.get("last_sync_reason", "Unknown"), inline=False)
    embed.add_field(name="Synced This Session", value=str(bot.has_synced_this_session), inline=False)
    
    # Check if command structure has changed
    current_hash = await bot.get_commands_hash()
    stored_hash = sync_info.get("commands_hash", "None")
    hash_changed = current_hash != stored_hash
    
    embed.add_field(name="Commands Changed Since Last Sync", value=str(hash_changed), inline=False)
    
    if hash_changed:
        embed.add_field(name="Current Hash", value=current_hash[:8] + "...", inline=True)
        embed.add_field(name="Stored Hash", value=stored_hash[:8] + "...", inline=True)
    
    # Add rate limit info
    cooldown_active = False
    if bot.rate_limit_handler.sync_cooldown_until:
        if datetime.datetime.utcnow() < bot.rate_limit_handler.sync_cooldown_until:
            cooldown_active = True
            time_left = (bot.rate_limit_handler.sync_cooldown_until - datetime.datetime.utcnow()).total_seconds()
            cooldown_str = f"Active for {time_left:.2f} more seconds"
        else:
            cooldown_str = "Not active"
    else:
        cooldown_str = "Not active"
    
    embed.add_field(name="Sync Cooldown", value=cooldown_str, inline=False)
    
    # Recent rate limits
    recent_rate_limits = []
    for endpoint, limits in bot.rate_limit_handler.rate_limits.items():
        for limit in limits:
            if (current_time - limit["timestamp"]).total_seconds() < 3600:
                recent_rate_limits.append(limit)
    
    if recent_rate_limits:
        embed.add_field(
            name="Recent Rate Limits (last hour)", 
            value=str(len(recent_rate_limits)), 
            inline=False
        )
    
    await ctx.send(embed=embed)

@bot.command()
@commands.is_owner()
async def rate_limit_history(ctx):
    """View recent rate limit history"""
    current_time = datetime.datetime.utcnow()
    
    embed = discord.Embed(
        title="Rate Limit History",
        color=discord.Color.red()
    )
    
    # Group by endpoint
    for endpoint, limits in bot.rate_limit_handler.rate_limits.items():
        if not limits:
            continue
            
        # Get limits from last 24 hours
        recent = [l for l in limits if (current_time - l["timestamp"]).total_seconds() < 86400]
        if not recent:
            continue
            
        # Format the limits
        limit_str = "\n".join([
            f"{(current_time - l['timestamp']).total_seconds()/60:.1f}m ago: {l['retry_after']:.1f}s"
            for l in recent[:5]  # Show at most 5 per endpoint
        ])
        
        if len(recent) > 5:
            limit_str += f"\n...and {len(recent) - 5} more"
            
        embed.add_field(
            name=f"{endpoint} ({len(recent)} times)",
            value=limit_str,
            inline=False
        )
    
    if not embed.fields:
        embed.description = "No rate limits recorded in the last 24 hours."
        
    await ctx.send(embed=embed)

@bot.command()
@commands.is_owner()
async def guild_sync(ctx, guild_id: str = None):
    """Sync commands to a specific guild instead of globally"""
    if not guild_id and not ctx.guild:
        await ctx.send("Please provide a guild ID or run this command in a guild.")
        return
        
    guild_id = guild_id or str(ctx.guild.id)
    
    try:
        guild = discord.Object(id=int(guild_id))
        synced = await bot.tree.sync(guild=guild)
        await ctx.send(f"Synced {len(synced)} command(s) to guild {guild_id}!")
    except Exception as e:
        await ctx.send(f"Failed to sync commands to guild: {e}")

@bot.event
async def on_ready():
    print(f"Bot is ready. Logged in as {bot.user}")
    
    # Set bot activity
    await bot.change_presence(activity=discord.Activity(
        type=discord.ActivityType.watching, 
        name="over everything."
    ))
    
    # Check if we've already synced commands this session
    if bot.has_synced_this_session:
        print("Commands already synced this session, skipping check")
        return
    
    # Ensure sync_info collection exists
    collections = await bot.db.list_collection_names()
    if "sync_info" not in collections:
        await bot.db.create_collection("sync_info")
    
    # Get current command structure hash
    current_hash = await bot.get_commands_hash()
    print(f"Current command hash: {current_hash[:8]}...")
    
    # Get last sync info
    sync_info = await bot.db.sync_info.find_one({"bot_id": str(bot.user.id)})
    
    # Determine if we should sync
    should_sync = False
    reason = ""
    
    if not sync_info:
        should_sync = True
        reason = "First run, no sync history found"
    else:
        stored_hash = sync_info.get("commands_hash")
        if stored_hash != current_hash:
            should_sync = True
            reason = f"Command structure has changed (old: {stored_hash[:8]}..., new: {current_hash[:8]}...)"
            print(f"Command hash changed: {stored_hash[:8]}... -> {current_hash[:8]}...")
        else:
            print(f"Command hash unchanged: {stored_hash[:8]}...")
            
            # Check last sync time - but only for information, not to trigger a sync
            current_time = datetime.datetime.utcnow()
            last_sync = sync_info.get("last_sync")
            if last_sync:
                time_diff = current_time - last_sync
                print(f"Last sync was {time_diff.days} days, {time_diff.seconds // 3600} hours ago")
    
    # Check if we should avoid syncing due to rate limits
    if should_sync:
        can_sync = await bot.rate_limit_handler.should_sync_commands()
        if not can_sync:
            should_sync = False
            print("Skipping command sync due to rate limit cooldown")
    
    # Sync if needed
    if should_sync:
        print(f"Syncing slash commands... Reason: {reason}")
        try:
            # First try to sync with a test guild if configured
            test_guild_id = os.getenv("TEST_GUILD_ID")
            if test_guild_id:
                test_guild = discord.Object(id=int(test_guild_id))
                guild_synced = await bot.tree.sync(guild=test_guild)
                print(f"Synced {len(guild_synced)} command(s) to test guild")
                # Wait a bit before global sync
                await asyncio.sleep(5)
            
            # Now do global sync
            synced = await bot.tree.sync()
            print(f"Synced {len(synced)} command(s) globally")
            
            # Update hash and sync time
            await bot.db.sync_info.update_one(
                {"bot_id": str(bot.user.id)},
                {"$set": {
                    "commands_hash": current_hash,
                    "last_sync": datetime.datetime.utcnow(),
                    "last_sync_reason": reason
                }},
                upsert=True
            )
            
            bot.has_synced_this_session = True
        except discord.HTTPException as e:
            if e.status == 429:
                # Rate limited, log it
                await bot.rate_limit_handler.log_rate_limit("on_ready_sync", e.retry_after)
                print(f"Rate limited during command sync. Retry after: {e.retry_after}s")
            else:
                print(f"HTTP error during command sync: {e}")
        except Exception as e:
            print(f"Failed to sync commands: {e}")
    else:
        print("Skipping command sync: No changes detected or rate limit cooldown active")

@bot.event
async def on_message(message):
    # This makes sure both on_message handlers in cogs AND commands work
    await bot.process_commands(message)

@bot.event
async def on_guild_join(guild):
    """Handle bot joining a new server"""
    print(f"Bot joined a new guild: {guild.name} (ID: {guild.id})")
    
    # Sync commands to this specific guild to avoid global rate limits
    try:
        guild_obj = discord.Object(id=guild.id)
        synced = await bot.tree.sync(guild=guild_obj)
        print(f"Synced {len(synced)} command(s) to new guild {guild.name}")
    except Exception as e:
        print(f"Failed to sync commands to new guild: {e}")
    
    # Create a welcome message
    channel = guild.system_channel or next((ch for ch in guild.text_channels if ch.permissions_for(guild.me).send_messages), None)
    
    if channel:
        embed = discord.Embed(
            title="Axis has been added to this server. You really got lucky huh.",
            description="I can help moderate, chat, setup tickets, marketposts, starboards, and much more.",
            color=discord.Color.red()
        )
        embed.add_field(name="Setup", value="Use `/help` to see some commands to run.", inline=False)
        embed.set_footer(text="For help or issues, contact the bot owner")
        
        try:
            await channel.send(embed=embed)
        except discord.Forbidden:
            print(f"Cannot send welcome message to {guild.name}")

@bot.event
async def on_error(event, *args, **kwargs):
    """Global error handler to catch and handle rate limits"""
    error_type, error, tb = sys.exc_info()
    
    if isinstance(error, discord.HTTPException) and error.status == 429:
        # Handle rate limits
        endpoint = f"error_in_{event}"
        retry_after = getattr(error, "retry_after", 60)
        
        print(f"Rate limit in {event}. Retry after: {retry_after}s")
        await bot.rate_limit_handler.log_rate_limit(endpoint, retry_after)
    else:
        # Log other errors
        print(f"Unhandled error in {event}: {error}")

# Run the bot with the token from .env file
if __name__ == "__main__":
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("Error: No Discord token found in .env file")
        exit(1)
        
    try:
        # Add an environment variable to use a test guild for development
        # This will allow you to test commands without hitting global rate limits
        test_guild_id = os.getenv("TEST_GUILD_ID")
        if test_guild_id:
            print(f"Test guild ID configured: {test_guild_id}")
        
        bot.run(token.strip())
    except discord.LoginFailure:
        print("Error: Invalid Discord token")
    except Exception as e:
        print(f"Error starting bot: {e}")
