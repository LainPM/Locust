# commands/ai/chat.py
import discord
from discord import app_commands
from discord.ext import commands

class AIChatCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @app_commands.command(
        name="ai-clear",
        description="Clear your conversation history with the AI"
    )
    async def clear_conversation(
        self,
        interaction: discord.Interaction
    ):
        """Clear your conversation history in this channel"""
        # Get the AI system
        ai_system = await self.bot.get_system("AISystem")
        if not ai_system:
            return await interaction.response.send_message("AI system is not available.")
        
        # Clear the conversation
        await ai_system.storage.clear_conversation(
            interaction.user.id,
            interaction.channel.id
        )
        
        await interaction.response.send_message("Your conversation history has been cleared.")
    
    @app_commands.command(
        name="ai-status",
        description="Show your current AI conversation status"
    )
    async def ai_status(
        self,
        interaction: discord.Interaction
    ):
        """Show status of active conversations"""
        # Get the AI system
        ai_system = await self.bot.get_system("AISystem")
        if not ai_system:
            return await interaction.response.send_message("AI system is not available.")
        
        # Get status
        is_active, message_count, token_count, max_tokens = await ai_system.processor.get_status(
            interaction.user.id,
            interaction.channel.id
        )
        
        if is_active:
            await interaction.response.send_message(
                f"You are in an active conversation with Axis.\n"
                f"Messages in history: {message_count}\n"
                f"Estimated tokens: {token_count}/{max_tokens}\n"
                f"The conversation will automatically end after {ai_system.processor.conversation_timeout} minutes of inactivity."
            )
        else:
            await interaction.response.send_message(
                "You are not in an active conversation with Axis. Start one by saying 'Hey Axis'!"
            )

async def setup(bot):
    await bot.add_cog(AIChatCommand(bot))
