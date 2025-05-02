import os
import discord
import asyncio
import datetime
import hashlib
import json
import random
import time
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
        
        # Command sync is completely disabled on startup
        self.disable_all_syncing = True
        
        # Currently syncing flag to prevent multiple syncs
        self.currently_syncing = False
        
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
        print("IMPORTANT: Command syncing is DISABLED on startup to prevent rate limits.")
        print("Use !sync_one or !sync_all to manually sync commands when needed.")
        
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

# Create bot instance
bot = MyBot()

@bot.command()
@commands.is_owner()
async def sync_status(ctx):
    """Check the current sync status and list available commands"""
    sync_info = await bot.db.sync_info.find_one({"bot_id": str(bot.user.id)})
    
    commands = bot.tree.get_commands()
    
    embed = discord.Embed(
        title="Command Sync Status",
        color=discord.Color.blue()
    )
    
    if not sync_info:
        embed.description = "No sync information found. The bot has not synced commands yet."
    else:
        # Last sync info
        last_sync = sync_info.get("last_sync", "Never")
        if last_sync != "Never":
            time_since = datetime.datetime.utcnow() - last_sync
            days = time_since.days
            hours = time_since.seconds // 3600
            minutes = (time_since.seconds % 3600) // 60
            time_since_str = f"{days} days, {hours} hours, {minutes} minutes ago"
        else:
            time_since_str = "Never"
            
        embed.add_field(name="Last Sync", value=time_since_str, inline=False)
        embed.add_field(name="Last Sync Reason", value=sync_info.get("last_sync_reason", "Unknown"), inline=False)
        
        # Check if command structure has changed
        current_hash = await bot.get_commands_hash()
        stored_hash = sync_info.get("commands_hash", "None")
        hash_changed = current_hash != stored_hash
        
        embed.add_field(name="Commands Changed Since Last Sync", value=str(hash_changed), inline=False)
        
        if hash_changed:
            embed.add_field(name="Current Hash", value=current_hash[:8] + "...", inline=True)
            embed.add_field(name="Stored Hash", value=stored_hash[:8] + "...", inline=True)
    
    # Add syncing status
    embed.add_field(name="Currently Syncing", value=str(bot.currently_syncing), inline=False)
    embed.add_field(name="Startup Sync", value="Disabled", inline=False)
    
    # List available commands
    command_list = "\n".join([f"- {cmd.name}" for cmd in commands[:10]])
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
              "- `!sync_status`: Show this status\n"
              "- `!sync_cancel`: Cancel ongoing sync",
        inline=False
    )
    
    await ctx.send(embed=embed)

@bot.command()
@commands.is_owner()
async def sync_one(ctx, command_name: str):
    """Sync a single command by name"""
    if bot.currently_syncing:
        await ctx.send("A sync operation is already in progress. Use `!sync_cancel` to cancel it.")
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
            await ctx.send(f"Command '{command_name}' not found.")
            bot.currently_syncing = False
            return
        
        await ctx.send(f"Syncing command '{command.name}'...")
        
        # Create command payload
        cmd_payload = command.to_dict()
        
        # Get the application ID
        application_id = bot.application_id
        
        # Make request
        try:
            # Use the HTTP adapter directly
            http = bot.http
            
            # Check for existing command ID
            command_id = getattr(command, 'id', None)
            
            if command_id:
                # Update existing command
                route = discord.http.Route(
                    'PATCH',
                    '/applications/{application_id}/commands/{command_id}',
                    application_id=application_id,
                    command_id=command_id
                )
            else:
                # Create new command
                route = discord.http.Route(
                    'POST',
                    '/applications/{application_id}/commands',
                    application_id=application_id
                )
            
            response = await http.request(route, json=cmd_payload)
            
            # Update the hash since we've synced a command
            current_hash = await bot.get_commands_hash()
            await bot.db.sync_info.update_one(
                {"bot_id": str(bot.user.id)},
                {"$set": {
                    "last_sync": datetime.datetime.utcnow(),
                    "last_sync_reason": f"Single command sync: {command.name}"
                }},
                upsert=True
            )
            
            await ctx.send(f"✅ Command '{command.name}' synced successfully!")
            
        except discord.HTTPException as e:
            if e.status == 429:  # Rate limited
                retry_after = e.retry_after
                await ctx.send(f"Rate limited! Please wait {retry_after:.1f} seconds before trying again.")
            else:
                await ctx.send(f"HTTP Error: {e}")
        except Exception as e:
            await ctx.send(f"Error syncing command: {e}")
    finally:
        bot.currently_syncing = False

