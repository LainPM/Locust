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

# CRITICAL: OVERRIDE discord.py's CommandTree.sync method to prevent automatic syncing
original_sync = app_commands.CommandTree.sync

async def disabled_sync(*args, **kwargs):
    print("⚠️ SYNC ATTEMPT BLOCKED: Command sync was attempted but is disabled")
    print(f"Called with args: {args}, kwargs: {kwargs}")
    print("Use !sync_status and manual sync commands instead")
    return []  # Return empty list of commands

# Apply the monkey patch - this completely disables the standard sync method
app_commands.CommandTree.sync = disabled_sync

class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)
        
        # Initialize MongoDB connection
        self.mongo_client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URI)
        self.db = self.mongo_client["discord_bot"]
        self.warnings_collection = self.db["warnings"]
        
        # Explicitly store the original sync method for when we actually want to use it
        self._original_sync = original_sync
        
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
                        # Ignore if we can't delete
                        pass
    
    async def on_command_error(self, ctx, error):
        # Send error message
        if isinstance(error, commands.CommandNotFound):
            return
        elif isinstance(error, commands.MissingPermissions):
            message = await ctx.send("You don't have permission to use this command.")
        elif isinstance(error, commands.BotMissingPermissions):
            message = await ctx.send("I don't have the necessary permissions to do that.")
        elif isinstance(error, commands.NotOwner):
            message = await ctx.send("Only the bot owner can use this command.")
        else:
            # Log other errors
            print(f"Command error: {error}")
            message = await ctx.send(f"An error occurred: {error}")
        
        # Delete error message after 5 seconds
        try:
            await asyncio.sleep(5)
            await message.delete()
        except:
            # Ignore if we can't delete
            pass
    
    async def on_app_command_error(self, interaction: discord.Interaction, error):
        # Send error message
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

    async def sync_command_direct(self, command):
        """Sync a single command directly using the HTTP API"""
        try:
            # Get application ID
            application_id = self.application_id
            
            # Convert command to JSON data
            command_data = command.to_dict()
            
            # Use direct HTTP request to create/update the command
            route = discord.http.Route(
                'POST',
                '/applications/{application_id}/commands',
                application_id=application_id
            )
            
            await self.http.request(route, json=command_data)
            return True
        except Exception as e:
            print(f"Error syncing command {command.name}: {e}")
            return False

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
    
    # Delete message after 5 seconds if it's a bot owner command
    is_owner = await bot.is_owner(ctx.author)
    if is_owner and ctx.guild:
        try:
            await asyncio.sleep(5)
            await message.delete()
            await ctx.message.delete()
        except:
            pass

@bot.command()
@commands.is_owner()
async def sync_one(ctx, command_name: str):
    """Sync a single command by name"""
    try:
        # Find the command
        command = None
        for cmd in bot.tree.get_commands():
            if cmd.name.lower() == command_name.lower():
                command = cmd
                break
        
        if not command:
            message = await ctx.send(f"Command '/{command_name}' not found.")
            await asyncio.sleep(5)
            await message.delete()
            await ctx.message.delete()
            return
        
        status_message = await ctx.send(f"Syncing command '/{command.name}'...")
        
        # Use the direct HTTP method to sync the command
        success = await bot.sync_command_direct(command)
        
        if success:
            await status_message.edit(content=f"✅ Command '/{command.name}' synced successfully!")
        else:
            await status_message.edit(content=f"❌ Failed to sync command '/{command.name}'.")
        
        # Delete messages after 5 seconds
        await asyncio.sleep(5)
        try:
            await status_message.delete()
            await ctx.message.delete()
        except:
            pass
            
    except discord.HTTPException as e:
        if e.status == 429:  # Rate limited
            retry_after = e.retry_after
            message = await ctx.send(f"Rate limited! Please wait {retry_after:.1f} seconds before trying again.")
        else:
            message = await ctx.send(f"HTTP Error: {e}")
            
        # Delete error message after 5 seconds
        await asyncio.sleep(5)
        try:
            await message.delete()
            await ctx.message.delete()
        except:
            pass
    except Exception as e:
        message = await ctx.send(f"Unexpected error: {e}")
        await asyncio.sleep(5)
        try:
            await message.delete()
            await ctx.message.delete()
        except:
            pass

