import os
import discord
import asyncio
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()
intents = discord.Intents.default()
intents.message_content = True

class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)
        
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

bot = MyBot()

@bot.event
async def on_ready():
    print(f"Bot is ready. Logged in as {bot.user}")
    
    # Sync commands with Discord
    print("Syncing slash commands...")
    try:
        # For global commands (available in all servers where the bot is)
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s) globally")
        
        # Alternatively, to make commands only available in a specific guild/server
        # Replace GUILD_ID with your server ID if you want guild-specific commands
        # guild = discord.Object(id=GUILD_ID)
        # synced = await bot.tree.sync(guild=guild)
        # print(f"Synced {len(synced)} command(s) to guild {guild.id}")
        
    except Exception as e:
        print(f"Failed to sync commands: {e}")

if __name__ == "__main__":
    bot.run(os.getenv("DISCORD_TOKEN").strip())
