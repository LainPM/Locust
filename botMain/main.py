# Load all enviroment dependencies
import botMain.dependencies as dependencies

# Load environment variables
intents, MONGO_URI, original_sync = dependencies.initializeDependencies()

async def disabled_sync(*args, **kwargs):
    print("⚠️ SYNC ATTEMPT BLOCKED: Command sync was attempted but is disabled")
    print(f"Called with args: {args}, kwargs: {kwargs}")
    print("Use !sync_status and manual sync commands instead")
    return []

# Apply the monkey patch
dependencies.app_commands.CommandTree.sync = disabled_sync

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
    """Sync a single command by name using direct HTTP API with 10-second timeout"""
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
        
        status_message = await ctx.send(f"Syncing command '/{command.name}' with 10-second timeout...")
        
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
        
        # Sync command with 10-second timeout
        success, result = await bot.sync_direct(command_data, timeout=10.0)
        
        if success:
            # Force refresh the registered commands cache
            await bot.get_registered_commands(force_refresh=True)
            await status_message.edit(content=f"✅ Command '/{command.name}' synced successfully!")
        else:
            if isinstance(result, TimeoutError):
                # Timeout error
                await status_message.edit(content=f"⏱️ Sync timed out after 10 seconds for command '/{command.name}'. Try again later.")
            elif isinstance(result, discord.HTTPException) and result.status == 429:
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
async def sync_all(ctx, wait_time: int = 15):
    """Sync only commands that aren't already synced with per-command timeout. 
    Optional parameter: wait_time (default: 15 seconds)"""
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
        
        status_message = await ctx.send(f"Found {total} commands that need syncing. This will sync them one by one with {wait_time}-second delays between each. Continue? (yes/no)")
        message_deleted = False
        
        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel and m.content.lower() in ["yes", "no"]
        
        try:
            response = await bot.wait_for("message", check=check, timeout=30.0)
            if response.content.lower() != "yes":
                if not message_deleted:
                    try:
                        await status_message.edit(content="Sync cancelled.")
                        # Delete messages after 5 seconds if in a guild
                        if ctx.guild:
                            try:
                                await asyncio.sleep(5)
                                await status_message.delete()
                                await ctx.message.delete()
                                await response.delete()
                            except:
                                message_deleted = True
                    except discord.NotFound:
                        message_deleted = True
                
                bot.end_sync()  # Mark sync as complete
                return
                
            # Try to delete the response message
            if ctx.guild:
                try:
                    await response.delete()
                except:
                    pass
        except asyncio.TimeoutError:
            if not message_deleted:
                try:
                    await status_message.edit(content="No response received. Sync cancelled.")
                    # Delete messages after 5 seconds if in a guild
                    if ctx.guild:
                        try:
                            await asyncio.sleep(5)
                            await status_message.delete()
                            await ctx.message.delete()
                        except:
                            message_deleted = True
                except discord.NotFound:
                    message_deleted = True
            
            bot.end_sync()  # Mark sync as complete
            return
        
        # Start time for progress tracking
        start_time = asyncio.get_event_loop().time()
        
        try:
            await status_message.edit(content=f"Starting sync of {total} commands. This will take approximately {total * wait_time / 60:.1f} minutes...")
        except discord.NotFound:
            message_deleted = True
            # Create a new status message since the old one was deleted
            try:
                status_message = await ctx.send(f"Starting sync of {total} commands. This will take approximately {total * wait_time / 60:.1f} minutes...")
            except:
                # If we can't send a new message, continue without status updates
                pass
        
        success_count = 0
        error_count = 0
        timeout_count = 0
        rate_limited = False
        
        for i, command in enumerate(commands_to_sync):
            try:
                # Update progress message if it hasn't been deleted
                if not message_deleted:
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
                    
                    try:
                        await status_message.edit(content=status_text)
                    except discord.NotFound:
                        message_deleted = True
                
                # Get command data and sync with a 15-second timeout
                command_data = bot.get_command_json(command)
                success, result = await bot.sync_direct(command_data, timeout=15.0)
                
                if success:
                    success_count += 1
                else:
                    if isinstance(result, TimeoutError):
                        # Timeout error - just move on to the next command
                        timeout_count += 1
                        try:
                            error_message = await ctx.send(f"⏱️ Sync timed out for command '/{command.name}' - moving to next command.")
                            if ctx.guild:
                                try:
                                    await asyncio.sleep(5)
                                    await error_message.delete()
                                except:
                                    pass
                        except:
                            # If we can't send a message, just continue
                            pass
                    elif isinstance(result, discord.HTTPException) and result.status == 429:
                        # Rate limited, wait longer
                        retry_after = result.retry_after * 1.5  # Add buffer
                        rate_limited = True
                        
                        if not message_deleted:
                            try:
                                await status_message.edit(
                                    content=f"⏱️ Rate limited on command {i+1}/{total}: `/{command.name}`\n"
                                            f"Waiting {retry_after:.1f} seconds before continuing..."
                                )
                            except discord.NotFound:
                                message_deleted = True
                        
                        # Wait the required time
                        await asyncio.sleep(retry_after)
                        
                        # Try again
                        success, retry_result = await bot.sync_direct(command_data, timeout=15.0)
                        if success:
                            success_count += 1
                        elif isinstance(retry_result, TimeoutError):
                            timeout_count += 1
                            try:
                                error_message = await ctx.send(f"⏱️ Sync timed out for command '/{command.name}' after retry - moving to next command.")
                                if ctx.guild:
                                    try:
                                        await asyncio.sleep(5)
                                        await error_message.delete()
                                    except:
                                        pass
                            except:
                                # If we can't send a message, just continue
                                pass
                        else:
                            error_count += 1
                            try:
                                error_message = await ctx.send(f"Failed to sync `/{command.name}` after retry: {retry_result}")
                                if ctx.guild:
                                    try:
                                        await asyncio.sleep(5)
                                        await error_message.delete()
                                    except:
                                        pass
                            except:
                                # If we can't send a message, just continue
                                pass
                    else:
                        # Other error
                        error_count += 1
                        try:
                            error_message = await ctx.send(f"Error syncing `/{command.name}`: {result}")
                            if ctx.guild:
                                try:
                                    await asyncio.sleep(5)
                                    await error_message.delete()
                                except:
                                    pass
                        except:
                            # If we can't send a message, just continue
                            pass
                
                # Wait between commands - user specified or default 15s
                await asyncio.sleep(wait_time)
                
            except Exception as e:
                error_count += 1
                print(f"Error syncing command {command.name}: {e}")
                print(traceback.format_exc())
                try:
                    error_message = await ctx.send(f"Unexpected error during sync for /{command.name}: {e}")
                    if ctx.guild:
                        try:
                            await asyncio.sleep(5)
                            await error_message.delete()
                        except:
                            pass
                except:
                    # If we can't send a message, just continue
                    pass
        
        # Force refresh the registered commands cache
        await bot.get_registered_commands(force_refresh=True)
        
        # Final status
        total_time = asyncio.get_event_loop().time() - start_time
        minutes = int(total_time // 60)
        seconds = int(total_time % 60)
        
        final_message = (
            f"Sync complete!\n"
            f"✅ Successfully synced: {success_count}/{total} commands\n"
            f"⏱️ Timed out: {timeout_count}/{total} commands\n"
            f"❌ Failed: {error_count}/{total} commands\n"
            f"Total time: {minutes}m {seconds}s"
        )
        
        # Send final status as a new message, or update existing if not deleted
        if message_deleted:
            try:
                status_message = await ctx.send(final_message)
            except:
                # If we can't send a message, just continue
                pass
        else:
            try:
                await status_message.edit(content=final_message)
            except discord.NotFound:
                # If message was just deleted, send a new one
                try:
                    status_message = await ctx.send(final_message)
                except:
                    # If we can't send a message, just continue
                    pass
        
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
        try:
            error_message = await ctx.send(f"Error during sync: {e}")
            if ctx.guild:
                try:
                    await asyncio.sleep(5)
                    await error_message.delete()
                    await ctx.message.delete()
                except:
                    pass
        except:
            # If we can't send a message, just continue
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
