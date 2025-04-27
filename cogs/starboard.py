import discord
import json
import os
from discord import app_commands
from discord.ext import commands
from discord import Permissions

# Define the config file path
config_path = os.path.join(os.path.dirname(__file__), '../../../data/starboard.json')

class StarboardConfig:
    def __init__(self, channel_ids, emoji, only_attachments, auto_thread, hall_of_fame_channel_id=None, threshold=None):
        self.channel_ids = channel_ids
        self.emoji = emoji
        self.only_attachments = only_attachments
        self.auto_thread = auto_thread
        self.hall_of_fame_channel_id = hall_of_fame_channel_id
        self.threshold = threshold

def save_config(guild_id, data):
    configs = []
    # Check if the config file exists, if not, create an empty one
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            configs = json.load(f)
    
    # Filter out any old configs for the guild_id
    configs = [config for config in configs if config['guildId'] != guild_id]

    # Add the new config
    configs.append({'guildId': guild_id, **data.__dict__})

    # Write the updated configs back to the file
    with open(config_path, 'w') as f:
        json.dump(configs, f, indent=2)

class Starboard(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="starboard", description="Configure starboard reaction behavior")
    @app_commands.describe(
        channels="List of channels to monitor (#mentions or IDs, space-separated)",
        emoji="Emoji to react with",
        only_attachments="Only react to messages with attachments",
        auto_thread="Automatically create a thread after reacting",
        hall_of_fame="Optional channel for Hall of Fame reposts",
        threshold="Number of reactions before reposting to Hall of Fame"
    )
    async def starboard(self, interaction: discord.Interaction, channels: str, emoji: str, only_attachments: bool = False, auto_thread: bool = False, hall_of_fame: discord.TextChannel = None, threshold: int = None):
        guild_id = interaction.guild.id
        # Extract numeric IDs from the provided channel string
        ids = list(set([m.group(1) for m in re.finditer(r'(\d{17,19})', channels)]))

        # Validate channels
        valid_channel_ids = []
        for cid in ids:
            channel = interaction.guild.get_channel(int(cid))
            if isinstance(channel, discord.TextChannel):
                valid_channel_ids.append(cid)
        
        if not valid_channel_ids:
            return await interaction.response.send_message('❌ No valid text channels found in your input.')

        config_data = StarboardConfig(
            channel_ids=valid_channel_ids,
            emoji=emoji,
            only_attachments=only_attachments,
            auto_thread=auto_thread,
            hall_of_fame_channel_id=hall_of_fame.id if hall_of_fame else None,
            threshold=threshold
        )

        # Save the configuration to a JSON file
        save_config(guild_id, config_data)

        # Build confirmation message
        confirmation = [
            f"✅ Starboard configured for channels: {' '.join([f'<#{cid}>' for cid in valid_channel_ids])}",
            f"• Emoji: {emoji}",
            f"• Only attachments: {only_attachments}",
            f"• Auto-thread: {auto_thread}"
        ]
        if hall_of_fame:
            confirmation.append(f"• Hall of Fame: <#{hall_of_fame.id}>")
        if threshold:
            confirmation.append(f"• Threshold: {threshold} reactions")

        await interaction.response.send_message('\n'.join(confirmation))

async def setup(bot):
    await bot.add_cog(Starboard(bot))

