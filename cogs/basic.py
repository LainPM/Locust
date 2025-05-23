import discord
from discord import app_commands
from discord.ext import commands
import time
import datetime # Required for serverinfo

class BasicCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.start_time = time.time() # For uptime in /info

    @app_commands.command(name="ping", description="Check the bot's latency.")
    async def ping(self, interaction: discord.Interaction):
        latency = self.bot.latency * 1000  # Convert to milliseconds
        await interaction.response.send_message(f"Pong! Latency: {latency:.2f}ms")

    @app_commands.command(name="info", description="Get information about the bot.")
    async def info(self, interaction: discord.Interaction):
        current_time = time.time()
        uptime_seconds = int(round(current_time - self.start_time))
        uptime_str = str(datetime.timedelta(seconds=uptime_seconds))

        embed = discord.Embed(
            title=f"{self.bot.user.name} Information",
            description="A multi-purpose Discord bot.",
            color=discord.Color.blue()
        )
        if self.bot.user.avatar:
            embed.set_thumbnail(url=self.bot.user.avatar.url)
        
        embed.add_field(name="Bot Version", value="1.0.0 (New Structure)", inline=True) # Placeholder version
        embed.add_field(name="Library", value=f"discord.py {discord.__version__}", inline=True)
        embed.add_field(name="Uptime", value=uptime_str, inline=True)
        embed.add_field(name="Creator", value="Bot Developer", inline=True) # Updated creator
        embed.add_field(name="Servers", value=str(len(self.bot.guilds)), inline=True)
        embed.add_field(name="Total Users", value=str(len(set(self.bot.get_all_members()))), inline=True)

        # Add a link to your bot's source code or support server if you have one
        # embed.add_field(name="Source Code", value="[GitHub](your_github_link_here)", inline=False)

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="serverinfo", description="Display information about the current server.")
    async def serverinfo(self, interaction: discord.Interaction):
        guild = interaction.guild
        if not guild:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return

        embed = discord.Embed(
            title=f"{guild.name} Server Information",
            color=discord.Color.green()
        )
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)

        embed.add_field(name="Server ID", value=guild.id, inline=True)
        embed.add_field(name="Owner", value=guild.owner.mention if guild.owner else "Unknown", inline=True)
        embed.add_field(name="Member Count", value=str(guild.member_count), inline=True)
        
        embed.add_field(name="Creation Date", value=guild.created_at.strftime("%Y-%m-%d %H:%M:%S UTC"), inline=True)
        
        embed.add_field(name="Roles", value=str(len(guild.roles)), inline=True)
        embed.add_field(name="Text Channels", value=str(len(guild.text_channels)), inline=True)
        embed.add_field(name="Voice Channels", value=str(len(guild.voice_channels)), inline=True)
        embed.add_field(name="Categories", value=str(len(guild.categories)), inline=True)
        
        # Boost status
        embed.add_field(name="Boost Level", value=str(guild.premium_tier), inline=True)
        embed.add_field(name="Boosters", value=str(guild.premium_subscription_count), inline=True)
        
        # Verification Level
        embed.add_field(name="Verification Level", value=str(guild.verification_level).capitalize(), inline=True)

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="membercount", description="Display the current member count of the server.")
    async def membercount(self, interaction: discord.Interaction):
        guild = interaction.guild
        if not guild:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return
        await interaction.response.send_message(f"This server, **{guild.name}**, has **{guild.member_count}** members.")

async def setup(bot: commands.Bot):
    await bot.add_cog(BasicCommands(bot))
