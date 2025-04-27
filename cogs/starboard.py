import os
import re
import logging
import discord
from discord import app_commands
from discord.ext import commands
import aiomysql

log = logging.getLogger(__name__)

class StarboardConfig:
    def __init__(
        self,
        guild_id: int,
        watch_channel_id: int,
        emoji: str,
        only_attachments: bool,
        hall_of_fame_id: int,
        auto_thread: bool,
        threshold: int
    ):
        self.guild_id = guild_id
        self.watch_channel_id = watch_channel_id
        self.emoji = emoji
        self.only_attachments = only_attachments
        self.hall_of_fame_id = hall_of_fame_id
        self.auto_thread = auto_thread
        self.threshold = threshold

class Starboard(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.configs: dict[int, StarboardConfig] = {}
        self.starred_messages: set[tuple[int, int]] = set()

    def _parse_channel(self, input_str: str, guild: discord.Guild) -> discord.TextChannel | None:
        m = re.match(r"<#!?(\d+)>", input_str)
        channel_id = int(m.group(1)) if m else (int(input_str) if input_str.isdigit() else None)
        return guild.get_channel(channel_id) if channel_id else None

    @app_commands.command(name="starboard", description="Configure or update starboard settings")
    @app_commands.describe(
        channels="Channel to monitor for stars",
        emoji="Emoji to count for stars",
        only_attachments="Require attachments to star (optional)",
        hall_of_fame="Channel to post starred messages (optional)",
        auto_thread="Auto-create threads on starred messages (optional)",
        threshold="Number of stars required (optional, default 1)"
    )
    async def starboard(
        self,
        interaction: discord.Interaction,
        channels: str,
        emoji: str,
        only_attachments: bool = False,
        hall_of_fame: str = None,
        auto_thread: bool = False,
        threshold: int = 1
    ):
        # Parse watched channel
        watch_channel = self._parse_channel(channels, interaction.guild)
        if not watch_channel:
            return await interaction.response.send_message("❌ Invalid watch channel.")

        # Parse hall_of_fame or default
        hall_channel = watch_channel
        if hall_of_fame:
            parsed = self._parse_channel(hall_of_fame, interaction.guild)
            if not parsed:
                return await interaction.response.send_message("❌ Invalid hall_of_fame channel.")
            hall_channel = parsed

        # Upsert into database
        async with self.bot.db.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    INSERT INTO starboard_configs \
                        (guild_id, watch_channel_id, emoji, only_attachments, hall_of_fame_id, auto_thread, threshold)\
                    VALUES (%s, %s, %s, %s, %s, %s, %s)\
                    ON DUPLICATE KEY UPDATE\
                        watch_channel_id=VALUES(watch_channel_id), emoji=VALUES(emoji),\
                        only_attachments=VALUES(only_attachments), hall_of_fame_id=VALUES(hall_of_fame_id),\
                        auto_thread=VALUES(auto_thread), threshold=VALUES(threshold)
                    """,
                    (interaction.guild.id, watch_channel.id, emoji,
                     only_attachments, hall_channel.id, auto_thread, threshold)
                )
                await conn.commit()

        # Update in-memory
        self.configs[interaction.guild.id] = StarboardConfig(
            guild_id=interaction.guild.id,
            watch_channel_id=watch_channel.id,
            emoji=emoji,
            only_attachments=only_attachments,
            hall_of_fame_id=hall_channel.id,
            auto_thread=auto_thread,
            threshold=threshold
        )

        await interaction.response.send_message(
            f"✅ Starboard set for {watch_channel.mention} with emoji `{emoji}`.\n"
            f"Threshold: {threshold}, Only attachments: {only_attachments},\\n"
            f"Hall of Fame: {hall_channel.mention}, Auto threads: {auto_thread}"
        )

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction: discord.Reaction, user: discord.User):
        if user.bot or not reaction.message.guild:
            return

        guild_id = reaction.message.guild.id
        config = self.configs.get(guild_id)
        if not config:
            return

        if reaction.message.channel.id != config.watch_channel_id:
            return

        if str(reaction.emoji) != config.emoji:
            return

        if config.only_attachments and not reaction.message.attachments:
            return

        if reaction.count < config.threshold:
            return

        key = (guild_id, reaction.message.id)
        if key in self.starred_messages:
            return

        hall = reaction.message.guild.get_channel(config.hall_of_fame_id)
        if not hall:
            return

        embed = discord.Embed(
            description=reaction.message.content or "(no text)",
            color=discord.Color.gold(),
            timestamp=reaction.message.created_at
        )
        embed.set_author(
            name=reaction.message.author.display_name,
            icon_url=reaction.message.author.avatar.url if reaction.message.author.avatar else None
        )
        if reaction.message.attachments:
            embed.set_image(url=reaction.message.attachments[0].url)

        sent = await hall.send(embed=embed)
        self.starred_messages.add(key)
        if config.auto_thread:
            await sent.create_thread(name="Starboard Discussion")

async def setup(bot: commands.Bot):
    # Initialize DB pool and table
    bot.db = await aiomysql.create_pool(
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT", 3306)),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASS"),
        db=os.getenv("DB_NAME"),
        autocommit=True
    )
    async with bot.db.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                CREATE TABLE IF NOT EXISTS starboard_configs (
                    guild_id BIGINT PRIMARY KEY,
                    watch_channel_id BIGINT NOT NULL,
                    emoji VARCHAR(191) NOT NULL,
                    only_attachments BOOLEAN NOT NULL DEFAULT FALSE,
                    hall_of_fame_id BIGINT NOT NULL,
                    auto_thread BOOLEAN NOT NULL DEFAULT FALSE,
                    threshold INT NOT NULL DEFAULT 1
                )
                """
            )
    # Load existing configs
    async with bot.db.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT guild_id, watch_channel_id, emoji, only_attachments, hall_of_fame_id, auto_thread, threshold FROM starboard_configs"
            )
            for (gid, wc, em, oa, hf, at, th) in await cur.fetchall():
                bot.add_cog(Starboard(bot))
                bot.get_cog("Starboard").configs[gid] = StarboardConfig(gid, wc, em, oa, hf, at, th)
    # Finally add the cog
    await bot.add_cog(Starboard(bot))
