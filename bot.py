import os
import discord
import asyncio
import datetime
import hashlib
import json
import traceback
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
        
    async def process_commands(self, message):
        if message.content.startswith(self.command_prefix):
            ctx = await self.get_context(message)
            if ctx.command is not None:
                # Check if this is a bot owner command
                is_owner_command = ctx.command.checks and any(check.__qualname__.startswith('is_owner') for check in ctx.command.checks)
                
                # Invoke the command
                await self.invoke(ctx)
                
                # If it's an owner command, delete the message after 5 seconds
                if is_owner_command and message.guild:
                    try:
                        await asyncio.sleep(5)
                        await message.delete()
                    except:
                        pass
    
    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.CommandNotFound):
            return
        elif isinstance(error, commands.MissingPermissions):
            message = await ctx.send("You don't have permission to use this command.")
        elif isinstance(error, commands.BotMissingPermissions):
            message = await ctx.send("I don't have the necessary permissions to do that.")
        elif isinstance(error, commands.NotOwner):
            message = await ctx.send("Only the bot owner can use this command.")
        else:
            print(f"Command error: {error}")
            message = await ctx.send(f"An error occurred: {error}")
        
        # Delete error message after 5 seconds
        try:
            await asyncio.sleep(5)
            await message.delete()
        except:
            pass
    
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
    
    async def sync_direct(self, command_data, guild_id=None):
        """Sync a command directly using Discord's API with better error handling"""
        try:
            # Get application ID
            application_id = self.application.id
            
            if guild_id:
                # Guild-specific endpoint
                route = discord.http.Route(
                    'POST',
                    '/applications/{application_id}/guilds/{guild_id}/commands',
                    application_id=application_id,
                    guild_id=guild_id
                )
            else:
                # Global endpoint
                route = discord.http.Route(
                    'POST',
                    '/applications/{application_id}/commands',
                    application_id=application_id
                )
            
            result = await self.http.request(route, json=command_data)
            return True, result
        except discord.HTTPException as e:
            # Properly handle rate limits and other HTTP errors
            if e.status == 429:
                print(f"Rate limited syncing command: {command_data.get('name', 'unknown')}")
                print(f"Retry After: {e.retry_after} seconds")
                print(f"Headers: {e.response.headers if hasattr(e, 'response') else 'No headers'}")
            else:
                print(f"HTTP error syncing command: {e}")
                print(f"Status: {e.status}")
                print(f"Code: {e.code if hasattr(e, 'code') else 'No code'}")
                
            return False, e
        except Exception as e:
            print(f"Unexpected error syncing command: {e}")
            print(traceback.format_exc())
            return False, e
    
    async def get_registered_commands(self, force_refresh=False):
        """Get all commands currently registered with Discord"""
        now = datetime.datetime.now()
        
        # Use cached result if available and recent (within last 5 minutes)
        if not force_refresh and self.last_command_fetch and (now - self.last_command_fetch).total_seconds() < 300:
            return self.registered_commands
        
        try:
            # Get application ID
            application_id = self.application.id
            
            # Global commands endpoint
            route = discord.http.Route(
                'GET',
                '/applications/{application_id}/commands',
                application_id=application_id
            )
            
            registered_commands = await self.http.request(route)
            
            # Update cache
            self.registered_commands = registered_commands
            self.last_command_fetch = now
            
            return registered_commands
        except discord.HTTPException as e:
            print(f"HTTP error fetching registered commands: {e}")
            # Return cached results if available
            return self.registered_commands if self.registered_commands else []
        except Exception as e:
            print(f"Unexpected error fetching registered commands: {e}")
            print(traceback.format_exc())
            return self.registered_commands if self.registered_commands else []
    
    def get_command_json(self, command):
        """Extract JSON data from a command"""
        data = {
            "name": command.name,
            "description": command.description
        }
        
        # Add options/parameters if present
        options = []
        for param in getattr(command, 'parameters', []):
            option = {
                "name": param.name,
                "description": param.description,
                "required": param.required,
                "type": param.type.value
            }
            
            # Add choices if any
            if hasattr(param, 'choices') and param.choices:
                option["choices"] = [
                    {"name": choice.name, "value": choice.value}
                    for choice in param.choices
                ]
            
            options.append(option)
        
        if options:
            data["options"] = options
        
        return data
    
    def is_command_synced(self, command, registered_commands):
        """Check if a command is already properly synced with Discord"""
        for reg_cmd in registered_commands:
            if reg_cmd["name"] == command.name:
                # Command exists, but we should also check if it needs updating
                # For simplicity, we'll just check the description and parameter count
                if reg_cmd["description"] != command.description:
                    return False
                
                # Check parameters
                cmd_params = getattr(command, 'parameters', [])
                reg_options = reg_cmd.get("options", [])
                
                if len(cmd_params) != len(reg_options):
                    return False
                
                # Command exists and looks similar enough
                return True
                
        # Command doesn't exist
        return False

