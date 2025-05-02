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
# This is a monkey patch that prevents any automatic syncing
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
                
    async def actual_sync(self, *args, **kwargs):
        """Wrapper around the actual sync method when we want to use it"""
        return await self._original_sync(self.tree, *args, **kwargs)

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
    
    await ctx.send(embed=embed)

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
            await ctx.send(f"Command '/{command_name}' not found.")
            return
        
        await ctx.send(f"Syncing command '/{command.name}'...")
        
        # Create a temporary CommandTree with just this command
        temp_tree = app_commands.CommandTree(bot)
        
        # Add just this command to the tree
        # We need to recreate the command to add it to a new tree
        # This is a bit hacky but should work for basic commands
        new_cmd = app_commands.Command(
            name=command.name,
            description=command.description,
            callback=command.callback,
            nsfw=getattr(command, 'nsfw', False),
            parent=None
        )
        
        # Add parameters if any
        for param in getattr(command, 'parameters', []):
            new_cmd._params.append(param)
            
        temp_tree.add_command(new_cmd)
        
        # Use the actual sync method on just this tree
        try:
            # Temporarily restore the original sync method
            temp_original = app_commands.CommandTree.sync
            app_commands.CommandTree.sync = original_sync
            
            # Sync the command
            await temp_tree.sync()
            
            # Restore our disabled sync
            app_commands.CommandTree.sync = temp_original
            
            await ctx.send(f"✅ Command '/{command.name}' synced successfully!")
            
        except discord.HTTPException as e:
            if e.status == 429:  # Rate limited
                retry_after = e.retry_after
                await ctx.send(f"Rate limited! Please wait {retry_after:.1f} seconds before trying again.")
            else:
                await ctx.send(f"HTTP Error: {e}")
        except Exception as e:
            await ctx.send(f"Error syncing command: {e}")
    except Exception as e:
        await ctx.send(f"Unexpected error: {e}")

@bot.command()
@commands.is_owner()
async def sync_all(ctx):
    """Sync all commands very slowly to avoid rate limits"""
    commands = bot.tree.get_commands()
    total = len(commands)
    
    if not total:
        await ctx.send("No commands to sync.")
        return
    
    status_message = await ctx.send(f"This will sync {total} commands over a LONG period to avoid rate limits. Continue? (yes/no)")
    
    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel and m.content.lower() in ["yes", "no"]
    
    try:
        response = await bot.wait_for("message", check=check, timeout=30.0)
        if response.content.lower() != "yes":
            await status_message.edit(content="Sync cancelled.")
            return
    except asyncio.TimeoutError:
        await status_message.edit(content="No response received. Sync cancelled.")
        return
    
    await status_message.edit(content=f"Starting safe sync of {total} commands. This will take a LONG time...")
    
    # Temporarily restore the original sync method
    temp_original = app_commands.CommandTree.sync
    app_commands.CommandTree.sync = original_sync
    
    success_count = 0
    error_count = 0
    
    for i, command in enumerate(commands):
        try:
            # Create a temporary CommandTree with just this command
            temp_tree = app_commands.CommandTree(bot)
            
            # Add just this command to the tree
            new_cmd = app_commands.Command(
                name=command.name,
                description=command.description,
                callback=command.callback,
                nsfw=getattr(command, 'nsfw', False),
                parent=None
            )
            
            # Add parameters if any
            for param in getattr(command, 'parameters', []):
                new_cmd._params.append(param)
                
            temp_tree.add_command(new_cmd)
            
            # Update status
            await status_message.edit(
                content=f"Syncing command {i+1}/{total}: `/{command.name}`\n"
                        f"Progress: {((i+1)/total)*100:.1f}%\n"
                        f"Waiting 10 seconds between commands to avoid rate limits."
            )
            
            # Sync this command
            try:
                await temp_tree.sync()
                success_count += 1
            except discord.HTTPException as e:
                if e.status == 429:  # Rate limited
                    retry_after = e.retry_after
                    await ctx.send(f"Rate limited! Waiting {retry_after + 5} seconds...")
                    await asyncio.sleep(retry_after + 5)
                    
                    # Try again
                    try:
                        await temp_tree.sync()
                        success_count += 1
                    except Exception as retry_e:
                        error_count += 1
                        await ctx.send(f"Failed to sync `/{command.name}` after retry: {retry_e}")
                else:
                    error_count += 1
                    await ctx.send(f"HTTP Error syncing `/{command.name}`: {e}")
            except Exception as e:
                error_count += 1
                await ctx.send(f"Error syncing `/{command.name}`: {e}")
            
            # Wait between commands - very conservative 10 seconds
            await asyncio.sleep(10)
            
        except Exception as e:
            await ctx.send(f"Unexpected error during sync for /{command.name}: {e}")
            error_count += 1
    
    # Restore our disabled sync
    app_commands.CommandTree.sync = temp_original
    
    # Final status
    await status_message.edit(
        content=f"Sync complete!\n"
                f"Successfully synced {success_count}/{total} commands with {error_count} errors."
    )

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
