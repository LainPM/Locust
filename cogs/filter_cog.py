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
        # Ensure DB collections and references
        self.ensure_collections()
        # Caches for quick lookups
        self.blacklist_cache = {}  # {guild_id: {item: match_type}}
        self.whitelist_cache = {}  # {guild_id: {item: match_type}}
        # Active pagination views
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
        guild_id = message.guild.id
        if guild_id not in self.blacklist_cache:
            await self.load_cache_for_guild(guild_id)
        if not self.blacklist_cache.get(guild_id):
            return
        content = message.content.lower()
        if await self._is_whitelisted(content, guild_id):
            return
        if await self._is_blacklisted(content, guild_id):
            try:
                await message.delete()
                await message.channel.send(
                    f"{message.author.mention}, your message was removed because it contained blacklisted content.",
                    delete_after=5
                )
            except discord.Forbidden:
                print(f"Missing permissions to delete message in {message.guild.name}#{message.channel.name}")
            except Exception as e:
                print(f"Error deleting message: {e}")

    async def _is_blacklisted(self, content: str, guild_id: int) -> bool:
        for item, mtype in self.blacklist_cache.get(guild_id, {}).items():
            if self._matches(content, item, mtype):
                return True
        return False

    async def _is_whitelisted(self, content: str, guild_id: int) -> bool:
        for item, mtype in self.whitelist_cache.get(guild_id, {}).items():
            if self._matches(content, item, mtype):
                return True
        return False

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
        except Exception as e:
            print(f"Match error {item}/{match_type}: {e}")
        return False

    # ─── Slash Commands ──────────────────────────────────────────────────────────

    @app_commands.command(name="blacklist", description="Add an item to the blacklist")
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
    async def blacklist(
        self, interaction: discord.Interaction,
        item: str,
        match_type: str = "contains",
        reason: Optional[str] = None
    ):
        # remove from whitelist if present
        gid = interaction.guild.id
        if gid not in self.blacklist_cache:
            self.blacklist_cache[gid] = {}
        if gid not in self.whitelist_cache:
            self.whitelist_cache[gid] = {}
        if await self.whitelist_collection.find_one({"guild_id": gid, "item": item}):
            await self.whitelist_collection.delete_one({"guild_id": gid, "item": item})
            self.whitelist_cache[gid].pop(item, None)
        # insert or update blacklist
        existing = await self.blacklist_collection.find_one({"guild_id": gid, "item": item})
        if existing:
            await self.blacklist_collection.update_one(
                {"_id": existing["_id"]},
                {"$set": {"match_type": match_type, "reason": reason}}
            )
            self.blacklist_cache[gid][item] = match_type
            await interaction.response.send_message(f"Updated blacklist `{item}` ({match_type})", ephemeral=True)
        else:
            await self.blacklist_collection.insert_one({
                "guild_id": gid,
                "item": item,
                "match_type": match_type,
                "reason": reason,
                "added_by": interaction.user.id,
                "added_at": discord.utils.utcnow().isoformat()
            })
            self.blacklist_cache[gid][item] = match_type
            await interaction.response.send_message(f"Added blacklist `{item}` ({match_type})", ephemeral=True)

    @app_commands.command(name="whitelist", description="Add an item to the whitelist")
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
    async def whitelist(
        self, interaction: discord.Interaction,
        item: str,
        match_type: str = "contains",
        reason: Optional[str] = None
    ):
        gid = interaction.guild.id
        if gid not in self.blacklist_cache:
            self.blacklist_cache[gid] = {}
        if gid not in self.whitelist_cache:
            self.whitelist_cache[gid] = {}
        if await self.blacklist_collection.find_one({"guild_id": gid, "item": item}):
            await self.blacklist_collection.delete_one({"guild_id": gid, "item": item})
            self.blacklist_cache[gid].pop(item, None)
        existing = await self.whitelist_collection.find_one({"guild_id": gid, "item": item})
        if existing:
            await self.whitelist_collection.update_one(
                {"_id": existing["_id"]},
                {"$set": {"match_type": match_type, "reason": reason}}
            )
            self.whitelist_cache[gid][item] = match_type
            await interaction.response.send_message(f"Updated whitelist `{item}` ({match_type})", ephemeral=True)
        else:
            await self.whitelist_collection.insert_one({
                "guild_id": gid,
                "item": item,
                "match_type": match_type,
                "reason": reason,
                "added_by": interaction.user.id,
                "added_at": discord.utils.utcnow().isoformat()
            })
            self.whitelist_cache[gid][item] = match_type
            await interaction.response.send_message(f"Added whitelist `{item}` ({match_type})", ephemeral=True)

    @app_commands.command(name="show_blacklisted", description="Show all blacklisted items")
    @app_commands.describe(match_type="Filter by type", ephemeral="Ephemeral output")
    @app_commands.default_permissions(manage_messages=True)
    async def show_blacklisted(
        self, interaction: discord.Interaction,
        match_type: str = "all",
        ephemeral: bool = True
    ):
        gid = interaction.guild.id
        query = {"guild_id": gid}
        if match_type != "all": query["match_type"] = match_type
        items = await self.blacklist_collection.find(query).to_list(None)
        if not items:
            return await interaction.response.send_message("No items found.", ephemeral=ephemeral)
        view = FilterListView(self, gid, "blacklist", items)
        embed = view.get_embed()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=ephemeral)
        msg = await interaction.original_response()
        view.message = msg
        self.active_views[f"{gid}_blacklist"] = view

    @app_commands.command(name="show_whitelisted", description="Show all whitelisted items")
    @app_commands.describe(match_type="Filter by type", ephemeral="Ephemeral output")
    @app_commands.default_permissions(manage_messages=True)
    async def show_whitelisted(
        self, interaction: discord.Interaction,
        match_type: str = "all",
        ephemeral: bool = True
    ):
        gid = interaction.guild.id
        query = {"guild_id": gid}
        if match_type != "all": query["match_type"] = match_type
        items = await self.whitelist_collection.find(query).to_list(None)
        if not items:
            return await interaction.response.send_message("No items found.", ephemeral=ephemeral)
        view = FilterListView(self, gid, "whitelist", items)
        embed = view.get_embed()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=ephemeral)
        msg = await interaction.original_response()
        view.message = msg
        self.active_views[f"{gid}_whitelist"] = view

    @app_commands.command(name="remove_filter", description="Remove an item from blacklist or whitelist")
    @app_commands.describe(item="Item to remove", list_type="Which list")
    @app_commands.choices(list_type=[
        app_commands.Choice(name="Blacklist", value="blacklist"),
        app_commands.Choice(name="Whitelist", value="whitelist"),
        app_commands.Choice(name="Both", value="both")
    ])
    @app_commands.default_permissions(manage_messages=True)
    async def remove_filter(
        self, interaction: discord.Interaction,
        item: str,
        list_type: str
    ):
        gid = interaction.guild.id
        msg = []
        if list_type in ("blacklist","both"):
            res = await self.blacklist_collection.delete_one({"guild_id": gid, "item": item})
            if res.deleted_count: msg.append(f"Removed `{item}` from blacklist.")
            self.blacklist_cache[gid].pop(item, None)
        if list_type in ("whitelist","both"):
            res = await self.whitelist_collection.delete_one({"guild_id": gid, "item": item})
            if res.deleted_count: msg.append(f"Removed `{item}` from whitelist.")
            self.whitelist_cache[gid].pop(item, None)
        await interaction.response.send_message("\n".join(msg) or "Nothing removed.", ephemeral=True)

    @app_commands.command(name="clear_filters", description="Clear all items from blacklist or whitelist")
    @app_commands.describe(list_type="Which list", confirm="Type 'confirm'")
    @app_commands.choices(list_type=[
        app_commands.Choice(name="Blacklist", value="blacklist"),
        app_commands.Choice(name="Whitelist", value="whitelist"),
        app_commands.Choice(name="Both", value="both")
    ])
    @app_commands.default_permissions(administrator=True)
    async def clear_filters(
        self, interaction: discord.Interaction,
        list_type: str,
        confirm: str
    ):
        if confirm.lower() != "confirm":
            return await interaction.response.send_message("Type 'confirm' to proceed.", ephemeral=True)
        gid = interaction.guild.id
        msg = []
        if list_type in ("blacklist","both"): 
            res = await self.blacklist_collection.delete_many({"guild_id": gid})
            self.blacklist_cache[gid] = {}
            msg.append(f"Cleared {res.deleted_count} blacklist items.")
        if list_type in ("whitelist","both"): 
            res = await self.whitelist_collection.delete_many({"guild_id": gid})
            self.whitelist_cache[gid] = {}
            msg.append(f"Cleared {res.deleted_count} whitelist items.")
        await interaction.response.send_message("\n".join(msg), ephemeral=True)

    @app_commands.command(name="test_filter", description="Test if text would be filtered")
    @app_commands.describe(text="Text to test")
    @app_commands.default_permissions(manage_messages=True)
    async def test_filter(
        self, interaction: discord.Interaction,
        text: str
    ):
        gid = interaction.guild.id
        wl = await self._is_whitelisted(text.lower(), gid)
        bl = await self._is_blacklisted(text.lower(), gid)
        if wl and bl:
            desc = "✅ Matches both (whitelist overrides)."
        elif wl:
            desc = "✅ Whitelisted."
        elif bl:
            desc = "❌ Blacklisted."
        else:
            desc = "✅ Allowed."
        embed = discord.Embed(title="Filter Test", description=desc,
                              color=discord.Color.green() if not bl or wl else discord.Color.red())
        details = []
        for item,mt in self.blacklist_cache.get(gid,{}).items():
            if self._matches(text.lower(), item, mt):
                details.append(f"Blacklist: `{item}` ({mt})")
        for item,mt in self.whitelist_cache.get(gid,{}).items():
            if self._matches(text.lower(), item, mt):
                details.append(f"Whitelist: `{item}` ({mt})")
        if details:
            embed.add_field(name="Matches", value="\n".join(details), inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="export_filters", description="Export all filters as JSON")
    @app_commands.default_permissions(administrator=True)
    async def export_filters(self, interaction: discord.Interaction):
        import json, io
        gid = interaction.guild.id
        bl = await self.blacklist_collection.find({"guild_id": gid}).to_list(None)
        wl = await self.whitelist_collection.find({"guild_id": gid}).to_list(None)
        for d in bl+wl: d.pop("_id", None)
        data = {
            "guild_id": gid,
            "exported_at": discord.utils.utcnow().isoformat(),
            "blacklist": bl,
            "whitelist": wl
        }
        fp = io.BytesIO(json.dumps(data, indent=2).encode())
        file = discord.File(fp, filename=f"filters_{gid}.json")
        await interaction.response.send_message("Here is your export:", file=file, ephemeral=True)