# Create bot instance
bot = MyBot()

@bot.command()
@commands.is_owner()
async def sync_status(ctx):
    """Check the current sync status and list commands that need syncing"""
    status_message = await ctx.send("Fetching command status...")
    
    try:
        # Get local commands
        local_commands = bot.tree.get_commands()
        
        # Get registered commands from Discord
        registered_commands = await bot.get_registered_commands(force_refresh=True)
        
        # Determine which commands need syncing
        unsynced_commands = []
        for cmd in local_commands:
            if not bot.is_command_synced(cmd, registered_commands):
                unsynced_commands.append(cmd)
        
        embed = discord.Embed(
            title="Command Sync Status",
            color=discord.Color.blue()
        )
        
        # Show sync operation status
        if bot.currently_syncing:
            elapsed = (datetime.datetime.now() - bot.sync_start_time).total_seconds()
            embed.add_field(
                name="Sync Operation", 
                value=f"⚠️ **Sync in progress** for {elapsed:.1f} seconds\n"
                      f"Use `!sync_reset` to clear if stuck",
                inline=False
            )
        
        # Display sync status summary
        embed.add_field(
            name="Command Status", 
            value=f"🔄 **{len(unsynced_commands)}** commands need syncing\n"
                  f"✅ **{len(local_commands) - len(unsynced_commands)}** commands already synced\n"
                  f"📋 **{len(local_commands)}** total local commands\n"
                  f"📡 **{len(registered_commands)}** registered on Discord",
            inline=False
        )
        
        # List commands that need syncing
        if unsynced_commands:
            command_list = "\n".join([f"- `/{cmd.name}`: {cmd.description}" for cmd in unsynced_commands[:15]])
            if len(unsynced_commands) > 15:
                command_list += f"\n...and {len(unsynced_commands) - 15} more"
            
            embed.add_field(name=f"Commands Needing Sync ({len(unsynced_commands)} total)", value=command_list, inline=False)
        else:
            embed.add_field(name="Commands Needing Sync", value="All commands are in sync! 🎉", inline=False)
        
        # Available sync commands
        embed.add_field(
            name="Sync Commands", 
            value="- `!sync_one <name>`: Sync a single command by name\n"
                  "- `!sync_all`: Sync all non-synced commands\n"
                  "- `!sync_status`: Show this status\n"
                  "- `!sync_reset`: Reset sync status if stuck",
            inline=False
        )
        
        await status_message.edit(content=None, embed=embed)
        
        # Delete message after 5 seconds if in a guild
        if ctx.guild:
            try:
                await asyncio.sleep(5)
                await status_message.delete()
                await ctx.message.delete()
            except:
                pass
    except Exception as e:
        print(f"Error in sync_status: {e}")
        print(traceback.format_exc())
        await status_message.edit(content=f"Error checking sync status: {e}")
        
        if ctx.guild:
            try:
                await asyncio.sleep(5)
                await status_message.delete()
                await ctx.message.delete()
            except:
                pass

@bot.command()
@commands.is_owner()
async def sync_reset(ctx):
    """Force reset the sync status if it gets stuck"""
    old_status = bot.currently_syncing
    
    if bot.sync_start_time:
        elapsed = (datetime.datetime.now() - bot.sync_start_time).total_seconds()
        message = await ctx.send(f"Resetting sync status. Sync was in progress for {elapsed:.1f} seconds.")
        bot.end_sync()
    else:
        message = await ctx.send("Sync was not in progress. No action needed.")
    
    # Delete message after 5 seconds if in a guild
    if ctx.guild:
        try:
            await asyncio.sleep(5)
            await message.delete()
            await ctx.message.delete()
        except:
            pass

