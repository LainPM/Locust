import os
import discord
import asyncio
import datetime
import hashlib
import json
import random
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

class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)
        
        # Initialize MongoDB connection
        self.mongo_client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URI)
        self.db = self.mongo_client["discord_bot"]
        self.warnings_collection = self.db["warnings"]
        
        # Track if we've synced commands during this session
        self.has_synced_this_session = False
        
        # Last time we synced a command (for incremental syncing)
        self.last_command_sync_time = None
        
        # Flag to disable auto-sync on startup
        self.disable_startup_sync = os.getenv("DISABLE_STARTUP_SYNC", "false").lower() == "true"
        
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
        else:
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
            print(f"Slash command error: {error}")
            
            try:
                if interaction.response.is_done():
                    await interaction.followup.send("An error occurred while processing this command.", ephemeral=True)
                else:
                    await interaction.response.send_message("An error occurred while processing this command.", ephemeral=True)
            except:
                pass
    
    async def sync_incremental(self, ctx=None):
        """Sync commands one at a time to avoid rate limits"""
        # Get commands
        commands = self.tree.get_commands()
        
        if not commands:
            if ctx:
                await ctx.send("No commands to sync.")
            return
        
        total = len(commands)
        synced = 0
        errors = 0
        
        status_message = None
        if ctx:
            status_message = await ctx.send(f"Starting incremental sync of {total} commands...")
        
        # Use app_commands._state._http internal API to sync one by one
        # This isn't ideal but currently there's no public API to sync individual commands
        for i, command in enumerate(commands):
            try:
                # Create a copy of the command
                cmd_payload = command.to_dict()
                
                # Get the application ID
                application_id = self.application_id
                
                # Use the HTTP adapter directly
                http = self.http
                
                # Make request
                try:
                    await http.request(
                        discord.http.Route(
                            'PUT',
                            '/applications/{application_id}/commands/{command_id}',
                            application_id=application_id,
                            command_id=command.id if hasattr(command, 'id') and command.id else '@me'
                        ),
                        json=cmd_payload
                    )
                    synced += 1
                    
                    # Update status every few commands
                    if ctx and status_message and i % 3 == 0:
                        await status_message.edit(content=f"Syncing commands... {i+1}/{total} complete")
                    
                    # Delay between commands to avoid rate limits
                    await asyncio.sleep(2.5)  # 2.5 seconds between commands
                    
                except discord.HTTPException as e:
                    if e.status == 429:  # Rate limited
                        retry_after = e.retry_after
                        if ctx:
                            await ctx.send(f"Rate limited! Waiting {retry_after:.2f} seconds before continuing...")
                        
                        # Wait the required time plus some buffer
                        await asyncio.sleep(retry_after * 1.1)
                        
                        # Try again (recursive)
                        try:
                            await http.request(
                                discord.http.Route(
                                    'PUT',
                                    '/applications/{application_id}/commands/{command_id}',
                                    application_id=application_id,
                                    command_id=command.id if hasattr(command, 'id') and command.id else '@me'
                                ),
                                json=cmd_payload
                            )
                            synced += 1
                        except Exception as retry_e:
                            errors += 1
                            print(f"Error syncing command {command.name} after retry: {retry_e}")
                    else:
                        errors += 1
                        print(f"HTTP error syncing command {command.name}: {e}")
                        
            except Exception as e:
                errors += 1
                print(f"Error syncing command {command.name}: {e}")
        
        # Update the hash since we've synced manually
        current_hash = await self.get_commands_hash()
        await self.db.sync_info.update_one(
            {"bot_id": str(self.user.id)},
            {"$set": {
                "commands_hash": current_hash,
                "last_sync": datetime.datetime.utcnow(),
                "last_sync_reason": "Incremental sync"
            }},
            upsert=True
        )
        
        self.has_synced_this_session = True
        
        if ctx and status_message:
            await status_message.edit(content=f"Incremental sync complete! Synced {synced}/{total} commands with {errors} errors.")

# Create bot instance
bot = MyBot()

@bot.command()
@commands.is_owner()
async def force_sync(ctx):
    """Manually sync application commands incrementally to avoid rate limits"""
    await ctx.send("Starting incremental command sync... This might take a moment.")
    await bot.sync_incremental(ctx)

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
    
    # Count total commands
    command_count = len(bot.tree.get_commands())
    embed.add_field(name="Total Commands", value=str(command_count), inline=False)
    
    # Add startup sync status
    startup_sync = "Disabled" if bot.disable_startup_sync else "Enabled"
    embed.add_field(name="Startup Sync", value=startup_sync, inline=False)
    
    await ctx.send(embed=embed)

@bot.command()
@commands.is_owner()
async def toggle_startup_sync(ctx):
    """Toggle whether commands sync on startup"""
    current_setting = os.getenv("DISABLE_STARTUP_SYNC", "false").lower() == "true"
    new_setting = not current_setting
    
    # Update in-memory setting
    bot.disable_startup_sync = new_setting
    
    # We can't actually modify the .env file easily, but we can store this in the database
    await bot.db.bot_settings.update_one(
        {"setting": "disable_startup_sync"},
        {"$set": {"value": new_setting}},
        upsert=True
    )
    
    await ctx.send(f"Startup sync is now {'disabled' if new_setting else 'enabled'}.")

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
    
    # Load setting from database
    setting = await bot.db.bot_settings.find_one({"setting": "disable_startup_sync"})
    if setting:
        bot.disable_startup_sync = setting.get("value", False)
    
    # Skip if startup sync is disabled
    if bot.disable_startup_sync:
        print("Startup sync is disabled. Skipping command sync.")
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
        print(f"Syncing slash commands incrementally... Reason: {reason}")
        try:
            await bot.sync_incremental()
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
