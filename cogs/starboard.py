import discord
from discord import app_commands
from discord.ext import commands

class StarboardConfig:
    def __init__(self, watch_channel_id: int, emoji: str, only_attachments: bool, hall_of_fame_id: int, auto_thread: bool, threshold: int):
        self.watch_channel_id = watch_channel_id
        self.emoji = emoji
        self.only_attachments = only_attachments
        self.hall_of_fame_id = hall_of_fame_id
        self.auto_thread = auto_thread
        self.threshold = threshold

class Starboard(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.configs = {}  # guild_id: StarboardConfig
        self.starred_messages = set()  # (guild_id, message_id)

    @app_commands.command(name="starboard", description="Set up the starboard configuration.")
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
        channels: discord.TextChannel,
        emoji: str,
        only_attachments: bool = False,
        hall_of_fame: discord.TextChannel = None,
        auto_thread: bool = False,
        threshold: int = 1
    ):
        await interaction.response.defer(ephemeral=True)

        cfg = StarboardConfig(
            watch_channel_id=channels.id,
            emoji=emoji,
            only_attachments=only_attachments,
            hall_of_fame_id=hall_of_fame.id if hall_of_fame else channels.id,
            auto_thread=auto_thread,
            threshold=threshold
        )

        self.configs[interaction.guild_id] = cfg

        await interaction.followup.send(
            f"✅ Starboard set for {channels.mention} with emoji `{emoji}`\n"
            f"• Only attachments: {only_attachments}\n"
            f"• Hall of Fame: {(hall_of_fame.mention if hall_of_fame else channels.mention)}\n"
            f"• Auto threads: {auto_thread}\n"
            f"• Threshold: {threshold}",
            ephemeral=True
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

        message_key = (guild_id, reaction.message.id)
        if message_key in self.starred_messages:
            return  # Already posted

        self.starred_messages.add(message_key)

        hall_channel = reaction.message.guild.get_channel(config.hall_of_fame_id)
        if not hall_channel:
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

        sent_message = await hall_channel.send(embed=embed)

        if config.auto_thread:
            await sent_message.create_thread(name="Star Discussion")

async def setup(bot: commands.Bot):
    await bot.add_cog(Starboard(bot))