@bot.command()
@commands.is_owner()
async def sync_one(ctx, command_name: str):
    """Sync a single command by name using direct HTTP API"""
    if bot.currently_syncing:
        elapsed = (datetime.datetime.now() - bot.sync_start_time).total_seconds()
        message = await ctx.send(f"A sync operation is already in progress for {elapsed:.1f} seconds. Use `!sync_reset` if it's stuck.")
        if ctx.guild:
            try:
                await asyncio.sleep(5)
                await message.delete()
                await ctx.message.delete()
            except:
                pass
        return
        
    bot.start_sync()  # Mark sync as started
    
    try:
        # Find the command
        command = None
        for cmd in bot.tree.get_commands():
            if cmd.name.lower() == command_name.lower():
                command = cmd
                break
        
        if not command:
            message = await ctx.send(f"Command '/{command_name}' not found.")
            if ctx.guild:
                try:
                    await asyncio.sleep(5)
                    await message.delete()
                    await ctx.message.delete()
                except:
                    pass
            bot.end_sync()  # Mark sync as complete
            return
        
        status_message = await ctx.send(f"Syncing command '/{command.name}'...")
        
        # Get registered commands to check if already synced
        registered_commands = await bot.get_registered_commands()
        
        # Check if command is already synced
        if bot.is_command_synced(command, registered_commands):
            await status_message.edit(content=f"⚠️ Command '/{command.name}' is already synced. No action needed.")
            if ctx.guild:
                try:
                    await asyncio.sleep(5)
                    await status_message.delete()
                    await ctx.message.delete()
                except:
                    pass
            bot.end_sync()  # Mark sync as complete
            return
        
        # Get command data
        command_data = bot.get_command_json(command)
        
        # Sync command
        success, result = await bot.sync_direct(command_data)
        
        if success:
            # Force refresh the registered commands cache
            await bot.get_registered_commands(force_refresh=True)
            await status_message.edit(content=f"✅ Command '/{command.name}' synced successfully!")
        else:
            if isinstance(result, discord.HTTPException) and result.status == 429:
                # Rate limited
                retry_after = result.retry_after
                await status_message.edit(content=f"⏱️ Rate limited! Please wait {retry_after:.1f} seconds before trying again.")
            else:
                await status_message.edit(content=f"❌ Failed to sync command '/{command.name}': {result}")
        
        # Delete messages after 5 seconds if in a guild
        if ctx.guild:
            try:
                await asyncio.sleep(5)
                await status_message.delete()
                await ctx.message.delete()
            except:
                pass
    except Exception as e:
        print(f"Error in sync_one: {e}")
        print(traceback.format_exc())
        error_message = await ctx.send(f"Unexpected error: {e}")
        if ctx.guild:
            try:
                await asyncio.sleep(5)
                await error_message.delete()
                await ctx.message.delete()
            except:
                pass
    finally:
        bot.end_sync()  # Always mark sync as complete, even if there was an error

