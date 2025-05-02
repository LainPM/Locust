import os
import discord
import asyncio
import datetime
from datetime import timedelta
import hashlib
import json
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
import motor.motor_asyncio

# Load environment variables
load_dotenv()

# Set up intents
intents = discord.Intents.default()
intents.message_content = True  # Required to read message content
intents.members = True  # Required for user-related features

# MongoDB setup
MONGO_URI = os.getenv("MONGO_URI")

class MyBot(commands.Bot):
    def __init__(self):
        # Fix: Set a valid command prefix
        super().__init__(command_prefix="!", intents=intents)
        
        # Initialize MongoDB connection
        self.mongo_client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URI)
        self.db = self.mongo_client["discord_bot"]
        self.warnings_collection = self.db["warnings"]
        
        # Track if we've synced commands during this session
        self.has_synced_this_session = False
        
    async def get_commands_hash(self):
        """Generate a deterministic hash of the current command structure"""
        # Get a sorted, stable representation of all commands
        commands = []
        for cmd in self.tree.get_commands():
            # Only include stable properties that don't change between restarts
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
        
        # Sort commands by name for stability
        commands.sort(key=lambda x: x["name"])
        
        # Convert to a stable JSON string
        commands_str = json.dumps(commands, sort_keys=True)
        return hashlib.sha256(commands_str.encode()).hexdigest()
        
    async def setup_hook(self):
        # Auto-load all cogs from the cogs directory
        print("Loading cogs...")
        for filename in os.listdir('./cogs'):
            if filename.endswith('.py'):
                try:
                    cog_name = f"cogs.{filename[:-3]}"  # Remove .py extension
                    await self.load_extension(cog_name)
                    print(f"Loaded extension {cog_name}")
                except Exception as e:
                    print(f"Failed to load extension {filename}: {e}")
                    
        print("Cogs loaded successfully.")
        
    # IMPORTANT FIX: Modified to process commands properly while allowing on_message events 
    async def process_commands(self, message):
        # Only process commands if message starts with prefix
        if message.content.startswith(self.command_prefix):
            ctx = await self.get_context(message)
            if ctx.command is not None:
                await self.invoke(ctx)
    
    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.CommandNotFound):
            # Ignore command not found errors
            return
        elif isinstance(error, commands.MissingPermissions):
            await ctx.send("You don't have permission to use this command.")
        elif isinstance(error, commands.BotMissingPermissions):
            await ctx.send("I don't have the necessary permissions to do that.")
        else:
            # Log other errors
            print(f"Command error: {error}")
            await ctx.send(f"An error occurred: {error}")
    
    async def on_app_command_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.CommandOnCooldown):
            await interaction.response.send_message(
                f"This command is on cooldown. Try again in {error.retry_after:.2f} seconds.", 
                ephemeral=True
            )
        elif isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                "You don't have permission to use this command.", 
                ephemeral=True
            )
        else:
            # Log other errors
            print(f"Slash command error: {error}")
            
            # Try to respond if interaction hasn't been responded to
            try:
                if interaction.response.is_done():
                    await interaction.followup.send("An error occurred while processing this command.", ephemeral=True)
                else:
                    await interaction.response.send_message("An error occurred while processing this command.", ephemeral=True)
            except:
                # If all else fails, at least we logged it
                pass

# Create bot instance
bot = MyBot()

@bot.command()
@commands.is_owner()  # Only bot owner can use this
async def force_sync(ctx):
    """Manually sync application commands globally, ignoring cooldown"""
    await ctx.send("Forcing global command sync... This might take a moment.")
    try:
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
        # Fix for time deprecation - use timedelta properly
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
    
    await ctx.send(embed=embed)

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
    
    # Sync if needed
    if should_sync:
        print(f"Syncing slash commands... Reason: {reason}")
        try:
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
        except Exception as e:
            print(f"Failed to sync commands: {e}")
    else:
        print("Skipping command sync: No changes detected")

@bot.event
async def on_message(message):
    # This makes sure both on_message handlers in cogs AND commands work
    await bot.process_commands(message)

@bot.event
async def on_guild_join(guild):
    """Handle bot joining a new server"""
    print(f"Bot joined a new guild: {guild.name} (ID: {guild.id})")
    
    # Optional: Create a welcome message in the system channel or first available text channel
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

# Run the bot with the token from .env file
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
