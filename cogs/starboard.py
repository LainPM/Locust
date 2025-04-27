import discord
from discord import app_commands
from discord.ext import commands

class StarboardConfig:
    def __init__(self, channels, emoji, only_attachments, hall_of_fame, auto_thread, threshold):
        self.channels = channels  # list of channel IDs
        self.emoji = emoji
        self.only_attachments = only_attachments
        self.hall_of_fame = hall_of_fame  # channel ID
        self.auto_thread = auto_thread
        self.threshold = threshold

class Starboard(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # config per guild_id
        self.configs: dict[int, StarboardConfig] = {}
        # track posted messages to avoid duplicates
        self.posted: set[tuple[int, int]] = set()

    @app_commands.command(name="starboard", description="Configure or update starboard settings")
    @app_commands.describe(
        channels="Channel to watch for stars",  # normally one, but could extend
        emoji="Emoji used to star messages",
        only_attachments="Only star messages with attachments",
        hall_of_fame="Channel where starred messages are posted",
        auto_thread="Automatically create a thread on star",
        threshold="Number of reactions required"
    )
    async def starboard(
        self,
        interaction: discord.Interaction,
        channels: discord.TextChannel,
        emoji: str,
        only_attachments: bool,
        hall_of_fame: discord.TextChannel,
        auto_thread: bool,
        threshold: int
    ):
        # Save the config
        cfg = StarboardConfig(
            channels.id,
            emoji,
            only_attachments,
            hall_of_fame.id,
            auto_thread,
            threshold
        )
        self.configs[interaction.guild_id] = cfg
        await interaction.response.send_message(
            f"✅ Starboard configured: watch {channels.mention}, emoji {emoji}, "
            f"only_attachments={only_attachments}, hall_of_fame={hall_of_fame.mention}, "
            f"auto_thread={auto_thread}, threshold={threshold}",
            ephemeral=True
        )

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction: discord.Reaction, user: discord.User):
        # ignore bot reactions
        if user.bot:
            return
        guild_id = reaction.message.guild_id
        cfg = self.configs.get(guild_id)
        if not cfg:
            return
        # only track in configured channel
        if reaction.message.channel.id != cfg.channels:
            return
        # only specific emoji (can be unicode or custom)
        if str(reaction.emoji) != cfg.emoji:
            return
        # only attachments if set
        if cfg.only_attachments and not reaction.message.attachments:
            return
        # check threshold
        if reaction.count < cfg.threshold:
            return
        key = (reaction.message.id, guild_id)
        if key in self.posted:
            return
        # post to hall_of_fame
        hall = reaction.message.guild.get_channel(cfg.hall_of_fame)
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
        # include attachments
        if reaction.message.attachments:
            embed.set_image(url=reaction.message.attachments[0].url)
        # send
        msg = await hall.send(embed=embed)
        self.posted.add(key)
        # auto thread
        if cfg.auto_thread:
            await msg.create_thread(name="Starboard Discussion")

async def setup(bot: commands.Bot):
    await bot.add_cog(Starboard(bot))