@bot.command()
@commands.is_owner()
async def sync_all(ctx):
    """Sync only commands that aren't already synced"""
    if bot.currently_syncing:
        elapsed = (datetime.datetime.now() - bot.sync_start_time).total_seconds()
        message = await ctx.send(f"A sync operation is already in progress for {elapsed:.1f} seconds. Use `!sync_reset` if it's stuck.")
        if ctx.guild:
            try:
                await asyncio.sleep(5)
                await message.delete()
                await ctx.message.delete()
            except:
                pass
        return
        
    bot.start_sync()  # Mark sync as started
    
    try:
        # First, get all commands that need syncing
        local_commands = bot.tree.get_commands()
        registered_commands = await bot.get_registered_commands(force_refresh=True)
        
        # Filter for commands that need syncing
        commands_to_sync = []
        for cmd in local_commands:
            if not bot.is_command_synced(cmd, registered_commands):
                commands_to_sync.append(cmd)
        
        total = len(commands_to_sync)
        
        if not total:
            message = await ctx.send("All commands are already synced! Nothing to do.")
            if ctx.guild:
                try:
                    await asyncio.sleep(5)
                    await message.delete()
                    await ctx.message.delete()
                except:
                    pass
            bot.end_sync()  # Mark sync as complete
            return
        
        status_message = await ctx.send(f"Found {total} commands that need syncing. This will sync them one by one with 10-second delays between each. Continue? (yes/no)")
        
        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel and m.content.lower() in ["yes", "no"]
        
        try:
            response = await bot.wait_for("message", check=check, timeout=30.0)
            if response.content.lower() != "yes":
                await status_message.edit(content="Sync cancelled.")
                # Delete messages after 5 seconds if in a guild
                if ctx.guild:
                    try:
                        await asyncio.sleep(5)
                        await status_message.delete()
                        await ctx.message.delete()
                        await response.delete()
                    except:
                        pass
                bot.end_sync()  # Mark sync as complete
                return
                
            # Try to delete the response message
            if ctx.guild:
                try:
                    await response.delete()
                except:
                    pass
        except asyncio.TimeoutError:
            await status_message.edit(content="No response received. Sync cancelled.")
            # Delete messages after 5 seconds if in a guild
            if ctx.guild:
                try:
                    await asyncio.sleep(5)
                    await status_message.delete()
                    await ctx.message.delete()
                except:
                    pass
            bot.end_sync()  # Mark sync as complete
            return
        
        # Start time for progress tracking
        start_time = asyncio.get_event_loop().time()
        
        await status_message.edit(content=f"Starting sync of {total} commands. This will take approximately {total * 10 / 60:.1f} minutes...")
        
        success_count = 0
        error_count = 0
        rate_limited = False
        
        for i, command in enumerate(commands_to_sync):
            try:
                # Update progress message
                elapsed = asyncio.get_event_loop().time() - start_time
                estimated_total = (elapsed / (i + 1)) * total if i > 0 else 0
                remaining = max(0, estimated_total - elapsed)
                
                status_text = f"Syncing command {i+1}/{total}: `/{command.name}`\n"
                status_text += f"Progress: {((i+1)/total)*100:.1f}%\n"
                status_text += f"Elapsed: {int(elapsed//60)}m {int(elapsed%60)}s | "
                status_text += f"Remaining: ~{int(remaining//60)}m {int(remaining%60)}s"
                
                if rate_limited:
                    status_text += "\n⚠️ Rate limited on previous command. Proceeding with caution."
                    rate_limited = False
                
                await status_message.edit(content=status_text)
                
                # Get command data and sync
                command_data = bot.get_command_json(command)
                success, result = await bot.sync_direct(command_data)
                
                if success:
                    success_count += 1
                else:
                    if isinstance(result, discord.HTTPException) and result.status == 429:
                        # Rate limited, wait longer
                        retry_after = result.retry_after * 1.5  # Add buffer
                        rate_limited = True
                        
                        await status_message.edit(
                            content=f"⏱️ Rate limited on command {i+1}/{total}: `/{command.name}`\n"
                                    f"Waiting {retry_after:.1f} seconds before continuing..."
                        )
                        
                        # Wait the required time
                        await asyncio.sleep(retry_after)
                        
                        # Try again
                        success, retry_result = await bot.sync_direct(command_data)
                        if success:
                            success_count += 1
                        else:
                            error_count += 1
                            error_message = await ctx.send(f"Failed to sync `/{command.name}` after retry: {retry_result}")
                            if ctx.guild:
                                try:
                                    await asyncio.sleep(5)
                                    await error_message.delete()
                                except:
                                    pass
                    else:
                        # Other error
                        error_count += 1
                        error_message = await ctx.send(f"Error syncing `/{command.name}`: {result}")
                        if ctx.guild:
                            try:
                                await asyncio.sleep(5)
                                await error_message.delete()
                            except:
                                pass
                
                # Wait between commands - very conservative
                await asyncio.sleep(10)
                
            except Exception as e:
                error_count += 1
                print(f"Error syncing command {command.name}: {e}")
                print(traceback.format_exc())
                error_message = await ctx.send(f"Unexpected error during sync for /{command.name}: {e}")
                if ctx.guild:
                    try:
                        await asyncio.sleep(5)
                        await error_message.delete()
                    except:
                        pass
        
        # Force refresh the registered commands cache
        await bot.get_registered_commands(force_refresh=True)
        
        # Final status
        total_time = asyncio.get_event_loop().time() - start_time
        minutes = int(total_time // 60)
        seconds = int(total_time % 60)
        
        await status_message.edit(
            content=f"Sync complete!\n"
                    f"Successfully synced {success_count}/{total} commands with {error_count} errors.\n"
                    f"Total time: {minutes}m {seconds}s"
        )
        
        # Final status stays longer - 10 seconds
        if ctx.guild:
            try:
                await asyncio.sleep(10)
                await status_message.delete()
                await ctx.message.delete()
            except:
                pass
        
    except Exception as e:
        print(f"Error in sync_all: {e}")
        print(traceback.format_exc())
        error_message = await ctx.send(f"Error during sync: {e}")
        if ctx.guild:
            try:
                await asyncio.sleep(5)
                await error_message.delete()
                await ctx.message.delete()
            except:
                pass
    finally:
        bot.end_sync()  # Always mark sync as complete, even if there was an error

@bot.event
async def on_ready():
    print(f"Bot is ready. Logged in as {bot.user}")
    
    # Set bot activity
    await bot.change_presence(activity=discord.Activity(
        type=discord.ActivityType.watching, 
        name="over everything."
    ))
    
    print("⚠️ AUTO-SYNC IS DISABLED: Use !sync_status to check which commands need syncing")
    
    # Reset sync status in case bot was restarted during sync
    bot.end_sync()
    
    # Pre-fetch registered commands in the background
    try:
        await bot.get_registered_commands(force_refresh=True)
        print(f"✅ Pre-fetched {len(bot.registered_commands)} registered commands from Discord")
    except:
        print("❌ Failed to pre-fetch registered commands")

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
