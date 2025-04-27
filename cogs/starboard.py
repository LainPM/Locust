import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional

class StarboardConfig:
    def __init__(self, channels: int, emoji: str, only_attachments: bool = False,
                 hall_of_fame: Optional[int] = None, auto_thread: bool = False, threshold: int = 1):
        self.channels = channels  # channel ID to watch
        self.emoji = emoji
        self.only_attachments = only_attachments
        # default hall_of_fame to the watched channel if not provided
        self.hall_of_fame = hall_of_fame or channels
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
        channels="Channel to watch for stars",
        emoji="Emoji used to star messages",
        only_attachments="Only star messages with attachments",
        hall_of_fame="Channel where starred messages are posted (default: same as watched channel)",
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
        """
        /starboard channels:<#channel> emoji:<emoji> [only_attachments:<bool>] [hall_of_fame:<#channel>] [auto_thread:<bool>] [threshold:<int>]
        """
        # Save the config
        cfg = StarboardConfig(
            channels.id,
            emoji,
            only_attachments,
            hall_of_fame.id if hall_of_fame else None,
            auto_thread,
            threshold
        )
        self.configs[interaction.guild_id] = cfg

        # Prepare response message
        hf_mention = hall_of_fame.mention if hall_of_fame else channels.mention
        await interaction.response.send_message(
            f"✅ Starboard configured:\n"
            f"• Watch: {channels.mention}\n"
            f"• Emoji: {emoji}\n"
            f"• Only Attachments: {only_attachments}\n"
            f"• Hall of Fame: {hf_mention}\n"
            f"• Auto Thread: {auto_thread}\n"
            f"• Threshold: {threshold}",
            ephemeral=True
        )

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction: discord.Reaction, user: discord.User):
        # ignore bot reactions
        if user.bot or reaction.message.guild_id not in self.configs:
            return
        cfg = self.configs[reaction.message.guild_id]
        # only track in configured channel
        if reaction.message.channel.id != cfg.channels:
            return
        # only specific emoji (unicode or custom)
        if str(reaction.emoji) != cfg.emoji:
            return
        # only attachments if set
        if cfg.only_attachments and not reaction.message.attachments:
            return
        # check threshold
        if reaction.count < cfg.threshold:
            return
        key = (reaction.message.id, reaction.message.guild_id)
        if key in self.posted:
            return
        # get hall_of_fame channel
        hall = reaction.message.guild.get_channel(cfg.hall_of_fame)
        if not hall:
            return
        # build embed
        embed = discord.Embed(
            description=reaction.message.content or "(no text)",
            timestamp=reaction.message.created_at,
            color=discord.Color.gold()
        )
        embed.set_author(
            name=reaction.message.author.display_name,
            icon_url=(reaction.message.author.avatar.url if reaction.message.author.avatar else None)
        )
        # include first attachment
        if reaction.message.attachments:
            embed.set_image(url=reaction.message.attachments[0].url)
        # send to hall_of_fame
        msg = await hall.send(embed=embed)
        self.posted.add(key)
        # auto thread
        if cfg.auto_thread:
            await msg.create_thread(name="Starboard Discussion")

async def setup(bot: commands.Bot):
    await bot.add_cog(Starboard(bot))