@bot.command()
@commands.is_owner()
async def sync_all(ctx):
    """Sync all commands very slowly to avoid rate limits"""
    if bot.currently_syncing:
        await ctx.send("A sync operation is already in progress. Use `!sync_cancel` to cancel it.")
        return
    
    bot.currently_syncing = True
    
    try:
        commands = bot.tree.get_commands()
        total = len(commands)
        
        if not total:
            await ctx.send("No commands to sync.")
            return
        
        status_message = await ctx.send(f"Starting sync of {total} commands. This will be very slow to avoid rate limits...")
        
        success_count = 0
        error_count = 0
        
        # Store start time to track progress
        start_time = time.time()
        
        # Set up a cancellation flag
        cancel_file = f"sync_cancel_{ctx.author.id}.flag"
        with open(cancel_file, "w") as f:
            f.write("active")
        
        for i, command in enumerate(commands):
            # Check for cancellation
            try:
                if not os.path.exists(cancel_file):
                    await status_message.edit(content=f"Sync cancelled after {i} of {total} commands.")
                    return
            except:
                pass
            
            try:
                # Create command payload
                cmd_payload = command.to_dict()
                
                # Get the application ID
                application_id = bot.application_id
                
                # Update status every command
                elapsed = time.time() - start_time
                estimated_total = (elapsed / (i + 1)) * total if i > 0 else 0
                remaining = max(0, estimated_total - elapsed)
                
                await status_message.edit(
                    content=f"Syncing command {i+1}/{total}: `{command.name}`\n"
                            f"Progress: {((i+1)/total)*100:.1f}%\n"
                            f"Elapsed: {int(elapsed//60)}m {int(elapsed%60)}s | "
                            f"Remaining: ~{int(remaining//60)}m {int(remaining%60)}s\n"
                            f"Use `!sync_cancel` to stop the sync."
                )
                
                # Make request
                try:
                    # Use the HTTP adapter directly
                    http = bot.http
                    
                    # Check for existing command ID
                    command_id = getattr(command, 'id', None)
                    
                    if command_id:
                        # Update existing command
                        route = discord.http.Route(
                            'PATCH',
                            '/applications/{application_id}/commands/{command_id}',
                            application_id=application_id,
                            command_id=command_id
                        )
                    else:
                        # Create new command
                        route = discord.http.Route(
                            'POST',
                            '/applications/{application_id}/commands',
                            application_id=application_id
                        )
                    
                    response = await http.request(route, json=cmd_payload)
                    success_count += 1
                    
                except discord.HTTPException as e:
                    if e.status == 429:  # Rate limited
                        retry_after = e.retry_after * 1.5  # Add buffer
                        
                        await status_message.edit(
                            content=f"Rate limited on command {i+1}/{total}: `{command.name}`\n"
                                    f"Waiting {retry_after:.1f} seconds before continuing...\n"
                                    f"Progress: {(i/total)*100:.1f}%\n"
                                    f"Use `!sync_cancel` to stop the sync."
                        )
                        
                        # Wait the required time
                        await asyncio.sleep(retry_after)
                        
                        # Try again
                        try:
                            await http.request(route, json=cmd_payload)
                            success_count += 1
                        except Exception as retry_e:
                            error_count += 1
                            print(f"Error syncing command {command.name} after retry: {retry_e}")
                    else:
                        error_count += 1
                        print(f"HTTP error syncing command {command.name}: {e}")
                except Exception as e:
                    error_count += 1
                    print(f"Error syncing command {command.name}: {e}")
                
                # Delay between commands - very conservative 6-8 seconds
                delay = random.uniform(6, 8)
                await asyncio.sleep(delay)
                
            except Exception as e:
                print(f"Unexpected error during sync for {command.name}: {e}")
                error_count += 1
        
        # Update the hash since we've synced
        current_hash = await bot.get_commands_hash()
        await bot.db.sync_info.update_one(
            {"bot_id": str(bot.user.id)},
            {"$set": {
                "commands_hash": current_hash,
                "last_sync": datetime.datetime.utcnow(),
                "last_sync_reason": "Full command sync"
            }},
            upsert=True
        )
        
        # Clean up cancel file
        try:
            os.remove(cancel_file)
        except:
            pass
        
        # Final status
        total_time = time.time() - start_time
        minutes = int(total_time // 60)
        seconds = int(total_time % 60)
        
        await status_message.edit(
            content=f"Sync complete!\n"
                    f"Successfully synced {success_count}/{total} commands with {error_count} errors.\n"
                    f"Total time: {minutes}m {seconds}s"
        )
        
    except Exception as e:
        await ctx.send(f"Error during sync: {e}")
    finally:
        bot.currently_syncing = False

@bot.command()
@commands.is_owner()
async def sync_cancel(ctx):
    """Cancel an ongoing sync operation"""
    cancel_file = f"sync_cancel_{ctx.author.id}.flag"
    
    if not bot.currently_syncing:
        await ctx.send("No sync operation is currently running.")
        return
    
    try:
        # Remove the cancel file to signal cancellation
        os.remove(cancel_file)
        await ctx.send("Sync cancellation requested. The sync will stop after the current command completes.")
    except:
        await ctx.send("Failed to cancel sync. It may have already completed or been cancelled.")

@bot.event
async def on_ready():
    print(f"Bot is ready. Logged in as {bot.user}")
    
    # Set bot activity
    await bot.change_presence(activity=discord.Activity(
        type=discord.ActivityType.watching, 
        name="over everything."
    ))
    
    # DO NOT sync commands on startup
    print("Command syncing on startup is DISABLED to prevent rate limits.")
    print("Use !sync_one or !sync_all to manually sync commands when needed.")

@bot.event
async def on_message(message):
    # This makes sure both on_message handlers in cogs AND commands work
    await bot.process_commands(message)

@bot.event
async def on_guild_join(guild):
    """Handle bot joining a new server"""
    print(f"Bot joined a new guild: {guild.name} (ID: {guild.id})")
    
    # Do NOT automatically sync commands to new guild
    
    # Create a welcome message
    channel = guild.system_channel or next((ch for ch in guild.text_channels if ch.permissions_for(guild.me).send_messages), None)
    
    if channel:
        embed = discord.Embed(
            title="Axis has been added to this server. You really got lucky huh.",
            description="I can help moderate, chat, setup tickets, marketposts, starboards, and much more.",
            color=discord.Color.red()
        )
        embed.add_field(name="Setup", value="Use `!sync_status` to check available commands.", inline=False)
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
