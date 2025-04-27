import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional

class StarboardConfig:
    def __init__(self, channels, emoji, only_attachments, hall_of_fame, auto_thread, threshold):
        self.channels = channels  # channel ID
        self.emoji = emoji
        self.only_attachments = only_attachments
        self.hall_of_fame = hall_of_fame  # channel ID or None
        self.auto_thread = auto_thread
        self.threshold = threshold

class Starboard(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.configs: dict[int, StarboardConfig] = {}
        self.posted: set[tuple[int, int]] = set()

    @app_commands.command(name="starboard", description="Configure or update starboard settings")
    @app_commands.describe(
        channels="Channel to watch for stars",
        emoji="Emoji used to star messages",
        only_attachments="Only star messages with attachments",
        hall_of_fame="Channel where starred messages are posted (default: watched channel)",
        auto_thread="Automatically create a thread on star",
        threshold="Number of reactions required (default: 1)"
    )
    async def starboard(
        self,
        interaction: discord.Interaction,
        channels: discord.TextChannel,
        emoji: str,
        only_attachments: bool = False,
        hall_of_fame: Optional[discord.TextChannel] = None,
        auto_thread: bool = False,
        threshold: int = 1
    ):
        await interaction.response.defer(ephemeral=True)

        cfg = StarboardConfig(
            channels.id,
            emoji,
            only_attachments,
            hall_of_fame.id if hall_of_fame else None,
            auto_thread,
            threshold
        )
        self.configs[interaction.guild_id] = cfg

        hall_of_fame_display = hall_of_fame.mention if hall_of_fame else channels.mention

        await interaction.followup.send(
            f"✅ Starboard configured:\n"
            f"• Watch: {channels.mention}\n"
            f"• Emoji: {emoji}\n"
            f"• Only Attachments: {only_attachments}\n"
            f"• Hall of Fame: {hall_of_fame_display}\n"
            f"• Auto Thread: {auto_thread}\n"
            f"• Threshold: {threshold}",
            ephemeral=True
        )

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction: discord.Reaction, user: discord.User):
        if user.bot or not reaction.message.guild:
            return

        guild_id = reaction.message.guild_id
        cfg = self.configs.get(guild_id)
        if not cfg:
            return

        if reaction.message.channel.id != cfg.channels:
            return

        if str(reaction.emoji) != cfg.emoji:
            return

        if cfg.only_attachments and not reaction.message.attachments:
            return

        if reaction.count < cfg.threshold:
            return

        key = (reaction.message.id, guild_id)
        if key in self.posted:
            return

        hall_channel_id = cfg.hall_of_fame or cfg.channels
        hall = reaction.message.guild.get_channel(hall_channel_id)
        if not hall:
            return

        embed = discord.Embed(
            description=reaction.message.content or "(no text)",
            timestamp=reaction.message.created_at,
            color=discord.Color.gold()
        )
        embed.set_author(
            name=reaction.message.author.display_name,
            icon_url=reaction.message.author.avatar.url if reaction.message.author.avatar else None
        )

        if reaction.message.attachments:
            embed.set_image(url=reaction.message.attachments[0].url)

        msg = await hall.send(embed=embed)
        self.posted.add(key)

        if cfg.auto_thread:
            await msg.create_thread(name="Starboard Discussion")

async def setup(bot: commands.Bot):
    await bot.add_cog(Starboard(bot))
