import discord
from discord import app_commands
from discord.ext import commands
from enum import Enum
import re
from typing import List, Optional

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
        # Initialize database collections
        self.ensure_collections()
        # Caches for blacklist/whitelist
        self.blacklist_cache = {}
        self.whitelist_cache = {}

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

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        await self.load_cache_for_guild(guild.id)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        gid = message.guild.id
        if gid not in self.blacklist_cache:
            await self.load_cache_for_guild(gid)
        if not self.blacklist_cache.get(gid):
            return
        content = message.content.lower()
        if any(self._matches(content, itm, mt) for itm, mt in self.whitelist_cache.get(gid, {}).items()):
            return
        if any(self._matches(content, itm, mt) for itm, mt in self.blacklist_cache.get(gid, {}).items()):
            try:
                await message.delete()
                await message.channel.send(
                    f"{message.author.mention}, your message was removed because it contained blacklisted content.",
                    delete_after=5
                )
            except discord.Forbidden:
                pass

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
        except:
            return False
        return False

    # ─── Slash Commands ──────────────────────────────────────────────────────────

    @app_commands.command(name="blacklist", description="Add or update an item in the blacklist")
    @app_commands.describe(
        item="The word/phrase/link to blacklist",
        match_type="Match type (contains, exact, etc.)",
        reason="Optional reason for blacklisting"
    )
    @app_commands.choices(match_type=[
        app_commands.Choice(name="Contains", value=MatchType.CONTAINS.value),
        app_commands.Choice(name="Exact", value=MatchType.EXACT.value),
        app_commands.Choice(name="Starts With", value=MatchType.STARTS_WITH.value),
        app_commands.Choice(name="Ends With", value=MatchType.ENDS_WITH.value),
        app_commands.Choice(name="Regex", value=MatchType.REGEX.value)
    ])
    @app_commands.default_permissions(manage_messages=True)
    async def blacklist(
        self,
        interaction: discord.Interaction,
        item: str,
        match_type: str = MatchType.CONTAINS.value,
        reason: Optional[str] = None
    ):
        gid = interaction.guild.id
        await self.blacklist_collection.update_one(
            {"guild_id": gid, "item": item},
            {"$set": {
                "match_type": match_type,
                "reason": reason,
                "added_by": interaction.user.id,
                "added_at": discord.utils.utcnow().isoformat()
            }},
            upsert=True
        )
        self.blacklist_cache.setdefault(gid, {})[item] = match_type
        await interaction.response.send_message(
            f"🚫 Blacklisted `{item}` ({match_type})",
            ephemeral=True
        )

    @app_commands.command(name="whitelist", description="Add or update an item in the whitelist")
    @app_commands.describe(
        item="The word/phrase/link to whitelist",
        match_type="Match type (contains, exact, etc.)",
        reason="Optional reason for whitelisting"
    )
    @app_commands.choices(match_type=[
        app_commands.Choice(name="Contains", value=MatchType.CONTAINS.value),
        app_commands.Choice(name="Exact", value=MatchType.EXACT.value),
        app_commands.Choice(name="Starts With", value=MatchType.STARTS_WITH.value),
        app_commands.Choice(name="Ends With", value=MatchType.ENDS_WITH.value),
        app_commands.Choice(name="Regex", value=MatchType.REGEX.value)
    ])
    @app_commands.default_permissions(manage_messages=True)
    async def whitelist(
        self,
        interaction: discord.Interaction,
        item: str,
        match_type: str = MatchType.CONTAINS.value,
        reason: Optional[str] = None
    ):
        gid = interaction.guild.id
        await self.whitelist_collection.update_one(
            {"guild_id": gid, "item": item},
            {"$set": {
                "match_type": match_type,
                "reason": reason,
                "added_by": interaction.user.id,
                "added_at": discord.utils.utcnow().isoformat()
            }},
            upsert=True
        )
        self.whitelist_cache.setdefault(gid, {})[item] = match_type
        await interaction.response.send_message(
            f"✅ Whitelisted `{item}` ({match_type})",
            ephemeral=True
        )

    @app_commands.command(name="show_blacklisted", description="Show all blacklisted items")
    @app_commands.default_permissions(manage_messages=True)
    async def show_blacklisted(
        self,
        interaction: discord.Interaction,
        match_type: str = "all",
        ephemeral: bool = True
    ):
        gid = interaction.guild.id
        items = await self.blacklist_collection.find({"guild_id": gid}).to_list(length=None)
        if not items:
            return await interaction.response.send_message(
                "No blacklisted items found.",
                ephemeral=ephemeral
            )
        embed = discord.Embed(
            title="Blacklisted Items",
            description=f"Filter: {match_type}",
            color=discord.Color.red()
        )
        for doc in items:
            if match_type == "all" or doc["match_type"] == match_type:
                embed.add_field(
                    name=doc["item"],
                    value=f"Type: {doc['match_type']}",
                    inline=False
                )
        await interaction.response.send_message(embed=embed, ephemeral=ephemeral)

    @app_commands.command(name="show_whitelisted", description="Show all whitelisted items")
    @app_commands.default_permissions(manage_messages=True)
    async def show_whitelisted(
        self,
        interaction: discord.Interaction,
        match_type: str = "all",
        ephemeral: bool = True
    ):
        gid = interaction.guild.id
        items = await self.whitelist_collection.find({"guild_id": gid}).to_list(length=None)
        if not items:
            return await interaction.response.send_message(
                "No whitelisted items found.",
                ephemeral=ephemeral
            )
        embed = discord.Embed(
            title="Whitelisted Items",
            description=f"Filter: {match_type}",
            color=discord.Color.green()
        )
        for doc in items:
            if match_type == "all" or doc["match_type"] == match_type:
                embed.add_field(
                    name=doc["item"],
                    value=f"Type: {doc['match_type']}",
                    inline=False
                )
        await interaction.response.send_message(embed=embed, ephemeral=ephemeral)

async def setup(bot: commands.Bot):
    await bot.add_cog(FilterCog(bot))
