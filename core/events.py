import discord
from discord.ext import commands

class CoreEvents(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        print(f"{self.bot.user} has connected to Discord!")
        print(f"Running on discord.py {discord.__version__}")

    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        print(f"Joined new guild: {guild.name} (ID: {guild.id})")
        # Potentially send a welcome message to a default channel if permissions allow.

async def setup(bot):
    await bot.add_cog(CoreEvents(bot))