class FilterListView(discord.ui.View):
    def __init__(self, cog: FilterCog, guild_id: int, list_type: str, items: List[dict], timeout: float = 180):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.guild_id = guild_id
        self.list_type = list_type
        self.items = items
        self.current_page = 0
        self.items_per_page = 10
        self.max_pages = (len(items)-1)//self.items_per_page+1
        self.update_buttons()

    def update_buttons(self):
        self.previous_button.disabled = self.current_page == 0
        self.next_button.disabled = self.current_page >= self.max_pages-1

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary, emoji="⬅️")
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page>0:
            self.current_page -= 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.get_embed(), view=self)
        else:
            await interaction.response.defer()

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary, emoji="➡️")
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page<self.max_pages-1:
            self.current_page += 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.get_embed(), view=self)
        else:
            await interaction.response.defer()

    async def on_timeout(self):
        key = f"{self.guild_id}_{self.list_type}"
        self.cog.active_views.pop(key, None)
        for child in self.children:
            child.disabled = True
        try:
            await self.message.edit(view=self)
        except:
            pass

    def get_embed(self) -> discord.Embed:
        start = self.current_page*self.items_per_page
        end   = start+self.items_per_page
        subset = self.items[start:end]
        title = "Blacklisted" if self.list_type=="blacklist" else "Whitelisted"
        color = discord.Color.red() if self.list_type=="blacklist" else discord.Color.green()
        embed = discord.Embed(title=f"{title} Items", description=f"Page {self.current_page+1}/{self.max_pages}", color=color)
        for idx,item in enumerate(subset, start+1):
            reason = f"\nReason: {item.get('reason')}" if item.get('reason') else ""
            embed.add_field(name=f"#{idx} {item['item']}", value=f"Match: {item['match_type']}{reason}", inline=False)
        return embed

async def setup(bot: commands.Bot):
    await bot.add_cog(FilterCog(bot))
