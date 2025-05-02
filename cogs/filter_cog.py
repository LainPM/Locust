import discord
from discord import app_commands
from discord.ext import commands
from enum import Enum
import re
from typing import List, Optional

# Replace with your development/test guild ID for instant registration
GUILD = discord.Object(id=YOUR_DEV_GUILD_ID)

class MatchType(Enum):
    CONTAINS = "contains"
    EXACT = "exact"
    STARTS_WITH = "starts_with"
    ENDS_WITH = "ends_with"
    REGEX = "regex"

class FilterCog(commands.Cog):
    """Cog for managing content filtering with blacklist and whitelist functionality"""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.ensure_collections()
        self.blacklist_cache = {}
        self.whitelist_cache = {}
        self.active_views = {}

    def ensure_collections(self):
        if not hasattr(self.bot, 'db'):
            print("Warning: Bot database not initialized")
            return
        if "blacklist" not in self.bot.db.list_collection_names():
            self.bot.db.create_collection("blacklist")
        if "whitelist" not in self.bot.db.list_collection_names():
            self.bot.db.create_collection("whitelist")
        self.blacklist_collection = self.bot.db["blacklist"]
        self.whitelist_collection = self.bot.db["whitelist"]

    async def load_cache_for_guild(self, guild_id: int):
        self.blacklist_cache[guild_id] = {}
        self.whitelist_cache[guild_id] = {}
        async for doc in self.blacklist_collection.find({"guild_id": guild_id}):
            self.blacklist_cache[guild_id][doc["item"]] = doc["match_type"]
        async for doc in self.whitelist_collection.find({"guild_id": guild_id}):
            self.whitelist_cache[guild_id][doc["item"]] = doc["match_type"]

    async def cog_load(self):
        print("Loading FilterCog...")
        for guild in self.bot.guilds:
            await self.load_cache_for_guild(guild.id)

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        await self.load_cache_for_guild(guild.id)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        if message.content.startswith(self.bot.command_prefix):
            return
        gid = message.guild.id
        if gid not in self.blacklist_cache:
            await self.load_cache_for_guild(gid)
        if not self.blacklist_cache.get(gid):
            return
        content = message.content.lower()
        if await self._is_whitelisted(content, gid):
            return
        if await self._is_blacklisted(content, gid):
            try:
                await message.delete()
                await message.channel.send(
                    f"{message.author.mention}, your message was removed because it contained blacklisted content.",
                    delete_after=5
                )
            except discord.Forbidden:
                print(f"Missing permissions to delete in {message.guild.name}#{message.channel.name}")

    async def _is_blacklisted(self, content: str, guild_id: int) -> bool:
        return any(self._matches(content, item, mtype)
                   for item, mtype in self.blacklist_cache.get(guild_id, {}).items())

    async def _is_whitelisted(self, content: str, guild_id: int) -> bool:
        return any(self._matches(content, item, mtype)
                   for item, mtype in self.whitelist_cache.get(guild_id, {}).items())

    def _matches(self, content: str, item: str, match_type: str) -> bool:
        try:
            if match_type == MatchType.CONTAINS.value:
                return item.lower() in content
            if match_type == MatchType.EXACT.value:
                return content == item.lower()
            if match_type == MatchType.STARTS_WITH.value:
                return content.startswith(item.lower())
            if match_type == MatchType.ENDS_WITH.value:
                return content.endswith(item.lower())
            if match_type == MatchType.REGEX.value:
                return bool(re.search(item, content, re.IGNORECASE))
        except Exception:
            return False
        return False

    # ─── Slash Commands ──────────────────────────────────────────────────────────

    @app_commands.command(name="blacklist", description="Add an item to the blacklist")
    @app_commands.guilds(GUILD)
    @app_commands.describe(
        item="The word, phrase, link, etc. to blacklist",
        match_type="How to match this item in messages",
        reason="Optional reason"
    )
    @app_commands.choices(match_type=[
        app_commands.Choice(name="Contains", value="contains"),
        app_commands.Choice(name="Exact", value="exact"),
        app_commands.Choice(name="Starts With", value="starts_with"),
        app_commands.Choice(name="Ends With", value="ends_with"),
        app_commands.Choice(name="Regex", value="regex")
    ])
    @app_commands.default_permissions(manage_messages=True)
    async def blacklist(self, interaction: discord.Interaction, item: str, match_type: str = "contains", reason: Optional[str] = None):
        await self.blacklist_collection.update_one(
            {"guild_id": interaction.guild_id, "item": item},
            {"$set": {"match_type": match_type, "reason": reason}},
            upsert=True
        )
        self.blacklist_cache.setdefault(interaction.guild_id, {})[item] = match_type
        await interaction.response.send_message(f"Added/Updated blacklist `{item}` ({match_type})", ephemeral=True)

    @app_commands.command(name="whitelist", description="Add an item to the whitelist")
    @app_commands.guilds(GUILD)
    @app_commands.describe(
        item="The word, phrase, link, etc. to whitelist",
        match_type="How to match this item in messages",
        reason="Optional reason"
    )
    @app_commands.choices(match_type=[
        app_commands.Choice(name="Contains", value="contains"),
        app_commands.Choice(name="Exact", value="exact"),
        app_commands.Choice(name="Starts With", value="starts_with"),
        app_commands.Choice(name="Ends With", value="ends_with"),
        app_commands.Choice(name="Regex", value="regex")
    ])
    @app_commands.default_permissions(manage_messages=True)
    async def whitelist(self, interaction: discord.Interaction, item: str, match_type: str = "contains", reason: Optional[str] = None):
        await self.whitelist_collection.update_one(
            {"guild_id": interaction.guild_id, "item": item},
            {"$set": {"match_type": match_type, "reason": reason}},
            upsert=True
        )
        self.whitelist_cache.setdefault(interaction.guild_id, {})[item] = match_type
        await interaction.response.send_message(f"Added/Updated whitelist `{item}` ({match_type})", ephemeral=True)

    @app_commands.command(name="show_blacklisted", description="Show all blacklisted items")
    @app_commands.guilds(GUILD)
    @app_commands.default_permissions(manage_messages=True)
    async def show_blacklisted(self, interaction: discord.Interaction, match_type: str = "all", ephemeral: bool = True):
        items = self.blacklist_cache.get(interaction.guild_id, {})
        if not items:
            await interaction.response.send_message("No blacklisted items found.", ephemeral=ephemeral)
            return
        embed = discord.Embed(title="Blacklisted Items", color=discord.Color.red())
        for item, mtype in items.items():
            if match_type == "all" or mtype == match_type:
                embed.add_field(name=item, value=f"Match: `{mtype}`", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=ephemeral)

    @app_commands.command(name="show_whitelisted", description="Show all whitelisted items")
    @app_commands.guilds(GUILD)
    @app_commands.default_permissions(manage_messages=True)
    async def show_whitelisted(self, interaction: discord.Interaction, match_type: str = "all", ephemeral: bool = True):
        items = self.whitelist_cache.get(interaction.guild_id, {})
        if not items:
            await interaction.response.send_message("No whitelisted items found.", ephemeral=ephemeral)
            return
        embed = discord.Embed(title="Whitelisted Items", color=discord.Color.green())
        for item, mtype in items.items():
            if match_type == "all" or mtype == match_type:
                embed.add_field(name=item, value=f"Match: `{mtype}`", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=ephemeral)

async def setup(bot: commands.Bot):
    await bot.add_cog(FilterCog(bot))