@bot.command()
@commands.is_owner()
async def sync_all(ctx):
    """Sync all commands very slowly to avoid rate limits"""
    commands = bot.tree.get_commands()
    total = len(commands)
    
    if not total:
        message = await ctx.send("No commands to sync.")
        await asyncio.sleep(5)
        try:
            await message.delete()
            await ctx.message.delete()
        except:
            pass
        return
    
    status_message = await ctx.send(f"This will sync {total} commands one by one with 10-second delays between each. Continue? (yes/no)")
    
    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel and m.content.lower() in ["yes", "no"]
    
    try:
        response = await bot.wait_for("message", check=check, timeout=30.0)
        if response.content.lower() != "yes":
            await status_message.edit(content="Sync cancelled.")
            # Delete messages after 5 seconds
            await asyncio.sleep(5)
            try:
                await status_message.delete()
                await ctx.message.delete()
                await response.delete()
            except:
                pass
            return
            
        # Try to delete the response message
        try:
            await response.delete()
        except:
            pass
    except asyncio.TimeoutError:
        await status_message.edit(content="No response received. Sync cancelled.")
        # Delete messages after 5 seconds
        await asyncio.sleep(5)
        try:
            await status_message.delete()
            await ctx.message.delete()
        except:
            pass
        return
    
    await status_message.edit(content=f"Starting safe sync of {total} commands. This will take a LONG time...")
    
    success_count = 0
    error_count = 0
    
    for i, command in enumerate(commands):
        try:
            # Update status
            await status_message.edit(
                content=f"Syncing command {i+1}/{total}: `/{command.name}`\n"
                        f"Progress: {((i+1)/total)*100:.1f}%\n"
                        f"Waiting 10 seconds between commands to avoid rate limits."
            )
            
            # Sync this command using direct HTTP
            success = await bot.sync_command_direct(command)
            
            if success:
                success_count += 1
            else:
                error_count += 1
            
            # Wait between commands - very conservative 10 seconds
            await asyncio.sleep(10)
            
        except discord.HTTPException as e:
            if e.status == 429:  # Rate limited
                retry_after = e.retry_after
                temp_message = await ctx.send(f"Rate limited! Waiting {retry_after + 5} seconds...")
                await asyncio.sleep(retry_after + 5)
                
                # Try again
                try:
                    success = await bot.sync_command_direct(command)
                    if success:
                        success_count += 1
                    else:
                        error_count += 1
                except Exception as retry_e:
                    error_count += 1
                    temp_message = await ctx.send(f"Failed to sync `/{command.name}` after retry: {retry_e}")
                    await asyncio.sleep(5)
                    await temp_message.delete()
                
                # Delete the rate limit message
                try:
                    await temp_message.delete()
                except:
                    pass
                    
            else:
                error_count += 1
                temp_message = await ctx.send(f"HTTP Error syncing `/{command.name}`: {e}")
                await asyncio.sleep(5)
                try:
                    await temp_message.delete()
                except:
                    pass
                
        except Exception as e:
            error_count += 1
            temp_message = await ctx.send(f"Error syncing `/{command.name}`: {e}")
            await asyncio.sleep(5)
            try:
                await temp_message.delete()
            except:
                pass
    
    # Final status
    await status_message.edit(
        content=f"Sync complete!\n"
                f"Successfully synced {success_count}/{total} commands with {error_count} errors."
    )
    
    # Delete messages after 10 seconds (longer for the final status)
    await asyncio.sleep(10)
    try:
        await status_message.delete()
        await ctx.message.delete()
    except:
        pass

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
        embed.add_field(
            name="Setup", 
            value="**Note:** Slash commands are disabled until the bot owner runs `!sync_one` or `!sync_all`\nUse prefix commands like `!help` until then.", 
            inline=False
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
