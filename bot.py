import os
import discord
import asyncio
import datetime
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
        
        # Currently syncing flag
        self.currently_syncing = False
        
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
        print("⚠️ Slash commands will not work until manually synced with !sync_one or !sync_all")
        
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
        """Sync a command directly using Discord's API"""
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
        except Exception as e:
            return False, e
    
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

# Create bot instance
bot = MyBot()

@bot.command()
@commands.is_owner()
async def sync_status(ctx):
    """Check the current sync status and list available commands"""
    commands = bot.tree.get_commands()
    
    embed = discord.Embed(
        title="Command Sync Status",
        description="⚠️ **AUTO-SYNC IS DISABLED**\nSlash commands won't work until manually synced.",
        color=discord.Color.blue()
    )
    
    # List available commands
    command_list = "\n".join([f"- `/{cmd.name}`: {cmd.description}" for cmd in commands[:10]])
    if len(commands) > 10:
        command_list += f"\n...and {len(commands) - 10} more"
    
    if command_list:
        embed.add_field(name=f"Available Commands ({len(commands)} total)", value=command_list, inline=False)
    else:
        embed.add_field(name="Available Commands", value="No commands available", inline=False)
    
    # Available sync commands
    embed.add_field(
        name="Sync Commands", 
        value="- `!sync_one <name>`: Sync a single command by name\n"
              "- `!sync_all`: Sync all commands (very slow)\n"
              "- `!sync_status`: Show this status",
        inline=False
    )
    
    message = await ctx.send(embed=embed)
    
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
        message = await ctx.send("A sync operation is already in progress.")
        if ctx.guild:
            try:
                await asyncio.sleep(5)
                await message.delete()
                await ctx.message.delete()
            except:
                pass
        return
        
    bot.currently_syncing = True
    
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
            bot.currently_syncing = False
            return
        
        status_message = await ctx.send(f"Syncing command '/{command.name}'...")
        
        # Get command data
        command_data = bot.get_command_json(command)
        
        # Sync command
        success, result = await bot.sync_direct(command_data)
        
        if success:
            await status_message.edit(content=f"✅ Command '/{command.name}' synced successfully!")
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
        error_message = await ctx.send(f"Unexpected error: {e}")
        if ctx.guild:
            try:
                await asyncio.sleep(5)
                await error_message.delete()
                await ctx.message.delete()
            except:
                pass
    finally:
        bot.currently_syncing = False

@bot.command()
@commands.is_owner()
async def sync_all(ctx):
    """Sync all commands very slowly to avoid rate limits"""
    if bot.currently_syncing:
        message = await ctx.send("A sync operation is already in progress.")
        if ctx.guild:
            try:
                await asyncio.sleep(5)
                await message.delete()
                await ctx.message.delete()
            except:
                pass
        return
        
    bot.currently_syncing = True
    
    try:
        commands = bot.tree.get_commands()
        total = len(commands)
        
        if not total:
            message = await ctx.send("No commands to sync.")
            if ctx.guild:
                try:
                    await asyncio.sleep(5)
                    await message.delete()
                    await ctx.message.delete()
                except:
                    pass
            bot.currently_syncing = False
            return
        
        status_message = await ctx.send(f"This will sync {total} commands one by one with 10-second delays between each. Continue? (yes/no)")
        
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
                bot.currently_syncing = False
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
            bot.currently_syncing = False
            return
        
        # Start time for progress tracking
        start_time = asyncio.get_event_loop().time()
        
        await status_message.edit(content=f"Starting safe sync of {total} commands. This will take approximately {total * 10 / 60:.1f} minutes...")
        
        success_count = 0
        error_count = 0
        
        for i, command in enumerate(commands):
            try:
                # Update progress message
                elapsed = asyncio.get_event_loop().time() - start_time
                estimated_total = (elapsed / (i + 1)) * total if i > 0 else 0
                remaining = max(0, estimated_total - elapsed)
                
                await status_message.edit(
                    content=f"Syncing command {i+1}/{total}: `/{command.name}`\n"
                            f"Progress: {((i+1)/total)*100:.1f}%\n"
                            f"Elapsed: {int(elapsed//60)}m {int(elapsed%60)}s | "
                            f"Remaining: ~{int(remaining//60)}m {int(remaining%60)}s"
                )
                
                # Get command data and sync
                command_data = bot.get_command_json(command)
                success, result = await bot.sync_direct(command_data)
                
                if success:
                    success_count += 1
                else:
                    error_count += 1
                    if isinstance(result, discord.HTTPException) and result.status == 429:
                        # Rate limited, wait longer
                        retry_after = result.retry_after * 1.5  # Add buffer
                        
                        await status_message.edit(
                            content=f"Rate limited on command {i+1}/{total}: `/{command.name}`\n"
                                    f"Waiting {retry_after:.1f} seconds before continuing..."
                        )
                        
                        # Wait the required time
                        await asyncio.sleep(retry_after)
                        
                        # Try again
                        success, retry_result = await bot.sync_direct(command_data)
                        if success:
                            success_count += 1
                            error_count -= 1  # Correct the count since we succeeded on retry
                    else:
                        # Other error
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
                error_message = await ctx.send(f"Unexpected error during sync for /{command.name}: {e}")
                if ctx.guild:
                    try:
                        await asyncio.sleep(5)
                        await error_message.delete()
                    except:
                        pass
        
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
        error_message = await ctx.send(f"Error during sync: {e}")
        if ctx.guild:
            try:
                await asyncio.sleep(5)
                await error_message.delete()
                await ctx.message.delete()
            except:
                pass
    finally:
        bot.currently_syncing = False

@bot.event
async def on_ready():
    print(f"Bot is ready. Logged in as {bot.user}")
    
    # Set bot activity
    await bot.change_presence(activity=discord.Activity(
        type=discord.ActivityType.watching, 
        name="over everything."
    ))
    
    print("⚠️ AUTO-SYNC IS DISABLED: Slash commands won't work until synced with !sync_one or !sync_all")

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
