from botMain.dependencies import (
    commands,
    app_commands,
    discord,
    asyncio
)

class ErrorHandler():
    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.CommandNotFound):
            return
        elif isinstance(error, commands.MissingPermissions):
            message = await ctx.send("You don't have permission to use this command.")
        elif isinstance(error, commands.BotMissingPermissions):
            message = await ctx.send("I don't have the necessary permissions to do that.")
        elif isinstance(error, commands.NotOwner):
            message = await ctx.send("Only the bot owner can use this command.")
        else:
            print(f"Command error: {error}")
            message = await ctx.send(f"An error occurred: {error}")
        
        # Delete error message after 5 seconds
        try:
            await asyncio.sleep(5)
            await message.delete()
        except:
            pass
    
    async def on_app_command_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.CommandOnCooldown):
            await interaction.response.send_message(
                f"This command is on cooldown. Try again in {error.retry_after:.2f} seconds.", 
                ephemeral=True
            )
        elif isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                "You don't have permission to use this command.", 
                ephemeral=True
            )
        else:
            print(f"Slash command error: {error}")
            
            try:
                if interaction.response.is_done():
                    await interaction.followup.send("An error occurred while processing this command.", ephemeral=True)
                else:
                    await interaction.response.send_message("An error occurred while processing this command.", ephemeral=True)
            except:
                pass